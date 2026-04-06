# 老年人康复运动分析系统 (Elder Rehabilitation Exercise Assessment)

## 项目概述

一套完整的信号处理管道，用于从可穿戴设备 (IMU + 心率监测) 中提取和分析老年人康复运动指标。

**主要功能**：
- ✅ 步态特征提取 (步频、步长、步长变异性)
- ✅ 心率指标计算 (平均心率、最大心率、心率恢复)
- ✅ 数据质量评估和异常检测
- ✅ 多源数据融合处理

---

## 📁 项目结构

```
elder_rehab/
├── README.md                           # 本文件
├── .gitignore                          # Git 忽略配置
├── input.json                          # 示例输入配置
│
├── signal_processing_pipeline/         # 核心处理管道
│   ├── config.py                       # 全局配置参数
│   ├── main.py                         # 主程序入口
│   ├── requirements.txt                # Python 依赖
│   │
│   ├── modules/                        # 计算模块
│   │   ├── step_frequency.py           # 步频计算
│   │   ├── step_length.py              # 步长计算
│   │   ├── step_variability.py         # 步长变异性
│   │   ├── hr_mean.py                  # 心率指标 (QRS 检测)
│   │   └── quality_anomaly.py          # 数据质量和异常检测
│   │
│   ├── utils/                          # 工具函数
│   │   ├── dataloader.py               # 多格式数据加载
│   │   ├── preprocessing.py            # 信号预处理 (滤波、重采样)
│   │   └── __init__.py
│   │
│   ├── validate_duo_gait.py            # ⭐ DUO-GAIT 真实数据验证
│   ├── validate_duo_gait_batch.py      # ⭐ 批量验证脚本
│   ├── DUO_GAIT_VALIDATION_GUIDE.md    # ⭐ DUO-GAIT 使用指南
│   │
│   ├── validate_small_sample.py        # 合成数据验证 (逻辑验证)
│   ├── validate_improved.py            # 改进的合成数据验证
│   ├── VALIDATION_REPORT.md            # 验证报告
│   ├── VALIDATION_SUMMARY.py           # 验证摘要
│   │
│   └── README.md                       # 模块文档
│
├── EXTERNAL_DRIVE_GUIDE.md             # 外挂硬盘数据访问指南
│
└── docs/                               # 文档 (可选)
    └── architecture.md                 # 系统架构说明
```

---

## 🚀 快速开始

### 1. 环境配置

```bash
# 创建 conda 环境
conda create -n elder python=3.9
conda activate elder

# 安装依赖
cd signal_processing_pipeline
pip install -r requirements.txt
```

### 2. 验证系统（使用真实 DUO-GAIT 数据）

```bash
# 单个参与者验证
python validate_duo_gait.py

# 批量验证 (前 3 个参与者)
python validate_duo_gait_batch.py

# 详细使用请见: DUO_GAIT_VALIDATION_GUIDE.md
```

### 3. 运行完整管道

```bash
python main.py --input ../input.json --output ./output/
```

---

## 📊 支持的数据集

### 1. DUO-GAIT (推荐 ⭐)
- **位置**: `/Volumes/ChouSSD/elder_datasets/DUO-GAIT/`
- **特点**: 真实康复患者、多部位 IMU、同步心率
- **参与者**: 18+ 人
- **任务**: 单任务 (ST) 和双任务 (DT)

### 2. GSTRIDE
- **位置**: `/Volumes/ChouSSD/elder_datasets/GSTRIDE_database/`
- **特点**: 标准步态数据库，IMU 传感器
- **采样率**: 104-128 Hz

### 3. PhysioNet Wearable Frailty
- **位置**: `/Volumes/ChouSSD/elder_datasets/PhysioNet_Wearable_Frailty/`
- **特点**: 心电图 (ECG) 数据，官方 QRS 标注

---

## 📈 验证结果

### 小批量验证 (3 个参与者)
```
✓ 成功率: 100%
✓ 指标一致性: A+ 优秀
✓ 数据完整性: 100%

指标范围:
- 步频: 1.05 - 1.65 Hz (合理 ✓)
- 步长: 0.30 - 0.47 m (合理 ✓)  
- 平均心率: 93 - 125 bpm (合理 ✓)
```

更多详情见: [DUO_GAIT_VALIDATION_GUIDE.md](signal_processing_pipeline/DUO_GAIT_VALIDATION_GUIDE.md)

---

## 🔧 配置

编辑 `signal_processing_pipeline/config.py` 来修改参数：

```python
# 采样率
TARGET_SAMPLE_RATE = 100

# 数据路径
EXTERNAL_DRIVE_PATH = "/Volumes/ChouSSD"
DUO_GAIT_DATA_DIR = f"{EXTERNAL_DRIVE_PATH}/DUO-GAIT"

# 算法参数
MIN_PEAK_DISTANCE_SEC = 0.06  # 步频峰值最小间距
PEAK_HEIGHT_MULTIPLIER = 1.0  # 峰值高度阈值

# 心率范围
HR_MIN_BPM = 30
HR_MAX_BPM = 200
```

---

## 📝 当前验证状态

| 模块 | 验证 | 数据源 | 状态 |
|------|------|--------|------|
| 步频计算 | ✅ | DUO-GAIT (3 subjects) | ✓ 优秀 |
| 步长计算 | ✅ | DUO-GAIT (3 subjects) | ✓ 优秀 |
| 步长变异性 | ✅ | 合成数据 | ✓ 逻辑正确 |
| 心率计算 | ✅ | DUO-GAIT (3 subjects) | ✓ 优秀 |
| 数据质量检测 | ✅ | DUO-GAIT | ✓ 100% 完整 |
| 异常检测 | ✅ | 合成数据 | ✓ 正常 |

---

## 🔗 数据访问

所有数据集已迁移到外挂硬盘：

```bash
# 查看硬盘挂载
ls /Volumes/ChouSSD/elder_datasets/

# Python 访问
import config
print(config.DUO_GAIT_DATA_DIR)  # /Volumes/ChouSSD/elder_datasets/DUO-GAIT
```

详见: [EXTERNAL_DRIVE_GUIDE.md](EXTERNAL_DRIVE_GUIDE.md)

---

## 📚 文档

- [外挂硬盘访问指南](EXTERNAL_DRIVE_GUIDE.md) - 数据集位置和访问方法
- [DUO-GAIT 验证指南](signal_processing_pipeline/DUO_GAIT_VALIDATION_GUIDE.md) - 数据集和结果说明
- [验证报告](signal_processing_pipeline/VALIDATION_REPORT.md) - 详细验证结果
- [系统架构](docs/architecture.md) - 技术架构说明

---

## 🛠️ 依赖

- Python 3.9+
- NumPy, SciPy, Pandas
- scikit-learn
- wfdb (PhysioNet 数据)
- NeuroKit2 (ECG 处理)

完整列表见: [requirements.txt](signal_processing_pipeline/requirements.txt)

---

## 📧 联系方式

项目维护者: [您的名字]  
最后更新: 2026-04-06

---

## 📜 许可证

MIT License

---

## 🎯 后续工作

- [ ] 扩展验证到所有 DUO-GAIT 参与者
- [ ] 对比单任务 vs 双任务性能差异
- [ ] 实现跌倒风险预测模型
- [ ] 性能优化和并行处理
- [ ] 医学数据库集成
