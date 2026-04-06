"""
质量与异常检测模块 - Quality & Anomaly Detection

包括数据质量评分、异常标记检测
"""

import numpy as np
from typing import Dict, List, Tuple
import logging

import config
from modules.step_frequency import StepFrequency
from modules.step_variability import StepVariability
from modules.hr_mean import HRMean

logger = logging.getLogger(__name__)


class QualityChecker:
    """数据质量评估器"""
    
    def __init__(self):
        self.step_freq_calc = StepFrequency()
        self.step_var_calc = StepVariability()
        self.hr_mean_calc = HRMean()
    
    def calculate_snr_imu(self, acc_mag: np.ndarray) -> float:
        """
        计算 IMU 的信噪比（SNR）
        
        SNR = P_signal / P_noise
        其中信号功率在步频频带，噪声功率在高频
        
        Parameters
        ----------
        acc_mag : np.ndarray
            加速度合向量
        
        Returns
        -------
        float
            信噪比（线性单位）
        """
        
        # 简单估计：低频功率 / 高频功率
        # 这里仅作示例，实际可使用FFT
        
        signal_power = np.std(acc_mag) ** 2
        noise_power = np.std(np.diff(acc_mag)) ** 2
        
        if noise_power > 0:
            snr = signal_power / noise_power
        else:
            snr = 0.0
        
        return float(snr)
    
    def calculate_qrs_detection_rate(self, data_dict: Dict) -> float:
        """
        计算 QRS 检测成功率
        
        Returns
        -------
        float
            检测成功率 [0, 1]
        """
        
        if 'ecg' not in data_dict:
            return None
        
        # 估计预期心率（假设 60-100 bpm）
        window_sec = data_dict['timestamp'][-1] - data_dict['timestamp'][0]
        expected_qrs_count_min = int(60 * window_sec / 60)  # 最少 60 bpm
        expected_qrs_count_max = int(100 * window_sec / 60)  # 最多 100 bpm
        expected_qrs_count = (expected_qrs_count_min + expected_qrs_count_max) / 2
        
        # 实际 QRS 检测数
        try:
            hr_mean = self.hr_mean_calc.calculate(data_dict)
            actual_qrs_count = int(hr_mean * window_sec / 60)
        except:
            actual_qrs_count = 0
        
        if expected_qrs_count > 0:
            detection_rate = actual_qrs_count / expected_qrs_count
        else:
            detection_rate = 0.0
        
        return float(np.clip(detection_rate, 0, 1))
    
    def calculate_imu_data_quality(self, data_dict: Dict) -> float:
        """
        计算 IMU 数据质量分数
        
        Returns
        -------
        float
            质量分数 [0, 1]
        """
        
        if 'acc_x' not in data_dict:
            return None
        
        acc_x = data_dict['acc_x']
        acc_y = data_dict['acc_y']
        acc_z = data_dict['acc_z']
        
        acc_mag = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        # 计算 SNR
        snr = self.calculate_snr_imu(acc_mag)
        
        # SNR 到质量分数的转换
        quality_snr = min(1.0, snr / config.SNR_REFERENCE)
        
        return float(quality_snr)
    
    def calculate_ecg_data_quality(self, data_dict: Dict) -> float:
        """
        计算 ECG 数据质量分数
        
        Returns
        -------
        float
            质量分数 [0, 1]
        """
        
        detection_rate = self.calculate_qrs_detection_rate(data_dict)
        
        if detection_rate is None:
            return None
        
        return float(detection_rate)
    
    def calculate_overall_quality(self, data_dict: Dict) -> float:
        """
        计算综合数据质量分数
        
        Returns
        -------
        float
            质量分数 [0, 1]
        """
        
        quality_imu = self.calculate_imu_data_quality(data_dict)
        quality_ecg = self.calculate_ecg_data_quality(data_dict)
        
        qualities = [q for q in [quality_imu, quality_ecg] if q is not None]
        
        if qualities:
            return float(np.mean(qualities))
        else:
            return None
    
    def get_quality_reason(self, quality_score: float, anomalies: List[str]) -> str:
        """
        根据质量分数和异常标记生成质量说明
        
        Parameters
        ----------
        quality_score : float
            质量分数 [0, 1]
        anomalies : list
            异常标记列表
        
        Returns
        -------
        str
            质量说明
        """
        
        if quality_score >= config.QUALITY_EXCELLENT:
            return "clean_signal"
        
        elif quality_score >= config.QUALITY_GOOD:
            if len(anomalies) <= 1:
                return "minor_noise"
            else:
                return "moderate_artifacts"
        
        elif quality_score >= config.QUALITY_ACCEPTABLE:
            return "moderate_artifacts"
        
        else:
            if len(anomalies) >= 3 or "sensor_dropout" in anomalies:
                return "data_quality_low"
            else:
                return "significant_dropout"


class AnomalyDetector:
    """异常检测器"""
    
    def __init__(self):
        self.step_freq_calc = StepFrequency()
        self.step_var_calc = StepVariability()
        self.hr_mean_calc = HRMean()
    
    def detect_imu_anomalies(self, data_dict: Dict) -> List[str]:
        """
        检测 IMU 相关的异常
        
        Returns
        -------
        list
            异常标记列表
        """
        
        anomalies = []
        
        acc_x = data_dict['acc_x']
        acc_y = data_dict['acc_y']
        acc_z = data_dict['acc_z']
        fs = data_dict['sample_rate']
        
        acc_mag = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        # 异常 1：传感器脱落
        dropout_threshold_samples = int(config.DROPOUT_DURATION_THRESHOLD_SEC * fs)
        dropout_mask = acc_mag < config.ACC_MAG_DROPOUT_THRESHOLD
        
        if np.sum(dropout_mask) > dropout_threshold_samples:
            anomalies.append("sensor_dropout")
            logger.warning("检测到传感器脱落")
        
        # 异常 2：长期静止
        stillness_threshold_samples = int(config.STILLNESS_DURATION_THRESHOLD_SEC * fs)
        acc_std = np.convolve(np.abs(np.diff(acc_mag)), 
                             np.ones(5)/5, mode='valid')  # 移动平均
        stillness_mask = acc_std < config.ACC_STILLNESS_THRESHOLD
        
        if np.sum(stillness_mask) > stillness_threshold_samples:
            anomalies.append("prolonged_stillness")
            logger.warning("检测到长期静止")
        
        # 异常 3：步态节律异常
        try:
            stats = self.step_var_calc.get_isi_statistics(data_dict)
            if stats and stats['isi_cv'] > config.ISI_CV_ANOMALY_THRESHOLD:
                anomalies.append("irregular_step_rhythm")
                logger.warning(f"步态节律异常：CV = {stats['isi_cv']:.1f}%")
        except Exception as e:
            logger.debug(f"步态变异性检测失败: {e}")
        
        return anomalies
    
    def detect_hr_anomalies(self, data_dict: Dict, 
                          hr_mean: float = None, hrr: float = None) -> List[str]:
        """
        检测心率相关的异常
        
        Returns
        -------
        list
            异常标记列表
        """
        
        anomalies = []
        
        if 'ecg' not in data_dict:
            return anomalies
        
        ecg = data_dict['ecg']
        
        # 异常 1：QRS 检测失败
        if np.sum(~np.isfinite(ecg)) / len(ecg) > config.QRS_DETECTION_FAILURE_RATE:
            anomalies.append("poor_qrs_detection")
            logger.warning("ECG 信号质量不佳，QRS 检测失败率高")
        
        # 异常 2：心率超出范围
        if hr_mean is not None:
            if hr_mean < config.HR_MIN_BPM or hr_mean > config.HR_MAX_BPM:
                anomalies.append("invalid_heart_rate")
                logger.warning(f"心率异常：{hr_mean:.1f} bpm")
        
        # 异常 3：恢复异常
        if hrr is not None:
            if hrr < config.HRR_ANOMALY_THRESHOLD:
                anomalies.append("abnormal_recovery")
                logger.warning(f"心率恢复异常：{hrr:.1f} bpm/min")
        
        return anomalies
    
    def detect_all_anomalies(self, data_dict: Dict,
                            hr_mean: float = None, hrr: float = None) -> Dict[str, List[str]]:
        """
        检测所有异常
        
        Returns
        -------
        dict
            包含 'imu' 和 'hr' 键的异常列表字典
        """
        
        imu_anomalies = self.detect_imu_anomalies(data_dict)
        hr_anomalies = self.detect_hr_anomalies(data_dict, hr_mean, hrr)
        
        return {
            'imu': imu_anomalies,
            'hr': hr_anomalies
        }


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO)
    
    # 创建合成数据
    fs = 100
    duration = 30
    t = np.arange(0, duration, 1/fs)
    signal = np.sin(2 * np.pi * 1.5 * t) + 0.05 * np.random.randn(len(t))
    
    data = {
        'acc_x': signal.astype(np.float32),
        'acc_y': (0.5 * signal).astype(np.float32),
        'acc_z': (9.8 + 0.1 * signal).astype(np.float32),
        'timestamp': t.astype(np.float32),
        'sample_rate': fs
    }
    
    # 质量检查
    qc = QualityChecker()
    quality = qc.calculate_overall_quality(data)
    
    print(f"\n数据质量分数: {quality:.2f}")
    
    # 异常检测
    ad = AnomalyDetector()
    anomalies = ad.detect_all_anomalies(data)
    
    print(f"异常标记: {anomalies}")
