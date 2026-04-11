# 四元数 & 认知任务数据详细指南

## 1. 四元数的来源与自采数据的麻烦程度

### 四元数是怎样产生的？

**四元数 ≠ 加速度计算的**

```
硬件层面（IMU 芯片内部）:

陀螺仪 (Gyro)       加速度计 (Accel)
    ↓                    ↓
角速度 (deg/s)      线性加速度 (g)
    ↓                    ↓
    └────→ 融合算法 (9-DOF IMU Fusion) ←─┘
                        ↓
                    四元数 (w,x,y,z)
                    表示 3D 姿态
```

### DUO-GAIT 中的四元数

```
数据来源: Physilog 5 传感器（Gait Up 公司）
- 集成 9 轴 MEMS IMU (加速度 + 陀螺仪 + 磁力计)
- 芯片内部运行 EKF (扩展卡尔曼滤波) 算法
- 实时输出四元数表示的姿态
- 采样率: 128 Hz

文件中看到的:
├── Accel X/Y/Z      (加速度原始值)
├── Gyro X/Y/Z       (陀螺仪原始值)
├── Quat W/X/Y/Z     (融合后的四元数)
├── Pressure/Temp    (气压和温度，附加)
└── Time             (时间戳)

→ 四元数是硬件输出的"成品"，不是我们计算的
```

### 自采数据的复杂度

#### 情况 1: 如果你买的 IMU 芯片有四元数输出 ✓ 容易
```
硬件支持：例如 MPU-9250 + DMP (Digital Motion Processor)
- 芯片内置 DMP，已整合 EKF 算法
- 直接读取四元数，无需额外处理
- 麻烦度: ⭐ 很简单
```

#### 情况 2: 如果 IMU 只有加速度 + 陀螺仪（无芯片级四元数输出）⚠️ 麻烦
```
需要自己实现融合算法:

选项 A: Madgwick 算法（推荐）
- 计算量小，适合实时处理
- 只需加速度 + 陀螺仪
- 麻烦度: ⭐⭐⭐ 中等
- 实现时间: ~ 1-2 天（有现成库）

选项 B: EKF (扩展卡尔曼滤波)
- 精度高但计算量大
- 需要加速度 + 陀螺仪 + 磁力计
- 麻烦度: ⭐⭐⭐⭐ 很麻烦
- 实现时间: ~ 3-5 天

选项 C: 不用四元数，用欧拉角直接从陀螺仪积分
- 最简单但漂移严重（几秒钟就不准）
- 麻烦度: ⭐ 简单但不可靠
```

#### 情况 3: 如果 IMU 只有加速度计（没有陀螺仪）❌ 不可行
```
无法生成四元数。原因：
- 加速度无法区分旋转和重力
- 需要角速度（陀螺仪）来感知动作
→ 无解，必须升级硬件
```

### 我的建议

**对于自采数据**：
```
采购建议:
1. ✓ 首选: 买有四元数输出的 IMU 模块
   例如: STM32 + LSM9DS1 (有内置四元数)
   
2. ⚠️ 次选: 买 9 轴 IMU (加速度 + 陀螺仪 + 磁力计)
   + 自己实现 Madgwick 算法
   例如: Raspberry Pi + MPU-9250 + 自写融合代码
   
3. ❌ 不推荐: 廉价 3 轴加速度计
   无法获得姿态信息
```

**时间成本**：
```
四元数提取的总工作量:
- 采用方案 1 (有芯片支持):  1 小时 (直接读取)
- 采用方案 2 (自实现 Madgwick): 1-2 天 (学习 + 测试)
- 采用方案 3 (自实现 EKF):     3-7 天 (复杂调试)
```

---

## 2. 认知任务数据解读

### 数据格式

```
transcript_control.csv:
number,duration(s)
5308,374         ← 开始数字 5308，用时 374 秒
5301,            ← 数字 5301，无时间戳记录
5294,
5287,
...

transcript_fatigue.csv:
number,duration(s)
7942,369         ← 开始数字 7942，用时 369 秒
7953,            ← 错误? 应该是 7935，但写的 7953 (往上) 
7928,
7921,
...
```

### 如何理解这些数字？

**实验设计**：
```
双重任务测试: 边跑步边做数字倒序任务

控制条件 (Control):
- 任务: 从 5308 开始，向下倒数 (5308 → 5307 → 5306 → ...)
- 强度: "轻运动，重认知" (跑步很轻松，重点在计数)
- 时间: 通常 5-10 分钟

疲劳条件 (Fatigue):
- 任务: 从 7942 开始，向下倒数 (7942 → 7941 → ...)
- 强度: "重运动，重认知" (运动强度已很高，还要继续计数)
- 时间: 通常 5-10 分钟 (或直到受试者说"停，我太累了")
```

### 如何评分认知表现？

#### 指标 1: 准确率 (Accuracy)

```python
def calculate_accuracy(transcript_df, expected_start=5308):
    """计算有多少个数字是正确的"""
    
    numbers = transcript_df['number'].dropna().astype(int).values
    
    # 预期的序列
    expected = np.array([
        expected_start - i 
        for i in range(len(numbers))
    ])
    
    # 计算有多少个是对的
    correct = np.sum(numbers == expected)
    accuracy = correct / len(expected) * 100
    
    return accuracy
    
# 例如:
# 表示的是: [5308, 5301, 5294, ...] 应该是 [5308, 5307, 5306, ...]
# 可以看到有的数字跳过了，说明受试者有错误或说不出来
```

**DUO-GAIT 的 sub_01 例子**：
```
transcript_control.csv:
5308 ✓ (正确的起始)
5301 ✗ (应该是 5307，错了 6 个数字！)
5294 ✗ (应该是 5306)
5287
...

→ 这表明受试者在 Control 条件下已经注意力不集中
    或者数字计数有中断
```

#### 指标 2: 速度 (Speed / Cadence)

```python
def calculate_speed(transcript_df):
    """每个数字平均用时"""
    
    durations = transcript_df['duration(s)'].dropna().values
    avg_time_per_number = np.mean(durations)  # 秒
    
    return avg_time_per_number

# 预期:
# - 健康人, 轻松计数: ~ 2-3 秒/数字
# - 轻微认知负荷: ~ 3-5 秒/数字
# - 高认知负荷: ~ 5-10+ 秒/数字 (已经吃力)
```

**速度下降表示什么？**
```
速度下降(变慢) = 认知能力下降

例如:
Control: 平均 3.5 秒/数字 (轻松)
Fatigue: 平均 7.2 秒/数字 (吃力，步调变慢)

→ 说明运动疲劳影响了认知表现
```

#### 指标 3: 数字顺序错误率

```python
def calculate_sequence_errors(transcript_df):
    """计算乱序和跳过的数字"""
    
    numbers = transcript_df['number'].dropna().astype(int).values
    
    # 检测乱序 (相邻数字应该是 -1)
    diffs = numbers[1:] - numbers[:-1]
    
    errors = []
    for i, d in enumerate(diffs):
        if d != -1:  # 不是标准的 -1 差
            errors.append({
                'position': i,
                'number1': numbers[i],
                'number2': numbers[i+1],
                'diff': d,
                'error_type': 'skip' if d < -1 else 'repeat/error'
            })
    
    error_rate = len(errors) / len(numbers) * 100
    return error_rate, errors

# 例如:
# [5308, 5301, 5294, ...] 中间都差 -7
# → 说明受试者忘记了中间的数字，或者有系统性的错误
```

### 如何验证"步态衰退 ↔ 认知衰退"的关联？

```python
def analyze_dual_task_effect(subject_id):
    """
    检验双重任务干扰假说
    """
    
    # 1. 计算运动指标衰退
    st_data = validate_subject(subject_id, task_type='st')  # 单一任务
    dt_data = validate_subject(subject_id, task_type='dt')  # 双重任务
    
    # 步频衰退 (DT 相比 ST 的下降)
    step_freq_st = st_data['avg_step_frequency']
    step_freq_dt = dt_data['avg_step_frequency']
    gait_decline = (step_freq_st - step_freq_dt) / step_freq_st * 100
    
    # 2. 计算认知任务衰退
    control_accuracy = calculate_accuracy(transcript_control)
    fatigue_accuracy = calculate_accuracy(transcript_fatigue)
    cognitive_decline = (control_accuracy - fatigue_accuracy) / control_accuracy * 100
    
    # 3. 对比
    result = {
        'gait_decline_percent': gait_decline,
        'cognitive_decline_percent': cognitive_decline,
        'dual_task_effect_detected': cognitive_decline > 10,  # > 10% 认知衰退
        'interpretation': {
            'if_both_high': '受试者在双重任务中表现出显著的资源竞争 '
                           '(步态和认知都衰退)',
            'if_gait_high_cognitive_low': '受试者优先保护步态稳定性，牺牲认知 '
                                        '(安全优先策略)',
            'if_cognitive_high_gait_low': '受试者优先完成认知任务，牺牲步态 '
                                        '(任务优先策略)',
            'if_both_low': '受试者具有良好的任务分工能力'
        }
    }
    
    return result

# 输出例如:
# {
#   'gait_decline': 15%,
#   'cognitive_decline': 20%,
#   'dual_task_effect': True,
#   'interpretation': 'Both decline → resource competition',
#   'clinical_significance': '老年人或衰弱患者的跌倒风险'
# }
```

### 临床意义

```
双重任务衰退程度可以用来:

1. 评估跌倒风险
   - 双重任务衰退 > 15% → 中等跌倒风险
   - 双重任务衰退 > 30% → 高跌倒风险

2. 评估认知功能
   - 认知衰退 > 20% → 明显的注意力缺陷
   
3. 康复进度
   - 追踪同一患者的双重任务衰退
   - 康复有效 → 衰退程度降低

4. 干预目标
   - 如果主要问题是步态衰退 → 重点训练步态稳定
   - 如果主要问题是认知干扰 → 训练任务分工
```

---

## 3. DUO-GAIT 中的认知任务数据缺失问题

### 现状

```
OG_dt_raw/
└── sub_01/
    ├── LF.csv, RF.csv, ...          (IMU 数据完整)
    ├── heart_rate.CSV               (心率完整)
    ├── transcript_control.csv       (认知任务数据)
    └── transcript_fatigue.csv       (认知任务数据)

但问题是:
- transcript 中有很多空白的 duration(s) 列
- 这意味着并非所有数字都有时间戳记录
- 可能是实验设计或数据录制问题
```

### 如何处理缺失的 duration 数据？

```python
def handle_missing_durations(transcript_df):
    """处理缺失的时间戳"""
    
    # 方案 1: 删除缺失行（保守）
    clean_df = transcript_df.dropna(subset=['duration(s)'])
    
    # 方案 2: 插值（乐观）
    transcript_df['duration(s)'].interpolate(method='linear', inplace=True)
    
    # 方案 3: 用平均值填充
    avg_duration = transcript_df['duration(s)'].median()
    transcript_df['duration(s)'].fillna(avg_duration, inplace=True)
    
    return transcript_df

# 建议: 用方案 1 (删除缺失)，这样更保守、更可信
```

---

## 总结表

| 问题 | 答案 |
|------|------|
| **四元数怎么来的？** | IMU 芯片内部的 EKF 算法实时计算，不是从加速度算的 |
| **自采四元数麻烦吗？** | ⭐⭐ 若硬件支持，很简单；⭐⭐⭐ 若要自实现 Madgwick，中等麻烦 |
| **认知数据怎么读？** | 倒序计数任务，统计准确率、速度、错误数 |
| **怎么验证步态↔认知关联？** | 比较 ST vs DT 条件下的衰退程度，相关性高说明双重任务干扰明显 |
| **缺失的 duration 怎么办？** | 删除缺失值（最保险）或用插值/平均值填充 |

