"""
步幅计算模块 - Step Length

计算单步的距离
"""

import numpy as np
from typing import Dict
import logging

import config
from modules.step_frequency import StepFrequency

logger = logging.getLogger(__name__)


class StepLength:
    """步幅计算器"""
    
    def __init__(self, method: str = 'velocity_based'):
        """
        初始化步幅计算器
        
        Parameters
        ----------
        method : str
            计算方法，'velocity_based' 或 'ins_zupt'
        """
        self.method = method
        self.step_frequency_calc = StepFrequency()
    
    def calculate_velocity_based(self, step_frequency_hz: float,
                                avg_velocity: float = 1.0) -> float:
        """
        基于速度的步幅估计
        
        公式：step_length ≈ average_velocity / (2 × step_frequency)
        
        Parameters
        ----------
        step_frequency_hz : float
            步频（Hz）
        avg_velocity : float
            平均速度（m/s），默认 1.0 m/s（可从IMU积分得到）
        
        Returns
        -------
        float
            步幅（米）
        """
        
        if step_frequency_hz <= 0:
            return 0.0
        
        # 一个步周期（双步）的时间
        step_period = 1.0 / (2 * step_frequency_hz)
        
        # 步幅 ≈ 速度 × 时间
        step_length = avg_velocity * step_period
        
        return float(np.clip(step_length, 
                           config.STEP_LENGTH_MIN_M,
                           config.STEP_LENGTH_MAX_M))
    
    def calculate_ins_zupt_based(self, peak_times: np.ndarray,
                                position_estimates: np.ndarray) -> float:
        """
        基于INS-ZUPT位移积分的步幅计算
        
        参数
        ----------
        peak_times : np.ndarray
            峰值时间戳（秒）
        position_estimates : np.ndarray
            各时刻的位置估计，形状 (N, 3)，单位米
        
        返回
        -------
        float
            平均步幅（米）
        """
        
        if len(peak_times) < 2:
            logger.warning("峰值数 < 2，无法计算步幅")
            return 0.0
        
        step_lengths = []
        
        # 根据峰值时间查找对应的位置
        for i in range(len(peak_times) - 1):
            # 注：这里假设 position_estimates 与 data_dict['timestamp'] 对齐
            # 实际实现需要根据 peak_times 索引地提取位置
            pos_current = position_estimates[i]
            pos_next = position_estimates[i + 1]
            
            # 计算水平位移距离
            distance = np.sqrt(
                (pos_next[0] - pos_current[0])**2 +
                (pos_next[1] - pos_current[1])**2
            )
            
            step_lengths.append(distance)
        
        # 平均步幅
        avg_step_length = np.mean(step_lengths) if step_lengths else 0.0
        
        return float(np.clip(avg_step_length,
                           config.STEP_LENGTH_MIN_M,
                           config.STEP_LENGTH_MAX_M))
    
    def calculate(self, data_dict: Dict, avg_velocity: float = None) -> float:
        """
        计算步幅
        
        Parameters
        ----------
        data_dict : dict
            预处理后的数据字典
        avg_velocity : float, optional
            平均速度（m/s）。如果提供，使用速度方法；否则使用默认值
        
        Returns
        -------
        float
            步幅（米），范围 [0.3, 1.5]
        
        Examples
        --------
        >>> calc = StepLength()
        >>> sl = calc.calculate(processed_data)
        >>> print(f"Step Length: {sl:.2f} m")
        """
        
        # 计算步频
        step_freq = self.step_frequency_calc.calculate(data_dict)
        
        # 如果没有提供速度，使用默认值
        if avg_velocity is None:
            # 默认假设以1.0 m/s的速度行走
            avg_velocity = 1.0
        
        # 使用速度方法计算
        step_length = self.calculate_velocity_based(step_freq, avg_velocity)
        
        logger.info(f"步幅: {step_length:.2f} m (步频: {step_freq:.2f}Hz, "
                   f"速度: {avg_velocity:.2f}m/s)")
        
        return step_length


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
    
    # 计算步幅
    calc = StepLength()
    sl = calc.calculate(data, avg_velocity=1.0)
    
    print(f"\n步幅: {sl:.2f} m")
    print(f"预期范围: {config.STEP_LENGTH_MIN_M:.2f} - {config.STEP_LENGTH_MAX_M:.2f} m")
