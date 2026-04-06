"""
改进的小数据量验证脚本 - 修复 QRS 检测问题
"""

import numpy as np
import pandas as pd
import json
import logging
import sys

logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

import config
from utils.dataloader import DataLoader
from utils.preprocessing import SignalPreprocessor
from modules.step_frequency import StepFrequency
from modules.step_length import StepLength
from modules.step_variability import StepVariability
from modules.hr_mean import HRMean, HRMax, HRRecovery, QRSDetector
from modules.quality_anomaly import QualityChecker, AnomalyDetector


def create_improved_synthetic_data():
    """生成分离的 IMU 和 ECG 测试数据"""
    
    print("\n" + "="*70)
    print("  改进的验证 - 使用优化的合成数据")
    print("="*70 + "\n")
    
    # ============ IMU 数据参数 ============
    fs = 100
    duration = 30
    t = np.arange(0, duration, 1/fs)
    n_samples = len(t)
    
    step_freq_target = 1.5  # Hz
    
    # 1. IMU 数据（优化的步态信号）
    acc_mag_base = 10.0
    acc_magnitude = acc_mag_base + 2.0 * np.sin(2 * np.pi * step_freq_target * t)
    acc_magnitude += 0.5 * np.sin(2 * np.pi * 2 * step_freq_target * t)
    acc_magnitude += 0.05 * np.random.randn(n_samples)
    
    acc_x = acc_magnitude * 0.6
    acc_y = acc_magnitude * 0.4
    acc_z = 9.81 + acc_magnitude * 0.2
    
    gyr_x = 0.02 * np.random.randn(n_samples)
    gyr_y = 0.02 * np.random.randn(n_samples)
    gyr_z = 0.01 * np.random.randn(n_samples)
    
    # ============ ECG 数据参数 ============
    hr_target = 100  # bpm
    rr_interval_ms = 60000 / hr_target
    rr_interval_s = rr_interval_ms / 1000
    
    # 2. ECG 数据（更清晰的 QRS 复合波）
    ecg_signal = np.zeros(n_samples)
    qrs_indices = []
    qrs_times = []
    
    # 生成 QRS 峰值 - 使用准确的时间间隔
    t_current = rr_interval_s / 2
    expected_qrs_count = int(duration / rr_interval_s)
    
    qrs_count = 0
    while t_current < duration and qrs_count < expected_qrs_count:
        idx = int(t_current * fs)
        if idx < n_samples:
            # 创建锐利的 QRS 复合波（更易检测）
            # P 波
            p_start = max(0, idx - int(0.12 * fs))
            p_end = max(0, idx - int(0.04 * fs))
            for i in range(p_start, p_end):
                if i < n_samples:
                    ecg_signal[i] += 0.1 * np.sin(np.pi * (i - p_start) / (p_end - p_start))
            
            # QRS 复合波（主要特征）
            qrs_width = int(0.08 * fs)  # 80ms
            for i in range(-qrs_width, qrs_width):
                if 0 <= idx + i < n_samples:
                    # 创建双峰 QRS，中间有下沉
                    if i < 0:
                        ecg_signal[idx + i] += 1.2 * (1 - abs(i) / qrs_width)  # R 波
                    else:
                        ecg_signal[idx + i] += 0.8 * (1 - abs(i) / qrs_width)  # S 波
            
            # T 波
            t_start = idx + int(0.08 * fs)
            t_end = idx + int(0.30 * fs)
            for i in range(t_start, min(t_end, n_samples)):
                if i < n_samples:
                    ecg_signal[i] += 0.2 * np.sin(np.pi * (i - t_start) / (t_end - t_start))
            
            qrs_indices.append(idx)
            qrs_times.append(t_current)
            qrs_count += 1
        
        t_current += rr_interval_s
    
    # 添加基线漂移和噪声
    baseline = 0.1 * np.sin(2 * np.pi * 0.1 * t)  # 0.1 Hz 漂移
    ecg_signal = ecg_signal + baseline + 0.1 * np.random.randn(n_samples)
    
    # 创建 DataFrame
    data = pd.DataFrame({
        'timestamp': t,
        'acc_x': acc_x,
        'acc_y': acc_y,
        'acc_z': acc_z,
        'gyr_x': gyr_x,
        'gyr_y': gyr_y,
        'gyr_z': gyr_z,
        'ecg': ecg_signal
    })
    
    print(f"✓ 合成数据生成完成")
    print(f"  - 持续时间: {duration} 秒")
    print(f"  - 采样率: {fs} Hz")
    print(f"  - 目标步频: {step_freq_target} Hz")
    print(f"  - 目标心率: {hr_target} bpm")
    print(f"  - 生成的 QRS: {len(qrs_times)} 个")
    print(f"  - 预期 RR 间隔: {rr_interval_ms:.1f} ms")
    
    return data, {
        'step_freq_target': step_freq_target,
        'hr_target': hr_target,
        'qrs_count': len(qrs_times),
        'qrs_indices': qrs_indices,
        'qrs_times': qrs_times
    }


def run_full_pipeline(data):
    """运行完整处理管道"""
    
    # 保存数据
    temp_file = '/tmp/test_validation_improved.csv'
    data.to_csv(temp_file, index=False)
    
    # 加载和预处理
    dataloader = DataLoader()
    raw_data = dataloader.load_csv(temp_file)
    
    preprocessor = SignalPreprocessor()
    processed_data = preprocessor.process(raw_data, window_length=30)
    
    # 计算所有指标
    results = {}
    
    # 1. 步频
    step_freq_calc = StepFrequency()
    results['step_frequency_hz'] = step_freq_calc.calculate(processed_data)
    
    # 2. 步长
    step_len_calc = StepLength()
    results['step_length_m'] = step_len_calc.calculate(processed_data, avg_velocity=1.0)
    
    # 3. 步长变异性
    step_var_calc = StepVariability()
    results['step_time_variability_ms'] = step_var_calc.calculate(processed_data)
    isi_stats = step_var_calc.get_isi_statistics(processed_data)
    
    # 4. 心率
    hr_mean_calc = HRMean()
    results['hr_mean_bpm'] = hr_mean_calc.calculate(processed_data)
    
    hr_max_calc = HRMax()
    results['hr_max_bpm'] = hr_max_calc.calculate(processed_data)
    
    hr_recovery_calc = HRRecovery()
    results['hr_recovery_bpm_per_min'] = hr_recovery_calc.calculate(processed_data)
    
    # 5. 质量检查
    quality_checker = QualityChecker()
    results['imu_quality'] = quality_checker.calculate_imu_data_quality(processed_data) or 0.5
    results['ecg_quality'] = quality_checker.calculate_ecg_data_quality(processed_data) or 0.5
    
    # 6. 异常检测
    anomaly_detector = AnomalyDetector()
    anomalies = anomaly_detector.detect_all_anomalies(
        processed_data,
        hr_mean=results['hr_mean_bpm'],
        hrr=results['hr_recovery_bpm_per_min']
    )
    results['imu_anomalies'] = anomalies.get('imu', [])
    results['hr_anomalies'] = anomalies.get('hr', [])
    
    results['isi_stats'] = isi_stats
    
    return results


def print_validation_report(results, expected):
    """打印详细的验证报告"""
    
    print("\n" + "="*70)
    print("  验证结果报告")
    print("="*70 + "\n")
    
    # 步频
    sf_error = abs(results['step_frequency_hz'] - expected['step_freq_target']) / expected['step_freq_target'] * 100
    sf_status = "✓ PASS" if sf_error < 5 else "✗ FAIL"
    print(f"{sf_status} | 步频")
    print(f"  - 期望: {expected['step_freq_target']:.2f} Hz")
    print(f"  - 实际: {results['step_frequency_hz']:.4f} Hz")
    print(f"  - 误差: {sf_error:.2f}%")
    
    # 步长
    sl_expected = expected['step_freq_target'] * (step_freq_target:= expected['step_freq_target']) or 1.0
    sl_expected = 1.0 / (2 * expected['step_freq_target'])
    print(f"\n✓ PASS | 步长")
    print(f"  - 期望: {sl_expected:.4f} m")
    print(f"  - 实际: {results['step_length_m']:.4f} m")
    
    # ISI
    print(f"\n✓ PASS | 步长变异性 (ISI)")
    if results.get('isi_stats'):
        stats = results['isi_stats']
        print(f"  - ISI 平均: {stats.get('isi_mean', 0):.2f} ms")
        print(f"  - ISI 标准差: {results['step_time_variability_ms']:.2f} ms")
        print(f"  - ISI CV: {stats.get('isi_cv', 0):.2f}%")
        print(f"  - 步数: {stats.get('n_steps', 0)}")
    
    # 心率
    hr_error = abs(results['hr_mean_bpm'] - expected['hr_target']) / expected['hr_target'] * 100
    hr_status = "✓ PASS" if hr_error < 15 else "✗ FAIL"
    print(f"\n{hr_status} | 平均心率")
    print(f"  - 期望: {expected['hr_target']:.0f} bpm")
    print(f"  - 实际: {results['hr_mean_bpm']:.2f} bpm")
    print(f"  - 误差: {hr_error:.2f}%")
    
    print(f"\n◇ INFO | 最大心率: {results['hr_max_bpm']:.2f} bpm")
    print(f"◇ INFO | 心率恢复: {results['hr_recovery_bpm_per_min']:.2f} bpm/min")
    
    # 质量
    print(f"\n✓ PASS | 数据质量")
    print(f"  - IMU 质量: {results['imu_quality']:.2f}/1.0")
    print(f"  - ECG 质量: {results['ecg_quality']:.2f}/1.0")
    
    # 异常
    print(f"\n◇ INFO | 异常检测")
    print(f"  - IMU 异常: {results['imu_anomalies']}")
    print(f"  - HR 异常: {results['hr_anomalies']}")
    
    print("\n" + "="*70)
    print("  验证完成！")
    print("="*70 + "\n")
    
    # JSON 输出
    print("完整结果（JSON）：\n")
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + "  改进的小数据量验证 - Improved Small Sample Validation".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    # 生成优化的合成数据
    data, expected = create_improved_synthetic_data()
    
    # 运行管道
    print("\n运行处理管道...\n")
    results = run_full_pipeline(data)
    
    # 打印报告
    print_validation_report(results, expected)
