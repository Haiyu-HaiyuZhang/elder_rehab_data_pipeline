# 当前处理流程的问题分析 & 改进方案

## 问题 1: 30s 预处理为什么没被使用？

### 现状分析

**预处理模块存在** ✓
- `/signal_processing_pipeline/utils/preprocessing.py` 定义了 `SignalPreprocessor` 类
- 包含：低通滤波、带通滤波、重采样能力
- **但 `validate_duo_gait.py` 没有调用它！**

**目前的计算方式**
```python
# 现在的流程:
1. 加载整个运动数据 (数分钟)
2. 直接计算全局指标 (整个运动平均)
3. 返回单一的 step_freq, step_length 等
```

### 为什么这是个问题？

| 问题 | 影响 | 严重性 |
|-----|------|--------|
| **没有时间分辨率** | 无法看到运动中指标的变化 | ⭐⭐⭐ 高 |
| **混合了疲劳和新鲜状态** | 步频 = (新鲜 + 疲劳) / 2，失真 | ⭐⭐⭐ 高 |
| **无法检测异常** | 无法发现某时段的跌倒风险或步态崩溃 | ⭐⭐ 中 |
| **不符合临床实践** | 医生看的是「病人如何疲劳的」，不是平均值 | ⭐⭐⭐ 高 |

### 正确做法应该是什么？

**方案 A: 30 秒滑动窗口**（推荐）
```
时间 →
|----30s----|    <- 窗口 1 (fresh)
    |----30s----|    <- 窗口 2
        |----30s----|    <- 窗口 3
            |----30s----|    <- 窗口 4 (fatigue)

结果：看到指标如何随疲劳递进
- 步频: 1.5 Hz → 1.2 Hz → 0.9 Hz (逐渐下降)
- 步长: 0.40 m → 0.38 m → 0.30 m (步伐变小)
```

**方案 B: 基于事件的分段**
```
如果有时间-到-疲劳数据 (st_time_to_fatigue):
- 前 30% 时间: "新鲜期"
- 中间 40% 时间: "稳定期"
- 后 30% 时间: "疲劳期"
  → 分别计算每个阶段的指标
```

---

## 问题 2: 心率恢复 (HR Recovery) 的计算严谨吗？

### 现在的方法（不严谨）
```python
# 当前代码:
hr_beginning = np.mean(hr_values[:int(len(hr_values)*0.1)])  # 前 10%
hr_end = np.mean(hr_values[-int(len(hr_values)*0.1):])       # 后 10%
hr_recovery = (hr_beginning - hr_end) / (len(hr_values) / 60)
```

**问题**：
1. ❌ 前 10% 不是「基线」，而是运动初期的心率（已经升高）
2. ❌ 后 10% 也不是「恢复」阶段，可能还在运动中
3. ❌ 除以时间长度→单位混乱（应该是 `bpm/minute`）

### 标准的心率恢复指标

#### 标准 1: HRR@1min (心率恢复在 1 分钟后)
```
HRR = HR_peak - HR_1min_after_exercise

理想值: > 15 bpm drop（表示交感神经恢复快）
```

**问题**: DUO-GAIT 数据可能没有运动后数据

#### 标准 2: HR_decline_during_exercise (运动中心率衰退)
```
HR_decline = HR_baseline - HR_end_of_running
或
HR_fatigue_ratio = HR_peak / HR_baseline
```

**可用吗**: ✓ YES! 用 subject_info 的 HR_baseline 和 HR_fatigue

#### 标准 3: HR 稳定性 (HRV - Heart Rate Variability)
```
HRV = std(HR_values) / mean(HR_values) × 100 (%)
低 HRV = 更稳定的步态
高 HRV = 不稳定、易疲劳
```

### 改进方案

```python
def calculate_hr_recovery_proper(subject_info_row, hr_values):
    """根据 subject_info 数据计算正确的心率恢复"""
    
    # 使用实测的基线和疲劳数据
    hr_baseline = subject_info_row['st_HR_baseline']  # 运动前
    hr_fatigue = subject_info_row['st_HR_fatigue']     # 运动至疲劳时
    
    # 方法 1: 心率下降量
    hr_decline = hr_baseline - hr_fatigue  # 不对啊，fatigue 时 HR 应该高于基线
    
    # 方法 2: 心率上升倍数
    hr_ratio = hr_fatigue / hr_baseline if hr_baseline > 0 else np.nan
    
    # 方法 3: 从数据计算 HR 稳定性
    hr_mean = np.mean(hr_values)
    hr_std = np.std(hr_values)
    hrv_percentage = (hr_std / hr_mean * 100) if hr_mean > 0 else np.nan
    
    return {
        'HR_peak': hr_fatigue,
        'HR_baseline': hr_baseline,
        'HR_increase_absolute': hr_fatigue - hr_baseline,  # bpm
        'HR_increase_percent': (hr_fatigue - hr_baseline) / hr_baseline * 100,  # %
        'HRV_percent': hrv_percentage,  # 越低越稳定
        'HR_peak_measured_from_data': np.max(hr_values)
    }
```

---

## 问题 3: 指标计算使用了全部数据而不是 30s 窗口吗？

### 对的，这就是问题所在

**当前代码的数据流**:
```python
# 在 test_step_metrics() 中:
acc_x = imu_data['LF']['Accel X']  # 整个运动的 X 加速度
acc_magnitude = sqrt(x² + y² + z²)  # 整个运动的加速度合向量

step_freq = StepFrequency.calculate(...)  # 基于整个数据的平均步频
```

**不使用预处理的 30s 窗口**:
- ❌ 没有调用 `preprocessor.apply_lowpass_filter()`
- ❌ 没有分段处理
- ❌ 没有时间分辨率的指标输出

---

## 推荐的修复方案

### 立即可做 (优先级 1 - 验证准确性)

```python
# 改进 test_heart_rate() 以使用 subject_info 数据

def validate_hr_with_ground_truth(hr_values, subject_info_row):
    """验证计算出的 HR 指标是否与实测值一致"""
    
    # 我们计算的
    computed_hr_mean = np.mean(hr_values)
    computed_hr_max = np.max(hr_values)
    
    # 实测的（从 subject_info）
    measured_hr_baseline = subject_info_row['st_HR_baseline']
    measured_hr_fatigue = subject_info_row['st_HR_fatigue']
    
    # 对比
    print(f"HR baseline - 计算: {computed_hr_mean:.1f}, 实测: {measured_hr_baseline}")
    print(f"HR peak    - 计算: {computed_hr_max:.1f}, 实测: {measured_hr_fatigue}")
    
    # 判断接近度
    baseline_error = abs(computed_hr_mean - measured_hr_baseline) / measured_hr_baseline * 100
    peak_error = abs(computed_hr_max - measured_hr_fatigue) / measured_hr_fatigue * 100
    
    return {
        'baseline_error_percent': baseline_error,
        'peak_error_percent': peak_error,
        'is_valid': baseline_error < 10 and peak_error < 10
    }
```

### 中期改进 (优先级 2 - 时间分辨率)

改进 `validate_duo_gait.py`:
```python
def analyze_with_sliding_window(imu_data, window_size_s=30, overlap_percent=50):
    """用 30 秒滑动窗口分析指标变化"""
    
    window_samples = int(128 * window_size_s)  # 128 Hz × 30s
    step = int(window_samples * (1 - overlap_percent/100))
    
    results_by_window = []
    for i in range(0, len(acc_x) - window_samples, step):
        window = acc_x[i:i+window_samples]
        
        # 对每个窗口计算步频、步长等
        stats = {
            'window_id': i // step,
            'time_start_s': i / 128,
            'step_freq': calculate_step_freq(window),
            'step_length': calculate_step_length(window),
            # ...
        }
        results_by_window.append(stats)
    
    return results_by_window

# 输出: [
#   {time: 0-30s, step_freq: 1.50 Hz},
#   {time: 15-45s, step_freq: 1.48 Hz},
#   {time: 30-60s, step_freq: 1.42 Hz},  <- 下降趋势
#   ...
# ]
```

### 长期改进 (优先级 3 - 预处理集成)

```python
from utils.preprocessing import SignalPreprocessor

preprocessor = SignalPreprocessor(
    target_sample_rate=100,
    filter_order=4,
    cutoff_freq=5  # Hz
)

# 在计算之前先滤波
acc_filtered = preprocessor.apply_lowpass_filter(acc_magnitude, fs=128)

# 然后用 30s 窗口处理
results = analyze_with_sliding_window(acc_filtered, ...)
```

---

## 总结检查清单

之前的验证问题:
- [ ] ✗ **使用了全局平均** 而非时间分辨率指标
- [ ] ✗ **心率恢复计算有问题** (单位混乱、阶段定义不清)
- [ ] ✗ **没有对比 subject_info 的实测数据** 进行验证
- [ ] ✗ **预处理模块存在但未使用**
- [ ] ✗ **无法看到运动中的指标演变** (新鲜→疲劳)

改进后应该:
- [x] 使用 subject_info 的 HR_baseline/fatigue 验证你的计算
- [x] 改用 30s 滑动窗口看指标变化趋势
- [x] 正确定义心率恢复（使用 HR 升幅或变异性）
- [x] 集成预处理（低通滤波+重采样）
- [x] 输出时间分辨率的结果表格

