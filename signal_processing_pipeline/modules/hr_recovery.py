"""
心率恢复率计算模块 (独立接口)
"""

from modules.hr_mean import HRRecovery
import logging

logger = logging.getLogger(__name__)


# 别名
HeartRateRecovery = HRRecovery


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 示例使用
    print("请参考 hr_mean.py 中的 HRRecovery 类")
