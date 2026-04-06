"""Signal Processing Pipeline - 运动生理学信号处理管道

主要模块：
- utils.dataloader: 多格式数据加载
- utils.preprocessing: 信号预处理（滤波、重采样）
- modules.step_frequency: 步频计算
- modules.step_length: 步幅计算
- modules.step_variability: 步态变异性
- modules.hr_mean: 平均心率和最大心率
- modules.hr_recovery: 心率恢复率
- modules.quality_anomaly: 质量评估和异常检测
"""

__version__ = "1.0.0"
__author__ = "Data Science Team"

from config import *
