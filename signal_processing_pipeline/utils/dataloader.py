"""
数据加载模块 - DataLoader

支持加载三种数据格式：
1. GSTRIDE 文本格式
2. PhysioNet WFDB 格式
3. 通用 CSV 格式
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
import scipy.io as sio
from typing import Dict, Tuple, Optional, Union
import logging

import config

logger = logging.getLogger(__name__)


class DataLoader:
    """通用数据加载器"""
    
    def __init__(self, verbose: bool = config.VERBOSE_LOGGING):
        self.verbose = verbose
        if self.verbose:
            logger.info("DataLoader 初始化完成")
    
    def load_gstride(self, filepath: str, device_id: Optional[str] = None,
                     calibration_matrix: Optional[np.ndarray] = None) -> Dict:
        """
        加载 GSTRIDE 数据文件
        
        Parameters
        ----------
        filepath : str
            数据文件路径，格式：V001_0001.txt
        device_id : str, optional
            设备ID，用于查询采样率配置
        calibration_matrix : np.ndarray, optional
            校准矩阵，形状 (6, 6)。如果为None，使用单位矩阵
        
        Returns
        -------
        dict
            包含以下键的字典：
            - 'acc_x', 'acc_y', 'acc_z': 加速度（m/s²，SI单位）
            - 'gyr_x', 'gyr_y', 'gyr_z': 陀螺仪（rad/s，SI单位）
            - 'timestamp': 时间戳（秒）
            - 'sample_rate': 采样率（Hz）
            - 'filename': 源文件名
        
        Examples
        --------
        >>> loader = DataLoader()
        >>> data = loader.load_gstride('V001_0001.txt', device_id='0001')
        >>> print(data['acc_x'].shape)  # (N,)
        """
        
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"文件不存在: {filepath}")
        
        # 读取原始数据（6列）
        raw_data = np.loadtxt(filepath)
        if raw_data.ndim == 1:
            raw_data = raw_data[np.newaxis, :]
        
        if raw_data.shape[1] != 6:
            raise ValueError(f"期望6列数据，但得到{raw_data.shape[1]}列")
        
        if self.verbose:
            logger.info(f"加载 GSTRIDE 文件: {filepath}, 形状: {raw_data.shape}")
        
        # 应用校准矩阵（如果存在）
        if calibration_matrix is not None:
            raw_data = (calibration_matrix @ raw_data.T).T
        
        # 提取各通道
        acc_x, acc_y, acc_z = raw_data[:, 0], raw_data[:, 1], raw_data[:, 2]
        gyr_x, gyr_y, gyr_z = raw_data[:, 3], raw_data[:, 4], raw_data[:, 5]
        
        # 获取采样率
        if device_id and device_id in config.GSTRIDE_DEVICES:
            sample_rate = config.GSTRIDE_DEVICES[device_id]["sample_rate"]
        else:
            sample_rate = config.GSTRIDE_SAMPLE_RATE
        
        # 生成时间戳
        n_samples = len(acc_x)
        timestamp = np.arange(n_samples) / sample_rate
        
        # 返回字典格式
        data_dict = {
            'acc_x': acc_x.astype(np.float32),
            'acc_y': acc_y.astype(np.float32),
            'acc_z': acc_z.astype(np.float32),
            'gyr_x': gyr_x.astype(np.float32),
            'gyr_y': gyr_y.astype(np.float32),
            'gyr_z': gyr_z.astype(np.float32),
            'timestamp': timestamp.astype(np.float32),
            'sample_rate': sample_rate,
            'filename': Path(filepath).name,
            'data_source': 'gstride'
        }
        
        return data_dict
    
    def load_physionet_wfdb(self, record_name: str, base_dir: str = config.PHYSIONET_DATA_DIR,
                           signal_types: list = None) -> Dict:
        """
        加载 PhysioNet WFDB 格式数据
        
        使用 wfdb 库读取 ECG 和加速度数据
        
        Parameters
        ----------
        record_name : str
            记录名称，不含扩展名（如 'sub01_rec01'）
        base_dir : str
            数据库基目录
        signal_types : list, optional
            要加载的信号类型，默认 ['ecg', 'acc']
        
        Returns
        -------
        dict
            包含 ECG 和 ACC 数据的字典，采样率已同步
        """
        
        try:
            import wfdb
        except ImportError:
            raise ImportError("需要安装 wfdb: pip install wfdb")
        
        if signal_types is None:
            signal_types = ['ecg', 'acc']
        
        data_dict = {}
        
        for signal_type in signal_types:
            record_path = os.path.join(base_dir, signal_type, record_name)
            
            if not os.path.exists(record_path + '.hea'):
                logger.warning(f"找不到文件: {record_path}.hea")
                continue
            
            # 使用 wfdb 读取
            record = wfdb.rdrecord(record_path)
            
            if self.verbose:
                logger.info(f"加载 {signal_type.upper()}: {record_name}, "
                           f"采样率: {record.fs}Hz, 长度: {len(record.p_signal)}s")
            
            # 提取信号
            if signal_type == 'ecg':
                data_dict['ecg'] = record.p_signal[:, 0].astype(np.float32)
                data_dict['ecg_sample_rate'] = record.fs
            
            elif signal_type == 'acc':
                if record.p_signal.shape[1] >= 3:
                    data_dict['acc_x'] = record.p_signal[:, 0].astype(np.float32)
                    data_dict['acc_y'] = record.p_signal[:, 1].astype(np.float32)
                    data_dict['acc_z'] = record.p_signal[:, 2].astype(np.float32)
                    data_dict['acc_sample_rate'] = record.fs
        
        if 'ecg' in data_dict:
            # 同步时间戳（使用 ECG 采样率作为参考）
            ecg_fs = data_dict['ecg_sample_rate']
            n_samples = len(data_dict['ecg'])
            data_dict['timestamp'] = np.arange(n_samples) / ecg_fs
            data_dict['sample_rate'] = ecg_fs
        elif 'acc_x' in data_dict:
            acc_fs = data_dict['acc_sample_rate']
            n_samples = len(data_dict['acc_x'])
            data_dict['timestamp'] = np.arange(n_samples) / acc_fs
            data_dict['sample_rate'] = acc_fs
        
        data_dict['filename'] = record_name
        data_dict['data_source'] = 'physionet'
        
        return data_dict
    
    def load_csv(self, filepath: str, sample_rate: float = None,
                 timestamp_col: str = 'timestamp') -> Dict:
        """
        加载 CSV 格式的通用传感器数据
        
        Parameters
        ----------
        filepath : str
            CSV 文件路径
        sample_rate : float, optional
            采样率（Hz）。如果 CSV 不包含时间戳列，则必需
        timestamp_col : str
            时间戳列名，默认 'timestamp'
        
        Returns
        -------
        dict
            传感器数据字典
        
        Examples
        --------
        假设 CSV 包含列：timestamp, acc_x, acc_y, acc_z, gyr_x, gyr_y, gyr_z
        >>> data = loader.load_csv('sensor_data.csv')
        """
        
        df = pd.read_csv(filepath)
        
        if self.verbose:
            logger.info(f"加载 CSV: {filepath}, 列: {list(df.columns)}")
        
        data_dict = {}
        
        # 提取时间戳
        if timestamp_col in df.columns:
            data_dict['timestamp'] = df[timestamp_col].values.astype(np.float32)
            # 如果没有提供采样率，从时间戳推断
            if sample_rate is None:
                dt = np.mean(np.diff(data_dict['timestamp']))
                sample_rate = 1.0 / dt
        else:
            if sample_rate is None:
                raise ValueError("必须提供 sample_rate 或 CSV 包含 timestamp 列")
            n_samples = len(df)
            data_dict['timestamp'] = np.arange(n_samples) / sample_rate
        
        data_dict['sample_rate'] = sample_rate
        
        # 提取传感器通道
        sensor_cols = ['acc_x', 'acc_y', 'acc_z', 'gyr_x', 'gyr_y', 'gyr_z', 'ecg']
        for col in sensor_cols:
            if col in df.columns:
                data_dict[col] = df[col].values.astype(np.float32)
        
        data_dict['filename'] = Path(filepath).name
        data_dict['data_source'] = 'csv'
        
        return data_dict
    
    def load_calibration_matrix(self, calib_file: str) -> np.ndarray:
        """
        加载设备校准矩阵
        
        Parameters
        ----------
        calib_file : str
            校准文件路径（.mat 或 .txt）
        
        Returns
        -------
        np.ndarray
            校准矩阵，形状 (6, 6)
        """
        
        if calib_file.endswith('.mat'):
            mat_data = sio.loadmat(calib_file)
            # 查找矩阵变量（可能的名称）
            for key in ['calibration', 'calib_matrix', 'M']:
                if key in mat_data:
                    return mat_data[key].astype(np.float32)
            # 使用第一个非元数据键
            for key, val in mat_data.items():
                if not key.startswith('__'):
                    return np.array(val, dtype=np.float32)
        
        elif calib_file.endswith('.txt'):
            return np.loadtxt(calib_file, dtype=np.float32)
        
        else:
            raise ValueError(f"不支持的校准文件格式: {calib_file}")
    
    def batch_load_gstride(self, directory: str = config.GSTRIDE_DATA_DIR,
                          pattern: str = 'V*.txt', max_files: int = None) -> list:
        """
        批量加载 GSTRIDE 文件
        
        Parameters
        ----------
        directory : str
            数据目录
        pattern : str
            文件名模式（glob）
        max_files : int, optional
            最多加载文件数
        
        Returns
        -------
        list
            数据字典列表
        """
        
        from glob import glob
        
        files = sorted(glob(os.path.join(directory, pattern)))
        if max_files:
            files = files[:max_files]
        
        all_data = []
        for filepath in files:
            try:
                # 提取设备ID
                filename = Path(filepath).stem
                device_id = filename.split('_')[-1] if '_' in filename else None
                
                data = self.load_gstride(filepath, device_id=device_id)
                all_data.append(data)
                
                if self.verbose:
                    logger.info(f"已加载: {Path(filepath).name}")
            
            except Exception as e:
                logger.error(f"加载失败: {filepath}, 错误: {e}")
        
        if self.verbose:
            logger.info(f"批量加载完成: {len(all_data)}/{len(files)} 文件成功")
        
        return all_data


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    logging.basicConfig(level=logging.INFO)
    
    loader = DataLoader(verbose=True)
    
    # 示例 1：加载 GSTRIDE 文件
    # print("\n--- 加载 GSTRIDE ---")
    # data = loader.load_gstride("../GSTRIDE_database/Test_recordings_raw/V001_0001.txt",
    #                             device_id="0001")
    # print(f"加速度X形状: {data['acc_x'].shape}")
    # print(f"采样率: {data['sample_rate']} Hz")
    
    # 示例 2：加载 CSV
    print("\n--- 加载 CSV ---")
    # data = loader.load_csv("./data/sample_data.csv")
    # print(f"数据形状: {data['acc_x'].shape}")
    
    # 示例 3：批量加载
    print("\n--- 批量加载 GSTRIDE ---")
    # all_data = loader.batch_load_gstride(max_files=3)
    # print(f"加载了 {len(all_data)} 个文件")
