"""
步态变异性计算模块 - Gait Variability

计算相邻步间间隔（ISI）的标准差，反映步态节律规律性
"""

import numpy as np
from typing import Dict, Tuple
import logging

import config
from modules.step_frequency import StepFrequency

logger = logging.getLogger(__name__)


class StepVariability:
    """步态变异性计算器"""
    
    def __init__(self):
        self.step_frequency_calc = StepFrequency()
    
    def calculate_isi(self, peak_times: np.ndarray) -> np.ndarray:
        """
        计算相邻步间间隔（ISI）
        
        公式：ISI[i] = peak_times[i+1] - peak_times[i]
        
        Parameters
        ----------
        peak_times : np.ndarray
            峰值时间戳（秒），形状 (N_peaks,)
        
        Returns
        -------
        np.ndarray
            ISI 数组（秒），形状 (N_peaks-1,)
        """
        
        if len(peak_times) < 2:
            logger.warning("检测到的峰值少于2个，无法计算ISI")
            return np.array([])
        
        # 计算相邻差
        isi = np.diff(peak_times)
        
        return isi
    
    def calculate(self, data_dict: Dict) -> float:
        """
        计算步态变异性（ISI标准差）
        
        公式：
        variability = sqrt(sum((ISI_i - mean(ISI))^2) / (n-1))
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典
        
        Returns
        -------
        float
            步态变异性（毫秒）
        
        Examples
        --------
        >>> calc = StepVariability()
        >>> var_ms = calc.calculate(processed_data)
        >>> print(f"Step Time Variability: {var_ms:.1f} ms")
        """
        
        # 获取峰值时间戳
        peak_times = self.step_frequency_calc.get_peak_times(data_dict)
        
        if len(peak_times) < 3:
            logger.warning(f"检测峰值数 {len(peak_times)} < 3，无法可靠计算变异性")
            return 0.0
        
        # 计算ISI（秒）
        isi_sec = self.calculate_isi(peak_times)
        
        # 转换为毫秒
        isi_ms = isi_sec * 1000.0
        
        # 计算标准差
        variability_ms = np.std(isi_ms, ddof=1)  # ddof=1 是无偏估计
        
        logger.info(f"ISI 统计 - 平均: {np.mean(isi_ms):.1f}ms, "
                   f"std: {variability_ms:.1f}ms, "
                   f"CV: {self.calculate_cv(isi_ms):.1f}%")
        
        return float(variability_ms)
    
    def calculate_cv(self, isi_ms: np.ndarray) -> float:
        """
        计算ISI的变异系数（Coefficient of Variation）
        
        公式：CV = std(ISI) / mean(ISI) × 100%
        
        Parameters
        ----------
        isi_ms : np.ndarray
            ISI 数组（毫秒）
        
        Returns
        -------
        float
            变异系数（%）
        """
        
        mean_isi = np.mean(isi_ms)
        std_isi = np.std(isi_ms, ddof=1)
        
        if mean_isi == 0:
            return 0.0
        
        cv = (std_isi / mean_isi) * 100.0
        
        return cv
    
    def get_isi_statistics(self, data_dict: Dict) -> Dict:
        """
        获取ISI的详细统计信息
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典
        
        Returns
        -------
        dict
            包含以下键的字典：
            - 'isi_mean': ISI 平均值（ms）
            - 'isi_std': ISI 标准差（ms）
            - 'isi_cv': ISI 变异系数（%）
            - 'isi_min': 最小 ISI（ms）
            - 'isi_max': 最大 ISI（ms）
            - 'n_steps': 步数
        """
        
        peak_times = self.step_frequency_calc.get_peak_times(data_dict)
        
        if len(peak_times) < 2:
            return {}
        
        isi_sec = self.calculate_isi(peak_times)
        isi_ms = isi_sec * 1000.0
        
        stats = {
            'isi_mean': float(np.mean(isi_ms)),
            'isi_std': float(np.std(isi_ms, ddof=1)),
            'isi_cv': float(self.calculate_cv(isi_ms)),
            'isi_min': float(np.min(isi_ms)),
            'isi_max': float(np.max(isi_ms)),
            'n_steps': len(peak_times)
        }
        
        return stats


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO)
    
    # 创建合成数据（固定步频 + 小变异性）
    fs = 100
    duration = 30
    t = np.arange(0, duration, 1/fs)
    
    # 1.5Hz 步频
    signal = np.sin(2 * np.pi * 1.5 * t) + 0.05 * np.random.randn(len(t))
    
    data = {
        'acc_x': signal.astype(np.float32),
        'acc_y': (0.5 * signal).astype(np.float32),
        'acc_z': (9.8 + 0.1 * signal).astype(np.float32),
        'timestamp': t.astype(np.float32),
        'sample_rate': fs
    }
    
    # 计算步态变异性
    calc = StepVariability()
    variability = calc.calculate(data)
    stats = calc.get_isi_statistics(data)
    
    print(f"\n步态变异性: {variability:.1f} ms")
    print(f"ISI 统计:")
    for key, val in stats.items():
        print(f"  {key}: {val:.2f}" if isinstance(val, float) else f"  {key}: {val}")
