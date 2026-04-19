# Mamdani 模糊推理系统 - 实现指南

## 📋 概述

本模块实现了基于 **Mamdani 模糊推理系统** 的三维运动分类器，用于 DUO-GAIT 数据集的自动标注。

**三个输出维度：**
1. **Exercise Load** (运动负荷): low / moderate / high / excessive
2. **Fatigue Level** (疲劳等级): none / mild / moderate / severe  
3. **Movement Quality** (动作质量): good / degraded / poor

---

## 🎯 核心模块

### 1. `fuzzy_classifier.py`
Mamdani 模糊推理系统的核心实现

**关键类：**
```python
classifier = FuzzyExerciseClassifier(age=70)  # MHR = 220 - age

# 分类单个窗口
result = classifier.classify(
    hr_mean=100,           # bpm
    step_var=25,           # ms (ISI 标准差)
    hr_recovery=18,        # bpm/min
    stride_length=0.55,    # m
    rpe_score=12           # Borg 6-20
)
# 返回 {
#     'exercise_load': (2.3, 'high'),
#     'fatigue_level': (1.8, 'mild'),
#     'movement_quality': (0.4, 'good'),
#     'confidence': 1.0,
#     'reasoning': '...'
# }
```

**隶属度函数（内置）：**
- 三角形函数 (triangular): 平滑的山形
- 梯形函数 (trapezoidal): 平顶的梯形

---

### 2. `process_windows_fuzzy.py`
批量处理 30s 窗口特征数据的脚本

**使用方法：**
```bash
python process_windows_fuzzy.py \
    --input features_windows.csv \
    --output output_labels.csv \
    --subject sub_01 \
    --age 70 \
    --report
```

**输入 CSV 格式：**
```
timestamp,hr_mean,step_var,hr_recovery,stride_length,rpe_score
window_001,105,22,18.5,0.55,12
window_002,110,28,16.2,0.53,12
...
```

**输出 CSV 格式：**
```
timestamp,exercise_load_value,exercise_load_category,fatigue_level_value,fatigue_level_category,movement_quality_value,movement_quality_category,confidence,reasoning
window_001,2.3,high,1.8,mild,0.4,good,1.0,"HR: 105 bpm (70% MHR) - 中等强度 | ..."
```

---

## 📊 模糊规则系统

### 维度 1: 运动负荷 (Exercise Load)

**输入隶属度：**
| 隶属度集合 | 范围 | 说明 |
|---------|------|------|
| low | 40-65% MHR | 轻度强度 |
| moderate | 55-85% MHR | 中等强度 |
| high | 75-100% MHR | 高强度 |
| excessive | 95%+ MHR | 过高强度 ⚠️ |

**规则：**
```
IF HR is low         THEN Load is low
IF HR is moderate    THEN Load is moderate
IF HR is high        THEN Load is high
IF HR is excessive   THEN Load is excessive

# RPE 冲突检测（安全优先原则）
IF RPE is heavy AND HR is moderate THEN Load is high (冲突升级)
IF RPE is heavy AND HR is high     THEN Load is excessive (冲突升级)
```

---

### 维度 2: 疲劳等级 (Fatigue Level)

**输入隶属度：**

| 输入维度 | 隶属度集合 | 阈值 |
|--------|---------|------|
| **step_var** | stable | <35 ms |
| | unstable | 25-65 ms |
| | at_risk | >55 ms ⚠️ |
| **hr_recovery** | poor | <15 bpm/min ⚠️ |
| | fair | 10-25 bpm/min |
| | good | >20 bpm/min ✓ |
| **stride_length** | short | <0.45 m |
| | normal | >0.38 m |
| **rpe_score** | light | <8 |
| | moderate | 7-10 |
| | heavy | >9 ⚠️ |

**规则评分系统：**
```
IF (step_var < 30 ms)           → fatigue += 0  (稳定)
IF (30 ≤ step_var < 60 ms)      → fatigue += 1  (有变异)
IF (step_var ≥ 60 ms)           → fatigue += 2  (严重 ⚠️)

IF (hr_recovery > 20 bpm/min)   → fatigue += 0  (恢复快)
IF (12 ≤ hr_recovery ≤ 20)      → fatigue += 1  (恢复一般)
IF (hr_recovery < 12 bpm/min)   → fatigue += 2  (恢复差 ⚠️)

IF (stride_length < 0.40 m)     → fatigue += 1  (步长短)

IF (rpe_score >= 9)             → fatigue += 1  (自报费力)

总分映射：
  fatigue_score = 0        → 'none'
  fatigue_score = 1-2      → 'mild'
  fatigue_score = 3        → 'moderate'
  fatigue_score ≥ 4        → 'severe' ⚠️
```

---

### 维度 3: 动作质量 (Movement Quality)

**规则：**
```
IF (step_var is stable) AND (stride_length is normal)
  → movement_quality is good ✓

IF (step_var is unstable) AND (stride_length is normal)
  OR (step_var is stable) AND (stride_length is short)
  → movement_quality is degraded (注意)

IF (step_var is at_risk) OR (stride_length is short AND step_var is unstable)
  → movement_quality is poor ⚠️
```

---

## 🏥 安全门槛值

**自动警告条件：**

| 信号 | 阈值 | 响应 |
|-------|------|------|
| HR_max | > 180 bpm | 立即中止，记录高心脏负荷 |
| HR | > MHR × 110% | 标记 excessive + 警告 |
| step_var | > 100 ms | 标记严重疲劳 |
| stride_length | < 0.25 m | 标记运动能力受损 |
| hr_recovery | < 3 bpm/min | 标记恢复困难 |

---

## 💻 集成到现有管道

### 步骤 1: 计算 30s 窗口特征

使用现有的 signal_processing_pipeline 计算以下指标：

```python
from signal_processing_pipeline import (
    calculate_hr_metrics,
    calculate_gait_metrics,
    calculate_fatigue_indices
)

# 对每个 30s 窗口计算
features = {
    'timestamp': '00:00',
    'hr_mean': 105.0,
    'step_var': 22.5,      # ISI std dev (ms)
    'hr_recovery': 18.0,   # HR slope (bpm/min)  
    'stride_length': 0.55,
    'rpe_score': 12        # 从实验记录或默认值
}
```

### 步骤 2: 批量分类

```python
from signal_processing_pipeline.fuzzy_classifier import (
    FuzzyExerciseClassifier,
    classify_batch
)

# 创建分类器
classifier = FuzzyExerciseClassifier(age=70)

# 分类一批窗口
windows = [...]  # 特征字典列表
results = classify_batch(classifier, windows)

# 保存结果
results_df = pd.DataFrame(results)
results_df.to_csv('classified_windows.csv', index=False)
```

### 步骤 3: 生成报告

```bash
python process_windows_fuzzy.py \
    --input features_windows.csv \
    --output final_labels.csv \
    --subject sub_01 \
    --age 70 \
    --report
```

输出包含：
- `final_labels.csv` - 完整的分类结果
- `classification_summary.txt` - 分布统计和异常检测

---

## 📈 典型分类结果

### 场景 A: 正常康复步行
```
HR: 100 bpm (67% MHR) - 中等强度
Step Var: 25 ms - 稳定
HR Recovery: 18 bpm/min - 一般
Stride: 0.55 m - 正常

✓ 结果：
  负荷: moderate (1.5)
  疲劳: mild (1.8)
  质量: good (0.3)
```

### 场景 B: 强度训练 (有疲劳迹象)
```
HR: 135 bpm (90% MHR) - 高强度
Step Var: 75 ms - 显著变异
HR Recovery: 8 bpm/min - 恢复差
Stride: 0.35 m - 步长短

⚠️ 结果：
  负荷: high (2.9)
  疲劳: severe (3.8)
  质量: poor (1.8)
```

### 场景 C: 危险指标 (立即停止)
```
HR: 160 bpm (107% MHR) - 过高
Step Var: 95 ms - 严重变异
HR Recovery: 3 bpm/min - 极差恢复
Stride: 0.25 m - 显著缩短

🚨 结果：
  负荷: excessive (3.8)
  疲劳: severe (3.8)
  质量: poor (1.8)
  
⚠️ 警告标记：high_cardiac_load, stop_exercise
```

---

## 🔧 参数调整指南

如果分类结果需要调整，修改 `fuzzy_classifier.py` 中的隶属函数参数：

```python
def _get_hr_membership(self, hr_mean):
    """HR 隶属度计算 - 可调整的参数"""
    
    # 示例：调整"高强度"范围
    # 原: [0.75*MHR, 0.9*MHR, 1.0*MHR]
    # 新: [0.80*MHR, 0.95*MHR, 1.05*MHR] (更严格)
    
    hr_high = self._triangular_mf(
        hr_mean,
        int(0.80*self.mhr),  # ← 修改起点
        int(0.95*self.mhr),  # ← 修改顶点
        int(1.05*self.mhr)   # ← 修改终点
    )
```

---

## 📚 与现有系统的关系

```
DUO-GAIT 原始数据
    ↓
process_pipeline.py (计算 30s 窗口特征)
    ├─ hr_mean, step_var, ...
    └─ output: features_windows.csv
    ↓
fuzzy_classifier.py (三维分类)
    ├─ Dim 1: Exercise Load
    ├─ Dim 2: Fatigue Level
    └─ Dim 3: Movement Quality
    ↓
process_windows_fuzzy.py (批量处理)
    ├─ 加载特征
    ├─ 应用分类
    └─ output: output_labels.csv
    ↓
最终产物
    ├─ output_labels.csv (详细分类)
    └─ classification_summary.txt (统计报告)
```

---

## ⚙️ 依赖项

```
numpy>=1.20.0
scipy>=1.6.0
pandas>=1.2.0
scikit-fuzzy>=0.4.2
```

安装：
```bash
pip install scikit-fuzzy
```

---

## 🧪 单元测试

运行内置测试：
```bash
python signal_processing_pipeline/fuzzy_classifier.py
```

预期输出：3 个测试场景的分类结果 (正常 / 高强度+疲劳 / 危险)

---

## 📝 常见问题

**Q: 如何应对没有 RPE_score 的数据？**  
A: 使用默认值 12 (中等)，process_windows_fuzzy.py 会自动填充。

**Q: 能否针对不同年龄调整阈值？**  
A: 是的。创建分类器时指定年龄：`FuzzyExerciseClassifier(age=75)`

**Q: 置信度 (confidence) 代表什么？**  
A: 基于 HR 和步伐变异是否在理想范围内 (0-1)。低置信度 (<0.6) 表示数据异常。

---

## 📞 支持

详见：
- `DATA_ARCHITECTURE_GUIDE.md` - 数据层结构
- `QUICK_REFERENCE.md` - 快速参数查询
- `PYTHON_IMPLEMENTATION_GUIDE.md` - 完整 API 文档
