"""
最大心率和心率恢复率模块

从 hr_mean.py 重新导出，以便独立使用
"""

from modules.hr_mean import HRMax, HRRecovery
import logging

logger = logging.getLogger(__name__)


# 别名
MaxHeartRate = HRMax
HeartRateRecovery = HRRecovery


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 示例使用
    print("请参考 hr_mean.py 中的 HRMax 和 HRRecovery 类")
