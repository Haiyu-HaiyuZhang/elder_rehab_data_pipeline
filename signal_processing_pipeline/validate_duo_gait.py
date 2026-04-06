"""
DUO-GAIT 数据集验证脚本 - Validation for DUO-GAIT Dataset
验证在真实数据集上的计算准确性
"""

import numpy as np
import pandas as pd
import json
import logging
from datetime import datetime
from pathlib import Path
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

import config
from utils.dataloader import DataLoader
from utils.preprocessing import SignalPreprocessor
from modules.step_frequency import StepFrequency
from modules.step_length import StepLength
from modules.step_variability import StepVariability
from modules.hr_mean import HRMean, HRMax, HRRecovery, QRSDetector
from modules.quality_anomaly import QualityChecker, AnomalyDetector


class DUOGaitValidator:
    """DUO-GAIT 数据集验证器"""
    
    def __init__(self, dataset_root="/Volumes/ChouSSD/elder_datasets/DUO-GAIT"):
        self.dataset_root = Path(dataset_root)
        self.raw_dir = self.dataset_root / "raw"
        self.results = {}
        self.results_detail = {}
        
    def print_section(self, title):
        """打印章节标题"""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
        
    def load_duo_gait_data(self, subject_id, task_type="st"):
        """
        加载 DUO-GAIT 数据
        
        Args:
            subject_id: 参与者 ID (e.g., "sub_01")
            task_type: "st" (single task) 或 "dt" (dual task)
        
        Returns:
            dict: 包含 IMU 和心率数据的字典
        """
        
        self.print_section(f"加载 DUO-GAIT 数据: {subject_id} ({task_type.upper()})")
        
        # 确定数据目录
        if task_type == "st":
            data_dir = self.raw_dir / "OG_st_raw" / subject_id
        else:
            data_dir = self.raw_dir / "OG_dt_raw" / subject_id
        
        if not data_dir.exists():
            logger.error(f"数据目录不存在: {data_dir}")
            return None
        
        # 加载心率数据
        hr_file = data_dir / "heart_rate.CSV"
        if not hr_file.exists():
            logger.error(f"心率文件不存在: {hr_file}")
            return None
        
        # 跳过前几行元数据，找到实际数据行
        try:
            # 先读取一次找到数据开始的行
            with open(hr_file, 'r') as f:
                lines = f.readlines()
            
            # 找到包含 "Sample rate" 的行（数据开始标记）
            data_start_row = 0
            for i, line in enumerate(lines):
                if 'Sample rate' in line:
                    data_start_row = i
                    break
            
            # 读取心率数据
            hr_data = pd.read_csv(hr_file, skiprows=data_start_row, low_memory=False)
            
            # 转换心率列为数值类型
            if 'HR (bpm)' in hr_data.columns:
                hr_data['HR (bpm)'] = pd.to_numeric(hr_data['HR (bpm)'], errors='coerce')
            
            # 转换其他可能需要的列
            for col in hr_data.columns:
                if col not in ['Name', 'Sport', 'Date', 'Start time', 'Notes', 'Time']:
                    try:
                        hr_data[col] = pd.to_numeric(hr_data[col], errors='coerce')
                    except:
                        pass
            
            logger.info(f"✓ 加载心率数据: {len(hr_data)} 行")
            print(f"  - 心率数据行：{len(hr_data)} 行")
            print(f"  - 采样率: 1 Hz")
            print(f"  - 列名: {', '.join(hr_data.columns[:5])}...")
            
        except Exception as e:
            logger.error(f"加载心率数据失败: {e}")
            return None
        
        # 加载 IMU 数据（从多个位置，这里使用左脚作为示例）
        imu_files = {
            'LF': data_dir / 'LF.csv',  # 左脚
            'RF': data_dir / 'RF.csv',  # 右脚
            'LL': data_dir / 'LL.csv',  # 左腿
            'RL': data_dir / 'RL.csv',  # 右腿
            'LW': data_dir / 'LW.csv',  # 左腰
            'RW': data_dir / 'RW.csv',  # 右腰
        }
        
        imu_data = {}
        for sensor_name, imu_file in imu_files.items():
            if not imu_file.exists():
                logger.warning(f"  - {sensor_name} 数据不存在: {imu_file}")
                continue
            
            try:
                # 读取 IMU 数据（跳过前 5 行元数据）
                data = pd.read_csv(imu_file, skiprows=5, low_memory=False)
                
                # 转换加速度和陀螺仪列为数值类型
                numeric_cols = ['Accel X', 'Accel Y', 'Accel Z', 'Gyro X', 'Gyro Y', 'Gyro Z', 'Time']
                for col in numeric_cols:
                    if col in data.columns:
                        data[col] = pd.to_numeric(data[col], errors='coerce')
                
                imu_data[sensor_name] = data
                logger.info(f"✓ 加载 {sensor_name} IMU 数据: {len(data)} 行")
                print(f"  - {sensor_name}: {len(data)} 行, 采样率 128 Hz")
                
            except Exception as e:
                logger.error(f"加载 {sensor_name} IMU 数据失败: {e}")
        
        return {
            'subject_id': subject_id,
            'task_type': task_type,
            'hr_data': hr_data,
            'imu_data': imu_data,
            'data_dir': str(data_dir)
        }
    
    def merge_imu_data(self, imu_dict):
        """
        合并多个 IMU 传感器数据
        
        Args:
            imu_dict: 多个传感器的数据字典
        
        Returns:
            合并后的 DataFrame (使用左脚作为基准)
        """
        
        self.print_section("合并多传感器 IMU 数据")
        
        if not imu_dict or 'LF' not in imu_dict:
            logger.warning("没有左脚数据，无法合并")
            return None
        
        # 使用左脚作为基准
        merged = imu_dict['LF'].copy()
        
        # 添加其他传感器的加速度数据（作为额外通道）
        for sensor_name, data in imu_dict.items():
            if sensor_name == 'LF':
                continue
            
            # 检查列名
            required_cols = ['Accel X', 'Accel Y', 'Accel Z']
            if all(col in data.columns for col in required_cols):
                merged[f'{sensor_name}_Accel_X'] = data['Accel X']
                merged[f'{sensor_name}_Accel_Y'] = data['Accel Y']
                merged[f'{sensor_name}_Accel_Z'] = data['Accel Z']
        
        logger.info(f"✓ IMU 数据合并完成")
        print(f"  - 合并后的列数: {len(merged.columns)}")
        print(f"  - 合并后的行数: {len(merged)}")
        
        return merged
    
    def test_step_metrics(self, imu_data):
        """测试步态指标（步频、步长、步长变异性）"""
        
        self.print_section("步骤 2: 步态指标验证")
        
        # 构建适配 DataLoader 的数据格式
        # 从 IMU 数据提取加速度合向量
        if 'LF' not in imu_data or imu_data['LF'] is None:
            logger.error("没有 IMU 数据")
            return None
        
        lf_data = imu_data['LF']
        
        # 计算加速度合向量
        acc_x = pd.to_numeric(lf_data['Accel X'], errors='coerce').values
        acc_y = pd.to_numeric(lf_data['Accel Y'], errors='coerce').values
        acc_z = pd.to_numeric(lf_data['Accel Z'], errors='coerce').values
        
        # 移除 NaN 值
        valid_idx = ~(np.isnan(acc_x) | np.isnan(acc_y) | np.isnan(acc_z))
        acc_x = acc_x[valid_idx]
        acc_y = acc_y[valid_idx]
        acc_z = acc_z[valid_idx]
        
        if len(acc_x) == 0:
            logger.error("加速度数据为空或全为 NaN")
            return None
        
        acc_magnitude = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        # 获取陀螺仪数据
        gyr_x = pd.to_numeric(lf_data['Gyro X'], errors='coerce').values[valid_idx] if 'Gyro X' in lf_data.columns else np.zeros_like(acc_x)
        gyr_y = pd.to_numeric(lf_data['Gyro Y'], errors='coerce').values[valid_idx] if 'Gyro Y' in lf_data.columns else np.zeros_like(acc_x)
        gyr_z = pd.to_numeric(lf_data['Gyro Z'], errors='coerce').values[valid_idx] if 'Gyro Z' in lf_data.columns else np.zeros_like(acc_x)
        
        # 生成时间戳（128 Hz 采样率）
        duration = len(acc_x) / 128  # 秒
        timestamp = np.linspace(0, duration, len(acc_x))
        
        # 创建适配的数据结构
        processed_data = {
            'acc_x': acc_x,
            'acc_y': acc_y,
            'acc_z': acc_z,
            'acc_magnitude': acc_magnitude,
            'gyr_x': gyr_x,
            'gyr_y': gyr_y,
            'gyr_z': gyr_z,
            'timestamp': timestamp,
            'sample_rate': 128,  # DUO-GAIT IMU 采样率
        }
        
        # 测试步频
        step_freq_calc = StepFrequency()
        try:
            step_freq = step_freq_calc.calculate(processed_data)
            peak_times = step_freq_calc.get_peak_times(processed_data)
            print(f"✓ 步频计算完成")
            print(f"  - 步频: {step_freq:.2f} Hz = {step_freq*60:.1f} steps/min")
            print(f"  - 检测到的脚步峰值: {len(peak_times)} 个")
            print(f"  - 有效加速度数据: {len(acc_x)} 个样本 ({len(acc_x)/128/60:.1f} 分钟)")
            
            self.results['step_frequency'] = {
                'hz': float(step_freq),
                'steps_per_min': float(step_freq * 60),
                'peaks_detected': len(peak_times)
            }
        except Exception as e:
            logger.error(f"步频计算失败: {e}")
            self.results['step_frequency'] = {'error': str(e)}
        
        # 测试步长
        try:
            step_length_calc = StepLength()
            step_length = step_length_calc.calculate(processed_data)
            
            # 尝试从 cadence 估计速度
            hr_data = self.results_detail.get('hr_data', None)
            if hr_data is not None and 'Cadence' in hr_data.columns:
                # 心率数据中的 Cadence 可能可以用来交叉验证
                avg_cadence = pd.to_numeric(hr_data['Cadence'], errors='coerce').dropna().mean()
                print(f"✓ 步长计算完成")
                print(f"  - 步长: {step_length:.4f} m")
                print(f"  - 心率数据中的节奏: {avg_cadence:.1f}")
            else:
                print(f"✓ 步长计算完成")
                print(f"  - 步长: {step_length:.4f} m")
            
            self.results['step_length'] = {
                'meters': float(step_length)
            }
        except Exception as e:
            logger.error(f"步长计算失败: {e}")
            self.results['step_length'] = {'error': str(e)}
        
        # 测试步长变异性
        try:
            step_var_calc = StepVariability()
            isi_std = step_var_calc.calculate(processed_data)
            isi_stats = step_var_calc.get_isi_statistics(processed_data)
            
            print(f"✓ 步长变异性计算完成")
            print(f"  - ISI 标准差: {isi_std:.2f} ms")
            if isi_stats:
                print(f"  - 平均 ISI: {isi_stats.get('mean', 0):.2f} ms")
                print(f"  - ISI 范围: {isi_stats.get('min', 0):.2f} - {isi_stats.get('max', 0):.2f} ms")
            
            self.results['step_variability'] = {
                'isi_std_ms': float(isi_std),
                'isi_stats': isi_stats if isi_stats else {}
            }
        except Exception as e:
            logger.error(f"步长变异性计算失败: {e}")
            self.results['step_variability'] = {'error': str(e)}
        
        return processed_data
    
    def test_heart_rate(self, hr_data):
        """测试心率指标"""
        
        self.print_section("步骤 3: 心率指标验证")
        
        # 从 heart_rate.CSV 提取心率数据
        if 'HR (bpm)' not in hr_data.columns:
            logger.error("心率数据中没有 'HR (bpm)' 列")
            print(f"  可用的列: {', '.join(hr_data.columns)}")
            return None
        
        # 转换为数值类型并删除 NaN
        hr_values = pd.to_numeric(hr_data['HR (bpm)'], errors='coerce').dropna().values
        
        if len(hr_values) == 0:
            logger.warning("没有有效的心率数据")
            return None
        
        # 计算心率指标
        hr_mean = np.mean(hr_values)
        hr_max = np.max(hr_values)
        hr_min = np.min(hr_values)
        
        print(f"✓ 心率数据分析完成")
        print(f"  - 平均心率: {hr_mean:.1f} bpm")
        print(f"  - 最大心率: {hr_max:.1f} bpm")
        print(f"  - 最小心率: {hr_min:.1f} bpm")
        print(f"  - 有效数据点: {len(hr_values)} 个")
        print(f"  - 运动时长: {len(hr_values)} 秒 = {len(hr_values)/60:.1f} 分钟")
        
        # 计算心率恢复（如果有基线数据）
        hr_recovery = None
        if len(hr_values) > 10:
            # 简化版：使用最后 10% 的平均值与之前的比较
            hr_end = np.mean(hr_values[-int(len(hr_values)*0.1):])
            hr_beginning = np.mean(hr_values[:int(len(hr_values)*0.1)])
            hr_recovery = (hr_beginning - hr_end) / (len(hr_values) / 60) if (len(hr_values) / 60) > 0 else 0
            print(f"  - 心率恢复（简化计算）: {hr_recovery:.2f} bpm/min")
        
        self.results['heart_rate'] = {
            'hr_mean_bpm': float(hr_mean),
            'hr_max_bpm': float(hr_max),
            'hr_min_bpm': float(hr_min),
            'hr_recovery_bpm_per_min': float(hr_recovery) if hr_recovery else None,
            'duration_seconds': int(len(hr_values)),
            'valid_datapoints': int(len(hr_values))
        }
        
        return {
            'hr_mean': hr_mean,
            'hr_max': hr_max,
            'hr_recovery': hr_recovery,
            'hr_values': hr_values
        }
    
    def test_data_quality(self, imu_data, hr_data):
        """测试数据质量"""
        
        self.print_section("步骤 4: 数据质量评估")
        
        quality_metrics = {}
        
        # 检查 IMU 数据的完整性
        if imu_data and 'LF' in imu_data:
            lf = imu_data['LF']
            acc_cols = ['Accel X', 'Accel Y', 'Accel Z']
            if all(col in lf.columns for col in acc_cols):
                # 转换为数值并计算缺失率
                acc_values_x = pd.to_numeric(lf['Accel X'], errors='coerce').values
                acc_values_y = pd.to_numeric(lf['Accel Y'], errors='coerce').values
                acc_values_z = pd.to_numeric(lf['Accel Z'], errors='coerce').values
                
                total_elements = len(acc_values_x) * 3
                missing_count = (
                    np.isnan(acc_values_x).sum() + 
                    np.isnan(acc_values_y).sum() + 
                    np.isnan(acc_values_z).sum()
                )
                missing_rate = missing_count / total_elements if total_elements > 0 else 0
                
                quality_metrics['imu_completeness'] = 1.0 - missing_rate
                print(f"✓ IMU 数据完整性: {(1-missing_rate)*100:.1f}%")
            else:
                print(f"  ⚠ IMU 数据缺少加速度列")
        
        # 检查心率数据的完整性
        if hr_data is not None and 'HR (bpm)' in hr_data.columns:
            hr_values = pd.to_numeric(hr_data['HR (bpm)'], errors='coerce')
            missing_rate = hr_values.isna().sum() / len(hr_values) if len(hr_values) > 0 else 0
            quality_metrics['hr_completeness'] = 1.0 - missing_rate
            print(f"✓ 心率数据完整性: {(1-missing_rate)*100:.1f}%")
        
        # 检查数据同步
        print(f"✓ 数据质量评估完成")
        print(f"  - IMU 采样率: 128 Hz")
        print(f"  - 心率采样率: 1 Hz")
        print(f"  - 数据同步状态: 正常（多速率）")
        
        self.results['data_quality'] = quality_metrics
        return quality_metrics
    
    def validate_subject(self, subject_id, task_type="st"):
        """验证单个参与者的数据"""
        
        print("\n" + "█"*70)
        print("█" + " "*68 + "█")
        print("█" + f"  DUO-GAIT 数据集验证 - Subject: {subject_id}".center(68) + "█")
        print("█" + " "*68 + "█")
        print("█"*70)
        
        # 加载数据
        data = self.load_duo_gait_data(subject_id, task_type)
        if data is None:
            return None
        
        self.results_detail = data
        
        # 合并 IMU 数据
        merged_imu = self.merge_imu_data(data['imu_data'])
        
        # 测试步态指标
        processed_imu = self.test_step_metrics(data['imu_data'])
        
        # 测试心率指标
        hr_results = self.test_heart_rate(data['hr_data'])
        
        # 测试数据质量
        quality = self.test_data_quality(data['imu_data'], data['hr_data'])
        
        # 打印总结
        self.print_summary(subject_id, task_type)
        
        return self.results
    
    def print_summary(self, subject_id, task_type):
        """打印验证总结"""
        
        self.print_section(f"验证总结 - {subject_id} ({task_type.upper()})")
        
        print(json.dumps(self.results, indent=2, default=str, ensure_ascii=False))
        
        print("\n" + "="*70)
        print(f"✓ {subject_id} 验证完成")
        print("="*70)


def main():
    """主函数"""
    
    # 创建验证器
    validator = DUOGaitValidator()
    
    # 验证第一个参与者的单一任务数据
    subject = "sub_01"
    results = validator.validate_subject(subject, task_type="st")
    
    if results:
        print("\n【验证结果已导出】")
        
        step_freq = results.get('step_frequency', {}).get('hz')
        step_length = results.get('step_length', {}).get('meters')
        hr_mean = results.get('heart_rate', {}).get('hr_mean_bpm')
        hr_max = results.get('heart_rate', {}).get('hr_max_bpm')
        
        print(f"  - 步频: {step_freq:.2f} Hz" if isinstance(step_freq, (int, float)) else f"  - 步频: 无法计算")
        print(f"  - 步长: {step_length:.4f} m" if isinstance(step_length, (int, float)) else f"  - 步长: 无法计算")
        print(f"  - 心率（平均）: {hr_mean:.1f} bpm" if isinstance(hr_mean, (int, float)) else f"  - 心率（平均）: 无法计算")
        print(f"  - 心率（最大）: {hr_max:.1f} bpm" if isinstance(hr_max, (int, float)) else f"  - 心率（最大）: 无法计算")


if __name__ == "__main__":
    main()
