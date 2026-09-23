# DUO-GAIT 数据处理 Pipeline 完整规范

## 目录
1. [项目概述](#项目概述)
2. [数据结构](#数据结构)
3. [JSON 输出格式](#json-输出格式)
4. [指标计算逻辑](#指标计算逻辑)（详细见 **[METRIC_CALCULATION.md](METRIC_CALCULATION.md)**）
5. [LLM 分类规则](#llm-分类规则)
6. [Fuzzy Logic Baseline](#fuzzy-logic-baseline)
7. [使用指南](#使用指南)

---

## 项目概述

### 核心流程
```
DUO-GAIT 数据集 (30秒窗口)
        ↓
指标计算 (5个核心指标)
        ↓
├─→ JSON 输出（给 LLM）
└─→ Fuzzy Logic 分类（baseline ground_truth）
        ↓
LLM 处理 + baseline 对比
```

### 设计原则
- **窗口大小**：30 秒（3840 个 IMU 采样 @ 128Hz，30 个 HR 采样 @ 1Hz）
- **输出格式**：标准 JSON（符合 LLM 处理要求）
- **质量控制**：包含 imu_quality 和 hr_quality 指标
- **基准对比**：Fuzzy Logic 作为 ground_truth 参考

---

## 数据结构

### 数据源

#### RAW 层（原始连续数据）
```
/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/
├─ OG_st_raw/sub_XX/
│  ├─ ST.csv          [128 Hz, 胸部传感器 IMU 数据]
│  ├─ LF.csv          [128 Hz, 左脚 IMU 数据]
│  ├─ RF.csv          [128 Hz, 右脚 IMU 数据]
│  └─ ...9 个传感器
├─ OG_st_raw/sub_XX/heart_rate.CSV  [1 Hz, 心率数据]
└─ subject_info.csv   [元数据：年龄、性别等]
```

#### INTERIM 层（手动切分的 6 分钟片段）
```
/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/
├─ OG_st_control/sub_XX/    [单任务-控制阶段]
├─ OG_st_fatigue/sub_XX/    [单任务-疲劳阶段]
├─ OG_dt_control/sub_XX/    [双任务-控制阶段]
├─ OG_dt_fatigue/sub_XX/    [双任务-疲劳阶段]
└─ ...其他任务变种
```

**关键**：每个 INTERIM CSV 已手动切割为恰好 6 分钟（48,000+ 行 @ 128Hz）

#### PROCESSED 层（已计算的步态参数）
```
/Volumes/ChouSSD/elder_datasets/DUO-GAIT/processed/
└─ OG_st_control/sub_XX/
   ├─ aggregate_params.csv       [全局聚合参数]
   ├─ left_foot_core_params.csv  [左脚逐步参数]
   └─ right_foot_core_params.csv [右脚逐步参数]
```

用于**可选离线对照**（脚本 `validate_duogait_metrics.py`）。**主流程 JSON 不读取 processed**，指标均为自算（见 METRIC_CALCULATION.md）。

### 关键参数

| 参数 | 采样率 | 范围 | 用途 |
|------|-------|------|------|
| IMU (ST) | 128 Hz | 3 轴加速度（+ 陀螺仪列存在但未参与当前指标） | 步频、步时变异、胸戴步长锚 |
| IMU (LF/RF) | 128 Hz | 与 ST 对齐的足部加速度 | 仅参与步长融合修正 |
| Heart Rate | 1 Hz | 30-200 bpm | 运动强度评估 |
| 窗口大小 | - | 30 秒 | 标准化处理单元 |

---

## JSON 输出格式

### 完整结构

```json
{
  "sample_id": "001",
  "subject_id": "sub_01",
  "player_age": 24,
  "dataset_source": "DUO-GAIT",

  "input_features": {
    "step_frequency_hz": 1.36,
    "step_length_m": 1.2,
    "step_time_variability_ms": 100.0,
    "mean_hr_bpm": 69.8,
    "max_hr_bpm": 71
  },

  "warmup_baseline": {
    "warmup_cadence_hz": 1.36,
    "warmup_stride_m": 1.2,
    "warmup_var_ms": 100.0
  },

  "rpe": null,

  "imu_quality": 0.95,
  "hr_quality": 0.85,

  "ground_truth": {
    "exercise_load": "moderate",
    "fatigue_level": "none",
    "movement_quality": "good",
    "composite_state": "normal"
  }
}
```

### 字段说明

#### sample_id
- **类型**：字符串
- **格式**：3 位零填充（001, 002, ...）
- **含义**：窗口序号

#### subject_id
- **类型**：字符串
- **格式**：sub_XX
- **含义**：受试者唯一标识

#### player_age
- **类型**：整数
- **来源**：subject_info.csv
- **用途**：计算 MHR = 220 - age（用于 %MHR 计算）

#### dataset_source
- **类型**：字符串
- **固定值**："DUO-GAIT"

#### input_features（5 个核心指标）
- **step_frequency_hz**：步频（赫兹）
  - 范围：0.5-2.5 Hz
  - 计算：从加速度峰值检测

- **step_length_m**：步幅（米）
  - 范围：0.3-1.5 m
  - 计算：基于加速度强度映射

- **step_time_variability_ms**：步时变异性（毫秒）
  - 范围：0-150 ms
  - 计算：相邻步间间隔 (ISI) 的标准差
  - 意义：反映步态稳定性

- **mean_hr_bpm**：平均心率（次/分）
  - 范围：30-200 bpm
  - 计算：30秒窗口内心率平均值

- **max_hr_bpm**：最大心率（次/分）
  - 范围：30-200 bpm
  - 计算：30秒窗口内心率峰值

#### warmup_baseline
- **来源**：自动从第 1 个窗口提取
- **用途**：相对调整时的参考（与 LLM 规则中的相对调整部分配合）
- **字段**：
  - warmup_cadence_hz：基准步频
  - warmup_stride_m：基准步幅
  - warmup_var_ms：基准变异性

#### rpe
- **类型**：null 或数字 (6-20)
- **含义**：Borg CR-10 主观感觉费力程度
- **当前状态**：null（数据不可用）

#### imu_quality & hr_quality
- **范围**：0.0-1.0
- **含义**：
  - \>0.9：优秀
  - 0.6-0.9：良好
  - <0.6：降权处理（在 LLM 推理中权重降低）

#### ground_truth（由 Fuzzy Logic 生成）
- **exercise_load**：low | moderate | high | excessive
  - 基于：mean_hr_bpm 与 %MHR 的对应关系

- **fatigue_level**：none | mild | moderate | severe
  - 基于：step_time_variability_ms, step_length_m, 可选 RPE

- **movement_quality**：good | degraded | poor
  - 基于：step_frequency_hz, step_length_m, step_time_variability_ms（绝对评级）
  - 考虑：与 warmup_baseline 的相对变化

- **composite_state**：normal | under_loaded | fatigue_risk
  - 综合判断：安全覆盖逻辑后的最终状态

---

## 指标计算逻辑

以下为与代码一致的摘要；**逐步公式、时间列 `timestamp`、心率对齐、足部步长融合、`STRIDE_LEN_OUTPUT_SCALE` 等**见 **[METRIC_CALCULATION.md](METRIC_CALCULATION.md)**。

| 指标 | 主要来源 | 要点 |
|------|-----------|------|
| **step_frequency_hz** | ST 加速度，峰检 + 低通 | `1/mean(ISI)`，ISI∈(0.3,2.0)s；不可靠时 **null**（默认）；兜底模式见 `METRIC_CALCULATION.md` |
| **step_time_variability_ms** | 同上 ST 峰间期 | `std(ISI)×1000`；默认 **不截顶**；兜底时 clip [5,100] ms |
| **step_length_m** | ST 强度映射锚 +（可选）LF/RF RMS 微调 + 身高/步频启发式混合 | × `STRIDE_LEN_OUTPUT_SCALE`（默认 1.0）；无可靠步频且无兜底时 **null** |
| **mean / max HR** | `heart_rate.CSV` 对齐窗 | 无效为 `null`；缺 HR 时 `hr_quality` 降低 |
| **imu / hr quality** | 启发式 | 双通道均 <0.6 → fuzzy 三维 `unknown` |

**INTERIM 时间列**：优先 `timestamp`（与当前 DUO 导出一致），兼容 `Time`。

**双任务**：INTERIM 在 `OG_dt_*` 时，心率目录使用 **`raw/OG_dt_raw/sub_XX`**。

---

## LLM 分类规则

### 参考范围（所有心率阈值以 %MHR 表示）

```
MHR = 220 - player_age

HR 区间：
  Target (安全范围)：50–70% MHR
  Alert (警告)：>70% MHR
  Ceiling (上限)：≥80% MHR → 强制停止或降载
```

### Dimension 1 - Exercise Load（运动负荷）

**分类**：low | moderate | high | excessive

**规则**：
```
mean_hr_pct = (mean_hr_bpm / MHR) × 100

<50%          → low
50–70%        → moderate
70–80%        → high
≥80%          → excessive (安全警告)

如果 RPE 存在且与 HR 区间冲突 ≥2 级 → 采用更高风险的信号
```

### Dimension 2 - Fatigue Level（疲劳程度）

**分类**：none | mild | moderate | severe

**计分规则**：
```
评分基础：

Step Time Variability:
  >60 ms     → +2
  30–60 ms   → +1
  <30 ms     → +0

Step Length:
  <0.40 m    → +1
  ≥0.40 m    → +0

RPE (if available):
  rpe ≥ 9    → +2
  rpe ≥ 7    → +1
  rpe < 7    → +0

总分映射：
  0       → none
  1–2     → mild
  3       → moderate
  ≥4      → severe
```

### Dimension 3 - Movement Quality（动作质量）

**分类**：good | degraded | poor

**绝对评级**（基于输入指标范围）：
```
Step Frequency:
  good:      [1.6, 2.0] Hz
  degraded:  [1.4, 1.6) or (2.0, 2.2] Hz
  poor:      <1.4 or >2.2 Hz

Step Length:
  good:      [0.45, 0.65] m
  degraded:  [0.35, 0.45) or (0.65, 0.75] m
  poor:      <0.35 or >0.75 m

Step Time Variability:
  good:      <30 ms
  degraded:  30–60 ms
  poor:      >60 ms
```

**计分**（绝对评级后）：
```
每个指标评分：good=0, degraded=1, poor=2

总分 = freq_score + length_score + var_score

分类：
  ≤1         → good
  2–3        → degraded
  ≥4         → poor
```

**相对调整**（与 warmup_baseline 对比）：
```
从 warmup 下降 ≥20%  → 严重度升级一级
  good    → degraded
  degraded → poor

在 ±10% 内         → 保持绝对评级
```

**极值覆盖**：
```
IF step_time_variability_ms >80 OR step_length_m <0.30
  → MUST be "poor"

IF step_time_variability_ms >60 AND step_length_m <0.35
  → MUST be "poor"
```

### Composite State（综合状态）

**分类**：normal | under_loaded | fatigue_risk

**安全覆盖逻辑**（优先级最高）：
```
IF ANY is true → composite_state = "fatigue_risk":

  · mean_hr_bpm ≥ 80% MHR
    → flag: "high_cardiac_load"

  · fatigue_level = "severe"
    → 建议暂停

  · movement_quality = "poor"
    → 建议暂停

  · rpe ≥ 9 (if available)
    → flag: "hard_stop"

  · step_time_variability_ms >80 AND mean_hr_bpm >70% MHR
    → flag: "hard_stop" (立即停止)

  · step_length_m drop ≥20% from warmup AND fatigue ≥ moderate
    → flag: "fatigue_compensation" (代偿机制)

  · step_time_variability_ms >60 AND step_length_m <0.35
    → flag: "fatigue_compensation"
```

**正常分类**（无安全覆盖触发时，代码实现摘要）：
- 若 **HR 在 50–70% MHR** 且 **至少 2 项 IMU 为 good、无 poor** → `composite_state = "normal"`
- 若 **HR < 50% MHR** 且 **三项 IMU 均为 good**，且 **（无 RPE 或 RPE≤3）** → `under_loaded`
- 其余 → `normal`（含 HR 缺失时无法判 under_loaded / 目标带的情形）

### 数据质量权重调整

```
imu_quality < 0.6  → 降权 IMU 相关推理
hr_quality < 0.6   → 降权 HR 相关推理

BOTH < 0.6 → 所有维度标记为 "unknown"（composite 置 neutral，见代码）
```

**心率缺失**：无 `mean_hr` 且无 RPE 时 **exercise_load = unknown**；有 RPE 时仅用 RPE 映射负荷；Dim2/Dim3 仍可由 IMU 计算。

---

## Fuzzy Logic Baseline

### 目的
在 JSON 生成时同步计算 **ground_truth**，用于：
- LLM 结果的参考基准
- 算法一致性验证
- 模型性能评估

### 实现位置
`signal_processing_pipeline/fuzzy_classifier.py` 中函数 **`classify_exercise_state`**（同事规则：Dim1–3、warmup 相对调整、极值/组合 override、安全覆盖、composite）。`FuzzyExerciseClassifier.classify` 为薄封装，返回 `(value, label)` 元组以兼容旧调用。

### 调用示例
```python
from fuzzy_classifier import classify_exercise_state

out = classify_exercise_state(
    mean_hr_bpm=72.0,
    max_hr_bpm=78.0,
    step_frequency_hz=1.55,
    step_length_m=0.58,
    step_time_variability_ms=28.0,
    warmup_baseline={"warmup_cadence_hz": 1.5, "warmup_stride_m": 0.6, "warmup_var_ms": 25.0},
    player_age=72,
    rpe=None,
    imu_quality=0.9,
    hr_quality=0.9,
)
# out["exercise_load"], out["fatigue_level"], out["movement_quality"], out["composite_state"]
```

### 与 LLM 规则的对齐
- 与本文 **LLM 分类规则** 同一套离散逻辑（非旧版 Mamdani 连续隶属输出）。
- 数据质量双低 → 三维 `unknown`。

### 注意事项
- 与 LLM 对比时若系统提示词与本文不一致，以团队最新规则为准并同步改 `classify_exercise_state`。
- 步长/步频绝对带按 **老年人干预** 量纲设计；DUO 年轻受试者可能出现更多 `degraded`/`poor`，属预期，可另选数据集或后续再商量量纲缩放（`STRIDE_LEN_OUTPUT_SCALE`，默认 1.0）。

---

## 使用指南

### 快速开始

```bash
cd /Users/zhanghaiyu/workspace/elder_rehab

python3 process_duogait_to_json.py
```

**某一受试者全部 INTERIM 任务（推荐）**：

```bash
python3 run_subject_all_windows.py --subject sub_01 --out-dir /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/
```

**输出**：
- 位置：`/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/`
- 格式：`sub_XX_task_type_window_NNNN.json`
- 数量：每个 INTERIM CSV 生成 ~16 个窗口（6 分钟 ÷ 30 秒）

### 配置选项

编辑 `process_duogait_to_json.py` 中的 main() 函数：

```python
def main():
    # 修改这些参数
    imu_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/sub_01'
    hr_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw/sub_01'
    output_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/'
    subject_id = 'sub_01'
    task_type = 'st_control'  # 或其他任务类型
    max_windows = None  # None=全部，或指定数字
```

### 输出验证

```bash
# 验证生成的 JSON 文件数量和格式
python3 << 'EOF'
import json
import glob

json_files = sorted(glob.glob('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/sub_01_st_control*.json'))
print(f"✅ 生成文件数：{len(json_files)}")

# 检查第一个文件
with open(json_files[0]) as f:
    data = json.load(f)

print(f"✅ JSON 结构有效")
print(f"  - input_features: {len(data['input_features'])} 指标")
print(f"  - ground_truth: {list(data['ground_truth'].keys())}")
EOF
```

### 扩展到多个受试者

对每个 `sub_XX` 运行：

```bash
python3 run_subject_all_windows.py --subject sub_XX --out-dir /path/to/json/
```

---

## 常见问题排查

### Q1：JSON 文件 ground_truth 都是 "unknown"

**原因**：imu_quality 和 hr_quality 都 < 0.6

**检查**：
```python
# 查看 JSON 中的质量指标
data['imu_quality']  # 应该 > 0.6
data['hr_quality']   # 应该 > 0.6
```

**解决**：
- 检查 HR 数据是否正确加载（skiprows=6）
- 检查 IMU 信号是否包含足够的峰值

### Q2：step_frequency_hz 过高或过低

**原因**：峰值检测参数不合适

**参数位置**：`signal_processing_pipeline/config.py`
```python
PEAK_HEIGHT_MULTIPLIER = 2.5  # 增大 → 检测少，减小 → 检测多
MIN_PEAK_DISTANCE_SEC = 0.4   # 最小步间距（秒）
```

### Q3：step_length_m 与 fuzzy 动作档不一致

**原因**：胸戴锚 + 足部微调 + `STRIDE_LEN_OUTPUT_SCALE`（默认 1.0）与峰值法步频/变异共同作用。

**调整**：见 `METRIC_CALCULATION.md`；映射系数在 `extract_gait_features()` 与 `duogait_metrics.stride_from_cadence_height_and_feet`。

---

## 版本信息

- **创建日期**：2026-04-20
- **Pipeline 版本**：1.0
- **核心库**：signal_processing_pipeline/
- **主脚本**：process_duogait_to_json.py
- **状态**：当前离线处理规范；真实数据运行需要本地 DUO-GAIT 数据目录

---
