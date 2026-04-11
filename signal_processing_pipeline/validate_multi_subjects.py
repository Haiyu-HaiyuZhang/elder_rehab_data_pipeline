"""
多受试者 DUO-GAIT 数据集验证脚本 - 增强心率验证版本
支持多个受试者、多个任务类型的批量验证
"""

import numpy as np
import pandas as pd
import json
import logging
from datetime import datetime
from pathlib import Path
import sys
from tabulate import tabulate
from collections import defaultdict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s | %(message)s'
)
logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

import config
from modules.step_frequency import StepFrequency
from modules.step_length import StepLength
from modules.step_variability import StepVariability


class MultiSubjectValidator:
    """多受试者 DUO-GAIT 验证器"""
    
    def __init__(self, dataset_root="/Volumes/ChouSSD/elder_datasets/DUO-GAIT"):
        self.dataset_root = Path(dataset_root)
        self.raw_dir = self.dataset_root / "raw"
        self.results_summary = []  # 存储所有受试者的汇总结果
        self.hr_validation_results = []  # 存储所有心率对比结果
        
        # 加载 subject_info 用于验证
        subject_info_path = self.raw_dir / "subject_info.csv"
        if subject_info_path.exists():
            self.subject_info = pd.read_csv(subject_info_path)
            logger.info(f"✓ 加载 subject_info: {len(self.subject_info)} 个受试者")
        else:
            self.subject_info = None
            logger.warning("⚠ subject_info 不可用")
    
    def print_section(self, title, level=1):
        """打印章节标题"""
        if level == 1:
            divider = "=" * 80
            print(f"\n{divider}")
            print(f"  {title}")
            print(f"{divider}\n")
        else:
            print(f"\n  → {title}")
    
    def load_duo_gait_data(self, subject_id, task_type="st"):
        """加载 DUO-GAIT 数据"""
        
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
                continue
            
            try:
                data_raw = pd.read_csv(imu_file, skiprows=5, low_memory=False)
                
                numeric_cols = ['Accel X', 'Accel Y', 'Accel Z', 'Gyro X', 'Gyro Y', 'Gyro Z', 'Time']
                for col in numeric_cols:
                    if col in data_raw.columns:
                        data_raw[col] = pd.to_numeric(data_raw[col], errors='coerce')
                
                imu_data[sensor_name] = data_raw
                
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
        """用 30 秒滑动窗口分析指标"""
        
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
        
        # 逐窗口分析
        results_by_window = []
        step_freq_calc = StepFrequency()
        step_length_calc = StepLength()
        step_var_calc = StepVariability()
        
        window_id = 0
        for i in range(0, len(acc_x) - window_samples + 1, stride_samples):
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
            }
            
            try:
                step_freq = step_freq_calc.calculate(processed_data)
                window_result['step_frequency_hz'] = float(step_freq)
            except:
                window_result['step_frequency_hz'] = None
            
            try:
                step_length = step_length_calc.calculate(processed_data)
                window_result['step_length_m'] = float(step_length)
            except:
                window_result['step_length_m'] = None
            
            try:
                isi_std = step_var_calc.calculate(processed_data)
                window_result['step_variability_ms'] = float(isi_std)
            except:
                window_result['step_variability_ms'] = None
            
            # 计算窗口内的心率统计
            if hr_values is not None and len(hr_values) > 0:
                window_start_s = window_result['time_start_s']
                window_end_s = window_result['time_end_s']
                
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
        
        return results_by_window
    
    def validate_hr_metrics(self, subject_id, task_type, results_by_window):
        """
        增强的心率验证 - 与 subject_info 对比、显示详细信息
        使用初始心率（而非平均值）来对比基线，因为基线是运动前的静息心率
        """
        
        if self.subject_info is None:
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
        
        # 从窗口结果计算全局统计
        hr_values = [w['hr_mean_bpm'] for w in results_by_window if w.get('hr_mean_bpm') is not None]
        
        if not hr_values:
            return {
                'subject_id': subject_id,
                'task_type': task_type,
                'status': 'no_data'
            }
        
        # 计算统计值
        computed_hr_mean = np.mean(hr_values)
        computed_hr_min = min(hr_values)
        computed_hr_max = max(hr_values)
        computed_hr_std = np.std(hr_values)
        
        # 计算初始和最终心率（从第一个和最后一个窗口）
        if len(results_by_window) > 0:
            computed_hr_initial = results_by_window[0].get('hr_mean_bpm')
            computed_hr_final = results_by_window[-1].get('hr_mean_bpm')
        else:
            computed_hr_initial = None
            computed_hr_final = None
        
        # 计算误差
        validation_result = {
            'subject_id': subject_id,
            'task_type': task_type,
            'hr_baseline_measured': float(hr_baseline_measured) if not pd.isna(hr_baseline_measured) else None,
            'hr_fatigue_measured': float(hr_fatigue_measured) if not pd.isna(hr_fatigue_measured) else None,
            'hr_mean_computed': float(computed_hr_mean),
            'hr_min_computed': float(computed_hr_min),
            'hr_max_computed': float(computed_hr_max),
            'hr_std_computed': float(computed_hr_std),
            'hr_initial_computed': float(computed_hr_initial) if computed_hr_initial else None,
            'hr_final_computed': float(computed_hr_final) if computed_hr_final else None,
        }
        
        # 计算误差百分比
        # 【改进】基线使用初始心率而不是平均值（基线是运动前的静息HR）
        if validation_result['hr_baseline_measured'] is not None and computed_hr_initial is not None:
            baseline_error_pct = abs(computed_hr_initial - validation_result['hr_baseline_measured']) / validation_result['hr_baseline_measured'] * 100
            validation_result['baseline_error_pct'] = float(baseline_error_pct)
        
        # 【不变】峰值使用最大心率
        if validation_result['hr_fatigue_measured'] is not None:
            fatigue_error_pct = abs(computed_hr_max - validation_result['hr_fatigue_measured']) / validation_result['hr_fatigue_measured'] * 100
            validation_result['fatigue_error_pct'] = float(fatigue_error_pct)
        
        return validation_result
    
    def validate_subject(self, subject_id, task_type="st"):
        """验证单个受试者的数据"""
        
        self.print_section(f"正在验证 {subject_id} ({task_type.upper()})", level=2)
        
        # 加载数据
        data = self.load_duo_gait_data(subject_id, task_type)
        if data is None:
            logger.error(f"无法加载 {subject_id} 的数据")
            return None
        
        logger.info(f"✓ 数据加载成功")
        
        # 分析窗口指标
        logger.info(f"分析窗口指标...")
        window_results = self.analyze_metrics_by_window(data['imu_data'], data['hr_data'])
        
        # HR 验证
        logger.info(f"验证心率数据...")
        validation_result = self.validate_hr_metrics(subject_id, task_type, window_results)
        
        return {
            'by_window': window_results,
            'validation': validation_result
        }
    
    def run_multi_subject_validation(self, subject_list, task_types=["st", "dt"]):
        """批量验证多个受试者"""
        
        self.print_section(f"批量验证 {len(subject_list)} 个受试者")
        print(f"受试者: {', '.join(subject_list)}")
        print(f"任务类型: {', '.join(task_types)}\n")
        
        all_results = {}
        
        for subject_id in subject_list:
            subject_results = {}
            
            for task_type in task_types:
                result = self.validate_subject(subject_id, task_type)
                if result:
                    subject_results[task_type] = result
                    
                    # 存储验证结果
                    if result['validation']:
                        self.hr_validation_results.append(result['validation'])
            
            all_results[subject_id] = subject_results
        
        return all_results
    
    def print_hr_validation_summary(self):
        """打印心率验证汇总表 - 改进版（使用初始心率对比基线）"""
        
        if not self.hr_validation_results:
            logger.warning("没有验证结果可显示")
            return
        
        self.print_section("心率验证汇总 - 与 subject_info 对比")
        
        # 构建表格数据
        table_data = []
        for result in self.hr_validation_results:
            subject_id = result['subject_id']
            task_type = result['task_type'].upper()
            
            row = [
                f"{subject_id}\n({task_type})",
                f"{result['hr_baseline_measured']:.0f}" if result['hr_baseline_measured'] else "N/A",
                f"{result['hr_initial_computed']:.1f}" if result['hr_initial_computed'] else "N/A",
                f"{result['baseline_error_pct']:.1f}%" if 'baseline_error_pct' in result else "N/A",
                f"{result['hr_fatigue_measured']:.0f}" if result['hr_fatigue_measured'] else "N/A",
                f"{result['hr_max_computed']:.1f}",
                f"{result['fatigue_error_pct']:.1f}%" if 'fatigue_error_pct' in result else "N/A",
                f"mean={result['hr_mean_computed']:.0f}\nmax={result['hr_max_computed']:.0f}\nstd={result['hr_std_computed']:.1f}",
            ]
            table_data.append(row)
        
        headers = [
            "受试者\n(任务)",
            "Baseline\n测量值(bpm)\n(运动前)",
            "Baseline\n计算值(bpm)\n(初始)",
            "误差\n(%)",
            "Fatigue\n测量值(bpm)",
            "Fatigue\n计算值(bpm)\n(最大)",
            "误差\n(%)",
            "全局统计\n(bpm)",
        ]
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # 计算平均误差
        baseline_errors = [r['baseline_error_pct'] for r in self.hr_validation_results if 'baseline_error_pct' in r]
        fatigue_errors = [r['fatigue_error_pct'] for r in self.hr_validation_results if 'fatigue_error_pct' in r]
        
        if baseline_errors:
            avg_baseline_error = np.mean(baseline_errors)
            print(f"\n  ✓ 平均 Baseline 误差: {avg_baseline_error:.1f}% ({len(baseline_errors)} 个结果)")
            print(f"    【初始心率 vs 运动前基线】")
        
        if fatigue_errors:
            avg_fatigue_error = np.mean(fatigue_errors)
            print(f"  ✓ 平均 Fatigue 误差: {avg_fatigue_error:.1f}% ({len(fatigue_errors)} 个结果)")
            print(f"    【最大心率 vs 疲劳时心率】")
    
    def save_results(self, all_results, output_prefix="multi_subject"):
        """保存所有结果到 JSON"""
        
        output_file = f"{output_prefix}_validation_results.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"✓ 结果已保存: {output_file}")
        
        # 也保存验证汇总
        summary_file = f"{output_prefix}_hr_validation_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(self.hr_validation_results, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"✓ 验证汇总已保存: {summary_file}")


def main():
    """主函数 - 批量验证多个受试者"""
    
    validator = MultiSubjectValidator()
    
    # 【用户可自定义：选择要测试的受试者】
    # 示例：随机选择 3 个受试者
    test_subjects = ["sub_01", "sub_03", "sub_05"]
    
    print(f"\n{'='*80}")
    print(f"  多受试者 DUO-GAIT 批量验证")
    print(f"{'='*80}\n")
    print(f"测试受试者: {', '.join(test_subjects)}")
    print(f"测试任务: ST (单任务) 和 DT (双任务)")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 运行批量验证
    all_results = validator.run_multi_subject_validation(
        subject_list=test_subjects,
        task_types=["st", "dt"]
    )
    
    # 打印心率验证汇总
    validator.print_hr_validation_summary()
    
    # 保存结果
    validator.save_results(all_results)
    
    print(f"\n{'='*80}")
    print(f"  验证完成！")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
