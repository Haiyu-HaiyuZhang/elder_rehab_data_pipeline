# 指标计算原理（当前实现）

本文描述 **`process_duogait_to_json.py` + `signal_processing_pipeline/`** 中五个输入特征与质量分的计算方式，以及与 **fuzzy / LLM 同事规则** 的量纲关系。实现以「**干预场景：胸戴 IMU（ST）+ 可选足部 IMU（LF/RF）+ 心率**」为准；**不使用 DUO `processed/` 目录**（算法不透明，仅作离线对照时可用 `validate_duogait_metrics.py`）。

---

## 1. 数据与时间基准

| 来源 | 路径约定 | 用途 |
|------|-----------|------|
| INTERIM 胸戴 | `.../interim/OG_*/sub_XX/ST.csv` | 步频、步时变异、胸戴步长锚 |
| INTERIM 足部（可选） | 同目录 `LF.csv`, `RF.csv` | 仅参与**步长**修正 |
| Raw 心率 | `.../raw/OG_st_raw` 或 `OG_dt_raw` / `sub_XX/heart_rate.CSV` | Garmin 导出，1 Hz 量级 |
| 受试者表 | `raw/subject_info.csv` | `age`、`height(cm)` 等 |

- **时间列**：INTERIM 常见列为 **`timestamp`**（秒，单调）；亦兼容 `Time`。
- **采样率**：由 `timestamp` 相邻差分估计，典型 **128 Hz**。
- **30 s 窗**：非重叠，`samples_per_window = floor(30 × fs)`；窗内 ST 子段与 LF/RF **按相同行索引切片**（要求与 ST 等长对齐）。
- **心率对齐**：用 interim ST 与 raw ST 加速度签名匹配，得到 `hr_start_offset`（秒），使 Garmin 时间轴与 interim 片段对齐。

---

## 2. 步频 `step_frequency_hz`（Hz）

**传感器**：仅 **ST 三轴加速度**（`AccX/Y/Z`）。

**流程**：

1. 合加速度模长 \( \|a\| = \sqrt{a_x^2+a_y^2+a_z^2} \)。
2. 去均值后取绝对值，**Butterworth 低通**（2 阶，截止取 `min(4 Hz, 0.8×Nyquist)`，且 ≥1 Hz 时生效）。
3. **`scipy.signal.find_peaks`**：高度阈值 `std(filtered) × 2.5`，最小峰距 **0.4 s**（与 `config.PEAK_HEIGHT_MULTIPLIER`、`MIN_PEAK_DISTANCE_SEC` 一致），`prominence = 0.5 ×` 高度阈值。
4. 相邻峰样本差 → 步间隔（秒），保留 **(0.3, 2.0) s** 的间隔。
5. `step_frequency_hz = 1 / mean(有效间隔)`。

### 验证模式 vs 兜底模式（`METRIC_ALLOW_DEFAULT_FALLBACKS`）

| 行为 | **默认 False**（验证优先，利于发现问题） | **True**（`ELDER_REHAB_METRIC_FALLBACKS=1`） |
|------|------------------------------------------|---------------------------------------------|
| 峰检后无有效 ISI | `step_frequency_hz` / `step_time_variability_ms` 为 **null** | 填 **1.5 Hz / 35 ms** |
| 峰数不足 | 同上，**不用 FFT** | **FFT** 0.5–4 Hz 主导频；失败再默认 1.5 Hz |
| 步频、变异数值 | **不 clip**（仅保证变异 ≥0） | clip 步频 [0.5,4] Hz、变异 [5,100] ms |
| 无可靠步频（且非兜底） | **步长 null**（不单独用强度估步长掩盖失败） | 仍估步长并 clip |

**建议**：初期验证保持默认 **False**；与同事对齐或上线前再按需打开兜底。

---

## 3. 步长 `step_length_m`（m）

**两阶段**：

### 3.1 胸戴锚（ST）

- 动态加速度强度：`sqrt(mean( (a_x² + a_y² + (a_z−1)²) ))`（Z 粗略去重力 1 g，与 DUO 导出单位一致时近似）。
- **经验映射**：`stride = 1.0 + (intensity / 0.2) × 0.4`，再 **clip [0.9, 1.5] m**（胸戴无法几何测步长，仅为弱相对指标）。

### 3.2 足部修正（若存在 LF/RF）

模块：`signal_processing_pipeline/duogait_metrics.py` → `stride_from_cadence_height_and_feet`。

- 用 **身高（m）** 与 **上一步得到的胸戴步频** 估步行速度量级，得到 `base` 步长；再与 **胸戴锚** 线性混合（约 55% 物理启发 + 45% 胸戴锚）。
- 对 LF、RF 窗口分别算 **去均值后加速度模长的 RMS**，作 **±几厘米** 内的微调。
- 最后乘以 **`config.STRIDE_LEN_OUTPUT_SCALE`**（默认 **1.0**：与老年人干预规则量纲一致；实验性缩放可设环境变量 `ELDER_REHAB_STRIDE_SCALE`，需与同事确认后再用）。

**不修改**：步频、步时变异仍只来自 ST（避免左右足峰值混串导致 ISI 失真）。

---

## 4. 步时变异 `step_time_variability_ms`（ms）

**定义**：相邻步事件间隔（ISI，秒）的 **标准差 × 1000**。

**传感器 / 事件**：与步频相同，来自 **ST 峰间间隔** 子集 (0.3, 2.0) s。

**后处理**：默认验证模式下 **不截顶**，便于发现峰检异常（极大值会直接体现在 JSON 与同事规则中）。兜底模式下仍为 **clip [5, 100] ms**。

---

## 5. 心率 `mean_hr_bpm` / `max_hr_bpm`

- 窗在时间轴上映射到 Garmin 表后，取 **`HR (bpm)`** 列数值；`mean` / `max`；无效则为 **null**（不写假数）。

---

## 6. 质量分 `imu_quality` / `hr_quality`

- **IMU**：`assess_data_quality(st_window, 'imu')`——缺失比例、零方差等启发式，默认约 0.95，异常则下调。
- **HR**：有窗口但无有效均值时 **`hr_quality` 上限压低**（与缺失 HR 一致）；空窗约 **0.25**。

**Fuzzy**：`imu_quality` 与 `hr_quality` **均 < 0.6** 时，三维负荷/疲劳/动作标 **`unknown`**（与数据质量规则一致）。

---

## 7. Warmup 与 Fuzzy / LLM

- **第一窗**的步频、步长、步时变异写入 `warmup_baseline`，供同事规则中的 **相对 ±10% / 恶化 ≥20%** 调整（见 `fuzzy_classifier.py`）。
- **`ground_truth`**：由 **`classify_exercise_state`** 按同事 **Dim1–3、安全覆盖、composite** 生成；与 JSON 字段集一致（不含 `condition` 等扩展字段）。

---

## 8. 参数一览（`signal_processing_pipeline/config.py`）

| 常量 | 含义 |
|------|------|
| `MIN_PEAK_DISTANCE_SEC` | 0.4 s，峰最小间距 |
| `PEAK_HEIGHT_MULTIPLIER` | 2.5，峰高相对 std |
| `STEP_FREQUENCY_MIN/MAX_HZ` | 0.5 / 2.5（提取后再 clip 到 4.0 为代码另一层上限） |
| `HR_MIN/MAX_BPM` | 30 / 200 |
| `STRIDE_LEN_OUTPUT_SCALE` | 默认 1.0；可选 `ELDER_REHAB_STRIDE_SCALE` |
| `METRIC_ALLOW_DEFAULT_FALLBACKS` | 默认 **False**；`ELDER_REHAB_METRIC_FALLBACKS=1` 开启 FFT/默认步频/clip |

---

## 9. 相关文档

- **规则与 JSON 字段**：`PIPELINE_SPECIFICATION.md`
- **数据目录层次**：`DATA_ARCHITECTURE_GUIDE.md`
- **批量导出某一受试者全部任务**：`run_subject_all_windows.py`

---

*最后更新：与仓库内 `process_duogait_to_json.py`、`duogait_metrics.py`、`fuzzy_classifier.py`、`config.py` 同步。*
