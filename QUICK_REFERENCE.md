# DUO-GAIT 数据处理 - 快速参考卡

## 🚀 30秒快速开始

```python
from data_loader import DUOGaitDataLoader
from data_align import DataAligner
from validation import ProcessedDataValidator

loader = DUOGaitDataLoader()
aligner = DataAligner()
validator = ProcessedDataValidator(loader)

# 1. 元数据
subject = loader.get_subject_info("sub_01")
mhr = loader.get_mhr("sub_01")

# 2. 加载数据
interim_imu = loader.load_interim_imu("sub_01", "st_control", "LF")
hr_aligned = aligner.extract_aligned_hr("sub_01", "st", "st_control")
processed = loader.load_processed_aggregate("sub_01", "st_control")

# 3. 验证结果
comparisons = validator.validate_metrics("sub_01", "st_control", py_results)
validator.print_validation_report(comparisons)
```

---

## 📍 文件位置速查表

| 数据层 | 位置 | 用途 | 我应该... |
|------|------|------|---------|
| **RAW** | `/Volumes/ChouSSD/.../DUO-GAIT/raw/` | 原始连续数据 | 提取 heart_rate.CSV，需要定位 Visit |
| **INTERIM** | `/Volumes/.../DUO-GAIT/interim/OG_st_control/` 等 | 6分钟切分片段 | 用其行数计算时间长度 |
| **PROCESSED** | `/Volumes/.../DUO-GAIT/processed/OG_st_control/` 等 | 已计算参数 | 对比验证我的算法 |

---

## 📊 关键参数速查表

| 参数 | 文件 | 字段名 | 单位 | 应用 |
|------|------|--------|------|------|
| 年龄 | subject_info.csv | age | years | MHR = 220 - age |
| MHR | 计算得出 | - | bpm | HR 合理性检查 |
| ST Baseline HR | subject_info.csv | st_HR_baseline | bpm | 验证初始心率 |
| ST Peak HR | subject_info.csv | st_HR_fatigue | bpm | 验证最大心率 |
| 步幅 | processed/.../aggregate_params.csv | stride_lengths_avg | m | 对比验证 |
| 步频 | processed/.../aggregate_params.csv | cadence_avg | steps/min | 对比验证 |
| 速度 | processed/.../aggregate_params.csv | speed_avg | m/s | 对比验证 |
| 变异系数 | processed/.../aggregate_params.csv | stride_lengths_CV | - | 稳定性指标 |

---

## 🔄 数据关系图

```
┌─────────────────────────────────────────────────────┐
│           Subject_info.csv (元数据)                  │
│  age, st_HR_baseline, st_HR_fatigue, dt_HR_*      │
└──────────────────┬──────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│   RAW 层         │  │  INTERIM 层      │
│ (连续录制)       │  │ (6分钟切分)      │
│ LF.csv →36MB    │  │ LF.csv →4MB     │
│ heart_rate.CSV  │  │ 采样率: 128Hz    │
│ 采样率: 1Hz     │  │ 行数: ~48,500    │
│                  │  │                  │
│ 需要定位时间戳   │◄─┤ 用行数推断时间  │
│ (Visit A/B)      │  │ 长度            │
└────────┬─────────┘  └──────────┬──────┘
         │                       │
         │    ┌──────────────────┘
         │    │
         │    ▼
         │  ┌──────────────────┐
         │  │  Python 算法    │
         │  │  计算步频/步幅  │
         │  └────────┬─────────┘
         │           │
         │           ▼
         │  ┌──────────────────┐
         └─►│  PROCESSED 层   │
            │ (参数基准)       │
            │ aggregate:      │
            │  -cadence_avg   │
            │  -speed_avg     │
            │  -stride_CV     │
            └──────────┬───────┘
                       │
                       ▼
            ┌───────────────────────┐
            │  验证对比             │
            │ Python vs Baseline    │
            │ 计算误差百分比        │
            └───────────────────────┘
```

---

## ⏱️ 时间转换公式

| 已知 | 求解 | 公式 | 例子 |
|-----|------|------|------|
| Interim CSV 行数 | 时间长度(秒) | `rows / 128` | 48,500 / 128 = 378.9 秒 |
| 时间长度(秒) | Interim CSV 行数 | `seconds * 128` | 379 * 128 = 48,512 行 |
| Raw HR 索引范围 | 时间长度(秒) | `(end - start) / 1` | (100 - 10) / 1 = 90 秒 |

---

## ✅ 数据质量检查清单

运行任何分析前，检查：

- [ ] HR 最小值 > 30 bpm
- [ ] HR 最大值 < MHR × 1.15
- [ ] HR 最大值 > subject_info['st_HR_fatigue'] × 0.85
- [ ] HR 初始值 ≈ subject_info['st_HR_baseline'] (误差 < 20%)
- [ ] HR 最大值 ≈ subject_info['st_HR_fatigue'] (误差 < 10%)
- [ ] HR 段长度 ≈ interim 时间长度 (误差 < 1 分钟)

---

## 🎯 验证误差容忍范围

| 指标 | 可接受范围 | 说明 |
|------|----------|------|
| **Baseline HR** | < 20% | 个体差异 |
| **Step Frequency** | < 5% | 采样结果 |
| **Step Length** | < 10% | 运动学差异 |
| **Speed** | < 10% | 综合指标 |
| **CV (变异系数)** | < 20% | 变异性较大 |
| **Peak HR** | < 2% | 采样精度最高 |

---

## 📁 PyCharm IDE 项目结构建议

```
elder_rehab/
├── signal_processing_pipeline/
│   ├── __init__.py
│   ├── config.py
│   ├── data_loader.py          ⭐ 新增
│   ├── data_align.py           ⭐ 新增
│   ├── validation.py           ⭐ 新增
│   ├── modules/
│   │   ├── step_frequency.py
│   │   ├── step_length.py
│   │   └── __init__.py
│   └── tests/
│       ├── test_data_loader.py ⭐ 新增
│       └── test_validation.py  ⭐ 新增
│
├── DATA_ARCHITECTURE_GUIDE.md       ⭐ 本指南
├── PYTHON_IMPLEMENTATION_GUIDE.md   ⭐ 本指南
├── QUICK_REFERENCE.md               ⭐ 本文件
└── examples/
    └── example_workflow.py          ⭐ 新增
```

---

## 🔗 跨文档导航

| 文档 | 内容 | 链接 |
|-----|------|------|
| **DATA_ARCHITECTURE_GUIDE.md** | 完整的数据层结构说明 + 工作流程 | 详细理论 |
| **PYTHON_IMPLEMENTATION_GUIDE.md** | 代码实现细节 + 完整工具类 | 代码实现 |
| **QUICK_REFERENCE.md** | 🔴 **本文件** - 速查表和快速示例 | 快速查询 |

**建议阅读顺序**：
1. 先读本文 (3 分钟) - 了解总体结构
2. 再读 DATA_ARCHITECTURE_GUIDE (20 分钟) - 理解原理
3. 最后读 PYTHON_IMPLEMENTATION_GUIDE (30 分钟) - 实现代码

---

## 💡 常见问题速答

### Q: 为什么 raw HR 需要定位？
A: Raw 是连续录制的完整数据，可能包含多个 Visit 和任务，需要找到对应的时间段。

### Q: INTERIM 的行数和时间长度怎么对应？
A: 采样率固定 128 Hz，所以 `行数 / 128 = 秒数`。例如 48,512 行 = 379 秒。

### Q: PROCESSED 数据用来做什么？
A: 作为验证基准，对比 Python 算法的输出，检查准确性 (通常误差 < 10%)。

### Q: 步频怎么计算?
A: 从 processed 的 `cadence_avg`（steps/min），转换为 `cadence_avg / 60` (steps/s)。

### Q: 哪个指标最重要？
A: **Peak HR** (最准确, 误差 <2%) → **Step Frequency** (误差 <5%) → **Speed** (误差 <10%)

---

## 🛠️ 故障排除

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| HR 数据里有 NaN | CSV 格式问题 | 检查 skiprows 参数是否正确 |
| Step frequency 与 processed 差异大 (>10%) | 采样率计算错误 | 确认使用了 128 Hz |
| 找不到对应的 HR 段 | Visit 定位错误 | 检查 subject_info 中的 dual_task_visit |
| Subject_info 字段报错 | 字段名拼写 | 用 loader.load_subject_info() 查看正确列名 |

---

## 📞 内部文件关系图

```
QUICK_REFERENCE.md (本文)
    │
    ├───► DATA_ARCHITECTURE_GUIDE.md
    │     ├─ 三层数据结构详解
    │     ├─ 处理流程说明
    │     └─ 完整使用示例 (Python)
    │
    └──────► PYTHON_IMPLEMENTATION_GUIDE.md
          ├─ DUOGaitDataLoader 类
          ├─ DataAligner 类
          ├─ ProcessedDataValidator 类
          └─ 完整工作流代码
```

---

## 版本和更新

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| 1.0 | 2026-04-19 | 初始版本 - 三层数据架构说明 |
| - | - | - |

**最后更新**: 2026-04-19  
**维护者**: Research Team  
**下一更新**: 根据实际应用反馈
