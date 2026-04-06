"""
步频计算模块 - Step Frequency

计算30秒窗口内的步数频率（Hz）
"""

import numpy as np
from scipy.signal import find_peaks
from typing import Dict, Tuple
import logging

import config

logger = logging.getLogger(__name__)


class StepFrequency:
    """步频计算器"""
    
    def __init__(self, min_distance_sec: float = config.MIN_PEAK_DISTANCE_SEC,
                 peak_height_multiplier: float = config.PEAK_HEIGHT_MULTIPLIER):
        """
        初始化步频计算器
        
        Parameters
        ----------
        min_distance_sec : float
            峰值最小间距（秒），默认 0.06s (60ms)
        peak_height_multiplier : float
            峰值高度阈值乘数（相对于噪声标准差）
        """
        self.min_distance_sec = min_distance_sec
        self.peak_height_multiplier = peak_height_multiplier
    
    def calculate_acc_magnitude(self, acc_x: np.ndarray, acc_y: np.ndarray,
                               acc_z: np.ndarray) -> np.ndarray:
        """
        计算加速度合向量
        
        公式：acc_mag(t) = sqrt(acc_x^2 + acc_y^2 + acc_z^2)
        
        Parameters
        ----------
        acc_x, acc_y, acc_z : np.ndarray
            三轴加速度，形状 (N,)
        
        Returns
        -------
        np.ndarray
            加速度合向量，形状 (N,)
        """
        
        acc_mag = np.sqrt(acc_x**2 + acc_y**2 + acc_z**2)
        
        return acc_mag.astype(np.float32)
    
    def detect_peaks(self, signal: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        检测信号中的峰值（步事件）
        
        Parameters
        ----------
        signal : np.ndarray
            输入信号（加速度合向量），形状 (N,)
        fs : float
            采样率（Hz）
        
        Returns
        -------
        peaks : np.ndarray
            峰值的样本索引
        properties : dict
            峰值属性（高度等）
        """
        
        # 计算最小峰间距（样本数）
        min_distance_samples = int(self.min_distance_sec * fs)
        
        # 计算峰值高度阈值
        noise_std = np.std(signal)
        peak_height = self.peak_height_multiplier * noise_std
        
        # 峰值检测
        peaks, properties = find_peaks(
            signal,
            distance=min_distance_samples,
            height=peak_height,
            prominence=noise_std * 0.5  # 峰值突出度
        )
        
        logger.debug(f"检测到 {len(peaks)} 个峰值，"
                    f"最小间距: {min_distance_samples}样本，"
                    f"高度阈值: {peak_height:.3f}")
        
        return peaks, properties
    
    def calculate(self, data_dict: Dict) -> float:
        """
        计算步频（Hz）
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典，包含：
            - 'acc_x', 'acc_y', 'acc_z': 加速度（m/s²）
            - 'timestamp': 时间戳（秒）
            - 'sample_rate': 采样率（Hz）
        
        Returns
        -------
        float
            步频（Hz），范围 [1.0, 3.0]
        
        Examples
        --------
        >>> step_freq = StepFrequency()
        >>> sf = step_freq.calculate(processed_data)
        >>> print(f"Step Frequency: {sf:.2f} Hz")
        """
        
        # 提取数据
        acc_x = data_dict['acc_x']
        acc_y = data_dict['acc_y']
        acc_z = data_dict['acc_z']
        fs = data_dict['sample_rate']
        timestamp = data_dict['timestamp']
        
        # 计算加速度合向量
        acc_mag = self.calculate_acc_magnitude(acc_x, acc_y, acc_z)
        
        # 检测峰值
        peaks, _ = self.detect_peaks(acc_mag, fs)
        
        # 计算步频
        if len(peaks) > 0:
            # 时间窗口长度
            window_time_sec = timestamp[-1] - timestamp[0]
            
            # 步频 = 峰值数 / 时间（秒）
            step_frequency_hz = len(peaks) / window_time_sec
        else:
            logger.warning("未检测到峰值，步频设为 0")
            step_frequency_hz = 0.0
        
        # 限制在有效范围
        step_frequency_hz = np.clip(
            step_frequency_hz,
            config.STEP_FREQUENCY_MIN_HZ,
            config.STEP_FREQUENCY_MAX_HZ
        )
        
        logger.info(f"步频: {step_frequency_hz:.2f} Hz ({step_frequency_hz*60:.1f} steps/min), "
                   f"检测峰值: {len(peaks)}")
        
        return float(step_frequency_hz)
    
    def get_peak_times(self, data_dict: Dict) -> np.ndarray:
        """
        获取峰值时间戳（用于步幅、变异性等后续计算）
        
        Returns
        -------
        np.ndarray
            峰值对应的时间戳（秒）
        """
        
        acc_x = data_dict['acc_x']
        acc_y = data_dict['acc_y']
        acc_z = data_dict['acc_z']
        fs = data_dict['sample_rate']
        timestamp = data_dict['timestamp']
        
        acc_mag = self.calculate_acc_magnitude(acc_x, acc_y, acc_z)
        peaks, _ = self.detect_peaks(acc_mag, fs)
        
        peak_times = timestamp[peaks]
        
        return peak_times


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    logging.basicConfig(level=logging.DEBUG)
    
    # 创建合成数据
    fs = 100
    duration = 30
    t = np.arange(0, duration, 1/fs)
    
    # 1.5Hz 步频的合成信号（正弦波 + 噪声）
    step_freq_true = 1.5
    signal = np.sin(2 * np.pi * step_freq_true * t) + 0.1 * np.random.randn(len(t))
    
    data = {
        'acc_x': signal.astype(np.float32),
        'acc_y': (0.5 * signal).astype(np.float32),
        'acc_z': (9.8 + 0.1 * signal).astype(np.float32),
        'timestamp': t.astype(np.float32),
        'sample_rate': fs
    }
    
    # 计算步频
    calculator = StepFrequency()
    sf = calculator.calculate(data)
    
    print(f"\n真实步频: {step_freq_true:.2f} Hz")
    print(f"计算步频: {sf:.2f} Hz")
    print(f"误差: {abs(sf - step_freq_true)/step_freq_true * 100:.1f}%")
