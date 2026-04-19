# DUO-GAIT JSON 导出处理指南

## 概述

`process_duogait_to_json.py` 将 DUO-GAIT 原始传感器数据转换为结构化的 JSON 格式，用于后续的 LLM 处理和 Fuzzy Logic 验证。

## 输入数据源

从 `/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw/` 读取：

- **ST.csv** - IMU 传感器数据 (128 Hz 采样率)
  - 包含：Time, Gyro X/Y/Z, Accel X/Y/Z, Pressure, Temperature, Quaternion
  - 大小：~37 MB per subject
  
- **heart_rate.CSV** - 心率和生理数据
  - 包含：Time, HR (bpm), Speed, Pace, Cadence, Altitude, etc.
  - 大小：~3-4 MB per subject

## 输出格式

JSON 文件结构（符合用户指定格式）：

```json
{
  "metadata": {
    "session_id": "session_sub_01_st",
    "player_id": "sub_01",
    "timestamp": "2026-04-19T18:06:23.155255Z",
    "window_sec": 30,
    "trigger_event": "window_complete"
  },
  "imu": {
    "features": {
      "step_frequency_hz": 1.71,
      "step_length_m": 0.55,
      "step_time_variability_ms": 100.0
    },
    "anomaly_flags": ["irregular_step_rhythm"],
    "data_quality": 0.85,
    "quality_reason": "irregular_step_rhythm"
  },
  "heart_rate": {
    "features": {
      "hr_mean_bpm": 80.0,
      "hr_max_bpm": 100.0,
      "hr_recovery_bpm_per_min": 5.0
    },
    "anomaly_flags": [],
    "data_quality": 0.85,
    "quality_reason": "clean signal"
  }
}
```

### 输出文件命名

```
{subject_id}_st_window_{window_index:04d}.json

例如：
  sub_01_st_window_0000.json  (第1个30秒窗口)
  sub_01_st_window_0001.json  (第2个30秒窗口)
  sub_01_st_window_0002.json  (第3个30秒窗口)
  ...
```

## 特征计算

### 步态特征 (IMU)

1. **step_frequency_hz** (步频，Hz)
   - 通过峰值检测加速度信号中的步伐
   - 使用 FFT 频域分析作为备选方法
   - 正常范围：0.5-4.0 Hz

2. **step_length_m** (步长，米)
   - 基于陀螺仪旋转信号估计
   - 使用公式：`stride_length = 0.55 + (mean_rotation / 100.0) * 0.3`
   - 范围：0.4-1.0 m

3. **step_time_variability_ms** (步时变异性，毫秒)
   - 步间间隔的标准差
   - 反映步态规律性
   - 范围：5-100 ms

### 心率特征

1. **hr_mean_bpm** - 30秒窗口内的平均心率
2. **hr_max_bpm** - 30秒窗口内的最大心率
3. **hr_recovery_bpm_per_min** - 估计恢复率

### 数据质量评估

- **data_quality** (0.0-1.0)
  - 检查缺失值百分比
  - 检查数据方差
  - 初始分数：0.95
  - 缺失数据 > 10%：-0.1
  - 零方差通道：-0.05 per channel

- **quality_reason** (字符串)
  - "clean signal" - 质量 > 0.90
  - 或列出具体问题

### 异常检测

**IMU异常标志**：
- `irregular_step_rhythm` - 步时变异性 > 60 ms
- `abnormal_step_frequency` - 步频 < 0.8 或 > 3.5 Hz
- `short_stride` - 步长 < 0.45 m

**心率异常标志**：
- `abnormal_hr_range` - HR > 180 或 < 40 bpm
- `high_hr_variability` - max_hr / mean_hr > 1.5

## 使用方法

### Python API

```python
from process_duogait_to_json import DUOGAITProcessor

# 初始化处理器
processor = DUOGAITProcessor(
    raw_data_dir='/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw/sub_01',
    output_dir='/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/',
    subject_id='sub_01'
)

# 加载数据
processor.load_data()

# 处理窗口
# 处理所有数据：processor.process_windows()
# 处理有限窗口：processor.process_windows(max_windows=10)
windows_created = processor.process_windows(max_windows=5)

print(f"Created {windows_created} JSON windows")
```

### 命令行运行

```bash
cd /Users/zhanghaiyu/workspace/elder_rehab
python process_duogait_to_json.py
```

脚本会自动：
1. 加载 ST.csv 和 heart_rate.CSV
2. 分割为 30 秒窗口
3. 计算每个窗口的特征
4. 导出为 JSON 文件

## 测试结果

### 小批量测试 (5个30秒窗口)

```
✓ Loaded ST data: 376,256 rows (约 49 分钟数据)
✓ ST sample rate: 128.0 Hz
✓ Loaded heart rate data: 2,616 rows

处理结果：
・Window 0: step_freq=1.71 Hz, stride=0.55 m
・Window 1: step_freq=1.07 Hz, stride=0.55 m
・Window 2: step_freq=0.95 Hz, stride=0.55 m
・Window 3: step_freq=1.07 Hz, stride=0.55 m
・Window 4: step_freq=1.83 Hz, stride=0.58 m

✓ 5 个 JSON 文件生成成功
・文件大小：每个 ~700 字节
・时间戳：自动生成，按窗口顺序递增
・异常标志：检测到的异常正确标记
```

## 集成工作流

### 第1步：导出 JSON
```bash
python process_duogait_to_json.py
# 输出：/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/*.json
```

### 第2步：LLM 处理
```python
# 读取 JSON 作为输入语料库
import json
import glob

json_files = glob.glob('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/*.json')
for json_file in json_files:
    with open(json_file) as f:
        window = json.load(f)
    
    # 发送给 LLM 生成标签
    # llm_label = llm_model.classify(window)
```

### 第3步：Fuzzy Logic 验证
```bash
# 使用 validate_with_fuzzy.py 验证
python validate_with_fuzzy.py \
    --input_dir /Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/ \
    --age 70 \
    --output fuzzy_results.csv \
    --report
```

## 配置和自定义

### 修改窗口大小

在 `process_duogait_to_json.py` 中修改：
```python
self.window_duration = 30  # 改为其他值（秒）
```

### 调整特征提取参数

**步频检测阈值**：
```python
peak_threshold = np.max([np.std(filtered) * 0.2, np.percentile(filtered, 25)])
#                                        ^^ 改为 0.1 或 0.3
```

**异常检测阈值**：
```python
if features.get('step_time_variability_ms', 0) > 60:  # 改为其他值
    anomalies.append("irregular_step_rhythm")
```

## 故障排查

### 问题：特征值为 0

**原因**：列名不匹配或数据加载失败

**解决**：
1. 检查 CSV 文件格式是否与预期一致
2. 验证列名（应包含 Accel X/Y/Z, Gyro X/Y/Z）
3. 查看日志中的"Columns"输出，确认加载的列名

### 问题：内存不足

**原因**：处理过多 window

**解决**：
```python
# 使用 max_windows 参数分批处理
processor.process_windows(max_windows=100)  # 仅处理前100个窗口
```

### 问题：特征值不合理

**原因**：采样率或陀螺仪数据问题

**解决**：
1. 检查 `st_sample_rate` 是否正确（应为 ~128 Hz）
2. 增加/减少峰值检测灵敏度
3. 手动检查原始 CSV 数据的有效性

## 性能特性

- **处理速度**：~100 ms per 30s window
- **内存使用**：~500 MB 加载全部 ST.csv + HR 数据
- **输出大小**：~700 字节 per JSON 文件
- **时间复杂度**：O(n) where n = 总样本数

## 下一步

1. **扩展到所有受试者**
   - 修改脚本以循环处理 sub_01 到 sub_16
   - 添加进度跟踪

2. **增强特征提取**
   - 添加更多时域特征（峰值，增长率）
   - 添加频域特征（频谱熵）
   - 使用小波分析检测步态模式

3. **LLM 标记**
   - 使用 JSON 作为 LLM 输入
   - 收集人工标签
   - 比较 LLM vs Fuzzy Logic 结果

4. **验证和校准**
   - 与临床标准对比
   - 调整 Fuzzy Logic 成员函数参数
   - 优化阈值

## 相关文件

- `process_duogait_to_json.py` - 本处理脚本
- `validate_with_fuzzy.py` - Fuzzy Logic 验证引擎
- `WINDOWS_PROCESSING_GUIDE.md` - 窗口处理完整指南
- `FUZZY_CLASSIFICATION_GUIDE.md` - Fuzzy Logic 详细说明

## 许可和引用

数据来源：DUO-GAIT 数据集
处理方法：基于生物力学特征析和传感器融合
