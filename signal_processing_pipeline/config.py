"""
全局配置文件 - Signal Processing Pipeline

包含所有常数、阈值、参数配置
"""

import numpy as np

# ============================================================
# 采样率与时间配置
# ============================================================

# 内部处理标准采样率（Hz）
TARGET_SAMPLE_RATE = 100

# 数据来源的原始采样率
GSTRIDE_SAMPLE_RATE = 104  # 或 128，设备特定
PHYSIONET_ECG_SAMPLE_RATE = 130
PHYSIONET_ACC_SAMPLE_RATE = 200

# 时间窗口
WINDOW_LENGTH_SEC = 30
HR_RECOVERY_WINDOW_SEC = 60

# ============================================================
# 滤波参数
# ============================================================

# Butterworth 低通滤波参数
FILTER_ORDER = 4
CUTOFF_FREQ = 5  # Hz (范围 3-5)
BUTTERWORTH_TYPE = 'low'

# ECG 带通滤波参数
ECG_BANDPASS_LOW = 5  # Hz
ECG_BANDPASS_HIGH = 40  # Hz

# ============================================================
# 步频检测参数
# ============================================================

# 峰值检测最小间距（秒）
MIN_PEAK_DISTANCE_SEC = 0.06  # 60ms，对应最大 ~16.7 Hz

# 峰值高度阈值倍数（相对于信号标准差）
PEAK_HEIGHT_MULTIPLIER = 1.0

# 步频范围（Hz）
STEP_FREQUENCY_MIN_HZ = 1.0
STEP_FREQUENCY_MAX_HZ = 3.0

# ============================================================
# 步幅范围
# ============================================================

STEP_LENGTH_MIN_M = 0.3
STEP_LENGTH_MAX_M = 1.5

# ============================================================
# 步态变异性参数
# ============================================================

# ISI 变异系数异常阈值（%）
ISI_CV_ANOMALY_THRESHOLD = 40.0

# ISI 标准差异常阈值（ms）
ISI_STD_ANOMALY_THRESHOLD = 80.0

# ============================================================
# 心率参数
# ============================================================

# 心率范围（bpm）
HR_MIN_BPM = 30
HR_MAX_BPM = 200

# 正常心率范围
HR_RESTING_MIN = 60
HR_RESTING_MAX = 100
HR_EXERCISE_MIN = 100
HR_EXERCISE_MAX = 200

# 心率恢复异常阈值（bpm/min）
HRR_ANOMALY_THRESHOLD = 1.0

# 良好恢复阈值（bpm/min）
HRR_GOOD_THRESHOLD = 12.0

# ============================================================
# 异常检测阈值
# ============================================================

# IMU 异常
ACC_MAG_DROPOUT_THRESHOLD = 5.0  # m/s²
DROPOUT_DURATION_THRESHOLD_SEC = 5.0  # 秒

ACC_STILLNESS_THRESHOLD = 0.1  # m/s²
STILLNESS_DURATION_THRESHOLD_SEC = 3.0  # 秒

# ECG 异常
QRS_DETECTION_FAILURE_RATE = 0.10  # 10%

# ============================================================
# 质量评分参数
# ============================================================

# SNR 基准
SNR_REFERENCE = 5.0

# 异常惩罚系数
IMU_ANOMALY_PENALTY_PER_ITEM = 0.15  # 每项异常penalty 15%
IMU_MAX_PENALTY = 0.5

ECG_ANOMALY_PENALTY_PER_ITEM = 0.10  # 每项异常penalty 10%
ECG_MAX_PENALTY = 0.3

# 质量评分阈值
QUALITY_EXCELLENT = 0.9
QUALITY_GOOD = 0.7
QUALITY_ACCEPTABLE = 0.6
QUALITY_POOR = 0.0

# ============================================================
# 单位转换常数
# ============================================================

# 加速度单位转换
G_TO_MS2 = 9.81  # 1g = 9.81 m/s²

# 时间转换
MS_TO_SEC = 0.001
SEC_TO_MIN = 60.0
MS_TO_MIN = SEC_TO_MIN / 1000.0

# ============================================================
# 数据来源特定的校准参数
# ============================================================

# GSTRIDE 设备字典
GSTRIDE_DEVICES = {
    "0001": {
        "sample_rate": 104,
        "location": "foot",
        "manufacturer": "CSIC",
    },
    "0185": {
        "sample_rate": 128,
        "location": "foot",
        "manufacturer": "Gaitup",
    }
}

# PhysioNet 传感器参数
PHYSIONET_ECG_CHANNELS = 1
PHYSIONET_ACC_CHANNELS = 3

# ============================================================
# 输出格式常数
# ============================================================

# JSON 和异常标记
ANOMALY_FLAGS_IMU = [
    "irregular_step_rhythm",
    "sensor_dropout",
    "prolonged_stillness",
]

ANOMALY_FLAGS_HR = [
    "poor_qrs_detection",
    "invalid_heart_rate",
    "abnormal_recovery",
]

# 质量原因列表
QUALITY_REASONS = [
    "clean_signal",
    "minor_noise",
    "moderate_artifacts",
    "significant_dropout",
    "data_quality_low",
]

# ============================================================
# 日志与调试配置
# ============================================================

DEBUG_MODE = False
VERBOSE_LOGGING = True
SAVE_INTERMEDIATE_RESULTS = False

# ============================================================
# 数据路径配置
# ============================================================

# 外挂硬盘基础路径
EXTERNAL_DRIVE_PATH = "/Volumes/ChouSSD/elder_datasets"

# GSTRIDE 数据库路径
GSTRIDE_DATA_DIR = f"{EXTERNAL_DRIVE_PATH}/GSTRIDE_database/Test_recordings_raw"
GSTRIDE_CALIB_DIR = f"{EXTERNAL_DRIVE_PATH}/GSTRIDE_database/Test_sensors_calibration_parameters"
GSTRIDE_OUTPUT_DIR = "./output/gstride"

# PhysioNet 可穿戴设备数据路径
PHYSIONET_DATA_DIR = f"{EXTERNAL_DRIVE_PATH}/PhysioNet_Wearable_Frailty"
PHYSIONET_OUTPUT_DIR = "./output/physionet"

# DLNN Framework 数据路径
DLNN_DATA_DIR = f"{EXTERNAL_DRIVE_PATH}/DLNN_Framework_Data"

# DUO-GAIT 数据集路径
DUO_GAIT_DATA_DIR = f"{EXTERNAL_DRIVE_PATH}/DUO-GAIT"
DUO_GAIT_RAW_DIR = f"{DUO_GAIT_DATA_DIR}/raw"
DUO_GAIT_ST_DIR = f"{DUO_GAIT_RAW_DIR}/OG_st_raw"  # Single Task
DUO_GAIT_DT_DIR = f"{DUO_GAIT_RAW_DIR}/OG_dt_raw"  # Dual Task
DUO_GAIT_INTERIM_DIR = f"{DUO_GAIT_DATA_DIR}/interim"
DUO_GAIT_PROCESSED_DIR = f"{DUO_GAIT_DATA_DIR}/processed"

# 本地输出和测试数据
TEST_DATA_DIR = "./data"
OUTPUT_DIR = "./output"

# ============================================================
# 扩展参数 (可选)
# ============================================================

# QRS 检测方法
QRS_DETECTION_METHOD = "neurokit2"  # or "pan_tompkins"

# 步长计算方法
STRIDE_LENGTH_METHOD = "ins_zupt"  # or "velocity_based"

# 是否启用缓存
ENABLE_CACHING = True
CACHE_DIR = "./.cache"
