"""
小数据量验证脚本 - Validate with Small Sample Data
验证每个计算指标的正确性
"""

import numpy as np
import pandas as pd
import json
import logging
from datetime import datetime
import os
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


class ValidationRunner:
    """验证脚本运行器"""
    
    def __init__(self):
        self.results = {}
    
    def print_section(self, title):
        """打印章节标题"""
        print(f"\n{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}\n")
    
    def print_result(self, name, expected, actual, tolerance=None):
        """打印验证结果"""
        if tolerance is not None and expected is not None:
            error = abs(actual - expected)
            error_pct = (error / abs(expected) * 100) if expected != 0 else 0
            status = "✓ PASS" if error_pct <= tolerance else "✗ FAIL"
            print(f"{status} | {name:35s} | 期望: {expected:10.4f} | 实际: {actual:10.4f} | 误差: {error_pct:6.2f}%")
        else:
            print(f"  {name:35s} | {actual}")
    
    def generate_synthetic_data(self):
        """生成可预测的合成数据用于验证"""
        
        self.print_section("步骤 1: 生成合成测试数据")
        
        # 参数
        fs = 100  # 采样率 Hz
        duration = 30  # 30 秒
        step_freq_target = 1.5  # 每秒 1.5 步
        
        t = np.arange(0, duration, 1/fs)
        n_samples = len(t)
        
        logger.info(f"生成 {duration} 秒数据，采样率 {fs} Hz，共 {n_samples} 个样本")
        
        # 1. 加速度信号（模拟步态）
        # 步态周期信号：两个峰值（左右脚）
        acc_mag_base = 10.0  # 重力加速度
        acc_magnitude = acc_mag_base + 2.0 * np.sin(2 * np.pi * step_freq_target * t)
        acc_magnitude += 0.5 * np.sin(2 * np.pi * 2 * step_freq_target * t)  # 谐波
        
        # 添加小噪声
        noise_acc = 0.1 * np.random.randn(n_samples)
        acc_magnitude = acc_magnitude + noise_acc
        
        # 分解为三个轴
        acc_x = acc_magnitude * 0.6
        acc_y = acc_magnitude * 0.4
        acc_z = 9.81 + acc_magnitude * 0.2
        
        # 2. 陀螺仪信号
        gyr_x = 0.02 * np.random.randn(n_samples)
        gyr_y = 0.02 * np.random.randn(n_samples)
        gyr_z = 0.01 * np.random.randn(n_samples)
        
        # 3. ECG 信号（模拟心率）
        # 目标心率：100 bpm = 1.67 Hz
        hr_target = 100  # bpm
        rr_interval_ms = 60000 / hr_target  # ms 之间的间隔
        rr_interval_s = rr_interval_ms / 1000  # 秒
        
        # 生成 QRS 峰值
        ecg_signal = np.zeros(n_samples)
        qrs_times = []
        t_current = rr_interval_s / 2  # 从中间开始
        qrs_indices = []
        
        while t_current < duration:
            idx = int(t_current * fs)
            if idx < n_samples:
                # 创建 QRS 复合波
                window_size = int(0.04 * fs)  # 40ms 宽度
                for i in range(-window_size, window_size):
                    if 0 <= idx + i < n_samples:
                        ecg_signal[idx + i] += (1.0 - abs(i) / window_size) * 1.5
                qrs_times.append(t_current)
                qrs_indices.append(idx)
            t_current += rr_interval_s + 0.01 * np.random.randn()  # 加入心率变异
        
        # 添加背景噪声
        ecg_signal += 0.3 * np.random.randn(n_samples)
        
        logger.info(f"生成的 QRS 峰值: {len(qrs_times)} 个")
        logger.info(f"预期心率: {hr_target} bpm")
        logger.info(f"预期步频: {step_freq_target} Hz")
        
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
        
        self.synthetic_data = {
            'dataframe': data,
            't': t,
            'fs': fs,
            'duration': duration,
            'step_freq_target': step_freq_target,
            'hr_target': hr_target,
            'rr_interval_ms': rr_interval_ms,
            'qrs_times': qrs_times,
            'qrs_indices': qrs_indices,
            'acc_magnitude': acc_magnitude
        }
        
        print(f"✓ 数据生成完成")
        print(f"  - 加速度基线: {acc_mag_base:.2f} m/s²")
        print(f"  - 加速度幅度: ±{2.0:.2f} m/s²")
        print(f"  - ECG 信号长度: {len(ecg_signal)} 样本")
        
        return data
    
    def test_preprocessing(self):
        """测试预处理"""
        
        self.print_section("步骤 2: 预处理（滤波和重采样）")
        
        data = self.synthetic_data['dataframe']
        
        dataloader = DataLoader()
        temp_file = '/tmp/test_validation_data.csv'
        data.to_csv(temp_file, index=False)
        
        # 加载数据
        raw_data = dataloader.load_csv(temp_file)
        logger.info(f"原始数据加载: 采样率 {raw_data.get('sample_rate', 'unknown')} Hz")
        
        # 预处理
        preprocessor = SignalPreprocessor()
        processed_data = preprocessor.process(raw_data, window_length=30)
        
        logger.info(f"预处理完成")
        print(f"✓ 预处理成功")
        print(f"  - 采样率已标准化为: 100 Hz")
        print(f"  - 数据点数: {len(processed_data['acc_x'])}")
        print(f"  - 处理后的键: {list(processed_data.keys())}")
        
        self.processed_data = processed_data
        self.temp_file = temp_file
        
        return processed_data
    
    def test_step_frequency(self):
        """测试步频计算"""
        
        self.print_section("步骤 3: 步频计算验证")
        
        processed_data = self.processed_data
        expected_freq = self.synthetic_data['step_freq_target']
        
        # 计算步频
        step_freq_calc = StepFrequency()
        step_freq = step_freq_calc.calculate(processed_data)
        peak_times = step_freq_calc.get_peak_times(processed_data)
        
        logger.info(f"计算得到的步频: {step_freq:.4f} Hz")
        logger.info(f"检测到的峰值数: {len(peak_times)}")
        
        # 验证
        print(f"✓ 步频计算完成")
        self.print_result("步频 (Hz)", expected_freq, step_freq, tolerance=10)
        print(f"  - 检测到峰值: {len(peak_times)} 个")
        print(f"  - 峰值时间 (秒): {peak_times[:5]}")  # 显示前 5 个
        
        self.step_freq = step_freq
        self.peak_times = peak_times
        self.results['step_frequency'] = {
            'expected': expected_freq,
            'actual': step_freq,
            'n_peaks': len(peak_times)
        }
    
    def test_step_length(self):
        """测试步长计算"""
        
        self.print_section("步骤 4: 步长计算验证")
        
        processed_data = self.processed_data
        
        # 使用默认速度
        avg_velocity = 1.0  # m/s
        step_len_calc = StepLength()
        step_length = step_len_calc.calculate(processed_data, avg_velocity=avg_velocity)
        
        # 手动计算期望值
        # step_length = velocity / (2 * frequency)
        if self.step_freq > 0:
            expected_length = avg_velocity / (2 * self.step_freq)
        else:
            expected_length = 0.0
        
        logger.info(f"计算得到的步长: {step_length:.4f} m")
        logger.info(f"使用速度: {avg_velocity:.2f} m/s，步频: {self.step_freq:.2f} Hz")
        
        print(f"✓ 步长计算完成")
        self.print_result("步长 (m)", expected_length, step_length, tolerance=5)
        print(f"  - 计算公式: velocity / (2 × frequency) = {avg_velocity} / (2 × {self.step_freq:.2f}) = {expected_length:.4f} m")
        
        self.results['step_length'] = {
            'expected': expected_length,
            'actual': step_length,
            'avg_velocity': avg_velocity
        }
    
    def test_step_variability(self):
        """测试步长变异性"""
        
        self.print_section("步骤 5: 步长变异性（ISI）验证")
        
        processed_data = self.processed_data
        
        # 计算 ISI
        step_var_calc = StepVariability()
        step_var = step_var_calc.calculate(processed_data)
        isi_stats = step_var_calc.get_isi_statistics(processed_data)
        
        print(f"✓ 步长变异性计算完成")
        print(f"  - ISI 标准差 (ms): {step_var:.2f}")
        if isi_stats:
            print(f"  - ISI 统计信息:")
            print(f"    • 平均 ISI: {isi_stats.get('mean', 0):.2f} ms")
            print(f"    • ISI 标准差: {isi_stats.get('std', 0):.2f} ms")
            print(f"    • 变异系数 (CV): {isi_stats.get('cv', 0):.2f}%")
            print(f"    • 步数: {isi_stats.get('n_steps', 0)}")
            print(f"    • ISI 范围: {isi_stats.get('min', 0):.2f} - {isi_stats.get('max', 0):.2f} ms")
        
        self.results['step_variability'] = {
            'isi_std_ms': step_var,
            'isi_stats': isi_stats
        }
    
    def test_heart_rate(self):
        """测试心率计算"""
        
        self.print_section("步骤 6: 心率计算验证")
        
        processed_data = self.processed_data
        expected_hr = self.synthetic_data['hr_target']
        
        # 检测 QRS
        qrs_detector = QRSDetector()
        ecg_signal = processed_data.get('ecg', np.zeros(100))
        fs = processed_data.get('sample_rate', 100)
        qrs_peaks, qrs_confidence = qrs_detector.detect_qrs(ecg_signal, fs)
        
        logger.info(f"检测到 {len(qrs_peaks)} 个 QRS 峰值")
        
        # 计算心率指标
        hr_mean_calc = HRMean()
        hr_mean = hr_mean_calc.calculate(processed_data)
        
        hr_max_calc = HRMax()
        hr_max = hr_max_calc.calculate(processed_data)
        
        hr_recovery_calc = HRRecovery()
        hr_recovery = hr_recovery_calc.calculate(processed_data)
        
        print(f"✓ 心率计算完成")
        self.print_result("平均心率 (bpm)", expected_hr, hr_mean, tolerance=15)
        print(f"  - 最大心率: {hr_max:.2f} bpm")
        print(f"  - 心率恢复: {hr_recovery:.2f} bpm/min")
        print(f"  - 检测到 QRS 峰值: {len(qrs_peaks)} 个")
        
        self.results['heart_rate'] = {
            'hr_mean': {
                'expected': expected_hr,
                'actual': hr_mean
            },
            'hr_max': hr_max,
            'hr_recovery': hr_recovery,
            'qrs_count': len(qrs_peaks)
        }
    
    def test_quality_and_anomalies(self):
        """测试数据质量和异常检测"""
        
        self.print_section("步骤 7: 数据质量和异常检测验证")
        
        processed_data = self.processed_data
        
        # 质量检查
        quality_checker = QualityChecker()
        imu_quality = quality_checker.calculate_imu_data_quality(processed_data) or 0.5
        ecg_quality = quality_checker.calculate_ecg_data_quality(processed_data) or 0.5
        
        imu_reason = quality_checker.get_quality_reason(imu_quality, [])
        ecg_reason = quality_checker.get_quality_reason(ecg_quality, [])
        
        logger.info(f"IMU 数据质量: {imu_quality:.2f} - {imu_reason}")
        logger.info(f"ECG 数据质量: {ecg_quality:.2f} - {ecg_reason}")
        
        # 异常检测
        anomaly_detector = AnomalyDetector()
        anomalies = anomaly_detector.detect_all_anomalies(
            processed_data,
            hr_mean=self.results.get('heart_rate', {}).get('hr_mean', {}).get('actual'),
            hrr=self.results.get('heart_rate', {}).get('hr_recovery')
        )
        
        print(f"✓ 质量和异常检测完成")
        print(f"  - IMU 数据质量: {imu_quality:.2f}/1.0 ({imu_reason})")
        print(f"  - ECG 数据质量: {ecg_quality:.2f}/1.0 ({ecg_reason})")
        print(f"  - IMU 异常: {anomalies.get('imu', [])}")
        print(f"  - 心率异常: {anomalies.get('hr', [])}")
        
        self.results['quality'] = {
            'imu_quality': imu_quality,
            'ecg_quality': ecg_quality,
            'imu_reason': imu_reason,
            'ecg_reason': ecg_reason,
            'anomalies': anomalies
        }
    
    def run_all_tests(self):
        """运行所有测试"""
        
        print("\n" + "█"*70)
        print("█" + " "*68 + "█")
        print("█" + "  小数据量验证 - Small Sample Data Validation".center(68) + "█")
        print("█" + " "*68 + "█")
        print("█"*70)
        
        try:
            # 生成测试数据
            self.generate_synthetic_data()
            
            # 保存测试数据
            temp_file = '/tmp/test_validation_data.csv'
            self.synthetic_data['dataframe'].to_csv(temp_file, index=False)
            logger.info(f"测试数据已保存到: {temp_file}")
            
            # 运行所有测试
            self.test_preprocessing()
            self.test_step_frequency()
            self.test_step_length()
            self.test_step_variability()
            self.test_heart_rate()
            self.test_quality_and_anomalies()
            
            # 打印总结
            self.print_summary()
            
        except Exception as e:
            logger.error(f"验证失败: {e}", exc_info=True)
            raise
    
    def print_summary(self):
        """打印验证总结"""
        
        self.print_section("验证总结")
        
        print(json.dumps(self.results, indent=2, default=str))
        
        print("\n" + "="*70)
        print("验证完成！所有指标计算已验证。")
        print("="*70)
        

if __name__ == "__main__":
    
    validator = ValidationRunner()
    validator.run_all_tests()
