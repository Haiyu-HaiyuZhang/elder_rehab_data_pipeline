# 外挂硬盘访问指南

## 硬盘信息

- **硬盘名称**：ChouSSD
- **挂载路径**：`/Volumes/ChouSSD`
- **数据集位置**：`/Volumes/ChouSSD/elder_datasets/`

---

## 数据集位置

### 已迁移的三个数据集

```
/Volumes/ChouSSD/elder_datasets/
├── DLNN_Framework_Data/           # Deep Learning Framework 数据 (46 MB)
│   ├── Autoencoder_Output_Correct.csv
│   ├── Autoencoder_Output_Incorrect.csv
│   ├── Data_Correct.csv
│   ├── Data_Incorrect.csv
│   ├── Labels_Correct.csv
│   ├── Labels_Incorrect.csv
│   └── ...
│
├── GSTRIDE_database/              # GSTRIDE 步态数据库 (3.2 GB)
│   ├── Gait_analysis_w_Python/
│   ├── Sensor_specifications/
│   ├── Test_outputs_gait_analysis/
│   ├── Test_recordings_calibrated/
│   ├── Test_recordings_raw/
│   ├── Database_register.csv
│   └── ...
│
└── PhysioNet_Wearable_Frailty/    # PhysioNet 可穿戴设备数据 (2.5 GB)
    ├── RECORDS
    ├── ANNOTATORS
    ├── acc/
    ├── ecg/
    ├── subject-info.csv
    └── ...
```

---

## 在 Python 中访问数据

### 方法 1：直接路径访问

```python
import pandas as pd
from pathlib import Path

# 基础路径
datasets_root = Path("/Volumes/ChouSSD/elder_datasets")

# 访问 GSTRIDE 数据
gstride_path = datasets_root / "GSTRIDE_database"
db_register = pd.read_csv(gstride_path / "Database_register.csv")

# 访问 DLNN 数据
dlnn_path = datasets_root / "DLNN_Framework_Data"
data_correct = pd.read_csv(dlnn_path / "Data_Correct.csv")

# 访问 PhysioNet 数据
physionet_path = datasets_root / "PhysioNet_Wearable_Frailty"
subject_info = pd.read_csv(physionet_path / "subject-info.csv")
```

### 方法 2：使用数据加载器

```python
from signal_processing_pipeline.utils.dataloader import DataLoader

loader = DataLoader()

# 批量加载 GSTRIDE 数据
datasets = loader.batch_load_gstride(
    "/Volumes/ChouSSD/elder_datasets/GSTRIDE_database/Test_recordings_raw/*"
)

# 加载 PhysioNet 数据
data = loader.load_physionet_wfdb(
    "/Volumes/ChouSSD/elder_datasets/PhysioNet_Wearable_Frailty/RECORDS",
    record_name="p001"
)
```

---

## 硬盘信息查询

### 查看硬盘挂载状态

```bash
# 列出所有挂载的硬盘
diskutil list

# 显示 ChouSSD 的详细信息
diskutil info ChouSSD

# 查看硬盘空间使用情况
df -h /Volumes/ChouSSD
```

### 查看数据集大小

```bash
# 显示每个数据集的大小
du -sh /Volumes/ChouSSD/elder_datasets/*

# 查看总占用空间
du -sh /Volumes/ChouSSD/elder_datasets/
```

---

## 配置脚本

如果需要在脚本中配置硬盘路径，编辑 `config.py`：

```python
# config.py

# 外挂硬盘路径
EXTERNAL_DRIVE_PATH = "/Volumes/ChouSSD"
DATASETS_ROOT = f"{EXTERNAL_DRIVE_PATH}/elder_datasets"

# 各数据集路径
DLNN_DATA_PATH = f"{DATASETS_ROOT}/DLNN_Framework_Data"
GSTRIDE_DATA_PATH = f"{DATASETS_ROOT}/GSTRIDE_database"
PHYSIONET_DATA_PATH = f"{DATASETS_ROOT}/PhysioNet_Wearable_Frailty"

# 默认数据源
DEFAULT_DATA_SOURCE = "gstride"
DEFAULT_GSTRIDE_DIR = f"{GSTRIDE_DATA_PATH}/Test_recordings_raw"
```

然后在脚本中使用：

```python
import config
from utils.dataloader import DataLoader

loader = DataLoader()
data = loader.load_gstride(f"{config.DEFAULT_GSTRIDE_DIR}/sample_file.txt")
```

---

## 可能的问题与解决

### 问题：硬盘未显示或无法访问

```bash
# 1. 检查硬盘是否已挂载
ls /Volumes/

# 2. 如果没看到，重新插入硬盘并等待 5 秒

# 3. 强制重新扫描
diskutil eject ChouSSD
diskutil mount ChouSSD
```

### 问题：权限错误（Permission denied）

```bash
# 检查目录权限
ls -la /Volumes/ChouSSD/elder_datasets/

# 如果需要，修改权限
chmod -R u+rwx /Volumes/ChouSSD/elder_datasets/
```

### 问题：文件读取速度慢

- USB 3.0 硬盘通常速度在 50-100 MB/s
- 如果速度过慢，检查 USB 连接是否已完全插入
- 避免同时进行多个读写操作

### 问题：卸载硬盘失败（Unmount of disk failed）

如果出现错误：`Unmount of disk6 failed: at least one volume could not be unmounted. Unmount was dissented by PID 19790 (managedcorespotlightd)`

**最有效的解决方案（推荐）：**

```bash
# 1. 关闭外接盘的 Spotlight
sudo mdutil -i off /Volumes/ChouSSD

# 2. 然后再尝试卸载
diskutil eject ChouSSD
```

**其他解决方案：**

```bash
# 方案 B：强制卸载（如果方案 A 不行）
diskutil unmountDisk force ChouSSD

# 方案 C：禁用所有 Spotlight 再卸载
sudo mdutil -a -i off
sleep 2
diskutil eject ChouSSD
sudo mdutil -a -i on
```

**或者从系统设置中：**
1. 打开 **System Settings** → **Siri & Spotlight** → **Spotlight Search**
2. 在搜索结果中勾选"Exclude"并添加 `/Volumes/ChouSSD`

**最简单的做法（不用命令行）：**
- 打开 Finder，在侧边栏找到 **ChouSSD** 
- 点击名称右边的 **⏏️** 按钮即可安全弹出

---

## 重要提示

⚠️ **备份建议**
- 这是您的原始数据，建议保持至少一份备份
- 定期检查硬盘健康状况

⚠️ **安全移除**
```bash
# 不要直接拔出硬盘，请先卸载
diskutil eject ChouSSD

# 等待输出显示已卸载后再拔出
```

---

## 快速命令参考

```bash
# 进入数据集目录
cd /Volumes/ChouSSD/elder_datasets

# 列出所有数据集
ls -lah /Volumes/ChouSSD/elder_datasets/

# 验证数据完整性
du -sh /Volumes/ChouSSD/elder_datasets/GSTRIDE_database
du -sh /Volumes/ChouSSD/elder_datasets/DLNN_Framework_Data  
du -sh /Volumes/ChouSSD/elder_datasets/PhysioNet_Wearable_Frailty

# 在 Python 中开始工作
conda activate elder
cd /Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline
python -c "
import pandas as pd
path = '/Volumes/ChouSSD/elder_datasets/GSTRIDE_database'
print(f'GSTRIDE database loaded from {path}')
"
```

---

## 更新日期

创建时间：2026-04-05  
硬盘品牌：ChouSSD  
总容量：~8 TB  
已用容量：~5.7 GB（三个数据集）
