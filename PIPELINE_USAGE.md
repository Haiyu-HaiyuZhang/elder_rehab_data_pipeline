# 🚀 DUO-GAIT 数据处理流程 - 使用指南

## 快速开始

### 方法 1️⃣: 使用 Python 脚本（推荐 ⭐）

```bash
# 处理 sub_01，任务 st
cd /Users/zhanghaiyu/workspace/elder_rehab
python3 run_pipeline.py sub_01 st

# 或指定其他受试者
python3 run_pipeline.py sub_02 control
python3 run_pipeline.py sub_03 st
```

### 方法 2️⃣: 使用 Bash 脚本

```bash
cd /Users/zhanghaiyu/workspace/elder_rehab
chmod +x run_full_pipeline.sh
./run_full_pipeline.sh sub_01 st
```

### 方法 3️⃣: 手动逐步运行

```bash
cd /Users/zhanghaiyu/workspace/elder_rehab

# 步骤 1: 生成 JSON 窗口
python3 process_duogait_to_json.py --subject sub_01 --task st

# 步骤 2: 应用 Fuzzy 分类并生成 CSV
python3 -c "
import sys
sys.path.insert(0, 'signal_processing_pipeline')
from validate_with_fuzzy import FuzzyValidationEngine
from pathlib import Path

engine = FuzzyValidationEngine(age=24, verbose=True)
json_files = sorted(Path('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/').glob('sub_01_st_window_*.json'))
results = engine.validate_batch_from_jsons(json_files)
results.to_csv('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/results/fuzzy_results_sub_01_st.csv', index=False)
print('✅ 完成')
"
```

---

## 📋 完整流程说明

### 流程概图

```
原始数据 (ST.csv, heart_rate.CSV)
         ↓ process_duogait_to_json.py
JSON 窗口 (30秒滑动窗口，97个)
         ↓ validate_with_fuzzy.py
CSV 结果 (分类、置信度、质量标志)
```

### 每一步详细说明

#### 🔍 步骤 1: 验证原始数据
- 检查 `/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/sub_01/` 目录
- 确认 `ST.csv`（IMU 传感器数据）和 `heart_rate.CSV`（心率数据）存在

**输入**: 原始 CSV 文件  
**检查**: 文件大小、行数、数据范围

#### 📝 步骤 2: 生成 JSON 窗口
运行: `process_duogait_to_json.py`

**功能**:
- 读取原始 IMU 和 HR 数据
- 按 30 秒滑动窗口分段
- 计算每个窗口的特征（步频、步长、步时变异性等）
- 评估数据质量
- 输出 JSON 格式

**输入**: `sub_01/ST.csv`, `sub_01/heart_rate.CSV`  
**输出**: `sub_01_st_window_0000.json` ... `sub_01_st_window_0096.json` (97 个文件)

**JSON 结构**:
```json
{
  "metadata": {
    "window_id": "window_ST_000",
    "player_id": "sub_01",
    "session_id": "session_sub_01_st",
    "timestamp": "2026-04-19T18:38:41.353043Z",
    "window_sec": 30
  },
  "imu": {
    "features": {
      "step_frequency_hz": 1.71,
      "step_length_m": 0.55,
      "step_time_variability_ms": 100.0
    },
    "data_quality": 0.85,
    "quality_reason": "clean signal"
  },
  "heart_rate": {
    "features": {
      "hr_mean_bpm": 80.0,
      "hr_max_bpm": 100.0,
      "hr_recovery_bpm_per_min": 5.0
    },
    "data_quality": 0.85,
    "quality_reason": "clean signal"
  }
}
```

#### 🤖 步骤 3: Fuzzy Logic 分类（LLM 对齐）
运行: `validate_with_fuzzy.py`

**功能**:
- 读取所有 JSON 窗口
- 应用 **3 维 Fuzzy Logic 分类**:
  - **Dim 1**: Exercise Load (低/中/高/过高)
  - **Dim 2**: Fatigue Level (无/轻/中/重)
  - **Dim 3**: Movement Quality (良好/降低/差) ← **LLM 对齐**
- 生成置信度分数
- 考虑数据质量权重
- 输出 CSV

**Movement Quality (Dim 3) 规则** - 完全对齐 LLM 规范:

| 指标 | Good | Degraded | Poor |
|------|------|----------|------|
| Cadence (Hz) | [1.6, 2.0] | [1.4,1.6)∪(2.0,2.2] | <1.4 ∪ >2.2 |
| Stride (m) | [0.45, 0.65] | [0.35,0.45)∪(0.65,0.75] | <0.35 ∪ >0.75 |
| Var (ms) | <30 | 30-60 | >60 |

**输入**: 所有 `sub_01_st_window_*.json` 文件  
**输出**: `fuzzy_results_sub_01_st.csv`

---

## 📊 输出文件说明

### JSON 文件位置
```
/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/
├── sub_01_st_window_0000.json
├── sub_01_st_window_0001.json
├── ...
└── sub_01_st_window_0096.json   (共 97 个窗口)
```

### CSV 结果文件位置
```
/Volumes/ChouSSD/elder_datasets/DUO-GAIT/results/
└── fuzzy_results_sub_01_st.csv
```

### CSV 列说明

```python
# 元数据
'window_id'          # 窗口 ID
'subject_id'         # 受试者 ID
'task_type'          # 任务类型
'timestamp'          # 时间戳

# IMU 特征
'cadence_hz'         # 步频 (Hz)
'stride_length'      # 步长 (m)
'step_var_ms'        # 步时变异性 (ms)

# HR 特征
'hr_mean'            # 平均心率 (bpm)
'hr_recovery'        # 心率恢复速率 (bpm/min)
'rpe_score'          # 主观费力程度

# 分类结果（值 + 类别）
'exercise_load_score'        # 负荷分数
'exercise_load_category'     # low/moderate/high/excessive
'fatigue_level_score'        # 疲劳分数
'fatigue_level_category'     # none/mild/moderate/severe
'movement_quality_score'     # 质量分数
'movement_quality_category'  # good/degraded/poor ← LLM对齐

# 数据质量
'imu_quality'        # IMU 质量 (0-1)
'hr_quality'         # HR 质量 (0-1)
'imu_quality_flag'   # high/low
'hr_quality_flag'    # high/low

# 置信度
'confidence'         # 分类置信度 (0-1)
'mhr'                # 最大心率 (bpm)
'hr_percent_mhr'     # HR 占 MHR 的百分比
```

---

## 🔧 命令行参数

### `run_pipeline.py`

```bash
python3 run_pipeline.py [SUBJECT] [TASK] [OPTIONS]

位置参数:
  SUBJECT              受试者 ID (default: sub_01)
                      例: sub_01, sub_02, sub_03, ...
  TASK                 任务类型 (default: st)
                      例: st, control, ...

可选参数:
  --skip-json          跳过 JSON 生成，直接使用现有文件
  -h, --help          显示帮助信息

例子:
  python3 run_pipeline.py                    # sub_01, st
  python3 run_pipeline.py sub_02             # sub_02, st
  python3 run_pipeline.py sub_03 control     # sub_03, control
  python3 run_pipeline.py sub_01 st --skip-json  # 跳过 JSON 生成
```

### `process_duogait_to_json.py`

```bash
python3 process_duogait_to_json.py [OPTIONS]

可选参数:
  --subject SUBJECT         受试者 ID (default: sub_01)
  --task TASK              任务类型 (default: st)
  --output_dir DIR         输出目录
  --verbose               打印详细信息
  -h, --help             显示帮助信息
```

---

## 📈 典型输出示例

### Sub_01 分类结果

```
✓ JSON 生成完成: 97 个窗口

✓ 分类完成: 97 个窗口

📊 分类分布:

  Exercise Load:
    • excessive     :   0 (  0.0%)
    • high          :   0 (  0.0%)
    • low           :  97 (100.0%)
    • moderate      :   0 (  0.0%)

  Fatigue Level:
    • mild          :   0 (  0.0%)
    • moderate      :   0 (  0.0%)
    • none          :   0 (  0.0%)
    • severe        :  97 (100.0%)

  Movement Quality (Dim 3 - LLM Aligned):
    • degraded      :   3 (  3.1%)
    • good          :   1 (  1.0%)
    • poor          :  93 ( 95.9%)

✓ 结果已保存到: /Volumes/ChouSSD/elder_datasets/DUO-GAIT/results/fuzzy_results_sub_01_st.csv

前 5 个窗口的分类结果:
   window_id  cadence_hz  stride_length  step_var_ms exercise_load_category fatigue_level_category movement_quality_category  confidence
window_ST_000        1.71           0.55        100.0                    low                 severe                      poor        0.55
window_ST_001        1.07           0.55        100.0                    low                 severe                      poor        0.55
window_ST_002        0.95           0.55        100.0                    low                 severe                      poor        0.55
window_ST_003        1.07           0.55        100.0                    low                 severe                      poor        0.55
window_ST_004        1.83           0.58        100.0                    low                 severe                      poor        0.55
```

---

## ✅ 验证清单

运行完成后，验证：

- [ ] JSON 文件生成: 97 个窗口 ✓
- [ ] CSV 文件创建: `/Volumes/ChouSSD/elder_datasets/DUO-GAIT/results/fuzzy_results_sub_01_st.csv` ✓
- [ ] CSV 有数据: `wc -l fuzzy_results_sub_01_st.csv` 应该是 98 行 (1 标题 + 97 数据)
- [ ] Movement Quality 分布合理: 1 good, 3 degraded, 93 poor
- [ ] 年龄正确: sub_01 应该是 24 岁（从 subject_info.csv 查询）
- [ ] MHR 计算正确: 220 - 24 = 196 bpm

---

## 🐛 常见问题

### Q1: JSON 文件找不到？
**A**: 检查是否已运行 `process_duogait_to_json.py`
```bash
ls -l /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/ | head
```

### Q2: 年龄信息错误？
**A**: 检查 subject_info.csv 是否存在且有正确的数据
```bash
grep sub_01 /Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/subject_info.csv
```

### Q3: CSV 结果为空？
**A**: 检查 JSON 文件是否正确生成
```bash
head -20 /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/sub_01_st_window_0000.json
```

### Q4: 分类全是 "unknown"？
**A**: 检查数据质量是否都 < 0.6
```bash
# 检查 JSON 中的数据质量
python3 -c "import json; print(json.load(open('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/sub_01_st_window_0000.json'))['imu']['data_quality'])"
```

---

## 🎯 下一步

1. **处理更多受试者**:
   ```bash
   for subj in sub_01 sub_02 sub_03; do
     python3 run_pipeline.py $subj st
   done
   ```

2. **合并所有结果**:
   ```bash
   cat /Volumes/ChouSSD/elder_datasets/DUO-GAIT/results/fuzzy_results_*.csv > all_results.csv
   ```

3. **与 LLM 输出对比**:
   - 准备 LLM 分类结果
   - 对齐格式
   - 计算一致性

---

## 📚 相关文件

- `process_duogait_to_json.py` - JSON 生成脚本
- `signal_processing_pipeline/fuzzy_classifier.py` - Fuzzy Logic 分类器
- `signal_processing_pipeline/validate_with_fuzzy.py` - 批量验证引擎
- `IMPLEMENTATION_SUMMARY.md` - 实现细节
- `LLM_RULE_SPEC.md` - LLM 规则规范

---

**最后更新**: 2026-04-20  
**状态**: ✅ 完全对齐 LLM 规则
