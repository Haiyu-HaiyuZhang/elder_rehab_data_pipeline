"""
快速开始指南 - Quick Start Guide

项目结构和核心模块概览
"""

# ============================================================
# 项目结构
# ============================================================

PROJECT_STRUCTURE = """
signal_processing_pipeline/
├── README.md                           # 完整文档
├── config.py                           # 全局配置
├── process_pipeline.py                 # 完整处理管道示例
├── requirements.txt                    # 依赖包
│
├── utils/
│   ├── __init__.py
│   ├── dataloader.py                   # 多格式数据加载（GSTRIDE、PhysioNet、CSV）
│   ├── preprocessing.py                # 信号预处理（滤波、重采样）
│   └── output_formatter.py            # JSON 输出格式化
│
├── modules/
│   ├── __init__.py
│   ├── step_frequency.py               # 步频 = 峰值数 / 窗口时间
│   ├── step_length.py                  # 步幅 = 平均速度 / (2×步频)
│   ├── step_variability.py             # 步态变异性 = std(ISI)
│   ├── hr_mean.py                      # 心率：平均值、最大值、恢复率
│   ├── hr_max.py                       # （别名到 hr_mean.py）
│   ├── hr_recovery.py                  # （别名到 hr_mean.py）
│   └── quality_anomaly.py              # 质量评估和6种异常检测
│
├── tests/
│   ├── test_step_frequency.py
│   ├── test_hr_mean.py
│   └── test_integration.py
│
└── data/
    ├── sample_gstride_v001.txt        # 示例数据
    └── sample_physionet_ecg.edf       # 示例数据
"""

# ============================================================
# 核心算法速查
# ============================================================

ALGORITHMS = """
┌─────────────────────────────────────────────────────────────────┐
│ 指标 1：步频 (step_frequency_hz)                               │
├─────────────────────────────────────────────────────────────────┤
│ 输入：  acc_x, acc_y, acc_z（100Hz，30秒）                    │
│ 算法：  │                                                       │
│         1. 计算合向量：acc_mag = sqrt(x²+y²+z²)                │
│         2. 低通滤波（5Hz）                                      │
│         3. 峰值检测（距离≥60ms）                                │
│         4. 步频 = 峰值数 / 30秒                                 │
│ 输出：  1.0-3.0 Hz                                              │
│ 代码：  modules/step_frequency.py                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 指标 2：步幅 (step_length_m)                                    │
├─────────────────────────────────────────────────────────────────┤
│ 输入：  步频 Hz，估计速度（default 1.0 m/s）                   │
│ 算法：  步幅 ≈ 速度 / (2 × 步频)                               │
│ 输出：  0.3-1.5 m                                               │
│ 代码：  modules/step_length.py                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 指标 3：步态变异性 (step_time_variability_ms)                   │
├─────────────────────────────────────────────────────────────────┤
│ 输入：  步峰值时间戳                                            │
│ 算法：  │                                                       │
│         1. ISI = 相邻峰值时间差（秒）× 1000（ms）              │
│         2. 变异性 = std(ISI)，自由度 = n-1                     │
│         3. 异常阈值：> 80ms 或 CV > 40%                         │
│ 输出：  10-100 ms（>80ms 异常）                                │
│ 代码：  modules/step_variability.py                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 指标 4-6：心率 (hr_mean_bpm, hr_max_bpm, hr_recovery_bpm/min) │
├─────────────────────────────────────────────────────────────────┤
│ 输入：  ECG 信号（130Hz，30秒）                                │
│ 算法：  │                                                       │
│         1. QRS 检测 → 心跳时间戳                                │
│         2. RR间隔 = 相邻心跳时间差（秒）                       │
│         3. HR_instant = 60 / RR_interval (bpm)                  │
│         4. hr_mean = mean(HR_instant)                           │
│         5. hr_max = max(HR_instant)                             │
│         6. hr_recovery = HR_end - HR_60s_after（bpm/min）      │
│ 输出：  30-200 bpm (HR)，0-40 bpm/min (恢复率)                 │
│ 代码：  modules/hr_mean.py                                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 质量和异常                                                      │
├─────────────────────────────────────────────────────────────────┤
│ IMU 异常（3种）：                                               │
│   - irregular_step_rhythm ：CV > 40% 或 std > 80ms              │
│   - sensor_dropout：acc < 5 m/s² 持续 > 5s                     │
│   - prolonged_stillness：std(acc) < 0.1 m/s² 持续 > 3s         │
│                                                                 │
│ 心率异常（3种）：                                               │
│   - poor_qrs_detection：QRS 检测失败率 > 10%                    │
│   - invalid_heart_rate：HR < 30 或 > 200 bpm                    │
│   - abnormal_recovery：HRR < 1 bpm/min                          │
│                                                                 │
│ 质量评分：                                                      │
│   - 0.9-1.0：优秀 → "clean_signal"                              │
│   - 0.7-0.9：良好 → "minor_noise"                               │
│   - 0.6-0.7：可接受 → "moderate_artifacts"                     │
│   - <0.6：不可接受 → "data_quality_low"                        │
│                                                                 │
│ 代码：  modules/quality_anomaly.py                             │
└─────────────────────────────────────────────────────────────────┘
"""

# ============================================================
# 快速使用示例
# ============================================================

QUICK_START = """
# 1. 安装依赖
pip install -r requirements.txt

# 2. 加载数据
from utils.dataloader import DataLoader

loader = DataLoader()

# GSTRIDE 数据
data = loader.load_gstride('GSTRIDE_database/Test_recordings_raw/V001_0001.txt')

# 或 CSV 数据
data = loader.load_csv('sensor_data.csv', sample_rate=104)

# 3. 预处理
from utils.preprocessing import SignalPreprocessor

processor = SignalPreprocessor()
processed = processor.process(data, window_length=30)

# 4. 计算指标
from modules.step_frequency import StepFrequency
from modules.step_variability import StepVariability
from modules.hr_mean import HRMean, HRRecovery

sf_calc = StepFrequency()
sf = sf_calc.calculate(processed)

var_calc = StepVariability()
var = var_calc.calculate(processed)

hr_calc = HRMean()
hr_mean = hr_calc.calculate(processed)

# 5. 质量检查和异常检测
from modules.quality_anomaly import QualityChecker, AnomalyDetector

qc = QualityChecker()
quality = qc.calculate_overall_quality(processed)

ad = AnomalyDetector()
anomalies = ad.detect_all_anomalies(processed, hr_mean=hr_mean)

# 6. 输出 JSON
import json

output = {
    'metadata': {...},
    'imu': {'features': {...}, 'anomaly_flags': [...], ...},
    'heart_rate': {'features': {...}, 'anomaly_flags': [...], ...}
}

print(json.dumps(output, indent=2))
"""

# ============================================================
# 数据来源配置
# ============================================================

DATA_SOURCES = """
GSTRIDE 数据库：
  位置：../GSTRIDE_database/Test_recordings_raw/
  格式：V{ID}_{DeviceID}.txt（6列空格分隔）
  采样率：104-128 Hz
  列：acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z
  官方参考输出：../GSTRIDE_database/Test_outputs_gait_analysis/

PhysioNet 可穿戴式虚弱患者：
  位置：../wearable-based-signals-.../
  格式：WFDB（.hea, .dat, .atr）
  子目录：ecg/, acc/
  采样率：ECG 130Hz，ACC 200Hz
  使用库：import wfdb

CSV 格式（通用）：
  列：timestamp, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z[, ecg, ...]
  采样率：需指定或从 timestamp 推断
"""

# ============================================================
# 关键参数
# ============================================================

KEY_PARAMETERS = """
为了微调处理，修改 config.py 中的参数：

滤波器：
  - FILTER_ORDER = 4              # Butterworth 阶数
  - CUTOFF_FREQ = 5              # 低通截止频率（Hz）
  - ECG_BANDPASS_LOW = 5         # ECG 带通下限（Hz）
  - ECG_BANDPASS_HIGH = 40       # ECG 带通上限（Hz）

步频：
  - MIN_PEAK_DISTANCE_SEC = 0.06 # 峰值最小间距（秒）
  - PEAK_HEIGHT_MULTIPLIER = 1.0 # 峰值高度阈值倍数

异常阈值：
  - ISI_CV_ANOMALY_THRESHOLD = 40.0           # 变异系数（%）
  - ISI_STD_ANOMALY_THRESHOLD = 80.0          # 标准差（ms）
  - HRR_ANOMALY_THRESHOLD = 1.0               # 恢复率（bpm/min）

质量评分：
  - QUALITY_EXCELLENT = 0.9
  - QUALITY_GOOD = 0.7
  - QUALITY_ACCEPTABLE = 0.6
"""

# ============================================================
# 主要导入
# ============================================================

MAIN_IMPORTS = """
# 数据处理
from utils.dataloader import DataLoader
from utils.preprocessing import SignalPreprocessor

# 指标计算
from modules.step_frequency import StepFrequency
from modules.step_length import StepLength
from modules.step_variability import StepVariability
from modules.hr_mean import HRMean, HRMax, HRRecovery

# 质量控制
from modules.quality_anomaly import QualityChecker, AnomalyDetector

# 完整管道
from process_pipeline import ProcessingPipeline
"""

if __name__ == "__main__":
    print("=" * 70)
    print("运动生理学信号处理管道 - 快速参考")
    print("=" * 70)
    
    print("\n📁 项目结构:")
    print(PROJECT_STRUCTURE)
    
    print("\n🔬 核心算法:")
    print(ALGORITHMS)
    
    print("\n⚡ 快速开始:")
    print(QUICK_START)
    
    print("\n📊 数据来源:")
    print(DATA_SOURCES)
    
    print("\n⚙️ 关键参数:")
    print(KEY_PARAMETERS)
    
    print("\n📦 主要导入:")
    print(MAIN_IMPORTS)
    
    print("\n" + "=" * 70)
    print("详见 README.md 获取完整文档")
    print("=" * 70)
