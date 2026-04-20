# LLM 规则规范与 Fuzzy Logic 对齐

## 一、IMU 绝对评分标准（从 LLM 提取）

### Cadence (Hz) - 步频
- **good**: [1.6, 2.0]
- **degraded**: [1.4, 1.6) ∪ (2.0, 2.2]
- **poor**: <1.4 ∪ >2.2

### Stride Length (m) - 步长
- **good**: [0.45, 0.65]
- **degraded**: [0.35, 0.45) ∪ (0.65, 0.75]
- **poor**: <0.35 ∪ >0.75

### Step-time Variability (ms) - 步时变异性
- **good**: <30
- **degraded**: 30–60
- **poor**: >60

---

## 二、Dim 3 — Movement Quality 评分规则

### 基础规则
1. **逐指标评分**: 
   - good=0, degraded=1, poor=2
2. **求和分类**:
   - Sum ≤1 → **good**
   - Sum 2–3 → **degraded**
   - Sum ≥4 → **poor**

### Override 规则（优先级最高）
1. **极端情况 Override**:
   - var >80ms **OR** stride <0.30m → **poor** (忽略 sum)
2. **组合情况 Override**:
   - var >60 **AND** stride <0.35 → **poor**

---

## 三、IMU 相对调整（Relative Adjustment）

**关键要求**：与 warmup baseline 对比

- **下降 ≥20% from warmup** → 严重程度升级一级
  - good → degraded
  - degraded → poor
- **波动 ±10% of warmup** → 保持绝对评分

**⚠️ 当前实现缺失**：我们现在没有 warmup baseline，暂时无法实现相对调整。

---

## 四、数据质量权重调整（Data Quality）

### 权重条件
```
imu.data_quality <0.6  → reduce IMU weight in reasoning
hr.data_quality <0.6   → reduce HR weight in reasoning
BOTH <0.6              → all dims "unknown", clinical_flag="data_invalid"
```

### 权重应用方法
- **high quality** (≥0.6): 100% 权重
- **low quality** (<0.6): 降权处理
  - 可能的做法：
    1. 输出 "unknown" 而非具体分类
    2. 提高阈值（被动延迟分类）
    3. 权重平均融合

---

## 五、Safety Override 检查

**在计算 Dim 3 Movement Quality 后**，需要检查安全条件：

```
If ANY:
  · var >80 AND HR >70% MHR → clinical_flag="hard_stop"
  · var >60 AND stride <0.35 → flag "fatigue_compensation"

Then:
  · movement_quality CANNOT be positive
  · Must trigger fatigue_risk composite state
```

---

## 六、必需的输入数据

为了完全实现 LLM 规则，Fuzzy Logic 需要：

| 数据项 | 当前状态 | 优先级 |
|------|--------|------|
| cadence (Hz) | ✓ JSON 有 | ✅ 立即需要 |
| stride_length (m) | ✓ JSON 有 | ✅ 立即需要 |
| step_time_variability_ms | ✓ JSON 有 | ✅ 立即需要 |
| warmup_baseline | ✗ 无 | ⚠️ 需要添加 |
| imu.data_quality | ✗ 无 | ⚠️ 需要计算 |
| hr.data_quality | ✗ 无 | ⚠️ 需要计算 |
| HR % MHR (age-based) | ✓ 有（已修复 age=24） | ✅ 立即需要 |
| RPE (Borg CR-10) | ✗ 无 | ⚠️ 可选，影响 Dim 1-2 |

---

## 七、实现路线图

### 阶段 1：立即修改 (Dim 3 - Movement Quality) ✅ COMPLETED
- ✅ 用上述绝对评分标准替换当前硬编码的值
- ✅ 添加 safety override 检查
- ✅ 集成 cadence (step_frequency_hz) 指标
- ✅ 修复 JSON 字段提取
- ✅ 添加数据质量权重调整
- ✅ 测试与 sub_01 完整数据集 (97 windows)
  - Result distribution: 1 good, 3 degraded, 93 poor
  - All rules correctly applied with override logic
  - CSV output: `/Volumes/ChouSSD/elder_datasets/DUO-GAIT/fuzzy_results_llm_aligned.csv`

### 阶段 2：中期改进 (数据质量)
⚠️ **状态**: 需要实现数据质量计算
- 为每个窗口计算 `imu.data_quality` 和 `hr.data_quality`
- 修改 Fuzzy Logic 权重调整逻辑

### 阶段 3：长期完善 (相对调整 + RPE)
⚠️ **状态**: 需要 warmup baseline 和 RPE 数据
- 实现相对调整 vs baseline
- 集成 RPE 影响因子

