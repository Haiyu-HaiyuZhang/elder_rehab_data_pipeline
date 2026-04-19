# DUO-GAIT 数据处理 Python 实现指南

## 概述

本文件提供了在 Python 中使用 DUO-GAIT 三层数据的具体实现方法。

---

## 1. 数据加载工具类

### 创建 `data_loader.py`

```python
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Optional

class DUOGaitDataLoader:
    """DUO-GAIT 数据加载器 - 处理 raw, interim, processed 层数据"""
    
    # 数据目录常量
    BASE_DIR = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT"
    RAW_DIR = f"{BASE_DIR}/raw"
    INTERIM_DIR = f"{BASE_DIR}/interim"
    PROCESSED_DIR = f"{BASE_DIR}/processed"
    
    # 任务类型映射
    TASK_PHASES = {
        'st_control': 'OG_st_control',
        'st_fatigue': 'OG_st_fatigue',
        'st_sit_to_stand': 'OG_st_sit_to_stand',
        'dt_control': 'OG_dt_control',
        'dt_fatigue': 'OG_dt_fatigue',
        'dt_sit_to_stand': 'OG_dt_sit_to_stand',
    }
    
    def __init__(self):
        """初始化加载器，预加载元数据"""
        self.subject_info = pd.read_csv(f"{self.RAW_DIR}/subject_info.csv")
        self.ipaq = pd.read_csv(f"{self.RAW_DIR}/IPAQ.csv")
    
    # ========================================================================
    # 1. RAW 层操作
    # ========================================================================
    
    def load_raw_imu(self, subject_id: str, task_type: str, sensor: str) -> pd.DataFrame:
        """
        加载 raw IMU 数据
        
        Args:
            subject_id: 'sub_01', 'sub_02' 等
            task_type: 'st' 或 'dt'
            sensor: 'LF', 'RF', 'LL', 'RL', 'LW', 'RW', 'HE', 'ST', 'SA'
            
        Returns:
            DataFrame: 加速度、陀螺仪、四元数等数据
        """
        task_dir = 'OG_st_raw' if task_type == 'st' else 'OG_dt_raw'
        csv_path = f"{self.RAW_DIR}/{task_dir}/{subject_id}/{sensor}.csv"
        
        # 跳过元数据行，直接到数据
        df = pd.read_csv(csv_path, skiprows=5)
        
        # 将数值列转换为 float
        numeric_cols = df.columns.drop('Time(s)')
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        
        return df
    
    def load_raw_hr(self, subject_id: str, task_type: str) -> Tuple[pd.DataFrame, pd.Series]:
        """
        加载 raw 心率数据（连续录制版本）
        
        Args:
            subject_id: 'sub_01' 等
            task_type: 'st' 或 'dt'
            
        Returns:
            (df_full, hr_values): 完整 DataFrame 和提取的 HR 值数组
        """
        task_dir = 'OG_st_raw' if task_type == 'st' else 'OG_dt_raw'
        hr_path = f"{self.RAW_DIR}/{task_dir}/{subject_id}/heart_rate.CSV"
        
        # 找到数据开始行
        with open(hr_path) as f:
            for i, line in enumerate(f):
                if 'Sample rate' in line:
                    data_start_row = i
                    break
        
        df_hr = pd.read_csv(hr_path, skiprows=data_start_row)
        hr_values = pd.to_numeric(df_hr['HR (bpm)'], errors='coerce').dropna()
        
        return df_hr, hr_values
    
    def get_mhr(self, subject_id: str) -> int:
        """
        获取最大心率（220 - 年龄）
        
        Args:
            subject_id: 'sub_01' 等
            
        Returns:
            int: 最大心率 (bpm)
        """
        age = self.subject_info.loc[self.subject_info['sub'] == subject_id, 'age'].values[0]
        return 220 - int(age)
    
    # ========================================================================
    # 2. INTERIM 层操作
    # ========================================================================
    
    def load_interim_imu(self, subject_id: str, task_phase: str, sensor: str) -> pd.DataFrame:
        """
        加载 interim 切分好的 6 分钟IMU数据
        
        Args:
            subject_id: 'sub_01' 等
            task_phase: 'st_control', 'st_fatigue', 'dt_control' 等
            sensor: 'LF', 'RF' 等
            
        Returns:
            DataFrame: 6分钟的IMU数据（≈48,500行）
        """
        folder_name = self.TASK_PHASES[task_phase]
        csv_path = f"{self.INTERIM_DIR}/{folder_name}/{subject_id}/{sensor}.csv"
        
        df = pd.read_csv(csv_path, skiprows=5)
        numeric_cols = df.columns.drop('Time(s)')
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
        
        return df
    
    def get_interim_duration(self, subject_id: str, task_phase: str, sensor: str = 'LF') -> float:
        """
        计算 interim 数据的实际时间长度
        
        Args:
            subject_id: 'sub_01'
            task_phase: 'st_control' 等
            sensor: 任意 IMU 传感器（它们应该有相同的采样点）
            
        Returns:
            float: 时间长度（秒）
        """
        df = self.load_interim_imu(subject_id, task_phase, sensor)
        n_rows = len(df)
        sample_rate = 128  # Hz
        duration_sec = n_rows / sample_rate
        return duration_sec
    
    # ========================================================================
    # 3. PROCESSED 层操作
    # ========================================================================
    
    def load_processed_aggregate(self, subject_id: str, task_phase: str) -> pd.Series:
        """
        加载 processed 聚合参数（全局指标）
        
        Args:
            subject_id: 'sub_01'
            task_phase: 'st_control' 等
            
        Returns:
            Series: 包含 stride_lengths_avg, cadence_avg, speed_avg 等
        """
        folder_name = self.TASK_PHASES[task_phase]
        csv_path = f"{self.PROCESSED_DIR}/{folder_name}/{subject_id}/aggregate_params.csv"
        
        df = pd.read_csv(csv_path)
        return df.iloc[0]  # 通常只有一行
    
    def load_processed_core_params(self, subject_id: str, task_phase: str, foot: str = 'left') -> pd.DataFrame:
        """
        加载 processed 核心参数（逐步数据）
        
        Args:
            subject_id: 'sub_01'
            task_phase: 'st_control' 等
            foot: 'left' 或 'right'
            
        Returns:
            DataFrame: 每行代表一个步长及其参数
        """
        folder_name = self.TASK_PHASES[task_phase]
        foot_prefix = 'left' if foot == 'left' else 'right'
        csv_path = f"{self.PROCESSED_DIR}/{folder_name}/{subject_id}/{foot_prefix}_foot_core_params.csv"
        
        df = pd.read_csv(csv_path)
        return df
    
    # ========================================================================
    # 4. 便利方法
    # ========================================================================
    
    def get_subject_info(self, subject_id: str) -> pd.Series:
        """获取受试者元数据"""
        return self.subject_info[self.subject_info['sub'] == subject_id].iloc[0]
    
    def validate_hr_bounds(self, subject_id: str, hr_values: np.ndarray, task_type: str = 'st') -> Dict[str, any]:
        """
        验证 HR 值是否在合理范围内
        
        Returns:
            Dict with 'valid': bool, 'issues': list of strings
        """
        subject = self.get_subject_info(subject_id)
        mhr = self.get_mhr(subject_id)
        
        # 参考值从 subject_info
        ref_baseline = subject[f'{task_type}_HR_baseline']
        ref_fatigue = subject[f'{task_type}_HR_fatigue']
        
        issues = []
        
        # 检查 min/max values
        hr_min = np.nanmin(hr_values)
        hr_max = np.nanmax(hr_values)
        
        if hr_min < 30:
            issues.append(f"HR min too low: {hr_min} bpm")
        if hr_max > mhr * 1.15:
            issues.append(f"HR max too high: {hr_max} bpm (>{mhr*1.15})")
        if hr_max < ref_fatigue * 0.85:
            issues.append(f"HR max too low: {hr_max} vs expected {ref_fatigue}")
        
        return {
            'valid': len(issues) == 0,
            'hr_min': hr_min,
            'hr_max': hr_max,
            'mhr': mhr,
            'ref_baseline': ref_baseline,
            'ref_fatigue': ref_fatigue,
            'issues': issues
        }

```

---

## 2. 数据对齐工具

### 创建 `data_align.py`

```python
import pandas as pd
import numpy as np
from typing import Tuple, Optional
from .data_loader import DUOGaitDataLoader

class DataAligner:
    """对齐 raw 数据中的 HR 段与 interim IMU 数据"""
    
    def __init__(self):
        self.loader = DUOGaitDataLoader()
    
    def find_hr_segment_in_raw(
        self,
        subject_id: str,
        task_phase: str,
        hr_raw_values: np.ndarray,
        window_size_sec: Optional[int] = None
    ) -> Tuple[int, int, float]:
        """
        在 raw 连续 HR 数据中定位对应 interim IMU 的 HR 片段
        
        Strategy:
            1. 计算 interim IMU 的时间长度（基于行数）
            2. 该长度就是 HR 数据中应该截取的长度
            3. 在 raw HR 中寻找匹配的心率升降模式
            
        Args:
            subject_id: 'sub_01'
            task_phase: 'st_control' 等
            hr_raw_values: 完整的 raw HR 时间序列（1 Hz 采样）
            window_size_sec: 指定窗口大小（秒），默认从 interim IMU 推断
            
        Returns:
            (start_idx, end_idx, confidence): HR 数据中的起始和结束索引，置信度
        """
        
        # 如果没有指定，从 interim 计算
        if window_size_sec is None:
            window_size_sec = self.loader.get_interim_duration(subject_id, task_phase)
        
        window_size = int(window_size_sec)  # 转换为行数（HR频率1Hz）
        
        # 从subject_info获取参考值
        subject = self.loader.get_subject_info(subject_id)
        ref_baseline = subject[f'{task_phase.split("_")[0]}_HR_baseline']
        ref_fatigue = subject[f'{task_phase.split("_")[0]}_HR_fatigue']
        
        # 在 raw HR 中搜索匹配的模式
        best_score = -1
        best_start = 0
        
        for start_idx in range(len(hr_raw_values) - window_size):
            segment = hr_raw_values.iloc[start_idx:start_idx + window_size]
            
            # 计算该段的特征
            seg_min = segment.min()
            seg_max = segment.max()
            seg_range = seg_max - seg_min
            seg_mean = segment.mean()
            
            # 评分：与预期相符的程度
            # 运动任务应该从低心率上升到高心率
            score = 0
            
            # 检查基线匹配
            baseline_error = abs(segment.iloc[0] - ref_baseline) / ref_baseline
            if baseline_error < 0.15:
                score += 10
            
            # 检查峰值匹配
            fatigue_error = abs(seg_max - ref_fatigue) / ref_fatigue
            if fatigue_error < 0.1:
                score += 20
            
            # 检查心率范围（应该有上升）
            if seg_range > (ref_fatigue - ref_baseline) * 0.7:
                score += 5
            
            if score > best_score:
                best_score = score
                best_start = start_idx
        
        end_idx = best_start + window_size
        confidence = min(best_score / 35.0, 1.0)  # 归一化到 0-1
        
        return best_start, end_idx, confidence
    
    def extract_aligned_hr(
        self,
        subject_id: str,
        task_type: str,
        task_phase: str
    ) -> pd.Series:
        """
        完整流程：从 raw HR 提取与 interim IMU 对齐的 HR 数据
        
        Returns:
            Series: 对齐后的 HR 时间序列
        """
        
        # 1. 加载数据
        _, hr_raw = self.loader.load_raw_hr(subject_id, task_type)
        
        # 2. 查找对齐位置
        start_idx, end_idx, confidence = self.find_hr_segment_in_raw(
            subject_id, task_phase, hr_raw
        )
        
        # 3. 提取对齐的 HR
        hr_aligned = hr_raw.iloc[start_idx:end_idx]
        
        print(f"Found HR segment for {subject_id} {task_phase}")
        print(f"  Position: [{start_idx}, {end_idx}]")
        print(f"  Duration: {len(hr_aligned):.0f} seconds")
        print(f"  HR range: {hr_aligned.min():.0f} - {hr_aligned.max():.0f} bpm")
        print(f"  Alignment confidence: {confidence:.1%}")
        
        return hr_aligned

```

---

## 3. 验证工具

### 创建 `validation.py`

```python
import pandas as pd
import numpy as np
from typing import Dict

class ProcessedDataValidator:
    """对比 Python 计算结果与 processed 基准数据"""
    
    def __init__(self, loader):
        self.loader = loader
    
    def validate_metrics(
        self,
        subject_id: str,
        task_phase: str,
        py_results: Dict
    ) -> Dict:
        """
        对比 Python 算法结果与 processed 基准
        
        Args:
            subject_id: 'sub_01'
            task_phase: 'st_control'
            py_results: {
                'step_frequency': float,  # Hz
                'step_length': float,     # m
                'step_variability': float # ms or CV%
            }
            
        Returns:
            Dict: 对比结果，包括误差百分比
        """
        
        # 加载基准数据
        baseline = self.loader.load_processed_aggregate(subject_id, task_phase)
        
        # 对比指标
        comparisons = {}
        
        # 1. 步频 / 节奏
        py_cadence = py_results['step_frequency'] * 60  # Hz → steps/min
        baseline_cadence = baseline['cadence_avg']
        error_cadence = abs(py_cadence - baseline_cadence) / baseline_cadence * 100
        comparisons['cadence'] = {
            'py': py_cadence,
            'baseline': baseline_cadence,
            'error_pct': error_cadence,
            'status': '✓' if error_cadence < 5 else '✗'
        }
        
        # 2. 步幅
        py_step_length = py_results['step_length']
        baseline_step_length = baseline['stride_lengths_avg']
        error_step_length = abs(py_step_length - baseline_step_length) / baseline_step_length * 100
        comparisons['step_length'] = {
            'py': py_step_length,
            'baseline': baseline_step_length,
            'error_pct': error_step_length,
            'status': '✓' if error_step_length < 10 else '✗'
        }
        
        # 3. 速度
        py_speed = py_results['step_frequency'] * py_results['step_length']
        baseline_speed = baseline['speed_avg']
        error_speed = abs(py_speed - baseline_speed) / baseline_speed * 100
        comparisons['speed'] = {
            'py': py_speed,
            'baseline': baseline_speed,
            'error_pct': error_speed,
            'status': '✓' if error_speed < 10 else '✗'
        }
        
        # 4. 变异系数
        if 'step_variability_cv' in py_results:
            py_cv = py_results['step_variability_cv']
            baseline_cv = baseline['stride_lengths_CV']
            error_cv = abs(py_cv - baseline_cv) / baseline_cv * 100
            comparisons['cv'] = {
                'py': py_cv,
                'baseline': baseline_cv,
                'error_pct': error_cv,
                'status': '✓' if error_cv < 20 else '✗'  # CV 通常变异较大
            }
        
        return comparisons
    
    def print_validation_report(self, comparisons: Dict):
        """打印验证报告"""
        print("\n" + "="*70)
        print("VALIDATION REPORT - Python vs Processed Baseline")
        print("="*70)
        
        for metric, comparison in comparisons.items():
            py = comparison['py']
            baseline = comparison['baseline']
            error = comparison['error_pct']
            status = comparison['status']
            
            print(f"\n{metric.upper()}")
            print(f"  Python calculated:     {py:.4f}")
            print(f"  Processed baseline:    {baseline:.4f}")
            print(f"  Error:                 {error:.2f}%  {status}")

```

---

## 4. 完整使用示例

### 创建 `example_workflow.py`

```python
"""
完整工作流示例：从加载数据到对比验证
"""

from data_loader import DUOGaitDataLoader
from data_align import DataAligner
from validation import ProcessedDataValidator

def main():
    # ====================================================================
    # 初始化
    # ====================================================================
    
    loader = DUOGaitDataLoader()
    aligner = DataAligner()
    validator = ProcessedDataValidator(loader)
    
    # ====================================================================
    # 第1步：选择受试者和任务
    # ====================================================================
    
    subject_id = "sub_01"
    task_type = "st"
    task_phase = "st_control"
    
    print(f"\n{'='*70}")
    print(f"Processing: {subject_id} - {task_phase}")
    print(f"{'='*70}")
    
    # ====================================================================
    # 第2步：加载元数据
    # ====================================================================
    
    subject = loader.get_subject_info(subject_id)
    mhr = loader.get_mhr(subject_id)
    
    print(f"\nSubject Info:")
    print(f"  Age: {subject['age']}")
    print(f"  Sex: {subject['sex']}")
    print(f"  MHR: {mhr} bpm")
    print(f"  ST HR Baseline: {subject['st_HR_baseline']} bpm")
    print(f"  ST HR Fatigue: {subject['st_HR_fatigue']} bpm")
    
    # ====================================================================
    # 第3步：加载 INTERIM IMU 数据（参考）
    # ====================================================================
    
    interim_duration = loader.get_interim_duration(subject_id, task_phase)
    
    print(f"\nInterim IMU Duration:")
    print(f"  {interim_duration:.1f} seconds ({interim_duration/60:.2f} minutes)")
    
    # ====================================================================
    # 第4步：加载 RAW HR 数据并对齐
    # ====================================================================
    
    _, hr_raw = loader.load_raw_hr(subject_id, task_type)
    
    print(f"\nRaw HR Data:")
    print(f"  Total points: {len(hr_raw)}")
    print(f"  Range: {hr_raw.min():.0f} - {hr_raw.max():.0f} bpm")
    
    # 对齐
    hr_aligned = aligner.extract_aligned_hr(subject_id, task_type, task_phase)
    
    # 验证 HR 范围
    hr_validation = loader.validate_hr_bounds(subject_id, hr_aligned.values, task_type)
    print(f"\nHR Validation:")
    for key, val in hr_validation.items():
        if key != 'issues':
            print(f"  {key}: {val}")
    if hr_validation['issues']:
        for issue in hr_validation['issues']:
            print(f"  ⚠ {issue}")
    
    # ====================================================================
    # 第5步：加载 INTERIM IMU 、PROCESSED 比较结果
    # ====================================================================
    
    df_interim_imu = loader.load_interim_imu(subject_id, task_phase, 'LF')
    
    print(f"\nInterim IMU Data (LF):")
    print(f"  Rows: {len(df_interim_imu)}")
    print(f"  Columns: {', '.join(df_interim_imu.columns[:5])}...")
    
    processed_agg = loader.load_processed_aggregate(subject_id, task_phase)
    
    print(f"\nProcessed Aggregate Parameters:")
    print(f"  Stride Length: {processed_agg['stride_lengths_avg']:.4f} m")
    print(f"  Cadence: {processed_agg['cadence_avg']:.1f} steps/min")
    print(f"  Speed: {processed_agg['speed_avg']:.3f} m/s")
    print(f"  Stride CV: {processed_agg['stride_lengths_CV']:.4f}")
    
    # ====================================================================
    # 第6步：模拟 Python 算法结果并验证
    # ====================================================================
    
    # 这里应该是你的步频/步幅算法计算的结果
    py_results = {
        'step_frequency': processed_agg['cadence_avg'] / 60,  # 模拟
        'step_length': processed_agg['stride_lengths_avg'],    # 模拟
        'step_variability_cv': processed_agg['stride_lengths_CV']
    }
    
    comparisons = validator.validate_metrics(subject_id, task_phase, py_results)
    validator.print_validation_report(comparisons)

if __name__ == "__main__":
    main()
```

---

## 5. 集成到已有项目

在你的 `signal_processing_pipeline` 中添加这些模块：

```
signal_processing_pipeline/
├── config.py                  # 【已有】
├── modules/
│   ├── step_frequency.py      # 【已有】
│   ├── step_length.py         # 【已有】
│   └── ...
├── data_loader.py             # 【新增】
├── data_align.py              # 【新增】
├── validation.py              # 【新增】
└── example_workflow.py        # 【新增】
```

### 在 config 中添加数据路径：

```python
# signal_processing_pipeline/config.py

# DUO-GAIT 三层数据路径
DUO_GAIT_BASE = "/Volumes/ChouSSD/elder_datasets/DUO-GAIT"
DUO_GAIT_RAW_DIR = f"{DUO_GAIT_BASE}/raw"
DUO_GAIT_INTERIM_DIR = f"{DUO_GAIT_BASE}/interim"
DUO_GAIT_PROCESSED_DIR = f"{DUO_GAIT_BASE}/processed"

# 元数据
SUBJECT_INFO_CSV = f"{DUO_GAIT_RAW_DIR}/subject_info.csv"
IPAQ_CSV = f"{DUO_GAIT_RAW_DIR}/IPAQ.csv"
```

---

## 6. 快速参考

### 常见操作

```python
# 初始化
from data_loader import DUOGaitDataLoader
loader = DUOGaitDataLoader()

# 获取 MHR
mhr = loader.get_mhr("sub_01")  # 返回: 196

# 加载 interim IMU
df = loader.load_interim_imu("sub_01", "st_control", "LF")

# 加载 processed 基准
baseline = loader.load_processed_aggregate("sub_01", "st_control")

# 验证 HR 范围
validation = loader.validate_hr_bounds("sub_01", hr_array, "st")
```

---

**更新日期**：2026-04-19  
**与主文档关联**：[DATA_ARCHITECTURE_GUIDE.md](DATA_ARCHITECTURE_GUIDE.md)
