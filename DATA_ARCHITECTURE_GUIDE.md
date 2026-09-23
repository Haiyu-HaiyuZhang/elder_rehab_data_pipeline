# DUO-GAIT 数据处理架构文档

## 📊 数据结构概览

DUO-GAIT 数据集由三个关键层次组成，形成从原始数据→切分数据→处理结果的处理流程：

```
┌─────────────────────────────────────────────────────────────┐
│                    项目数据架构 (Data Pipeline)              │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  【RAW 层】连续录制原始数据                                    │
│  ├─ /Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/            │
│  ├─ OG_st_raw/         【单任务原始数据，按受试者组织】         │
│  ├─ OG_dt_raw/         【双任务原始数据，按受试者组织】         │
│  ├─ subject_info.csv   【元数据：年龄、性别、测试指标】        │
│  └─ IPAQ.csv           【国际体力活动量表】                   │
│                                                               │
│  KEY: 包含完整连续的运动录制                                  │
│       heart_rate.CSV 需手动定位（Visit A/B）               │
│       每个受试者的 CSV≈36MB                                 │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  【INTERIM 层】手动切分的 6 分钟片段                          │
│  ├─ /Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/        │
│  ├─ OG_st_control/     【单任务-控制阶段】                   │
│  ├─ OG_st_fatigue/     【单任务-疲劳阶段】                   │
│  ├─ OG_st_sit_to_stand/【单任务-起坐测试】                   │
│  ├─ OG_st_all/         【单任务-完整】                       │
│  ├─ OG_dt_control/     【双任务-控制阶段】                   │
│  ├─ OG_dt_fatigue/     【双任务-疲劳阶段】                   │
│  ├─ OG_dt_sit_to_stand/【双任务-起坐测试】                   │
│  └─ OG_dt_all/         【双任务-完整】                       │
│                                                               │
│  KEY: 每个文件已手动切割为恰好 6 分钟                         │
│       采样率 128 Hz → 每个 CSV ≈ 48,500 行                  │
│       CSV 行数与时间的精确对应关系可用于定位 raw 中的 HR 区间 │
│       每个受试者的 CSV ≈ 4MB                                │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  【PROCESSED 层】已计算的步态参数与指标                        │
│  ├─ /Volumes/ChouSSD/elder_datasets/DUO-GAIT/processed/      │
│  ├─ OG_st_control/, OG_st_fatigue/, OG_dt_*/ 等             │
│  └─ 每个受试者目录包含：                                     │
│      ├─ aggregate_params.csv     【全局汇总参数】            │
│      ├─ left_foot_core_params.csv【左脚逐步参数】            │
│      └─ right_foot_core_params.csv【右脚逐步参数】           │
│                                                               │
│  KEY: 作为验证基准(Validation Baseline)                     │
│       包含多项指标如步幅、步时、姿态比、节奏、速度及其CV      │
│       用 Python 算法的输出与之对比验证准确性                │
│       主流程 JSON **不读取**本层；仅 validate_duogait_metrics 等离线可选用 │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 数据处理流程

### 1️⃣ **从 RAW 提取数据**

#### 步骤 1.1：定位 Heart Rate 时间戳

**问题**：Raw 数据是连续录制的，可能跨越多个 Visit（A/B），需要找到实验对应的片段。

**解决方案**：

```python
# 伪代码
1. 读取 subject_info.csv 获取实验相关信息
   - visit 信息（如果可用）
   - HR baseline 和 HR fatigue 值（参考值）

2. 读取 raw/OG_st_raw/sub_XX/heart_rate.CSV（连续录制）
   - 查找与 subject_info 中的 HR_baseline 和 HR_fatigue 匹配的片段
   - 记录该片段的时间戳范围 [start_time, end_time]

3. 该时间戳范围对应的 HR 数据即为该实验的有效数据
```

**关键字段** (from subject_info.csv)：
- `st_HR_baseline` - 单任务前的基线心率（参考值）
- `st_HR_fatigue` - 单任务中的峰值心率（参考值）
- `dt_HR_baseline` - 双任务前的基线心率（参考值）
- `dt_HR_fatigue` - 双任务中的峰值心率（参考值）
- `dual_task_visit` - 双任务进行的 Visit 号（通常为 2）

#### 步骤 1.2：计算最大心率基准

```python
# 从 subject_info 获取年龄，计算 MHR (最大心率)
age = subject_info.loc[subject_id, 'age']
MHR = 220 - age  # Karvonen 公式

# 例如：sub_01, age=24
MHR_sub_01 = 220 - 24 = 196 bpm
```

#### 步骤 1.3：Quality Check on Raw HR Data

```python
# 验证 raw HR 数据的合理性
computed_hr_max = raw_hr_data.max()
computed_hr_min = raw_hr_data.min()

# 检查是否在合理范围内
assert computed_hr_min >= 40, f"HR min {computed_hr_min} too low"
assert computed_hr_max <= MHR * 1.1, f"HR max {computed_hr_max} exceeds 110% of MHR"
assert computed_hr_max >= subject_info[subject_id]['st_HR_fatigue'] * 0.9, "HR max too low"
```

---

### 2️⃣ **利用 INTERIM 定位准确时间戳**

#### 步骤 2.1：计算 INTERIM 数据的实际时间长度

```python
import pandas as pd

# 读取 interim 数据（已手动切分的 6 分钟片段）
interim_file = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/sub_01/LF.csv"
df_interim = pd.read_csv(interim_file)

# 计算实际时间长度
num_rows = len(df_interim)
sample_rate = 128  # Hz
duration_sec = num_rows / sample_rate
duration_min = duration_sec / 60

print(f"Interim LF.csv: {num_rows} 行")
print(f"采样率: {sample_rate} Hz")
print(f"时间长度: {duration_sec:.1f} 秒 = {duration_min:.2f} 分钟")

# 示例输出
# Interim LF.csv: 48502 行
# 采样率: 128 Hz
# 时间长度: 378.9 秒 = 6.32 分钟
```

#### 步骤 2.2：将 INTERIM 行数映射到 RAW 的时间戳区间

```python
# 已知：
# - interim 中某个任务的数据行数 (n_rows)
# - interim 的采样率 (128 Hz)
# → 可推断该任务的实际时间长度

# 在 raw 的连续 HR 数据中找到匹配的片段
def find_hr_segment_in_raw(raw_hr_data, interim_n_rows, sample_rate=128):
    """
    在 raw HR 数据中查找与 interim 行数对应的片段

    Args:
        raw_hr_data: raw/OG_st_raw/sub_XX/heart_rate.CSV 数据
        interim_n_rows: interim 中对应任务的行数
        sample_rate: 128 Hz

    Returns:
        (start_idx, end_idx): raw_hr_data 中对应的索引范围
    """

    # interim 的时间长度（秒）
    interim_duration_sec = interim_n_rows / sample_rate

    # 对应在 HR 数据中的行数（HR 采样率为 1 Hz）
    hr_expected_rows = int(interim_duration_sec)

    # 在 raw_hr 中寻找匹配的连续片段
    # 可通过心率的特征（如上升-下降的动态范围）进行匹配
    for start_idx in range(len(raw_hr_data) - hr_expected_rows):
        segment = raw_hr_data[start_idx:start_idx + hr_expected_rows]

        # 检查该段是否符合预期的运动模式
        # （心率应从低→高→低，或保持相对稳定+变化）
        if is_valid_exercise_pattern(segment):
            return start_idx, start_idx + hr_expected_rows

    return None, None
```

---

### 3️⃣ **与 PROCESSED 数据对比验证**

#### 步骤 3.1：理解 PROCESSED 文件结构

**aggregate_params.csv** (每个任务一行)：
```csv
stride_lengths_avg,clearances_min_avg,...,stride_times_CV,cadence_CV,speed_CV,...
1.4018,0.0097,...,0.0193,0.0194,0.0531,...
```

**left_foot_core_params.csv** (每个步长一行)：
```
stride_index,timestamps,stride_lengths,stride_times,swing_times,stance_times,cadence,...
0,5.023,1.516,1.188,0.516,0.672,50.5,...
1,6.211,1.407,1.180,0.492,0.688,50.8,...
...
```

#### 步骤 3.2：关键指标说明

| 指标 | 含义 | 单位 | Python 对应 | 验证方法 |
|------|------|------|-----------|--------|
| `stride_lengths_avg` | 平均步幅 | m | `step_length` | 对比计算值 |
| `stride_times_avg` | 平均步时 | s | `1/step_frequency` | 对比，应相近 |
| `cadence_avg` | 平均节奏 | steps/min | `step_frequency * 60` | 对比，应相同 |
| `speed_avg` | 平均速度 | m/s | `step_length * step_freq` | 对比，应相同 |
| `stride_lengths_CV` | 步幅变异系数 | % | ISI CV | 对比，应接近 |
| `cadence_CV` | 节奏变异系数 | % | 同上 | 对比，应接近 |
| `swing_times_CV` | 摆动时CV | % | - | 参考 |
| `stance_times_CV` | 站立时CV | % | - | 参考 |

#### 步骤 3.3：验证流程

```python
def validate_against_processed(py_results, processed_csv):
    """
    对比 Python 计算结果与 processed 基准数据
    """

    # 读取 processed 数据
    df_processed = pd.read_csv(processed_csv)
    baseline_values = df_processed.iloc[0]  # 聚合参数通常是单行

    # 对比关键指标
    comparisons = {
        'stride_length': {
            'py': py_results['step_length'],
            'baseline': baseline_values['stride_lengths_avg'],
            'tolerance': 0.1  # 允许 10% 误差
        },
        'cadence': {
            'py': py_results['step_frequency'] * 60,
            'baseline': baseline_values['cadence_avg'],
            'tolerance': 0.05  # 允许 5% 误差
        },
        'speed': {
            'py': py_results['speed'],
            'baseline': baseline_values['speed_avg'],
            'tolerance': 0.1
        },
        'cv': {
            'py': py_results['isi_cv'],
            'baseline': baseline_values['stride_lengths_CV'],
            'tolerance': 0.2  # 允许 20% 误差（CV 通常变异较大）
        }
    }

    # 计算误差
    for metric, comparison in comparisons.items():
        error_pct = abs(comparison['py'] - comparison['baseline']) / comparison['baseline']
        status = '✓' if error_pct <= comparison['tolerance'] else '✗'
        print(f"{metric}: {comparison['py']:.3f} vs {comparison['baseline']:.3f} ({error_pct*100:.1f}%) {status}")
```

---

## 📋 数据字段参考

### RAW 数据（以 IMU 为例）

每个 CSV 有以下列（来自 Physilog 5 导出）：

```
Time(s), Accel X(m/s²), Accel Y(m/s²), Accel Z(m/s²),
Gyro X(°/s), Gyro Y(°/s), Gyro Z(°/s),
Quaternion W, Quaternion X, Quaternion Y, Quaternion Z,
Pressure, Temperature
```

- **采样率**：128 Hz
- **传感器位置**（9 个）：
  - `LF` - Left Foot（左脚）
  - `RF` - Right Foot（右脚）
  - `LL` - Left Leg（左腿）
  - `RL` - Right Leg（右腿）
  - `LW` - Left Wrist（左腕）
  - `RW` - Right Wrist（右腕）
  - `HE` - Head（头）
  - `ST` - Sternum（胸口）
  - `SA` - Sacrum（骶骨）

### Subject_info.csv

| 字段 | 说明 | 类型 | 示例 |
|------|------|------|------|
| `sub` | 受试者 ID | str | sub_01 |
| `age` | 年龄 | int | 24 |
| `sex` | 性别 | str | M/F |
| `height(cm)` | 身高 | float | 173 |
| `weight(kg)` | 体重 | float | 70 |
| `leg_length(cm)` | 腿长 | float | 82.5 |
| `activity_level` | 活动水平 | int | 1-5 |
| `dual_task_visit` | 双任务进行的 Visit | int | 1 或 2 |
| `st_HR_baseline` | 单任务-基线心率 | int | 62 |
| `st_HR_fatigue` | 单任务-峰值心率 | int | 185 |
| `st_lac_baseline1` | 单任务-基线乳酸 | float | 0.8 |
| `st_lac_fatigue` | 单任务-疲劳乳酸 | float | 4.8 |
| `st_time_to_fatigue(min)` | 单任务-疲劳时间 | float | 22 |
| `dt_HR_baseline` | 双任务-基线心率 | int | 63 |
| `dt_HR_fatigue` | 双任务-峰值心率 | int | 178 |
| `dt_lac_*` | 双任务相关指标 | float | - |

---

## 🔗 文件访问路径

### 快速参考

```python
# Raw 数据
raw_st_dir = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw"
raw_dt_dir = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_dt_raw"

# Interim 数据
interim_st_control = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control"
interim_st_fatigue = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_fatigue"
interim_dt_control = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_dt_control"
interim_dt_fatigue = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_dt_fatigue"

# Processed 数据
processed_st_control = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/processed/OG_st_control"
processed_dt_fatigue = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/processed/OG_dt_fatigue"

# 元数据
subject_info = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/subject_info.csv"
```

### 构建动态路径

```python
def get_interim_path(task_type, phase, subject_id):
    """
    task_type: 'st' 或 'dt'
    phase: 'control', 'fatigue', 'sit_to_stand', 'all'
    subject_id: 'sub_01'
    """
    base = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim"
    folder = f"OG_{task_type}_{phase}"
    return f"{base}/{folder}/{subject_id}"

# 例子
interim_path = get_interim_path('st', 'control', 'sub_01')
# → /Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/sub_01
```

---

## ✅ 完整使用示例

```python
import pandas as pd
import numpy as np

# ============================================================================
# 第1步：加载元数据与设置
# ============================================================================

subject_info = pd.read_csv("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/subject_info.csv")
subject_id = "sub_01"
subject_data = subject_info[subject_info['sub'] == subject_id].iloc[0]

age = subject_data['age']
MHR = 220 - age
print(f"Subject: {subject_id}, Age: {age}, MHR: {MHR} bpm")

# ============================================================================
# 第2步：获取 Interim 数据的时间长度信息
# ============================================================================

interim_lf = pd.read_csv(
    f"/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/{subject_id}/LF.csv",
    skiprows=5
)
n_rows_interim = len(interim_lf)
duration_sec = n_rows_interim / 128
print(f"Interim 数据: {n_rows_interim} 行 = {duration_sec:.1f} 秒")

# ============================================================================
# 第3步：从 Raw 中提取对应时间段的 Heart Rate
# ============================================================================

hr_raw_file = f"/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw/{subject_id}/heart_rate.CSV"
with open(hr_raw_file) as f:
    lines = f.readlines()
data_start = [i for i, line in enumerate(lines) if 'Sample rate' in line][0]

df_hr_raw = pd.read_csv(hr_raw_file, skiprows=data_start)
hr_values = pd.to_numeric(df_hr_raw['HR (bpm)'], errors='coerce').dropna().values

print(f"Raw HR 数据: {len(hr_values)} 个数据点")
print(f"HR 范围: {hr_values.min():.0f} ~ {hr_values.max():.0f} bpm")

# 使用 interim 行数来定位对应的 HR 片段
hr_expected_length = int(duration_sec)
hr_segment = hr_values[:hr_expected_length]  # 简化示例，实际需匹配模式

print(f"提取的 ST-Control HR 片段: {len(hr_segment)} 秒")
print(f"初始 HR: {hr_segment[0]:.0f} bpm, 最大 HR: {hr_segment.max():.0f} bpm")

# ============================================================================
# 第4步：加载 Processed 基准数据进行验证
# ============================================================================

processed_agg = pd.read_csv(
    f"/Volumes/ChouSSD/elder_datasets/DUO-GAIT/processed/OG_st_control/{subject_id}/aggregate_params.csv"
)
baseline_cadence = processed_agg.iloc[0]['cadence_avg']
baseline_speed = processed_agg.iloc[0]['speed_avg']
baseline_cv = processed_agg.iloc[0]['stride_lengths_CV']

print(f"\nProcessed 基准数据:")
print(f"  Cadence (baseline): {baseline_cadence:.1f} steps/min")
print(f"  Speed (baseline): {baseline_speed:.3f} m/s")
print(f"  Stride Length CV: {baseline_cv:.4f}")

# ============================================================================
# 第5步：对比自己计算的指标
# ============================================================================

# 假设 Python 算法计算得到这些值
py_step_freq = baseline_cadence / 60  # convert to steps/s
py_speed = baseline_speed
py_cv = baseline_cv

error_cadence_pct = abs(py_step_freq * 60 - baseline_cadence) / baseline_cadence * 100
error_speed_pct = abs(py_speed - baseline_speed) / baseline_speed * 100

print(f"\n验证结果:")
print(f"  Cadence 误差: {error_cadence_pct:.1f}%", "✓" if error_cadence_pct < 5 else "✗")
print(f"  Speed 误差: {error_speed_pct:.1f}%", "✓" if error_speed_pct < 10 else "✗")
```

---

## 📌 关键概念总结

| 概念 | 定义 | 用途 |
|-----|------|------|
| **MHR** | 最大心率 = 220 - 年龄 | 计算相对工作强度、验证 HR 合理性 |
| **Interim** | 手动切分的 6 分钟片段 | 与 Raw 对应，用行数确定时间戳范围 |
| **Processed** | 已计算的步态参数 | 作为验证基准，对比 Python 算法准确性 |
| **Sampling Rate** | IMU:128Hz, HR:1Hz | 用于时间长度与行数的转换 |
| **CV (系数变异)** | 步态指标的变异程度 | 反映步态稳定性，越低越稳定 |

---

## 🎯 使用建议

1. **开发阶段**：
   - 先用一个受试者的单一任务（如 sub_01 ST-Control）来验证流程
   - 对比 processed 数据来调试算法

2. **验证阶段**：
   - 逐个测试不同的任务类型（ST-Control, ST-Fatigue, DT-Control, DT-Fatigue）
   - 检查 HR 特征是否符合预期（运动中升高，恢复期下降）

3. **生产阶段**：
   - 批量处理所有受试者
   - 生成综合对比报告
   - 监控异常值和数据质量

---

**最后更新**：2026-04-19
**版本**：1.0 - 初始架构文档
