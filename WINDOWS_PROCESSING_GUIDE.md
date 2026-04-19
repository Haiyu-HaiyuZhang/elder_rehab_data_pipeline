# 窗口特征处理流程实现指南

## 📋 概述

实现了完整的 **30s 窗口特征 → JSON → Fuzzy 分类** 的三步流程：

```
Step 1: 计算特征
━━━━━━━━━━━━━━━━━━━━━━━━━→
从原始数据计算 30s 窗口的特征
(HR, 步频, 步幅, 变异性等)

Step 2: JSON 导出
━━━━━━━━━━━━━━━━━━━━━━━━━→
按分段编号将特征导出为 JSON
(每个 30s 窗口一个 JSON 文件)
用于 LLM 处理

Step 3: Fuzzy 分类
━━━━━━━━━━━━━━━━━━━━━━━━━→
应用 Mamdani 模糊推理
输出分类结果表格
(分段编号 ↔ 分类标签)
```

---

## 🛠️ 核心模块

### 1. `windows_json_exporter.py`
**功能**: 将 30s 窗口特征导出为分段编号的 JSON

**主要类**: `WindowJSONExporter`

**关键方法**:
```python
exporter = WindowJSONExporter(output_dir="./window_jsons")

# 为单个窗口创建 JSON 结构
window_json = exporter.create_window_json(
    window_id="window_001",
    subject_id="sub_01",
    task_type="st_control",
    timestamp="00:00",
    features={
        'hr_mean': 95,
        'step_var': 25,
        'hr_recovery': 18,
        'stride_length': 0.55,
        'rpe_score': 12,
        ...
    }
)

# 导出为 JSON 文件
exporter.export_window(window_json)

# 批量导出 DataFrame 中的所有窗口
files = exporter.batch_export(
    windows_df=df,
    subject_id="sub_01",
    task_type="st_control",
    prefix="ST"
)
```

**输出 JSON 结构**:
```json
{
  "metadata": {
    "window_id": "window_001",
    "subject_id": "sub_01",
    "task_type": "st_control",
    "timestamp": "00:00",
    "window_duration_sec": 30
  },
  "physiological_signals": {
    "heart_rate": {
      "mean_bpm": 95,
      "max_bpm": 120,
      "recovery_bpm_per_min": 18,
      ...
    }
  },
  "gait_features": {
    "step_frequency_hz": 1.8,
    "stride_length_m": 0.55,
    "step_variability_ms": 25,
    ...
  },
  "subjective_assessment": {
    "rpe_score": 12,
    "rpe_scale": "Borg 6-20"
  },
  "raw_feature_values": {
    "hr_mean": 95,
    "step_var": 25,
    "hr_recovery": 18,
    "stride_length": 0.55,
    "rpe_score": 12
  }
}
```

---

### 2. `validate_with_fuzzy.py`
**功能**: 读取 JSON 文件，应用 Fuzzy Logic，输出分类结果

**主要类**: `FuzzyValidationEngine`

**关键方法**:
```python
engine = FuzzyValidationEngine(age=70, verbose=True)

# 对单个 JSON 应用 Fuzzy 分类
result = engine.validate_single_window(window_json)

# 对整个目录批量验证
results_df = engine.validate_from_directory(
    input_dir="./window_jsons",
    subject_id="sub_01",
    task_type="st_control"
)

# 生成摘要报告
report = engine.generate_summary_report(results_df)
```

**输出 CSV 结构**:
```
window_id,subject_id,task_type,timestamp,
hr_mean,step_var,hr_recovery,stride_length,rpe_score,
exercise_load_score,exercise_load_category,
fatigue_level_score,fatigue_level_category,
movement_quality_score,movement_quality_category,
confidence,mhr,hr_percent_mhr,reasoning
```

---

## 🚀 使用示例

### 完整端到端流程

```python
import pandas as pd
from windows_json_exporter import WindowJSONExporter
from validate_with_fuzzy import FuzzyValidationEngine

# ========== Step 1: 准备特征数据 ==========
df_features = pd.read_csv("features_windows.csv")  # 从您的计算管道获取

# ========== Step 2: 导出为 JSON ==========
exporter = WindowJSONExporter(output_dir="./window_jsons")

files = exporter.batch_export(
    windows_df=df_features,
    subject_id="sub_01",
    task_type="st_control",
    prefix="ST"
)
print(f"导出 {len(files)} 个 JSON 文件")

# ========== Step 3: 应用 Fuzzy 分类 ==========
engine = FuzzyValidationEngine(age=70)

results_df = engine.validate_from_directory(
    input_dir="./window_jsons",
    subject_id="sub_01",
    task_type="st_control"
)

# ========== Step 4: 保存分类结果 ==========
results_df.to_csv("classification_results.csv", index=False)

# ========== Step 5: 查看摘要 ==========
report = engine.generate_summary_report(results_df)
print(f"运动负荷分布: {report['exercise_load_distribution']}")
print(f"疲劳等级分布: {report['fatigue_level_distribution']}")
print(f"动作质量分布: {report['movement_quality_distribution']}")
```

---

## 📊 命令行使用

### JSON 导出示例
```bash
python -c "
from windows_json_exporter import WindowJSONExporter
import pandas as pd

df = pd.read_csv('features.csv')
exporter = WindowJSONExporter()
exporter.batch_export(df, 'sub_01', 'st_control')
"
```

### Fuzzy 验证示例
```bash
python signal_processing_pipeline/validate_with_fuzzy.py \
    --input_dir ./window_jsons \
    --subject sub_01 \
    --task st_control \
    --age 70 \
    --output classification_results.csv \
    --report
```

**命令行选项**:
- `--input_dir`: JSON 文件目录 (必需)
- `--age`: 受试者年龄 (必需，用于 MHR 计算)
- `--subject`: 筛选特定受试者 (可选)
- `--task`: 筛选特定任务类型 (可选)
- `--output`: 输出 CSV 文件 (默认: fuzzy_results_*.csv)
- `--report`: 生成摘要报告 (可选)
- `--quiet`: 抑制详细输出 (可选)

---

## 📁 文件结构示例

### 输入: 特征数据 DataFrame
```
     timestamp  hr_mean  hr_max  step_frequency  step_var  ...
0       00:00   95      120     1.8             25        ...
1       00:30   98      125     1.75            28        ...
2       01:00   105     135     1.7             32        ...
3       01:30   110     145     1.65            38        ...
...
```

### 中间产物: 分段编号的 JSON 目录
```
./window_jsons/
├── sub_01_st_control_window_ST_000.json
├── sub_01_st_control_window_ST_001.json
├── sub_01_st_control_window_ST_002.json
├── sub_01_st_control_window_ST_003.json
└── ...
```

### 输出: 分类结果表格
```
window_id,exercise_load_category,fatigue_level_category,movement_quality_category
window_ST_000,low,mild,good
window_ST_001,low,moderate,good
window_ST_002,moderate,moderate,degraded
window_ST_003,high,severe,poor
...
```

---

## 🔄 与 LLM 的集成

### 现在 JSON 可用于 LLM 处理：

```python
# LLM 可以读取 JSON 并生成标签
import json

with open("sub_01_st_control_window_ST_000.json") as f:
    window = json.load(f)

# 提供给 LLM 作为输入
prompt = f"""
基于以下 30 秒运动数据标注标签：
- 心率: {window['physiological_signals']['heart_rate']['mean_bpm']} bpm
- 步幅变异: {window['gait_features']['step_variability_ms']} ms
- 主观费力程度: {window['subjective_assessment']['rpe_score']}

请生成：
1. 运动强度描述
2. 疲劳状态评估
3. 动作质量评价
"""

# LLM 生成标签
llm_labels = llm_model.generate(prompt)

# 与 Fuzzy 结果对比
fuzzy_result = results_df[results_df['window_id'] == 'window_ST_000'].iloc[0]
print(f"LLM 标签: {llm_labels}")
print(f"Fuzzy 标签: {fuzzy_result['exercise_load_category']}, {fuzzy_result['fatigue_level_category']}")
```

---

## 📊 3 个维度的分类验证

### 维度 1: 运动负荷 (Exercise Load)
```
low       :  HR < 65% MHR
moderate  :  HR 55-85% MHR
high      :  HR 75-100% MHR
excessive :  HR > 95% MHR
```

### 维度 2: 疲劳等级 (Fatigue Level)
```
none     : Step Var<30ms + HR Recovery>20
mild     : Step Var 30-60ms + Fair Recovery
moderate : Step Var>60ms + Fair Recovery + Short Stride
severe   : Step Var>60ms + Poor Recovery OR RPE>=9
```

### 维度 3: 动作质量 (Movement Quality)
```
good     : Stable gait + Normal stride
degraded : Slightly unstable OR short stride
poor     : At-risk variation OR significant stride reduction
```

---

## 🔍 质量检查

### JSON 验证清单
- ✅ 必需字段完整 (metadata, physiological_signals, gait_features)
- ✅ raw_feature_values 包含 5 个必需值
- ✅ 时间戳格式正确
- ✅ 数值范围合理

### CSV 验证清单
- ✅ 分类标签有效 (low/moderate/high/excessive 等)
- ✅ 置信度 0-1 之间
- ✅ 窗口 ID 与 JSON 对应
- ✅ 无缺失值

---

## ⚙️ 参数调整

### 调整 Fuzzy 隶属度范围
编辑 `fuzzy_classifier.py` 中的阈值：

```python
def _get_hr_membership(self, hr_mean):
    # 默认: [65%, 85%, 100%] MHR
    # 修改为: [60%, 80%, 95%] MHR
    hr_high = self._triangular_mf(
        hr_mean,
        int(0.60*self.mhr),  # ← 修改
        int(0.80*self.mhr),  # ← 修改
        int(0.95*self.mhr)   # ← 修改
    )
```

---

## 📚 相关文件

| 文件 | 用途 |
|------|------|
| `windows_json_exporter.py` | JSON 导出模块 |
| `validate_with_fuzzy.py` | Fuzzy 验证引擎 |
| `fuzzy_classifier.py` | Mamdani 分类器 (核心) |
| `end_to_end_test.py` | 完整流程测试 |

---

## 🎯 下一步

1. **准备特征数据**
   ```python
   df = pd.read_csv("your_features.csv")
   ```

2. **导出 JSON**
   ```python
   exporter.batch_export(df, "sub_01", "st_control")
   ```

3. **Fuzzy 分类**
   ```bash
   python validate_with_fuzzy.py --input_dir ./window_jsons --age 70 --report
   ```

4. **用 JSON 处理 LLM**
   ```python
   # 将 JSON 作为语料提供给 LLM
   ```

5. **对比结果**
   ```python
   # 对比 LLM 标签 vs Fuzzy 基准
   ```

---

**版本**: 1.0  
**最后更新**: 2026-04-19
