# 运动生理学信号处理管道 (Signal Processing Pipeline)

**版本：** 1.0  
**创建日期：** 2026-04-05  
**项目名称：** 老年康复运动传感器数据分析  

---

## 📋 目录

1. [项目概述](#项目概述)
2. [数据来源](#数据来源)
3. [系统架构](#系统架构)
4. [数据格式规范](#数据格式规范)
5. [处理流程](#处理流程)
6. [指标计算方法](#指标计算方法)
7. [输出格式](#输出格式)
8. [使用指南](#使用指南)
9. [项目结构](#项目结构)
10. [参考文献](#参考文献)

---

## 🎯 项目概述

### 目标
从原始传感器数据（IMU、ECG）计算30秒时间窗口内的运动生理学指标，用于老年康复患者的步态和心率分析。

### 核心功能
- **IMU特征提取**：步频、步幅、步态变异性
- **心率特征提取**：平均心率、最大心率、心率恢复率
- **质量控制**：数据质量评分、异常检测标记
- **JSON输出**：符合标准schema的结构化输出

### 应用场景
- 老年患者康复评估
- 心脏手术后恢复监测
- 步态稳定性评估
- 虚弱（Frailty）风险识别

---

## 📊 数据来源

本项目支持两个主要的开源传感器数据集：

### 1. GSTRIDE 数据库 (Gait STRIDE Database)

**特点**
- 专注于**步态分析**（IMU足部传感）
- 163份受试者记录
- 老年人群体（与康复患者相关）

**传感器规范**
| 参数 | 值 |
|------|-----|
| 采样率 | 104 Hz - 128 Hz |
| 传感器位置 | 足部（前中足） |
| 轴数 | 6轴（3轴加速度 + 3轴陀螺仪） |
| 输出单位 | 加速度：arbitrary units（任意单位），陀螺仪：arbitrary units |
| 校准方式 | 设备特定的校准矩阵（per-device calibration） |

**数据格式**
```
V{ID}_{DeviceID}.txt（例：V001_0001.txt）

格式：6列空格分隔，无表头
acc_x  acc_y  acc_z  gyr_x  gyr_y  gyr_z
-32764 -29832 7632   -18    -47    -61
-32611 -29702 7591   -48    -37    -51
...
```

**目录结构**
```
GSTRIDE_database/
├── Test_recordings_raw/          # 原始数据文件
│   ├── V001_0001.txt
│   ├── V002_0001.txt
│   └── ...
├── Test_sensors_calibration_parameters/  # 设备校准矩阵
├── Database_register.csv         # 元数据：受试者信息、临床指标
└── README.txt
```

**校准数据**
- 位置：`Test_sensors_calibration_parameters/`
- 格式：MATLAB .mat 文件或ASCII矩阵
- 内容：每设备的偏差(bias)、缩放(scale)、交轴失准(cross-axis misalignment)矩阵

**官方输出参考**
- 目录：`Test_outputs_gait_analysis/`
- 文件：`V{ID}_metrics.txt`
- 包含：13项参数/步（Cadence、Speed、Stride Length等）

---

### 2. PhysioNet 可穿戴式虚弱患者数据集

**特点**
- 专注于**心脏康复**（ECG + 加速度计）
- 100+ 份记录（60-90位患者）
- 心脏手术后患者（高风险老年人群体）

**传感器规范**
| 参数 | ECG | ACC |
|------|-----|-----|
| 采样率 | 130 Hz | 200 Hz |
| 通道数 | 1 | 3 |
| 单位 | mV | g (重力加速度) |
| 分辨率 | 32-bit | 32-bit |

**数据格式 (WFDB)**
```
标准PhysioNet WFDB格式

文件组成：
- {record_name}.hea      # 头文件（元数据）
- {record_name}.dat      # 二进制或文本数据
- {record_name}.atr      # 标注文件（QRS标记、事件）

例：
  ptb-xl_00001.hea
  ptb-xl_00001.dat
  ptb-xl_00001.atr
```

**目录结构**
```
wearable-based-signals-during-physical-exercises-.../
├── ecg/                          # ECG数据
│   ├── {record}.hea
│   ├── {record}.dat
│   └── {record}.atr
├── acc/                          # 加速度数据
│   ├── {record}.hea
│   ├── {record}.dat
│   └── {record}.atr
├── subject-info.csv              # 元数据：年龄、性别、诊断、用药
└── test-availability.csv         # 测试类型标记（6MWT、TUG等）
```

**元数据**
```
subject-info.csv 包含列：
- subject_id
- age
- gender
- height
- weight
- BMI
- post_surgery_days
- NYHA_class
- medications
- comorbidities
- exercise_type
```

**时间标记**
- 标注文件 (.atr) 标记：
  - STAIR：上楼梯
  - 6MWT：6分钟步行测试
  - TUG：Timed Up and Go
  - VELO：骑行（veloergometry）
  - GAIT_ANALYSIS：步态分析

---

## 🏗️ 系统架构

```
                    Raw Sensor Data
                   /             \
            GSTRIDE (104-128Hz)    PhysioNet (130/200Hz)
            IMU: acc+gyr           ECG + ACC
                   |                   |
                   └───────┬───────────┘
                           |
                  ┌────────▼────────┐
                  │  DataLoader     │
                  │  (加载+校准)     │
                  │  (单位转换)      │
                  └────────┬────────┘
                           |
                  ┌────────▼────────┐
                  │ Preprocessing   │
                  │  (滤波)         │
                  │  (重采样→100Hz) │
                  │  (缺失值处理)   │
                  └────────┬────────┘
                           |
        ┌──────┬───────┬──┴────┬───────┬────────┬─────────┐
        |      |       |       |       |        |         |
        ▼      ▼       ▼       ▼       ▼        ▼         ▼
      Step   Step   Gait    HR     HR Max   HR Recov  Quality
      Freq   Length  Var.    Mean            Rate      Check
        |      |       |       |       |        |         |
        └──────┴───────┴───┬───┴───────┴────────┴────────┘
                           |
                  ┌────────▼────────┐
                  │ OutputFormatter │
                  │  (JSON输出)     │
                  └────────┬────────┘
                           |
                      output.json
```

---

## 📁 数据格式规范

### 3.1 输入数据格式

#### GSTRIDE 输入
```
输入文件：V{ID}_{DeviceID}.txt
格式：6列空格分隔

acc_x [arbitrary units]
acc_y [arbitrary units]
acc_z [arbitrary units]
gyr_x [arbitrary units]
gyr_y [arbitrary units]
gyr_z [arbitrary units]

例：
-32764 -29832 7632 -18 -47 -61
-32611 -29702 7591 -48 -37 -51
```

#### PhysioNet 输入
```
使用wfdb库读取
- ECG：130 Hz，单位mV
- ACC：200 Hz，单位g

需要将两个不同采样率的信号同步
```

#### CSV 输入（通用格式）
```
timestamp,acc_x,acc_y,acc_z,gyr_x,gyr_y,gyr_z[,ecg,...]
0.0,0.5,0.6,-9.8,0.01,0.02,0.03[,0.1,...]
0.01,0.51,0.61,-9.79,0.01,0.02,0.03[,0.12,...]
```

### 3.2 处理过程中的数据格式

#### 预处理后的数据
```python
# Python字典格式
data_dict = {
    'acc_x': np.array([...]),      # (N,) 100Hz采样
    'acc_y': np.array([...]),
    'acc_z': np.array([...]),
    'gyr_x': np.array([...]),
    'gyr_y': np.array([...]),
    'gyr_z': np.array([...]),
    'ecg': np.array([...]),        # 可选
    'timestamp': np.array([...]),  # 秒
    'sample_rate': 100,            # Hz
    'window_start_time': 0.0       # 秒
}
```

### 3.3 输出数据格式

#### JSON 输出
完整格式见 [输出格式](#输出格式) 章节

---

## 🔄 处理流程

### 高层流程图

```
┌─────────────────┐
│  1. 数据加载    │  DataLoader.load_gstride() / load_physionet()
│  获取原始数据   │
└────────┬────────┘
         │
┌────────▼────────┐
│  2. 校准转换    │  calibrate() 应用设备校准矩阵
│  单位 → SI      │  arbitrary units → m/s²
└────────┬────────┘
         │
┌────────▼────────┐
│  3. 预处理      │  low_pass_filter(3-5Hz)
│  滤波、重采样   │  resample(target_rate=100Hz)
│                 │  normalize_to_window()
└────────┬────────┘
         │
┌────────▼────────────────────────────────────┐
│  4. 指标计算 (30秒窗口)                     │
│                                             │
│  IMU 特征:                                  │
│  ├─ step_frequency.calculate()             │
│  ├─ step_length.calculate()                │
│  ├─ step_variability.calculate()           │
│                                             │
│  心率特征:                                  │
│  ├─ hr_mean.calculate()                    │
│  ├─ hr_max.calculate()                     │
│  ├─ hr_recovery.calculate()                │
│                                             │
│  质量检查:                                  │
│  └─ quality_anomaly.detect()               │
└────────┬────────────────────────────────────┘
         │
┌────────▼────────────┐
│  5. 异常标记        │  标记异常情况
│  质量打分          │  计算data_quality分数
└────────┬────────────┘
         │
┌────────▼────────────┐
│  6. 输出格式化      │  JSON schema验证
│  JSON输出          │  null处理（缺失模态）
└────────┬────────────┘
         │
         output.json
```

### 详细步骤

#### Step 1：数据加载 (DataLoader)
```python
# 示例代码位置：utils/dataloader.py

loader = DataLoader()

# 加载 GSTRIDE 数据
data = loader.load_gstride(
    filepath="V001_0001.txt",
    calibration_matrix_path="device_0001_calib.mat",
    device_id="0001"
)

# 或加载 PhysioNet 数据
data = loader.load_physionet(
    record_name="sub01_rec01",
    base_dir="./wearable_data/"
)

# 或加载 CSV 数据
data = loader.load_csv(
    filepath="sensor_data.csv",
    sample_rate=104
)
```

#### Step 2：数据预处理 (Preprocessing)
```python
# 示例代码位置：utils/preprocessing.py

from utils.preprocessing import SignalPreprocessor

processor = SignalPreprocessor(
    target_sample_rate=100,        # Hz
    filter_order=4,                # Butterworth阶数
    cutoff_freq=5                  # Hz
)

# 应用滤波和重采样
processed_data = processor.process(data, window_length=30)
```

---

## 📐 指标计算方法

### 5.1 IMU 特征

#### A. 步频 (step_frequency_hz)

**定义**  
每秒的步数（单位：Hz）

**计算公式**
```
step_frequency (Hz) = n_peaks / window_time (sec)
```

**算法步骤**
```
1. 计算加速度合向量
   acc_mag(t) = √(acc_x(t)² + acc_y(t)² + acc_z(t)²)

2. 应用低通滤波（Butterworth 4阶，3-5Hz）

3. 峰值检测
   peaks, _ = find_peaks(
       acc_filtered,
       distance=int(0.06 * fs),         # 最小峰间距 60ms
       height=std(acc_filtered)          # 峰值阈值
   )

4. 计算步频
   step_frequency_hz = len(peaks) / 30  # 假设30秒窗口
```

**代码位置：** `modules/step_frequency.py`

**参考范围**
- 老年人：1.2-2.0 Hz (72-120 steps/min)
- 运动员：1.8-2.5 Hz (108-150 steps/min)

---

#### B. 步幅 (step_length_m)

**定义**  
单个步骤的距离（单位：米）

**计算方法（优先级排序）**

**方案A：基于INS-ZUPT位移积分（推荐）**
```
使用陀螺仪和加速度积分估计位移

步骤：
1. 获取姿态（Mahony AHRS）
2. 对加速度进行重力补偿
3. 积分得速度，再积分得位移
4. ZUPT修正（足接地时速度=0）
5. 计算相邻步间的水平位移

step_length = ||position[t_{i+1}] - position[t_i]|| (水平)
```

**方案B：速度/频率估计**
```
step_length ≈ average_velocity / (2 × step_frequency)
```

**代码位置：** `modules/step_length.py`

**参考范围**
- 老年人：0.6-0.8 m
- 年轻人：0.7-1.0 m

---

#### C. 步态变异性 (step_time_variability_ms)

**定义**  
相邻步间间隔（ISI）的标准差，反映步态节律的规律性

**计算公式**
$$\text{ISI Std Dev} = \sqrt{\frac{\sum_{i=1}^{n-1}(ISI_i - \overline{ISI})^2}{n-2}}$$

其中：
- $ISI_i = t_{i+1} - t_i$ （相邻两步时间间隔，秒）
- 转换为毫秒单位
- $\overline{ISI}$ 为 ISI 平均值
- $n$ 为检测到的步峰值总数

**算法步骤**
```
1. 从峰值检测获得步事件时间戳
   peaks_times = [t_1, t_2, t_3, ..., t_n]

2. 计算 ISI（毫秒）
   isi_ms = diff(peaks_times) × 1000

3. 计算标准差
   variability_ms = std(isi_ms, ddof=1)

4. 计算变异系数（可选）
   cv = variability_ms / mean(isi_ms) × 100%
   
   异常阈值：CV > 40% 或 std > 80ms
```

**代码位置：** `modules/step_variability.py`

**异常阈值**
- 正常：< 30 ms
- 中等变异：30-80 ms
- 异常：> 80 ms（标记为"irregular_step_rhythm"）

**临床意义**
- 帕金森病、前庭功能障碍特征
- 跌倒风险评估重要指标

---

### 5.2 心率特征

#### A. 平均心率 (hr_mean_bpm)

**定义**  
30秒窗口内的平均心率（单位：bpm）

**计算公式**
```
方法1（直接）：
  HR_mean = mean([60/RR_i for i in 1..n])

方法2（从RR平均）：
  HR_mean = 60 / mean(RR_intervals)
```

**算法步骤**
```
1. ECG QRS 检测
   - 带通滤波：5-40 Hz
   - 自适应峰值检测
   - 返回 QRS 时间戳：qrs_times[]

2. 计算 RR 间隔
   rr_intervals = diff(qrs_times)  # 秒

3. 转换为心率
   hr_instant = 60 / rr_intervals  # bpm

4. 取平均
   hr_mean_bpm = mean(hr_instant)
```

**代码位置：** `modules/hr_mean.py`

**参考范围**
- 静息：60-100 bpm
- 运动：120-200 bpm

---

#### B. 最大心率 (hr_max_bpm)

**定义**  
30秒窗口内的最高瞬时心率（单位：bpm）

**计算公式**
```
HR_max = max(60 / RR_intervals)
       = 60 / min(RR_intervals)
```

**代码位置：** `modules/hr_max.py`

---

#### C. 心率恢复率 (hr_recovery_bpm_per_min)

**定义**  
运动结束后心率下降的速率（单位：bpm/min）

**计算公式**
$$\text{HRR} = \frac{HR_{exercise\_end} - HR_{60s\_recovery}}{60\text{ seconds}} \times 60$$

$$= HR_{exercise\_end} - HR_{60s\_recovery} \quad \text{(bpm/min)}$$

**算法步骤**
```
1. 识别运动结束时刻 t_end
   - 从 metadata: trigger_event
   - 或自动：检测 HR 下降 > 15 bpm

2. 获取运动末期心率
   hr_end = mean(HR[t_end-5s : t_end])

3. 提取恢复窗口 [t_end, t_end+60s]

4. 获取恢复60秒时的心率
   hr_60s = mean(HR[t_end+55s : t_end+60s])

5. 计算恢复率
   HRR = (hr_end - hr_60s) / 1分钟
```

**代码位置：** `modules/hr_recovery.py`

**异常阈值**
- 良好恢复：> 12 bpm/min（异常标记触发：≤ 3 bpm/min）
- 临床意义：自主神经功能评估

---

### 5.3 质量与异常检测

#### A. 数据质量评分

**范围：** [0, 1]

**计算方法**
```
IMU 质量：
  SNR_imu = Power(signal) / Power(noise)
  quality_imu = min(1.0, SNR_imu / 5.0) × (1 - penalty)
  penalty = min(0.5, n_anomalies × 0.15)

ECG 质量：
  quality_ecg = qrs_detection_rate
  quality_ecg = quality_ecg × (1 - penalty)
  penalty = min(0.3, n_anomalies × 0.10)

综合：
  data_quality = (quality_imu + quality_ecg) / 2
```

**评级标准**
| 分数范围 | 评级 |
|--------|------|
| 0.9-1.0 | 优秀 (Excellent) |
| 0.7-0.9 | 良好 (Good) |
| 0.6-0.7 | 可接受 (Acceptable) |
| <0.6 | 不可接受 (Poor) → 标记"data_quality_low" |

#### B. 异常标记

| 标记 | 触发条件 | 严重程度 |
|------|--------|--------|
| `"irregular_step_rhythm"` | ISI CV > 40% 或 std > 80ms | 中/重 |
| `"sensor_dropout"` | acc_mag < 5 m/s² 持续 > 5s | 重 |
| `"prolonged_stillness"` | std(acc) < 0.1 m/s² 持续 > 3s | 中 |
| `"poor_qrs_detection"` | QRS 检测失败率 > 10% | 重 |
| `"invalid_heart_rate"` | HR < 30 或 HR > 200 bpm | 重 |
| `"abnormal_recovery"` | HRR < 1 bpm/min | 中 |

**代码位置：** `modules/quality_anomaly.py`

---

## 📤 输出格式

### 6.1 JSON 输出架构

```json
{
  "metadata": {
    "session_id": "string",           // 会话ID
    "player_id": "string",            // 受试者ID
    "timestamp": "ISO8601",           // UTC时间戳
    "window_sec": 30,                 // 窗口大小
    "trigger_event": "string"         // 事件标记
  },
  "imu": {
    "features": {
      "step_frequency_hz": float,
      "step_length_m": float,
      "step_time_variability_ms": float
    },
    "anomaly_flags": [array],         // 异常标记列表
    "data_quality": float,            // [0, 1]
    "quality_reason": "string"        // 质量说明
  },
  "heart_rate": {
    "features": {
      "hr_mean_bpm": float,
      "hr_max_bpm": float,
      "hr_recovery_bpm_per_min": float
    },
    "anomaly_flags": [array],
    "data_quality": float,
    "quality_reason": "string"
  }
}
```

### 6.2 输出示例

见 `/memories/repo/json_specification.md` 中的4个详细示例

---

## 🚀 使用指南

### 7.1 安装依赖

```bash
cd signal_processing_pipeline
pip install -r requirements.txt
```

**必需包：**
```
numpy>=1.20
scipy>=1.6
pandas>=1.2
scikit-signal>=0.17
wfdb>=3.4
matplotlib>=3.3
```

### 7.2 基本使用

```python
from utils.dataloader import DataLoader
from utils.preprocessing import SignalPreprocessor
from modules.step_frequency import StepFrequency
from modules.hr_mean import HRMean
from modules.quality_anomaly import QualityChecker
from utils.output_formatter import OutputFormatter

# 1. 加载数据
loader = DataLoader()
data = loader.load_gstride("V001_0001.txt")

# 2. 预处理
processor = SignalPreprocessor(target_sample_rate=100)
processed = processor.process(data, window_length=30)

# 3. 计算指标
step_freq = StepFrequency()
sf_hz = step_freq.calculate(processed)

hr_mean = HRMean()
hr_mean_bpm = hr_mean.calculate(processed)

# 4. 质量检查
checker = QualityChecker()
quality_data = checker.check(processed)

# 5. 输出
formatter = OutputFormatter()
output_json = formatter.format(
    metadata={...},
    imu_features={...},
    heart_rate_features={...},
    quality_data={...}
)

print(output_json)
```

### 7.3 批处理

```python
import glob
from pathlib import Path

# 处理所有 GSTRIDE 文件
for filepath in glob.glob("GSTRIDE_database/Test_recordings_raw/V*.txt"):
    # 加载→预处理→计算→输出
    result = process_file(filepath)
    save_output(result, filepath)
```

---

## 📂 项目结构

```
signal_processing_pipeline/
├── README.md                           # 本文件
├── requirements.txt                    # 依赖包
├── config.py                           # 全局配置
│
├── utils/
│   ├── __init__.py
│   ├── dataloader.py                   # 数据加载（GSTRIDE、PhysioNet、CSV）
│   ├── preprocessing.py                # 预处理（滤波、重采样、归一化）
│   ├── output_formatter.py             # JSON输出格式化
│   └── helpers.py                      # 辅助函数（单位转换等）
│
├── modules/
│   ├── __init__.py
│   ├── step_frequency.py               # 步频计算
│   ├── step_length.py                  # 步幅计算
│   ├── step_variability.py             # 步态变异性计算
│   ├── hr_mean.py                      # 平均心率
│   ├── hr_max.py                       # 最大心率
│   ├── hr_recovery.py                  # 心率恢复率
│   └── quality_anomaly.py              # 质量与异常检测
│
├── tests/
│   ├── __init__.py
│   ├── test_step_frequency.py          # 单元测试
│   ├── test_hr_mean.py
│   └── test_integration.py             # 集成测试
│
└── data/
    ├── sample_gstride_v001.txt         # 示例数据
    └── sample_physionet_ecg.edf        # 示例数据
```

---

## 📚 参考文献

### 主要参考资源

1. **GSTRIDE 数据库**
   - 数据来源：Gait Step Analysis Database
   - 特点：老年人步态，104-128Hz IMU采样
   - 用途：步频、步幅、步态参数验证

2. **PhysioNet 可穿戴式虚弱患者数据**
   - 数据来源：PhysioNet Wearable-based signals
   - 特点：心脏康复患者，ECG 130Hz + ACC 200Hz
   - 用途：心率、恢复率验证

3. **生物信号处理标准**
   - Butterworth 低通滤波：频率截止 3-5 Hz（去除高频噪声）
   - QRS 检测：Pan-Tompkins 算法或现代深度学习方法
   - 心率恢复：60秒恢复窗口标准（临床指南）

4. **指标计算参考**
   - ISI 变异性：Cohen et al., 步态节律分析
   - 心率恢复率：Cole et al., 自主神经功能评估
   - 步态参数：Perry & Burnfield, 步态分析正常异常

### 学术论文

- *Gait variability and fall risk in an ambulatory elderly population*, Hausdorff et al.
- *Heart rate recovery as a predictor of mortality*, Cole et al.
- *Wearable Sensors for Remote Health Monitoring*, Steinhubl et al.

### 在线资源

- GSTRIDE 官方文档：详见 `GSTRIDE_database/README.txt`
- PhysioNet 说明：https://www.physionet.org/
- scipy.signal 文档：https://docs.scipy.org/doc/scipy/reference/signal.html

---

## 📝 版本历史

| 版本 | 日期 | 描述 |
|------|------|------|
| 1.0 | 2026-04-05 | 初始版本：6个指标模块、完整预处理管道 |

---

## ✅ 质量控制检查清单

开发时使用此清单验证：

- [ ] **数据加载** - 支持 GSTRIDE、PhysioNet、CSV 格式
- [ ] **预处理** - 滤波、重采样至 100Hz、缺失值处理
- [ ] **步频** - 峰值检测与 GSTRIDE 官方数据误差 < 2%
- [ ] **步幅** - 使用 INS-ZUPT 或速度估计，范围 0.5-1.2m
- [ ] **步态变异性** - ISI 标准差计算，异常阈值 > 80ms
- [ ] **QRS 检测** - 灵敏度 > 95%（MIT-BIH 标准数据）
- [ ] **心率指标** - 三个指标计算准确
- [ ] **心率恢复** - 60秒窗口计算，异常阈值 < 1 bpm/min
- [ ] **异常标记** - 6种异常条件逻辑实装
- [ ] **数据质量** - 评分 0-1，质量原因匹配分数区间
- [ ] **JSON输出** - Schema 验证通过，null 处理正确
- [ ] **单元测试** - 覆盖率 > 80%
- [ ] **文档完整** - README 和代码注释齐全

---

**联系信息** | 问题反馈：见项目 Issues  
**许可证** | MIT  
**维护者** | 数据科学团队
