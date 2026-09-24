# DUO-GAIT Data Pipeline

将 DUO-GAIT 的 INTERIM IMU 片段和 RAW 心率数据切成 30 秒窗口，计算步态/心率特征，并输出供离线 LLM 推理和规则基线比较的 JSON。

## 当前主流程

```text
INTERIM/ST.csv (IMU, 约 128 Hz) ─┐
INTERIM/LF.csv, RF.csv (可选)     ├─> DUOGAITProcessor
RAW/heart_rate.CSV (约 1 Hz) ────┘        │
                                          ├─> 30 秒 JSON 窗口
                                          └─> fuzzy ground_truth
```

主流程只使用以下代码：

- `process_duogait_to_json.py`：单个受试者/任务的核心处理器。
- `batch_process_all.py`：批量处理预定义受试者和任务，可用参数筛选。
- `run_subject_all_windows.py`：扫描某一受试者的全部 `OG_*` 任务。
- `validate_duogait_metrics.py`：可选地与 DUO-GAIT `processed/` 结果做离线对照，不参与 JSON 主流程。
- `signal_processing_pipeline/config.py`：参数和环境变量配置。
- `signal_processing_pipeline/duogait_metrics.py`：可选 LF/RF 步长修正。
- `signal_processing_pipeline/fuzzy_classifier.py`：规则基线分类。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r signal_processing_pipeline/requirements.txt
```

## 使用

单个默认示例需要在 `process_duogait_to_json.py` 的 `main()` 中设置数据路径：

```bash
python3 process_duogait_to_json.py
```

批量处理：

```bash
python3 batch_process_all.py --dry-run
python3 batch_process_all.py --subjects sub_01 sub_02 --tasks OG_st_control OG_dt_control
python3 batch_process_all.py --skip-existing
python3 batch_process_all.py --dry-run \
  --interim-base /path/to/DUO-GAIT/interim \
  --raw-base /path/to/DUO-GAIT/raw \
  --out-dir /path/to/output/json
```

处理某一受试者的全部可用任务：

```bash
python3 run_subject_all_windows.py \
  --subject sub_01 \
  --interim-base /path/to/DUO-GAIT/interim \
  --raw-base /path/to/DUO-GAIT/raw \
  --out-dir /path/to/output/json
```

批处理器要求每个组合同时存在：

- `interim/<task>/<subject>/ST.csv`
- 对应 `raw/OG_st_raw/<subject>/heart_rate.CSV` 或 `raw/OG_dt_raw/<subject>/heart_rate.CSV`

缺失组合会被跳过并记录，不会伪造指标。输出目录在数据盘上，不应提交到 Git。

## 输入数据

- IMU：INTERIM 中的 `ST.csv`；典型采样率 128 Hz，至少需要三轴加速度列。
- 可选足部 IMU：同目录的 `LF.csv`、`RF.csv`，仅用于步长融合修正。
- 心率：RAW 中的 `heart_rate.CSV`，Garmin 导出格式，代码使用 `skiprows=6` 解析，典型约 1 Hz。
- 受试者信息：`subject_info.csv`，用于年龄和身高相关计算。

主流程不读取 `processed/` 作为 JSON 指标来源；它只用于可选离线对照。

## 输出指标

每个 30 秒窗口生成一个 JSON 文件，包含：

| 字段 | 来源 | 含义 |
|---|---|---|
| `step_frequency_hz` | ST 三轴加速度 | 峰值检测得到的步频 |
| `step_length_m` | ST，LF/RF 可选修正 | 胸部锚点和身高/步频启发式估计 |
| `step_time_variability_ms` | ST 峰间间隔 | ISI 标准差，单位毫秒 |
| `mean_hr_bpm` | HR | 窗口平均心率 |
| `max_hr_bpm` | HR | 窗口最大心率 |
| `imu_quality` / `hr_quality` | 对应窗口 | 0 到 1 的启发式质量分 |

首个窗口的三个步态特征会写入 `warmup_baseline`。RPE 当前没有数据来源，因此 JSON 中为 `null`。

计算细节见 [METRIC_CALCULATION.md](METRIC_CALCULATION.md)，完整 JSON 和规则见 [PIPELINE_SPECIFICATION.md](PIPELINE_SPECIFICATION.md)。

## 规则基线

`ground_truth` 由 `fuzzy_classifier.py` 生成，包含：

- `exercise_load`
- `fatigue_level`
- `movement_quality`
- `composite_state`

它是项目内的可重复规则基线，不等同于临床金标准。缺失或质量不足时输出 `null`/`unknown`，不会把缺失值默认为 0。

## 配置

默认采用验证优先模式：指标不可靠时输出 `null`。可通过环境变量临时开启旧的兜底行为：

```bash
ELDER_REHAB_METRIC_FALLBACKS=1 python3 process_duogait_to_json.py
ELDER_REHAB_STRIDE_SCALE=1.0 python3 process_duogait_to_json.py
```

## 文档导航

- [PIPELINE_SPECIFICATION.md](PIPELINE_SPECIFICATION.md)：JSON schema、指标和 fuzzy 规则。
- [METRIC_CALCULATION.md](METRIC_CALCULATION.md)：实现级计算细节和边界行为。
- [DATA_ARCHITECTURE_GUIDE.md](DATA_ARCHITECTURE_GUIDE.md)：DUO-GAIT RAW/INTERIM/PROCESSED 目录说明。
- [FILES_STRUCTURE.md](FILES_STRUCTURE.md)：仓库文件和入口说明。

## 验证

```bash
python3 -m compileall -q \
  process_duogait_to_json.py batch_process_all.py \
  run_subject_all_windows.py validate_duogait_metrics.py \
  signal_processing_pipeline
```

如果有 DUO-GAIT `processed/` 数据，可使用 `validate_duogait_metrics.py` 做参考对照；它不是主流程的单元测试，也不能替代独立的指标验证。
