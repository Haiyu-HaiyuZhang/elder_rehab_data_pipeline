"""
DUO-GAIT 数据集验证脚本 v2 - 30s 滑动窗口 + HR baseline 验证
"""

import numpy as np
import pandas as pd
import json
import logging
from datetime import datetime
from pathlib import Path
import sys
from tabulate import tabulate

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

import config
# 注：v2 版本已整合必要的实现，不需要这些库
# from utils.dataloader import DataLoader
# from utils.preprocessing import SignalPreprocessor
from modules.step_frequency import StepFrequency
from modules.step_length import StepLength
from modules.step_variability import StepVariability
# from modules.hr_mean import HRMean, HRMax, HRRecovery, QRSDetector
# from modules.quality_anomaly import QualityChecker, AnomalyDetector


class DUOGaitValidatorV2:
    """DUO-GAIT 数据集验证器 (改进版: 30s 窗口 + HR 验证)"""
    
    def __init__(self, dataset_root="/Volumes/ChouSSD/elder_datasets/DUO-GAIT"):
        self.dataset_root = Path(dataset_root)
        self.raw_dir = self.dataset_root / "raw"
        self.results = {}
        self.results_by_window = []
        self.results_detail = {}
        
        # 加载 subject_info 用于验证
        subject_info_path = self.raw_dir / "subject_info.csv"
        if subject_info_path.exists():
            self.subject_info = pd.read_csv(subject_info_path)
        else:
            self.subject_info = None
        
    def print_section(self, title):
        """打印章节标题"""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    
    def load_duo_gait_data(self, subject_id, task_type="st"):
        """加载 DUO-GAIT 数据（与原版相同）"""
        
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
        
        try:
            with open(hr_file, 'r') as f:
                lines = f.readlines()
            
            data_start_row = 0
            for i, line in enumerate(lines):
                if 'Sample rate' in line:
                    data_start_row = i
                    break
            
            hr_data = pd.read_csv(hr_file, skiprows=data_start_row, low_memory=False)
            
            if 'HR (bpm)' in hr_data.columns:
                hr_data['HR (bpm)'] = pd.to_numeric(hr_data['HR (bpm)'], errors='coerce')
            
            logger.info(f"✓ 加载心率数据: {len(hr_data)} 行")
            print(f"  - 心率数据行：{len(hr_data)} 行")
            print(f"  - 采样率: 1 Hz")
            
        except Exception as e:
            logger.error(f"加载心率数据失败: {e}")
            return None
        
        # 加载 IMU 数据
        imu_files = {
            'LF': data_dir / 'LF.csv',
            'RF': data_dir / 'RF.csv',
            'LL': data_dir / 'LL.csv',
            'RL': data_dir / 'RL.csv',
            'LW': data_dir / 'LW.csv',
            'RW': data_dir / 'RW.csv',
        }
        
        imu_data = {}
        for sensor_name, imu_file in imu_files.items():
            if not imu_file.exists():
                logger.warning(f"  - {sensor_name} 数据不存在")
                continue
            
            try:
                data = pd.read_csv(imu_file, skiprows=5, low_memory=False)
                
                numeric_cols = ['Accel X', 'Accel Y', 'Accel Z', 'Gyro X', 'Gyro Y', 'Gyro Z', 'Time']
                for col in numeric_cols:
                    if col in data.columns:
                        data[col] = pd.to_numeric(data[col], errors='coerce')
                
                imu_data[sensor_name] = data
                logger.info(f"✓ 加载 {sensor_name} IMU 数据: {len(data)} 行")
                
            except Exception as e:
                logger.error(f"加载 {sensor_name} 失败: {e}")
        
        return {
            'subject_id': subject_id,
            'task_type': task_type,
            'hr_data': hr_data,
            'imu_data': imu_data,
            'data_dir': str(data_dir)
        }
    
    def analyze_metrics_by_window(self, imu_data, hr_data):
        """
        用 30 秒滑动窗口分析指标的时间序列变化
        
        Returns:
            list: 每个窗口的指标列表
        """
        
        self.print_section("步骤 2: 30 秒滑动窗口分析")
        
        if 'LF' not in imu_data or imu_data['LF'] is None:
            logger.error("没有 LF IMU 数据")
            return []
        
        lf_data = imu_data['LF']
        
        # 提取加速度数据
        acc_x = pd.to_numeric(lf_data['Accel X'], errors='coerce').values
        acc_y = pd.to_numeric(lf_data['Accel Y'], errors='coerce').values
        acc_z = pd.to_numeric(lf_data['Accel Z'], errors='coerce').values
        
        # 去除 NaN
        valid_idx = ~(np.isnan(acc_x) | np.isnan(acc_y) | np.isnan(acc_z))
        acc_x = acc_x[valid_idx]
        acc_y = acc_y[valid_idx]
        acc_z = acc_z[valid_idx]
        
        if len(acc_x) == 0:
            logger.error("加速度数据为空")
            return []
        
        acc_magnitude = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        # 获取陀螺仪数据
        gyr_x = pd.to_numeric(lf_data['Gyro X'], errors='coerce').values[valid_idx] if 'Gyro X' in lf_data.columns else np.zeros_like(acc_x)
        gyr_y = pd.to_numeric(lf_data['Gyro Y'], errors='coerce').values[valid_idx] if 'Gyro Y' in lf_data.columns else np.zeros_like(acc_x)
        gyr_z = pd.to_numeric(lf_data['Gyro Z'], errors='coerce').values[valid_idx] if 'Gyro Z' in lf_data.columns else np.zeros_like(acc_x)
        
        # 生成时间戳
        duration = len(acc_x) / config.DUO_GAIT_SAMPLE_RATE
        timestamp = np.linspace(0, duration, len(acc_x))
        
        # 提取心率数据
        if 'HR (bpm)' in hr_data.columns:
            hr_values = pd.to_numeric(hr_data['HR (bpm)'], errors='coerce').dropna().values
        else:
            hr_values = None
        
        # 计算窗口参数
        window_samples = int(config.DUO_GAIT_SAMPLE_RATE * config.WINDOW_LENGTH_SEC)
        stride_samples = int(config.DUO_GAIT_SAMPLE_RATE * config.SLIDING_WINDOW_STRIDE_SEC)
        
        print(f"  - 总样本数: {len(acc_x)} ({duration:.1f} 秒)")
        print(f"  - 窗口大小: {config.WINDOW_LENGTH_SEC} 秒 ({window_samples} 样本)")
        print(f"  - 滑动步长: {config.SLIDING_WINDOW_STRIDE_SEC} 秒 ({stride_samples} 样本)")
        
        # 逐窗口分析
        results_by_window = []
        step_freq_calc = StepFrequency()
        step_length_calc = StepLength()
        step_var_calc = StepVariability()
        
        window_id = 0
        for i in range(0, len(acc_x) - window_samples + 1, stride_samples):
            # 提取窗口数据
            end_idx = i + window_samples
            
            acc_window = acc_magnitude[i:end_idx]
            ts_window = timestamp[i:end_idx]
            
            # 创建处理数据
            processed_data = {
                'acc_x': acc_x[i:end_idx],
                'acc_y': acc_y[i:end_idx],
                'acc_z': acc_z[i:end_idx],
                'acc_magnitude': acc_window,
                'gyr_x': gyr_x[i:end_idx],
                'gyr_y': gyr_y[i:end_idx],
                'gyr_z': gyr_z[i:end_idx],
                'timestamp': ts_window,
                'sample_rate': config.DUO_GAIT_SAMPLE_RATE,
            }
            
            # 计算步态指标
            window_result = {
                'window_id': window_id,
                'time_start_s': ts_window[0],
                'time_end_s': ts_window[-1],
                'duration_s': config.WINDOW_LENGTH_SEC,
            }
            
            try:
                step_freq = step_freq_calc.calculate(processed_data)
                window_result['step_frequency_hz'] = float(step_freq)
            except Exception as e:
                window_result['step_frequency_hz'] = None
                logger.warning(f"窗口 {window_id} 步频计算失败: {e}")
            
            try:
                step_length = step_length_calc.calculate(processed_data)
                window_result['step_length_m'] = float(step_length)
            except Exception as e:
                window_result['step_length_m'] = None
            
            try:
                isi_std = step_var_calc.calculate(processed_data)
                window_result['step_variability_ms'] = float(isi_std)
            except Exception as e:
                window_result['step_variability_ms'] = None
            
            # 计算窗口内的心率统计
            if hr_values is not None and len(hr_values) > 0:
                # HR 数据与 IMU 时间对齐（1 Hz → 秒为单位）
                window_start_s = window_result['time_start_s']
                window_end_s = window_result['time_end_s']
                
                # 假设 HR 数据的索引就是秒数
                hr_window_indices = np.where((np.arange(len(hr_values)) >= window_start_s) & 
                                            (np.arange(len(hr_values)) < window_end_s))[0]
                
                if len(hr_window_indices) > 0:
                    hr_window = hr_values[hr_window_indices]
                    window_result['hr_mean_bpm'] = float(np.mean(hr_window))
                    window_result['hr_max_bpm'] = float(np.max(hr_window))
                    window_result['hr_min_bpm'] = float(np.min(hr_window))
                    window_result['hr_std_bpm'] = float(np.std(hr_window))
                else:
                    window_result['hr_mean_bpm'] = None
                    window_result['hr_max_bpm'] = None
                    window_result['hr_min_bpm'] = None
                    window_result['hr_std_bpm'] = None
            
            results_by_window.append(window_result)
            window_id += 1
        
        print(f"\n✓ 分析完成：{len(results_by_window)} 个窗口")
        
        self.results_by_window = results_by_window
        return results_by_window
    
    def validate_with_subject_info(self, subject_id, task_type, hr_data):
        """
        与 subject_info.csv 的实测值进行对比验证
        """
        
        self.print_section("步骤 3: 与 subject_info 验证")
        
        if self.subject_info is None:
            logger.warning("subject_info 数据不可用")
            return None
        
        # 查找对应的受试者记录
        subject_row = self.subject_info[self.subject_info['sub'] == subject_id]
        if subject_row.empty:
            logger.warning(f"找不到 {subject_id} 的信息")
            return None
        
        subject_row = subject_row.iloc[0]
        
        # 提取实测的基线和疲劳时心率
        if task_type == "st":
            hr_baseline_measured = subject_row['st_HR_baseline']
            hr_fatigue_measured = subject_row['st_HR_fatigue']
        else:
            hr_baseline_measured = subject_row['dt_HR_baseline']
            hr_fatigue_measured = subject_row['dt_HR_fatigue']
        
        # 计算我们的 HR 统计
        if 'HR (bpm)' in hr_data.columns:
            hr_values = pd.to_numeric(hr_data['HR (bpm)'], errors='coerce').dropna().values
            computed_hr_mean = np.mean(hr_values)
            computed_hr_max = np.max(hr_values)
            computed_hr_min = np.min(hr_values)
        else:
            computed_hr_mean = None
            computed_hr_max = None
            computed_hr_min = None
        
        # 输出对比
        print(f"受试者ID: {subject_id}")
        print(f"任务类型: {task_type.upper()}")
        print(f"\n心率对比:")
        
        comparison_table = []
        
        # Baseline 对比
        if not pd.isna(hr_baseline_measured):
            baseline_error_bpm = abs(computed_hr_mean - hr_baseline_measured)
            baseline_error_pct = baseline_error_bpm / hr_baseline_measured * 100 if hr_baseline_measured > 0 else 0
            comparison_table.append([
                "HR 基线 (bpm)",
                f"{hr_baseline_measured:.0f}",
                f"{computed_hr_mean:.1f}",
                f"{baseline_error_bpm:.1f}",
                f"{baseline_error_pct:.1f}%"
            ])
        
        # Fatigue 对比
        if not pd.isna(hr_fatigue_measured):
            fatigue_error_bpm = abs(computed_hr_max - hr_fatigue_measured)
            fatigue_error_pct = fatigue_error_bpm / hr_fatigue_measured * 100 if hr_fatigue_measured > 0 else 0
            comparison_table.append([
                "HR 峰值 (bpm)",
                f"{hr_fatigue_measured:.0f}",
                f"{computed_hr_max:.1f}",
                f"{fatigue_error_bpm:.1f}",
                f"{fatigue_error_pct:.1f}%"
            ])
        
        if comparison_table:
            headers = ["指标", "实测值", "计算值", "误差(bpm)", "误差(%)"]
            print(tabulate(comparison_table, headers=headers, tablefmt="grid"))
            
            # 验证结论
            all_errors_pct = [row[4].rstrip('%') for row in comparison_table]
            max_error_pct = max([float(e) for e in all_errors_pct])
            
            if max_error_pct < 10:
                print(f"\n✓ 验证通过: 所有误差 < 10%")
            elif max_error_pct < 20:
                print(f"\n⚠ 误差可接受: 最大误差 {max_error_pct:.1f}% < 20%")
            else:
                print(f"\n✗ 验证失败: 最大误差 {max_error_pct:.1f}% >= 20%")
        
        return {
            'subject_id': subject_id,
            'task_type': task_type,
            'hr_baseline_measured': hr_baseline_measured,
            'hr_fatigue_measured': hr_fatigue_measured,
            'hr_mean_computed': computed_hr_mean,
            'hr_max_computed': computed_hr_max,
            'hr_min_computed': computed_hr_min,
        }
    
    def print_timeline_results(self):
        """打印时间序列结果表"""
        
        if not self.results_by_window:
            logger.warning("没有窗口结果数据")
            return
        
        self.print_section("时间序列指标")
        
        # 构建输出表格
        table_data = []
        for result in self.results_by_window:
            table_data.append([
                result['window_id'],
                f"{result['time_start_s']:.0f}-{result['time_end_s']:.0f}s",
                f"{result.get('step_frequency_hz', 'N/A'):.2f}" if result.get('step_frequency_hz') is not None else "N/A",
                f"{result.get('step_length_m', 'N/A'):.4f}" if result.get('step_length_m') is not None else "N/A",
                f"{result.get('hr_mean_bpm', 'N/A'):.1f}" if result.get('hr_mean_bpm') is not None else "N/A",
            ])
        
        headers = ["窗口ID", "时间 (s)", "步频 (Hz)", "步长 (m)", "心率 (bpm)"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # 计算趋势
        step_freqs = [r['step_frequency_hz'] for r in self.results_by_window if r['step_frequency_hz'] is not None]
        if len(step_freqs) > 1:
            freq_change_pct = (step_freqs[-1] - step_freqs[0]) / step_freqs[0] * 100
            print(f"\n趋势分析:")
            print(f"  - 步频变化: {step_freqs[0]:.2f} Hz → {step_freqs[-1]:.2f} Hz ({freq_change_pct:+.1f}%)")
            if freq_change_pct < -5:
                print(f"    → 检出步频衰退，可能表现疲劳")
            elif freq_change_pct > 5:
                print(f"    → 步频增加，可能适应运动")
            else:
                print(f"    → 步频稳定")
    
    def validate_subject(self, subject_id, task_type="st"):
        """验证单个受试者"""
        
        print("\n" + "█"*70)
        print("█" + " "*68 + "█")
        print("█" + f"  DUO-GAIT 验证 v2 - {subject_id} ({task_type.upper()})".center(68) + "█")
        print("█" + " "*68 + "█")
        print("█"*70)
        
        # 加载数据
        data = self.load_duo_gait_data(subject_id, task_type)
        if data is None:
            return None
        
        self.results_detail = data
        
        # 30s 窗口分析
        window_results = self.analyze_metrics_by_window(data['imu_data'], data['hr_data'])
        
        # HR 验证
        validation_result = self.validate_with_subject_info(subject_id, task_type, data['hr_data'])
        
        # 输出结果
        self.print_timeline_results()
        
        return {
            'by_window': window_results,
            'validation': validation_result
        }


def main():
    """主函数"""
    
    validator = DUOGaitValidatorV2()
    
    # 验证第一个受试者
    subject = "sub_01"
    results = validator.validate_subject(subject, task_type="st")
    
    # 保存结果
    if results:
        output_file = f"duo_gait_validation_v2_{subject}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n✓ 结果已保存: {output_file}")


if __name__ == "__main__":
    main()
