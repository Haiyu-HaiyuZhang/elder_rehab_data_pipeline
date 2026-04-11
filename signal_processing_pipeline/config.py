"""
全局配置文件 - Signal Processing Pipeline for DUO-GAIT

包含采样率、窗口、步态检测参数
"""

import numpy as np

# ============================================================
# 采样率与时间窗口配置
# ============================================================

# DUO-GAIT IMU 原始采样率（Hz）
DUO_GAIT_SAMPLE_RATE = 128

# 心率采样率（Hz）
HEART_RATE_SAMPLE_RATE = 1

# 分析窗口配置
WINDOW_LENGTH_SEC = 30          # 滑动窗口大小（秒）
SLIDING_WINDOW_STRIDE_SEC = 30  # 滑动步长（秒），非重叠设置为等于 WINDOW_LENGTH_SEC


# ============================================================
# 步频检测参数
# ============================================================

# 峰值检测最小间距（秒）
# 原值 0.06 (对应最大 ~16.7 Hz) 导致误检过多
# 改为 0.4s (对应最大 2.5 Hz)，更符合步态周期
MIN_PEAK_DISTANCE_SEC = 0.4

# 峰值高度阈值倍数（相对于信号标准差）
# 原值 1.0 太灵敏，导致检测噪声波动
# 改为 2.0-2.5 以减少误检，保留真实脚步
PEAK_HEIGHT_MULTIPLIER = 2.5

# 步频范围（Hz）
# 原值 0.5-3.0 过宽且上限过高
# 改为 0.8-2.5，符合老年人和健康人的实际步频范围
STEP_FREQUENCY_MIN_HZ = 0.8
STEP_FREQUENCY_MAX_HZ = 2.5

# ============================================================
# 步幅范围（米）
# ============================================================

STEP_LENGTH_MIN_M = 0.2
STEP_LENGTH_MAX_M = 1.5

# ============================================================
# 步态变异性参数
# ============================================================

# ISI 变异系数异常阈值（%）
ISI_CV_ANOMALY_THRESHOLD = 40.0

# ISI 标准差异常阈值（ms）
ISI_STD_ANOMALY_THRESHOLD = 80.0

# ============================================================
# 心率参数（bpm）
# ============================================================

HR_MIN_BPM = 30
HR_MAX_BPM = 200

# ============================================================
# 单位转换常数
# ============================================================

# 加速度单位：1g = 9.81 m/s²
G_TO_MS2 = 9.81

# ============================================================
# 数据路径配置
# ============================================================

# 外挂硬盘基础路径
EXTERNAL_DRIVE_PATH = "/Volumes/ChouSSD/elder_datasets"

# DUO-GAIT 数据集路径
DUO_GAIT_DATA_DIR = f"{EXTERNAL_DRIVE_PATH}/DUO-GAIT"
DUO_GAIT_RAW_DIR = f"{DUO_GAIT_DATA_DIR}/raw"
DUO_GAIT_ST_DIR = f"{DUO_GAIT_RAW_DIR}/OG_st_raw"      # Single Task
DUO_GAIT_DT_DIR = f"{DUO_GAIT_RAW_DIR}/OG_dt_raw"      # Dual Task
DUO_GAIT_SUBJECT_INFO = f"{DUO_GAIT_RAW_DIR}/subject_info.csv"

# 本地输出目录
OUTPUT_DIR = "./output"
