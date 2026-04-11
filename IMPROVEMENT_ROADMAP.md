# 改进方案总结 & 技术决策

## 1. 滤波算法需要吗？

### 评估表
| 滤波类型 | 是否需要？ | 原因 | 优先级 |
|--------|----------|------|--------|
| **低通滤波** | ⚠️ 有条件 | IMU 噪声较小，但可改善峰值检测精度 | 中 |
| **带通滤波** | ❌ 不需要 | 步态频率 1-2 Hz，远低于 IMU 噪声频率 | 低 |
| **重采样** | ✓ 应该做 | 128 Hz → 100 Hz 降低计储存开销，但不影响步态特征 | 中 |

### 具体建议

```python
# 需要做的预处理:
1. ✓ 去除 NaN/异常值 (当前有了)
2. ✓ 重采样 (128 Hz → 100 Hz) 以减少数据
3. ⚠️ 可选: 低通滤波 @ 5 Hz (改善峰值检测)

# 不需要做的:
❌ 带通滤波 (频率范围太大)
❌ 去趋势 (步态无直流漂移)
```

### 实践建议
**先不加滤波**，因为：
- 你已经用了 `min_distance=60ms` 的峰值检测（隐含滤波作用）
- 如果噪声成为问题，可后续加 5 Hz 低通（线性相位）

---

## 2. 四元数能做什么？✨

### 四元数基础
IMU 的四元数 `(w, x, y, z)` 表示**相对于地球的 3D 方向**

可转换为欧拉角：
```python
def quat_to_euler(w, x, y, z):
    # pitch: 前倾角 (-90° ~ +90°)
    pitch = np.arcsin(2*(w*y - x*z)) * 180/np.pi
    
    # roll: 左右倾斜 (-180° ~ +180°)
    roll = np.arctan2(2*(w*x + y*z), 1-2*(x*x+y*y)) * 180/np.pi
    
    # yaw: 旋转/头向 (-180° ~ +180°)
    yaw = np.arctan2(2*(w*z + x*y), 1-2*(y*y+z*z)) * 180/np.pi
    
    return pitch, roll, yaw
```

### 可计算的高级指标

| 指标 | 从四元数导出 | 临床意义 | 实现难度 |
|-----|-----------|--------|--------|
| **身体倾角** | `pitch` @ 左脚 | 步态时前倾程度，老年人>年轻人 | ⭐ 易 |
| **躯干稳定性** | LW 的 roll std | 左右摇晃，越小越稳定 | ⭐ 易 |
| **步态对称性** | LF roll vs RF roll | 两脚协调性，大偏差=步态不对称 | ⭐⭐ 中 |
| **跤跌风险指标** | 倾角变异系数 | pitch/roll 突然变化=可能跌倒 | ⭐⭐ 中 |
| **疲劳标志** | 倾角随时间变化 | 疲劳时前倾角增大（驼背）| ⭐⭐ 中 |

### 推荐实现

#### 最有用的指标：**躯干稳定性指数**

```python
def compute_trunk_stability(quaternions_lw, quaternions_rw):
    """
    从腰部传感器的四元数计算躯干稳定性
    
    Args:
        quaternions_lw: 左腰的四元数序列 (N, 4)
        quaternions_rw: 右腰的四元数序列 (N, 4)
    
    Returns:
        稳定性指标 (0-100，越高越稳定)
    """
    
    # 转换为欧拉角
    pitch_lw = quat_to_pitch(quaternions_lw)  # 前倾
    roll_lw = quat_to_roll(quaternions_lw)    # 左右摇晃
    
    # 计算变异性
    pitch_std = np.std(pitch_lw)   # 前倾波动
    roll_std = np.std(roll_lw)     # 左右波动
    
    # 对称性检查
    pitch_rw = quat_to_pitch(quaternions_rw)
    roll_rw = quat_to_roll(quaternions_rw)
    
    pitch_asymmetry = abs(pitch_lw.mean() - pitch_rw.mean())
    roll_asymmetry = abs(roll_lw.mean() - roll_rw.mean())
    
    # 综合稳定性评分
    stability_score = 100 * np.exp(-(pitch_std + roll_std + 
                                     pitch_asymmetry + roll_asymmetry) / 20)
    
    return {
        'pitch_stability': 1 / (1 + pitch_std),      # 0-1
        'roll_stability': 1 / (1 + roll_std),        # 0-1
        'left_right_symmetry': 1 / (1 + roll_asymmetry),
        'overall_score': stability_score,             # 0-100
        'fatigue_risk': 'HIGH' if stability_score < 50 else 'LOW'
    }
```

#### 次优的指标：**步态倾角**

```python
def foot_posture_analysis(quat_lf, quat_rf):
    """分析左右脚的倾斜是否对称"""
    
    # 只用 LF/RF 的前倾角（pitch）
    lf_pitch = quat_to_pitch(quat_lf)
    rf_pitch = quat_to_pitch(quat_rf)
    
    pitch_diff = lf_pitch - rf_pitch  # 正常应该接近 0
    
    return {
        'LF_mean_pitch_deg': lf_pitch.mean(),
        'RF_mean_pitch_deg': rf_pitch.mean(),
        'pitch_asymmetry_deg': abs(pitch_diff.mean()),
        'is_symmetrical': abs(pitch_diff.mean()) < 5,  # <5° 为对称
        'gait_quality': 'NORMAL' if abs(pitch_diff.mean()) < 5 else 'ASYMMETRIC'
    }
```

### 与疲劳的关系

```python
# 预期:
运动初期: pitch ≈ 10°, roll ≈ 0°, std 很小
运动中期: pitch/roll 逐渐增大，波动增加
运动末期: pitch → 15-20°, roll std 增大 (驼背+摇晃)

这与 Borg 评分应该相关:
Borg 18 → pitch_std > 3°, roll_std > 2°
```

---

## 3. 认知任务 Dual Task 数据

### 数据格式

```
OG_dt_raw/sub_01/
├── transcript_control.csv    # 第一阶段: 重控制/轻运动
│   └── 倒序计数 5308 → 5200 (条件)
│
├── transcript_fatigue.csv    # 第二阶段: 重运动/重认知
│   └── 倒序计数 7942 → 7600 (疲劳状态)
│
└── [其他 IMU 数据 + HR 数据]
```

### 如何计算认知任务的性能

```python
def analyze_cognitive_performance(transcript_control, transcript_fatigue):
    """
    分析认知任务的表现变化
    
    运动干扰假说:
    - 疲劳时认知能力下降 → 计数错误/变慢
    """
    
    # 1. 计算正确率
    def get_accuracy(transcript_df):
        """跳数检查"""
        numbers = transcript_df['number'].dropna().astype(int).values
        
        # 应该是标准倒序
        expected = np.arange(numbers[0], numbers[0]-len(numbers), -1)
        correct_count = sum(1 for n in expected if n in numbers)
        
        return correct_count / len(expected) * 100  # %
    
    control_accuracy = get_accuracy(transcript_control)
    fatigue_accuracy = get_accuracy(transcript_fatigue)
    
    # 2. 计算速度 (每个数字的平均持续时间)
    def get_speed(transcript_df):
        """更快 = 更好（正常情况）"""
        durations = transcript_df['duration(s)'].dropna().values
        return np.mean(durations) if len(durations) > 0 else 0
    
    control_speed = get_speed(transcript_control)
    fatigue_speed = get_speed(transcript_fatigue)
    
    return {
        'control_accuracy_percent': control_accuracy,
        'fatigue_accuracy_percent': fatigue_accuracy,
        'accuracy_decline_percent': control_accuracy - fatigue_accuracy,
        
        'control_speed_s_per_number': control_speed,
        'fatigue_speed_s_per_number': fatigue_speed,
        'speed_decline_percent': (fatigue_speed - control_speed) / fatigue_speed * 100,
        
        'dual_task_effect': 'SIGNIFICANT' if (
            fatigue_accuracy < control_accuracy * 0.9 or 
            fatigue_speed > control_speed * 1.1
        ) else 'NORMAL'
    }
```

### 验证双重任务效应

```python
# 交叉验证:
对每个受试者:

1. 计算 ST 条件下的步频衰退:
   step_freq_decline_ST = 
     (initial_step_freq - final_step_freq) / initial_step_freq * 100

2. 计算 DT 条件下的认知衰退:
   cognitive_decline_DT = 
     (control_accuracy - fatigue_accuracy) / control_accuracy * 100

3. 计算相关性:
   corr(step_freq_decline, cognitive_decline) = ?
   
   预期: 0.4-0.7（中等正相关）
   - 高度相关 → 表示步态和认知共享资源（双重任务干扰）
   - 不相关   → 表示某人的认知正常但步态差（某种特异性问题）
```

---

## 4. 改进计划总结

### Phase 1: 添加 30s 滑动窗口 ⭐⭐⭐ 必做

```python
# validate_duo_gait.py 中添加:

def analyze_metrics_by_window(imu_data, hr_data, window_duration_s=30, overlap=50):
    """30 秒滑动窗口分析"""
    
    results_timeline = []
    
    # 对每个窗口计算指标
    for window_idx in range(...):
        window_metrics = {
            'window_id': window_idx,
            'time_start_s': t_start,
            'time_end_s': t_end,
            'step_frequency_hz': calculate_step_freq(window),
            'step_length_m': calculate_step_length(window),
            'hr_mean_bpm': np.mean(hr_window),
            'gait_stability': ...
        }
        results_timeline.append(window_metrics)
    
    # 输出: 时间序列
    df = pd.DataFrame(results_timeline)
    
    return {
        'timeline': df,
        'trend': {
            'step_freq_slope': polyfit(df['time_s'], df['step_frequency_hz']),
            'indicates_fatigue': slope < 0
        }
    }
```

### Phase 2: 集成四元数分析 ⭐⭐ 建议

```python
# 在 test_step_metrics() 后添加:

def analyze_body_posture(imu_data):
    """从四元数计算躯干稳定性"""
    
    quat_lw = imu_data['LW'][['Quat W', 'Quat X', 'Quat Y', 'Quat Z']].values
    quat_rw = imu_data['RW'][['Quat W', 'Quat X', 'Quat Y', 'Quat Z']].values
    
    stability = compute_trunk_stability(quat_lw, quat_rw)
    
    return stability  # -> dict with pitch_stability, roll_stability, etc.
```

### Phase 3: 验证与 subject_info 的 HR baseline ⭐⭐⭐ 必做

```python
# 在 validate_subject() 中:

# 从 subject_info 读取
subject_info = pd.read_csv('.../subject_info.csv')
row = subject_info[subject_info['sub'] == subject_id].iloc[0]

measured_hr_baseline = row['st_HR_baseline']
measured_hr_fatigue = row['st_HR_fatigue']

# 与你的计算对比
computed_hr_mean = np.mean(hr_values)
computed_hr_max = np.max(hr_values)

print(f"HR baseline - measured: {measured_hr_baseline}, computed: {computed_hr_mean:.1f}")
print(f"HR peak     - measured: {measured_hr_fatigue}, computed: {computed_hr_max:.1f}")
```

### Phase 4: 双重任务认知-运动相关性分析 ⭐⭐ 建议

```python
# 新脚本: validate_dual_task_effect.py

def analyze_dual_task_interference(subject_id):
    """验证双重任务下的干扰效应"""
    
    # 加载 ST 数据
    st_results = validate_subject(subject_id, task_type='st')
    
    # 加载 DT 数据
    dt_results = validate_subject(subject_id, task_type='dt')
    
    # 加载认知任务数据
    cognitive_control = pd.read_csv('.../transcript_control.csv')
    cognitive_fatigue = pd.read_csv('.../transcript_fatigue.csv')
    
    cognitive_decline = analyze_cognitive_performance(
        cognitive_control, cognitive_fatigue
    )
    
    # 对比
    gait_decline = {
        'step_freq_decline_ST': 
          (st_results['step_frequency_hz'] - dt_results['step_frequency_hz']) 
          / st_results['step_frequency_hz'],
        'step_length_decline_ST': ...
    }
    
    return {
        'gait_decline': gait_decline,
        'cognitive_decline': cognitive_decline,
        'correlation': compute_correlation(...),
        'dual_task_effect_observed': True if ... else False
    }
```

---

## 5. 代码实现优先级

| 优先级 | 任务 | 影响 | 工作量 |
|-------|------|------|--------|
| **1** 🔴 | 30s 滑动窗口 | 能看到衰退趋势（关键发现） | 中 |
| **2** 🟠 | HR baseline 验证 | 验证算法准确性 | 小 |
| **3** 🟡 | 四元数-躯干稳定性 | 新的高阶指标 | 中 |
| **4** ⚪ | 双重任务相关性 | 科学价值（可发文章） | 中 |
| **5** ⚪ | 预处理-低通滤波 | 小幅改进精度 | 小 |

---

## 建议的下一步

**最快见效的做法（我的建议）**：

```
这周:
1. ✓ 加入 30s 滑动窗口 + 图表显示趋势
2. ✓ 加入 HR baseline 验证逻辑
   → 能立即发现算法问题或验证正确性

下周:
3. ○ 四元数提取（可选，如果有时间）
4. ○ 双重任务分析（后续研究）
```

需要我帮你写这些改进吗？先从 30s 窗口 + HR 验证开始？
