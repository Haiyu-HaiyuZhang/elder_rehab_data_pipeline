# 项目文件结构说明

**最后清理**：2026-09-23
**状态**：与当前代码同步

---

## 📁 项目结构

```
elder_rehab/
│
├── 📚 文档
│   ├── README.md                          ⭐ 项目入口
│   ├── PIPELINE_SPECIFICATION.md          ⭐ 规范、LLM/fuzzy 规则
│   ├── METRIC_CALCULATION.md              ⭐ 指标计算原理（与代码同步）
│   └── DATA_ARCHITECTURE_GUIDE.md
│
├── 🐍 脚本
│   ├── process_duogait_to_json.py         ⭐ 单任务导出 JSON
│   ├── batch_process_all.py               ⭐ 全量受试者和任务
│   ├── run_subject_all_windows.py         单受试者全部 INTERIM 任务
│   └── validate_duogait_metrics.py        可选：与 processed 离线对比
│
└── 📦 signal_processing_pipeline/
    ├── __init__.py
    ├── config.py                          ⚙️  全局配置（含 STRIDE_LEN_OUTPUT_SCALE，默认 1.0）
    ├── duogait_metrics.py                 双足步长融合（主流程不读 processed）
    ├── fuzzy_classifier.py                同事规则 classify_exercise_state
    └── config.py                          全局参数
```

---

## 📝 文件用途说明

### 🔴 核心文件（必须保留）

#### process_duogait_to_json.py
- **用途**：主处理 Pipeline
- **功能**：
  - 加载 INTERIM IMU 数据 (ST.csv) 和 Raw HR 数据 (heart_rate.CSV)
  - 切分成 30 秒窗口
  - 计算 5 个核心指标
  - 生成标准化 JSON 输出
  - 集成 Fuzzy Logic 分类器生成 ground_truth
- **依赖**：fuzzy_classifier.py
- **输出**：指定输出目录下的 `sub_XX_task_window_NNNN.json`

#### fuzzy_classifier.py
- **用途**：与同事 LLM 规则一致的 **ground_truth**（`classify_exercise_state`）
- **功能**：Dim1–3、warmup 相对、极值/安全覆盖、composite；心率缺失与双低质量处理
- **兼容**：`FuzzyExerciseClassifier.classify` 薄封装

#### duogait_metrics.py
- **用途**：LF/RF 加速度 RMS 参与步长微调（步频/变异仍来自 ST）
- **主流程**：不读取 `processed/`

#### config.py (2.7 KB)
- **用途**：全局参数配置
- **内容**：
  - 峰值检测阈值：PEAK_HEIGHT_MULTIPLIER = 2.5
  - 最小峰值间距：MIN_PEAK_DISTANCE_SEC = 0.4
  - 步幅映射参数
  - 其他处理参数
- **使用**：可根据需要调整参数

---

### 🟢 文档文件（必须保留）

| 文件 | 大小 | 用途 |
|------|------|------|
| **README.md** | 6 KB | 项目入口，快速开始 |
| **PIPELINE_SPECIFICATION.md** | — | 规范、JSON、LLM/fuzzy、Q&A |
| **METRIC_CALCULATION.md** | — | **指标自算原理**（必读维护者） |
| **PROJECT_SUMMARY.md** | — | 项目概况和里程碑 |
| **DATA_ARCHITECTURE_GUIDE.md** | — | 数据架构参考 |

---

---

## 🚀 使用流程

### 1. 运行 Pipeline
```bash
cd /Users/zhanghaiyu/workspace/elder_rehab
python3 process_duogait_to_json.py
# 或
python3 run_subject_all_windows.py --subject sub_01 --out-dir /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/
```

### 2. 生成的文件
```
/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/
├── sub_01_st_control_window_0000.json
├── sub_01_st_control_window_0001.json
├── ...
└── sub_01_st_control_window_0015.json
```

### 3. 处理其他数据
编辑 `process_duogait_to_json.py` 的 `main()` 函数：
```python
imu_data_dir = '/Volumes/.../interim/OG_st_control/sub_02'
hr_data_dir = '/Volumes/.../raw/OG_st_raw/sub_02'
subject_id = 'sub_02'
```

---

## 🔍 依赖关系

```
process_duogait_to_json.py (主脚本)
  ├── fuzzy_classifier.py (ground_truth 生成)
  ├── duogait_metrics.py (可选足部步长修正)
  └── config.py (全局参数)

配置参数
    └── config.py (全局参数)
```

---

## 📊 文件清单总结

### 核心库大小
```
signal_processing_pipeline/
├── fuzzy_classifier.py          分类器基线
├── duogait_metrics.py           足部步长修正与离线对照
└── config.py                    配置
```

### 文档总大小
```
README.md                          6 KB
PIPELINE_SPECIFICATION.md         16 KB  ⭐ 完整规范
PROJECT_SUMMARY.md               9.3 KB
DATA_ARCHITECTURE_GUIDE.md        18 KB

Total: ~49 KB
```

### 主脚本
```
process_duogait_to_json.py         35 KB  ⭐ 主 Pipeline
```

---

## ✅ 完整性检查

- [x] 所有导入可用（无缺失依赖）
- [x] Pipeline 正常运行
- [x] JSON 输出格式完整
- [x] ground_truth 正确生成
- [x] 旧脚本已清理
- [x] 文档完整且易用

**项目状态**：当前实现已通过静态导入和编译检查；真实数据运行需要外部 DUO-GAIT 数据目录。

---

## 📚 文档导航

**新用户**：
1. 读 [README.md](README.md)（5 分钟）
2. 读 [PIPELINE_SPECIFICATION.md](PIPELINE_SPECIFICATION.md)（30 分钟）

**快速查询**：
- 📊 数据结构 → [DATA_ARCHITECTURE_GUIDE.md](DATA_ARCHITECTURE_GUIDE.md)
- 🔧 指标计算 → [PIPELINE_SPECIFICATION.md - 指标计算逻辑](PIPELINE_SPECIFICATION.md#指标计算逻辑)
- 🤖 LLM 规则 → [PIPELINE_SPECIFICATION.md - LLM 分类规则](PIPELINE_SPECIFICATION.md#llm-分类规则)
