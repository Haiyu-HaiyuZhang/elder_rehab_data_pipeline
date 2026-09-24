# 仓库结构

本仓库只保留当前可运行的 DUO-GAIT 离线处理链和与其直接相关的说明。

```text
elder_rehab/
├── README.md
├── PIPELINE_SPECIFICATION.md
├── METRIC_CALCULATION.md
├── DATA_ARCHITECTURE_GUIDE.md
├── FILES_STRUCTURE.md
├── process_duogait_to_json.py       # 核心处理器
├── batch_process_all.py              # 批量处理入口
├── run_subject_all_windows.py        # 单受试者全任务入口
├── validate_duogait_metrics.py       # 可选 processed 对照
└── signal_processing_pipeline/
    ├── __init__.py
    ├── config.py                     # 参数和环境变量
    ├── duogait_metrics.py            # LF/RF 步长修正和对照辅助
    ├── fuzzy_classifier.py           # ground_truth 规则基线
    └── requirements.txt
```

## 入口职责

### `process_duogait_to_json.py`

加载一个 INTERIM 任务目录和一个 RAW 心率目录，完成时间对齐、30 秒非重叠窗口切分、五个核心指标计算、质量评分、fuzzy 分类和 JSON 写出。

### `batch_process_all.py`

处理预定义的 16 个实际受试者和 6 个任务类型。支持 `--dry-run`、`--subjects`、`--tasks`、`--skip-existing` 和 `--verbose`。

### `run_subject_all_windows.py`

根据某个受试者扫描所有 `OG_*` INTERIM 目录，适合做单受试者完整导出。它会跳过缺少 `ST.csv` 或 `heart_rate.CSV` 的任务。

### `validate_duogait_metrics.py`

将主流程的窗口指标与 DUO-GAIT `processed/` 中的聚合/逐步表做参考比较。由于两者统计口径不同，该脚本不参与主流程，也不是严格真值验证。

## 核心库

- `config.py`：采样率、窗口大小、峰值检测阈值、步长缩放和兜底开关。
- `duogait_metrics.py`：足部 IMU RMS 步长修正，以及读取 processed 对照表的辅助函数。
- `fuzzy_classifier.py`：根据心率、步态特征、warmup 和质量分生成四个结构化状态标签。

## 刻意未纳入仓库的内容

- 原始/中间/输出数据：数据在外接盘或其他数据存储中，不提交 Git。
- 论文 PDF：作为研究资料单独管理，不作为运行时依赖。
- 旧的 `modules/`、`utils/`：未被当前主流程导入，且与当前实现存在接口和导入路径偏差，已删除以避免误用。
- 重复的 shell 批处理器和旧版批处理脚本：统一使用 `batch_process_all.py`。
