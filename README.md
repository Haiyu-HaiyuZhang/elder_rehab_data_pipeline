# DUO-GAIT 数据处理 Pipeline

## 概述

完整的信号处理管道，用于 DUO-GAIT 数据集的处理：
- ✅ 从 RAW 数据提取 30 秒窗口
- ✅ 计算 5 个核心指标（步频、步幅、变异性、HR 平均、HR 最大）
- ✅ 生成标准化 JSON 输出（供 LLM 处理）
- ✅ Fuzzy Logic 生成 ground_truth 基准

---

## 📚 文档导航

### 必读文档
- **[PIPELINE_SPECIFICATION.md](PIPELINE_SPECIFICATION.md)** ⭐ （完整规范）
  - JSON 格式、LLM 规则、Fuzzy、Q&A
- **[METRIC_CALCULATION.md](METRIC_CALCULATION.md)** ⭐ **指标计算原理（与代码同步）**
  - ST/LF/RF、心率对齐、五步特征、质量分、与 fuzzy 量纲说明
- **[FILES_STRUCTURE.md](FILES_STRUCTURE.md)** 📁（项目文件说明）
  - 项目结构、文件用途、依赖关系

### 参考文档
- **[DATA_ARCHITECTURE_GUIDE.md](DATA_ARCHITECTURE_GUIDE.md)**（数据架构详解）

---

## 🚀 快速开始

### 前置要求
```bash
pip install -r signal_processing_pipeline/requirements.txt
```

### 生成 JSON 窗口
```bash
cd /Users/zhanghaiyu/workspace/elder_rehab

# 默认处理 sub_01 st_control 数据
python3 process_duogait_to_json.py

# 某一受试者：interim 下所有 OG_* 任务各跑满 30s 窗口
python3 run_subject_all_windows.py --subject sub_01 --out-dir /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/

# 全量处理（也可以用 --dry-run 先检查数据覆盖）
python3 batch_process_all.py \
   --interim-base /Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim \
   --raw-base /Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw \
   --out-dir /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json
```

### 配置选项

编辑 `process_duogait_to_json.py` 的 `main()` 函数：

```python
def main():
    imu_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control/sub_01'
    hr_data_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw/sub_01'
    output_dir = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/'
    subject_id = 'sub_01'
    task_type = 'st_control'
    max_windows = None  # None=全部，或指定数字

    processor = DUOGAITProcessor(imu_data_dir, hr_data_dir, output_dir, subject_id, task_type)
    processor.process_windows(max_windows)
```

---

## 📊 输出示例

**位置**：`/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/`

**文件名**：`sub_01_st_control_window_0000.json`

```json
{
  "sample_id": "000",
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

---

## 📁 项目结构

```
elder_rehab/
├── 📚 文档
│   ├── README.md
│   ├── PIPELINE_SPECIFICATION.md          # ⭐ 规范 + LLM/fuzzy 规则
│   ├── METRIC_CALCULATION.md              # ⭐ 指标计算原理（自算 IMU+HR）
│   ├── FILES_STRUCTURE.md
│   └── DATA_ARCHITECTURE_GUIDE.md
│
├── 🐍 脚本
│   ├── process_duogait_to_json.py         # ⭐ 单任务 / 默认 main
│   ├── batch_process_all.py               # ⭐ 全量受试者和任务
│   ├── run_subject_all_windows.py         # 单受试者全部 INTERIM 任务
│   └── validate_duogait_metrics.py        # 可选：与 processed 离线对比
│
└── 📦 signal_processing_pipeline/
    ├── config.py
    ├── duogait_metrics.py                   # 双足步长融合（无 processed 输入）
    ├── fuzzy_classifier.py                # classify_exercise_state / 同事规则
    │
```

**详见**：[FILES_STRUCTURE.md](FILES_STRUCTURE.md) —— 完整的文件用途和依赖关系说明

---

## 🔧 核心指标说明

| 指标 | 单位 | 范围 | 计算方式 |
|------|------|------|--------|
| **step_frequency_hz** | Hz | 0.5-2.5 | 加速度峰值检测 |
| **step_length_m** | m | 约 0.38–1.55 | 胸戴强度锚 + 可选 LF/RF 微调 + 身高/步频启发式；`STRIDE_LEN_OUTPUT_SCALE` 默认 **1.0**（老年人量纲） |
| **step_time_variability_ms** | ms | 5–100（写入） | ST 峰间期 ISI 标准差 |
| **mean_hr_bpm** | bpm | 30-200 | 30秒窗口平均 |
| **max_hr_bpm** | bpm | 30-200 | 30秒窗口最大 |

详见：[METRIC_CALCULATION.md](METRIC_CALCULATION.md)；规则索引：[PIPELINE_SPECIFICATION.md](PIPELINE_SPECIFICATION.md)

---

## 🤖 LLM 分类规则

JSON 中的 `ground_truth` 字段由 Fuzzy Logic 基于以下规则生成：

### 三维分类
1. **exercise_load**: low | moderate | high | excessive
   - 基于：mean_hr_bpm 与 %MHR（220-age）的对应关系

2. **fatigue_level**: none | mild | moderate | severe
   - 基于：step_time_variability_ms, step_length_m, RPE

3. **movement_quality**: good | degraded | poor
   - 基于：step_frequency_hz, step_length_m, step_time_variability_ms

4. **composite_state**: normal | under_loaded | fatigue_risk
   - 综合判断及安全覆盖逻辑

详见：[PIPELINE_SPECIFICATION.md - LLM 分类规则](PIPELINE_SPECIFICATION.md#llm-分类规则)

---

## ✅ 使用流程

```
1. 准备数据
   ├─ INTERIM CSV：6 分钟 IMU 数据 (128 Hz)
   └─ Raw HR CSV：心率数据 (1 Hz)

2. 运行 Pipeline
   ├─ 单任务：python3 process_duogait_to_json.py
   └─ 受试者全任务：python3 run_subject_all_windows.py --subject sub_01 --out-dir .../json/

3. 获得输出
   ├─ JSON 文件（每个 30 秒窗口）
   └─ ground_truth（Fuzzy Logic 基准）

4. 送入 LLM
   ├─ 输入：input_features + warmup_baseline
   └─ 对比：LLM 输出 vs ground_truth
```

## 实时协议边界

仓库当前交付的是 **DUO-GAIT 离线数据处理管线**，不包含 UDP 9101/9102 的传感器接收服务。实时协议应作为独立适配层：接收端负责校验 `session_id`、`seq`、时间戳和 `quality`，再将实时特征转换为与 `input_features` 兼容的结构。离线 JSON 与实时协议中的字段不能未经定义直接混用，尤其是 `step_time_variability_ms` 与 `step_time_cv` 的单位不同。

---

## 🔍 验证

```bash
# 验证生成的 JSON
python3 << 'EOF'
import json, glob

json_files = sorted(glob.glob('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/sub_01_st_control*.json'))
print(f"✅ 生成 {len(json_files)} 个 JSON 文件")

with open(json_files[0]) as f:
    data = json.load(f)

print(f"✅ 核心指标: {list(data['input_features'].keys())}")
print(f"✅ Ground Truth: {list(data['ground_truth'].keys())}")
EOF
```

---

## 📞 故障排查

详见：[PIPELINE_SPECIFICATION.md - 常见问题排查](PIPELINE_SPECIFICATION.md#常见问题排查)

---

## 版本信息

- **创建日期**：2026-04-20
- **状态**：当前离线处理管线；运行真实数据需要本地 DUO-GAIT 数据目录
- **主脚本**：process_duogait_to_json.py
- **核心库**：signal_processing_pipeline/
