"""
心率计算模块 - Heart Rate Metrics

包括平均心率、最大心率、心率恢复率
"""

import numpy as np
from scipy.signal import find_peaks
from typing import Dict, Tuple, Optional
import logging

import config

logger = logging.getLogger(__name__)


class QRSDetector:
    """QRS 检测器 - 识别ECG中的心跳"""
    
    def __init__(self, method: str = 'simple'):
        """
        初始化 QRS 检测器
        
        Parameters
        ----------
        method : str
            检测方法，'simple'（简单峰值检测）或 'neurokit2'（如可用）
        """
        self.method = method
    
    def detect_qrs_simple(self, ecg_signal: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        简单的 QRS 检测（基于峰值检测）
        
        Parameters
        ----------
        ecg_signal : np.ndarray
            ECG 信号（已滤波），形状 (N,)
        fs : float
            采样率（Hz）
        
        Returns
        -------
        qrs_peaks : np.ndarray
            QRS 峰值的样本索引
        qrs_confidence : np.ndarray
            检测置信度，形状 (len(qrs_peaks),)
        """
        
        # 对信号求导（追踪陡峭变化）
        ecg_diff = np.abs(np.diff(ecg_signal))
        
        # 平方和（增强特征）
        ecg_squared = ecg_signal ** 2
        
        # 最小峰间距（心率最高 200 bpm）
        min_distance = int(0.3 * fs)  # 300ms
        
        # 峰值检测
        peaks, properties = find_peaks(
            ecg_squared,
            distance=min_distance,
            height=np.median(ecg_squared) + np.std(ecg_squared)
        )
        
        # 简单置信度：基于峰值高度
        if len(peaks) > 0:
            heights = properties['peak_heights']
            confidence = heights / np.max(heights)
        else:
            confidence = np.array([])
        
        logger.debug(f"QRS 检测: {len(peaks)} 个峰值，平均置信度 {np.mean(confidence):.2f}")
        
        return peaks, confidence
    
    def detect_qrs(self, ecg_signal: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        QRS 检测（主接口）
        
        Parameters
        ----------
        ecg_signal : np.ndarray
            ECG 信号（已滤波）
        fs : float
            采样率（Hz）
        
        Returns
        -------
        qrs_peaks : np.ndarray
            QRS 峰值的样本索引
        qrs_confidence : np.ndarray
            检测置信度
        """
        
        if self.method == 'simple':
            return self.detect_qrs_simple(ecg_signal, fs)
        
        elif self.method == 'neurokit2':
            try:
                import neurokit2 as nk
                
                # 使用 neurokit2 检测
                signals, info = nk.ecg_process(ecg_signal, sampling_rate=fs)
                qrs_peaks = info['ECG_R_Peaks']
                
                # 简单置信度（都设为1）
                confidence = np.ones(len(qrs_peaks))
                
                return qrs_peaks, confidence
            
            except ImportError:
                logger.warning("neurokit2 未安装，降级为简单方法")
                return self.detect_qrs_simple(ecg_signal, fs)
        
        else:
            return self.detect_qrs_simple(ecg_signal, fs)


class HRMean:
    """平均心率计算器"""
    
    def __init__(self):
        self.qrs_detector = QRSDetector()
    
    def calculate_from_qrs(self, qrs_peaks: np.ndarray, fs: float) -> float:
        """
        从 QRS 峰值计算平均心率
        
        公式：
        RR_intervals = peaks时间差（秒）
        HR_instant = 60 / RR_intervals（bpm）
        hr_mean = mean(HR_instant)
        
        Parameters
        ----------
        qrs_peaks : np.ndarray
            QRS 峰值的样本索引
        fs : float
            采样率（Hz）
        
        Returns
        -------
        float
            平均心率（bpm）
        """
        
        if len(qrs_peaks) < 2:
            logger.warning("检测 QRS < 2 个，无法计算心率")
            return 0.0
        
        # 将峰值索引转换为时间（秒）
        qrs_times = qrs_peaks / fs
        
        # 计算 RR 间隔（秒）
        rr_intervals = np.diff(qrs_times)
        
        # 转换为心率（bpm）
        hr_instant = 60.0 / rr_intervals
        
        # 平均心率
        hr_mean = np.mean(hr_instant)
        
        return float(hr_mean)
    
    def calculate(self, data_dict: Dict) -> float:
        """
        计算平均心率
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典，包含 'ecg' 信号
        
        Returns
        -------
        float
            平均心率（bpm），范围 [30, 200]
        """
        
        if 'ecg' not in data_dict:
            logger.warning("数据中无 ECG 信号")
            return None
        
        ecg_signal = data_dict['ecg']
        fs = data_dict['sample_rate']
        
        # QRS 检测
        qrs_peaks, confidence = self.qrs_detector.detect_qrs(ecg_signal, fs)
        
        if len(qrs_peaks) < 2:
            logger.warning("检测 QRS 不足，无法计算心率")
            return None
        
        # 计算平均心率
        hr_mean = self.calculate_from_qrs(qrs_peaks, fs)
        
        # 限制范围
        hr_mean = np.clip(hr_mean, config.HR_MIN_BPM, config.HR_MAX_BPM)
        
        logger.info(f"平均心率: {hr_mean:.1f} bpm")
        
        return float(hr_mean)


class HRMax:
    """最大心率计算器"""
    
    def __init__(self):
        self.qrs_detector = QRSDetector()
    
    def calculate(self, data_dict: Dict) -> float:
        """
        计算最大心率
        
        公式：HR_max = 60 / min(RR_intervals)
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典
        
        Returns
        -------
        float
            最大心率（bpm）
        """
        
        if 'ecg' not in data_dict:
            logger.warning("数据中无 ECG 信号")
            return None
        
        ecg_signal = data_dict['ecg']
        fs = data_dict['sample_rate']
        
        # QRS 检测
        qrs_peaks, _ = self.qrs_detector.detect_qrs(ecg_signal, fs)
        
        if len(qrs_peaks) < 2:
            logger.warning("检测 QRS 不足，无法计算心率")
            return None
        
        # RR 间隔
        qrs_times = qrs_peaks / fs
        rr_intervals = np.diff(qrs_times)
        
        # 最大心率 = 60 / min(RR)
        hr_max = 60.0 / np.min(rr_intervals)
        
        # 限制范围
        hr_max = np.clip(hr_max, config.HR_MIN_BPM, config.HR_MAX_BPM)
        
        logger.info(f"最大心率: {hr_max:.1f} bpm")
        
        return float(hr_max)


class HRRecovery:
    """心率恢复率计算器"""
    
    def __init__(self):
        self.qrs_detector = QRSDetector()
    
    def calculate(self, data_dict: Dict, exercise_end_time: Optional[float] = None) -> float:
        """
        计算心率恢复率
        
        公式：
        HRR = (HR_exercise_end - HR_60s_recovery) / 60秒 × 60秒/分钟
            = HR_exercise_end - HR_60s_recovery (bpm/min)
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典
        exercise_end_time : float, optional
            运动结束时刻（秒）。如果为None，使用时间窗口的结束
        
        Returns
        -------
        float
            心率恢复率（bpm/min）
        """
        
        if 'ecg' not in data_dict:
            logger.warning("数据中无 ECG 信号")
            return None
        
        ecg_signal = data_dict['ecg']
        fs = data_dict['sample_rate']
        timestamp = data_dict['timestamp']
        
        # QRS 检测
        qrs_peaks, _ = self.qrs_detector.detect_qrs(ecg_signal, fs)
        
        if len(qrs_peaks) < 2:
            return None
        
        qrs_times = qrs_peaks / fs
        rr_intervals = np.diff(qrs_times)
        hr_instant = 60.0 / rr_intervals
        
        # 确定运动结束时刻
        if exercise_end_time is None:
            # 假设运动在窗口末尾结束
            exercise_end_time = timestamp[-1] - config.HR_RECOVERY_WINDOW_SEC
        
        # 获取运动末期心率（运动结束前5秒）
        end_mask = (qrs_times[:-1] > exercise_end_time - 5) & \
                  (qrs_times[:-1] <= exercise_end_time)
        
        if np.any(end_mask):
            hr_end = np.mean(hr_instant[end_mask])
        else:
            hr_end = hr_instant[-1]
        
        # 获取恢复期60秒时的心率
        recovery_mask = (qrs_times[:-1] > exercise_end_time + 55) & \
                       (qrs_times[:-1] <= exercise_end_time + 60)
        
        if np.any(recovery_mask):
            hr_recovery = np.mean(hr_instant[recovery_mask])
        else:
            logger.warning("无法获取恢复期数据，使用最后的心率")
            hr_recovery = hr_instant[-1]
        
        # 计算恢复率
        hrr = hr_end - hr_recovery
        
        logger.info(f"心率恢复: {hr_end:.1f} → {hr_recovery:.1f} bpm, "
                   f"HRR: {hrr:.1f} bpm/min")
        
        return float(hrr)


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO)
    
    # 创建合成ECG信号（75 bpm）
    fs = 130
    duration = 30
    t = np.arange(0, duration, 1/fs)
    
    # 75 bpm = 1.25 Hz
    ecg_signal = np.sin(2 * np.pi * 1.25 * t) + 0.05 * np.random.randn(len(t))
    
    data = {
        'ecg': ecg_signal.astype(np.float32),
        'timestamp': t.astype(np.float32),
        'sample_rate': fs
    }
    
    # 计算心率指标
    hr_mean_calc = HRMean()
    hr_max_calc = HRMax()
    
    hr_mean = hr_mean_calc.calculate(data)
    hr_max = hr_max_calc.calculate(data)
    
    print(f"\n心率：")
    print(f"  平均: {hr_mean:.1f} bpm")
    print(f"  最大: {hr_max:.1f} bpm")
