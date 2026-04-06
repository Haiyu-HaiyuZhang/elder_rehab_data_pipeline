"""
信号预处理模块 - SignalPreprocessor

包含滤波、重采样、归一化等操作
"""

import numpy as np
from scipy.signal import butter, sosfilt, resample
from typing import Dict, Tuple
import logging

import config

logger = logging.getLogger(__name__)


class SignalPreprocessor:
    """信号预处理器"""
    
    def __init__(self, target_sample_rate: float = config.TARGET_SAMPLE_RATE,
                 filter_order: int = config.FILTER_ORDER,
                 cutoff_freq: float = config.CUTOFF_FREQ):
        """
        初始化预处理器
        
        Parameters
        ----------
        target_sample_rate : float
            目标采样率（Hz），默认 100Hz
        filter_order : int
            Butterworth滤波器阶数，默认 4
        cutoff_freq : float
            低通滤波截止频率（Hz），默认 5Hz
        """
        self.target_sample_rate = target_sample_rate
        self.filter_order = filter_order
        self.cutoff_freq = cutoff_freq
        
        logger.info(f"预处理器初始化: fs_target={target_sample_rate}Hz, "
                   f"filter_order={filter_order}, cutoff={cutoff_freq}Hz")
    
    def apply_lowpass_filter(self, signal: np.ndarray, fs: float) -> np.ndarray:
        """
        应用Butterworth低通滤波（前向-后向，零相位失真）
        
        Parameters
        ----------
        signal : np.ndarray
            输入信号，形状 (N,)
        fs : float
            采样率（Hz）
        
        Returns
        -------
        np.ndarray
            滤波后的信号，形状 (N,)
        """
        
        # 设计滤波器
        sos = butter(self.filter_order, self.cutoff_freq, 
                    btype='low', fs=fs, output='sos')
        
        # 应用滤波（前向-后向）
        filtered = sosfilt(sos, signal)
        
        return filtered.astype(np.float32)
    
    def apply_bandpass_filter(self, signal: np.ndarray, fs: float,
                             low_freq: float, high_freq: float) -> np.ndarray:
        """
        应用带通滤波
        
        Parameters
        ----------
        signal : np.ndarray
            输入信号
        fs : float
            采样率（Hz）
        low_freq : float
            低频截止（Hz）
        high_freq : float
            高频截止（Hz）
        
        Returns
        -------
        np.ndarray
            滤波后的信号
        """
        
        sos = butter(self.filter_order, [low_freq, high_freq],
                    btype='band', fs=fs, output='sos')
        
        filtered = sosfilt(sos, signal)
        
        return filtered.astype(np.float32)
    
    def resample_signal(self, signal: np.ndarray, orig_fs: float,
                       target_fs: float = None) -> np.ndarray:
        """
        重采样信号到目标采样率
        
        Parameters
        ----------
        signal : np.ndarray
            输入信号
        orig_fs : float
            原始采样率（Hz）
        target_fs : float, optional
            目标采样率，默认使用 self.target_sample_rate
        
        Returns
        -------
        np.ndarray
            重采样后的信号
        """
        
        if target_fs is None:
            target_fs = self.target_sample_rate
        
        if orig_fs == target_fs:
            return signal
        
        # 计算新的样本数
        num_samples = int(len(signal) * target_fs / orig_fs)
        
        # 使用 scipy.signal.resample（傅里叶方法）
        resampled = resample(signal, num_samples)
        
        return resampled.astype(np.float32)
    
    def handle_missing_values(self, signal: np.ndarray, 
                             max_gap_samples: int = 20) -> np.ndarray:
        """
        处理缺失值和异常值
        
        Parameters
        ----------
        signal : np.ndarray
            输入信号
        max_gap_samples : int
            最大间隙大小（样本数），超过则不填充
        
        Returns
        -------
        np.ndarray
            处理后的信号
        """
        
        signal = signal.copy()
        
        # 检测 NaN 和 Inf
        bad_mask = ~np.isfinite(signal)
        
        if np.any(bad_mask):
            logger.warning(f"检测到 {np.sum(bad_mask)} 个非数值点")
            
            # 使用前向填充
            bad_indices = np.where(bad_mask)[0]
            for idx in bad_indices:
                if idx > 0:
                    signal[idx] = signal[idx-1]
                else:
                    signal[idx] = 0.0
        
        return signal.astype(np.float32)
    
    def normalize_to_window(self, data_dict: Dict, window_length_sec: float = config.WINDOW_LENGTH_SEC) -> Dict:
        """
        提取指定长度的时间窗口
        
        Parameters
        ----------
        data_dict : dict
            原始数据字典（来自 DataLoader）
        window_length_sec : float
            窗口长度（秒）
        
        Returns
        -------
        dict
            包含窗口内数据的字典，采样率统一为 target_sample_rate
        """
        
        # 获取原始采样率
        orig_fs = data_dict['sample_rate']
        
        # 计算窗口样本数
        window_samples = int(window_length_sec * orig_fs)
        
        # 如果数据不足窗口长度，进行填充或截断
        processed_dict = data_dict.copy()
        
        # 处理 IMU 数据
        imu_keys = ['acc_x', 'acc_y', 'acc_z', 'gyr_x', 'gyr_y', 'gyr_z']
        
        for key in imu_keys:
            if key in data_dict:
                signal = data_dict[key][:window_samples]
                
                # 处理缺失值
                signal = self.handle_missing_values(signal)
                
                # 应用滤波
                signal = self.apply_lowpass_filter(signal, orig_fs)
                
                # 重采样到目标采样率
                signal = self.resample_signal(signal, orig_fs, self.target_sample_rate)
                
                processed_dict[key] = signal
        
        # 处理 ECG 数据
        if 'ecg' in data_dict:
            signal = data_dict['ecg'][:window_samples]
            signal = self.handle_missing_values(signal)
            
            # ECG 使用带通滤波
            signal = self.apply_bandpass_filter(signal, orig_fs,
                                               config.ECG_BANDPASS_LOW,
                                               config.ECG_BANDPASS_HIGH)
            
            signal = self.resample_signal(signal, orig_fs, self.target_sample_rate)
            processed_dict['ecg'] = signal
        
        # 更新时间戳
        n_samples = len(processed_dict['acc_x']) if 'acc_x' in processed_dict else len(processed_dict['ecg'])
        processed_dict['timestamp'] = np.arange(n_samples) / self.target_sample_rate
        processed_dict['sample_rate'] = self.target_sample_rate
        
        logger.info(f"预处理完成: {orig_fs}Hz →{self.target_sample_rate}Hz, "
                   f"窗口长度: {window_length_sec}s ({n_samples}样本)")
        
        return processed_dict
    
    def process(self, data_dict: Dict, window_length: float = config.WINDOW_LENGTH_SEC) -> Dict:
        """
        完整的预处理流程
        
        Parameters
        ----------
        data_dict : dict
            原始数据字典
        window_length : float
            时间窗口长度（秒）
        
        Returns
        -------
        dict
            预处理后的数据字典
        """
        
        return self.normalize_to_window(data_dict, window_length_sec=window_length)


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO)
    
    # 示例：创建合成信号并预处理
    fs = 104  # 原始采样率
    duration = 30  # 秒
    t = np.arange(0, duration, 1/fs)
    
    # 创建 1.5Hz 的合成步频信号（正弦波）
    signal = np.sin(2 * np.pi * 1.5 * t) + 0.1 * np.random.randn(len(t))
    
    data = {
        'acc_x': signal.astype(np.float32),
        'acc_y': (0.5 * signal).astype(np.float32),
        'acc_z': (9.8 + 0.1 * signal).astype(np.float32),
        'gyr_x': (0.01 * np.random.randn(len(t))).astype(np.float32),
        'gyr_y': (0.01 * np.random.randn(len(t))).astype(np.float32),
        'gyr_z': (0.01 * np.random.randn(len(t))).astype(np.float32),
        'timestamp': t.astype(np.float32),
        'sample_rate': fs
    }
    
    # 预处理
    processor = SignalPreprocessor()
    processed = processor.process(data, window_length=30)
    
    print(f"原始形状: {len(data['acc_x'])}, 采样率: {data['sample_rate']}Hz")
    print(f"处理后形状: {len(processed['acc_x'])}, 采样率: {processed['sample_rate']}Hz")
