"""
完整处理管道示例 - Complete Processing Pipeline

演示从数据加载到输出的完整流程
"""

import json
import logging
import numpy as np
from datetime import datetime
from typing import Dict

import config
from utils.dataloader import DataLoader
from utils.preprocessing import SignalPreprocessor
from modules.step_frequency import StepFrequency
from modules.step_length import StepLength
from modules.step_variability import StepVariability
from modules.hr_mean import HRMean, HRMax, HRRecovery
from modules.quality_anomaly import QualityChecker, AnomalyDetector

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """完整的处理管道"""
    
    def __init__(self, verbose: bool = True):
        """初始化管道"""
        self.verbose = verbose
        
        # 数据加载和预处理
        self.dataloader = DataLoader(verbose=verbose)
        self.preprocessor = SignalPreprocessor()
        
        # IMU 计算
        self.step_freq_calc = StepFrequency()
        self.step_len_calc = StepLength()
        self.step_var_calc = StepVariability()
        
        # 心率计算
        self.hr_mean_calc = HRMean()
        self.hr_max_calc = HRMax()
        self.hr_recovery_calc = HRRecovery()
        
        # 质量检查
        self.quality_checker = QualityChecker()
        self.anomaly_detector = AnomalyDetector()
    
    def process_file(self, filepath: str, source: str = 'gstride',
                    session_id: str = None, player_id: str = None) -> Dict:
        """
        处理单个文件的完整流程
        
        Parameters
        ----------
        filepath : str
            数据文件路径
        source : str
            数据来源 ('gstride', 'physionet', 'csv')
        session_id : str, optional
            会话ID
        player_id : str, optional
            受试者ID
        
        Returns
        -------
        dict
            符合 input.json 格式的输出
        """
        
        logger.info(f"开始处理: {filepath}")
        
        # 1. 加载数据
        logger.info("Step 1: 加载数据...")
        if source == 'gstride':
            data = self.dataloader.load_gstride(filepath)
        elif source == 'physionet':
            # 假设 filepath 是记录名称
            data = self.dataloader.load_physionet_wfdb(filepath)
        elif source == 'csv':
            data = self.dataloader.load_csv(filepath)
        else:
            raise ValueError(f"未知的数据来源: {source}")
        
        # 2. 预处理
        logger.info("Step 2: 预处理（滤波、重采样）...")
        processed_data = self.preprocessor.process(data, window_length=config.WINDOW_LENGTH_SEC)
        
        # 3. 计算 IMU 特征
        logger.info("Step 3: 计算 IMU 特征...")
        imu_features = {}
        
        if 'acc_x' in processed_data:
            imu_features['step_frequency_hz'] = self.step_freq_calc.calculate(processed_data)
            imu_features['step_length_m'] = self.step_len_calc.calculate(processed_data)
            imu_features['step_time_variability_ms'] = self.step_var_calc.calculate(processed_data)
        else:
            imu_features = {k: None for k in ['step_frequency_hz', 'step_length_m', 'step_time_variability_ms']}
        
        # 4. 计算心率特征
        logger.info("Step 4: 计算心率特征...")
        hr_features = {}
        
        if 'ecg' in processed_data:
            hr_features['hr_mean_bpm'] = self.hr_mean_calc.calculate(processed_data)
            hr_features['hr_max_bpm'] = self.hr_max_calc.calculate(processed_data)
            hr_features['hr_recovery_bpm_per_min'] = self.hr_recovery_calc.calculate(processed_data)
        else:
            hr_features = {k: None for k in ['hr_mean_bpm', 'hr_max_bpm', 'hr_recovery_bpm_per_min']}
        
        # 5. 异常检测和质量评估
        logger.info("Step 5: 异常检测和质量评估...")
        anomalies = self.anomaly_detector.detect_all_anomalies(
            processed_data,
            hr_mean=hr_features.get('hr_mean_bpm'),
            hrr=hr_features.get('hr_recovery_bpm_per_min')
        )
        
        imu_anomalies = anomalies.get('imu', [])
        hr_anomalies = anomalies.get('hr', [])
        
        # 质量分数
        imu_quality = self.quality_checker.calculate_imu_data_quality(processed_data) or 0.5
        hr_quality = self.quality_checker.calculate_ecg_data_quality(processed_data) or 0.5
        
        imu_quality = max(0.0, imu_quality - len(imu_anomalies) * 0.15)
        hr_quality = max(0.0, hr_quality - len(hr_anomalies) * 0.10)
        
        imu_quality_reason = self.quality_checker.get_quality_reason(imu_quality, imu_anomalies)
        hr_quality_reason = self.quality_checker.get_quality_reason(hr_quality, hr_anomalies)
        
        # 6. 生成输出
        logger.info("Step 6: 生成 JSON 输出...")
        
        if session_id is None:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if player_id is None:
            player_id = f"player_{np.random.randint(1, 10000)}"
        
        output = {
            "metadata": {
                "session_id": session_id,
                "player_id": player_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "window_sec": config.WINDOW_LENGTH_SEC,
                "trigger_event": "window_complete",
                "source": source
            },
            "imu": {
                "features": imu_features,
                "anomaly_flags": imu_anomalies,
                "data_quality": float(imu_quality),
                "quality_reason": imu_quality_reason
            },
            "heart_rate": {
                "features": hr_features,
                "anomaly_flags": hr_anomalies,
                "data_quality": float(hr_quality),
                "quality_reason": hr_quality_reason
            }
        }
        
        logger.info("处理完成✓")
        
        return output
    
    def save_output(self, output: Dict, output_path: str = None) -> str:
        """
        保存输出为 JSON 文件
        
        Parameters
        ----------
        output : dict
            输出字典
        output_path : str, optional
            输出文件路径。如果为 None，使用默认路径
        
        Returns
        -------
        str
            保存文件路径
        """
        
        if output_path is None:
            session_id = output['metadata']['session_id']
            output_path = f"{config.OUTPUT_DIR}/{session_id}.json"
        
        # 确保目录存在
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info(f"输出已保存: {output_path}")
        
        return output_path


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    # 创建管道
    pipeline = ProcessingPipeline(verbose=True)
    
    # 示例 1：处理合成数据
    print("\n" + "="*60)
    print("示例：处理合成 GSTRIDE 数据")
    print("="*60)
    
    # 创建示例数据
    fs = 104
    duration = 30
    t = np.arange(0, duration, 1/fs)
    
    signal = np.sin(2 * np.pi * 1.5 * t) + 0.05 * np.random.randn(len(t))
    
    # 保存为临时 CSV
    import pandas as pd
    temp_file = "/tmp/test_data.csv"
    df = pd.DataFrame({
        'timestamp': t,
        'acc_x': signal,
        'acc_y': 0.5 * signal,
        'acc_z': 9.8 + 0.1 * signal,
        'gyr_x': 0.01 * np.random.randn(len(t)),
        'gyr_y': 0.01 * np.random.randn(len(t)),
        'gyr_z': 0.01 * np.random.randn(len(t))
    })
    df.to_csv(temp_file, index=False)
    
    # 处理
    output = pipeline.process_file(temp_file, source='csv',
                                  session_id='test_session_001',
                                  player_id='test_player_001')
    
    # 输出结果
    print("\n输出:")
    print(json.dumps(output, indent=2))
    
    # 保存
    output_file = pipeline.save_output(output, f"{config.OUTPUT_DIR}/test_output.json")
    
    print("\n✓ 处理完成！")
