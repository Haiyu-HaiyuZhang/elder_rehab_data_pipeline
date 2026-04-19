"""
Windows JSON Exporter - 将 30s 窗口特征输出为分段 JSON

将计算结果按窗口分段生成 JSON，每个窗口一个文件。
格式便于 LLM 处理，同时保留所有特征指标供后续 Fuzzy Logic 使用。
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import pandas as pd

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WindowJSONExporter:
    """30s 窗口特征的 JSON 导出器"""
    
    def __init__(self, output_dir: str = None):
        """
        初始化导出器
        
        Args:
            output_dir: JSON 输出目录，默认为 ./window_jsons/
        """
        self.output_dir = output_dir or "./window_jsons"
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
    
    def create_window_json(
        self,
        window_id: str,
        subject_id: str,
        task_type: str,  # 'st_control', 'st_fatigue', 'dt_control', 'dt_fatigue', etc.
        timestamp: str,  # ISO 8601 格式或简单时间戳
        features: Dict
    ) -> Dict:
        """
        构建单个窗口的 JSON 结构
        
        Args:
            window_id: 窗口编号 (如 'window_001', 'window_002')
            subject_id: 受试者ID (如 'sub_01')
            task_type: 任务类型
            timestamp: 时间戳
            features: 特征字典，应包含：
                - hr_mean, hr_max, hr_std
                - step_frequency, step_length
                - step_var (步幅变异)
                - hr_recovery
                - stride_length
                - rpe_score (可选)
                - (其他计算特征)
        
        Returns:
            格式化的 JSON 字典
        """
        
        # 验证必需特征
        required_features = [
            'hr_mean', 'step_var', 'hr_recovery', 'stride_length'
        ]
        missing = [f for f in required_features if f not in features or features[f] is None]
        if missing:
            logger.warning(f"窗口 {window_id} 缺少特征: {missing}")
        
        # 构建 JSON 结构
        window_json = {
            "metadata": {
                "window_id": window_id,
                "subject_id": subject_id,
                "task_type": task_type,
                "timestamp": timestamp,
                "window_duration_sec": config.WINDOW_LENGTH_SEC,
                "generated_at": datetime.utcnow().isoformat() + "Z"
            },
            "physiological_signals": {
                "heart_rate": {
                    "mean_bpm": float(features.get('hr_mean', 0)),
                    "max_bpm": float(features.get('hr_max', 0)),
                    "min_bpm": float(features.get('hr_min', 0)),
                    "std_bpm": float(features.get('hr_std', 0)),
                    "recovery_bpm_per_min": float(features.get('hr_recovery', 0)),
                    "quality_flag": features.get('hr_quality', 'normal')
                }
            },
            "gait_features": {
                "step_frequency_hz": float(features.get('step_frequency', 0)),
                "step_length_m": float(features.get('step_length', 0)),
                "stride_length_m": float(features.get('stride_length', 0)),
                "step_variability_ms": float(features.get('step_var', 0)),
                "cadence_steps_per_min": float(features.get('step_frequency', 0) * 60),
                "speed_m_per_sec": float(features.get('speed', 0)),
                "quality_flag": features.get('gait_quality', 'normal')
            },
            "subjective_assessment": {
                "rpe_score": int(features.get('rpe_score', 12)),
                "rpe_scale": "Borg 6-20",
                "notes": features.get('exercise_notes', '')
            },
            "computed_indices": {
                "hr_reserve_percent": float(
                    ((features.get('hr_mean', 0) - 60) / (features.get('mhr', 150) - 60) * 100)
                    if features.get('mhr', 150) > 60 else 0
                ),
                "step_regularity": float(
                    100 - min(features.get('step_var', 0), 100)  # 反向：变异越小越规则
                ),
                "locomotion_stability": self._compute_stability(features)
            },
            "raw_feature_values": {
                # 完整的原始特征值，供 Fuzzy Logic 使用
                "hr_mean": float(features.get('hr_mean', 0)),
                "step_var": float(features.get('step_var', 0)),
                "hr_recovery": float(features.get('hr_recovery', 0)),
                "stride_length": float(features.get('stride_length', 0)),
                "rpe_score": float(features.get('rpe_score', 12))
            }
        }
        
        return window_json
    
    @staticmethod
    def _compute_stability(features: Dict) -> float:
        """
        计算运动稳定性指数 (0-100)
        
        基于步频稳定性、步长稳定性、心率稳定性
        """
        # 步伐变异贡献（越低越稳定）
        step_var = float(features.get('step_var', 50))
        step_stability = 100 - min(step_var / 1.5, 100)  # 100ms → 33.3 稳定性
        
        # HR 变异贡献
        hr_std = float(features.get('hr_std', 15))
        hr_stability = 100 - min(hr_std / 0.3, 100)  # 30 bpm std → 0% 稳定性
        
        # 综合稳定性
        stability = (step_stability * 0.6 + hr_stability * 0.4)
        
        return float(max(0, min(100, stability)))
    
    def export_window(
        self,
        window_json: Dict,
        filename: str = None,
        return_path: bool = False
    ) -> Optional[str]:
        """
        导出单个窗口到 JSON 文件
        
        Args:
            window_json: 窗口 JSON 字典
            filename: 输出文件名，默认使用 window_id
            return_path: 是否返回文件路径
        
        Returns:
            保存的文件路径 (如果 return_path=True)
        """
        
        if filename is None:
            window_id = window_json['metadata']['window_id']
            subject_id = window_json['metadata']['subject_id']
            task_type = window_json['metadata']['task_type']
            filename = f"{subject_id}_{task_type}_{window_id}.json"
        
        filepath = Path(self.output_dir) / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(window_json, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ 导出: {filepath}")
        
        if return_path:
            return str(filepath)
    
    def batch_export(
        self,
        windows_df: pd.DataFrame,
        subject_id: str,
        task_type: str,
        prefix: str = ""
    ) -> List[str]:
        """
        批量导出多个窗口
        
        Args:
            windows_df: 包含窗口特征的 DataFrame
                必需列: hr_mean, step_var, hr_recovery, stride_length, rpe_score, timestamp
                可选列: hr_max, hr_min, hr_std, step_frequency, step_length, speed, mhr, etc.
            subject_id: 受试者ID
            task_type: 任务类型
            prefix: 输出文件前缀
        
        Returns:
            保存的文件路径列表
        """
        
        saved_files = []
        
        for idx, row in windows_df.iterrows():
            window_id = f"window_{prefix}_{idx:03d}" if prefix else f"window_{idx:03d}"
            timestamp = row.get('timestamp', f"T+{idx*config.WINDOW_LENGTH_SEC}s")
            
            # 构建特征字典
            features = row.to_dict()
            
            # 创建 JSON
            window_json = self.create_window_json(
                window_id=window_id,
                subject_id=subject_id,
                task_type=task_type,
                timestamp=timestamp,
                features=features
            )
            
            # 导出
            filename = f"{subject_id}_{task_type}_{window_id}.json"
            self.export_window(window_json, filename=filename)
            
            saved_files.append(filename)
        
        logger.info(f"✓ 批量导出完成: {len(saved_files)} 个窗口")
        
        return saved_files
    
    def load_window_json(self, filepath: str) -> Dict:
        """读取单个窗口 JSON 文件"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_exported_windows(self, pattern: str = "*.json") -> List[Path]:
        """列出导出目录中的所有窗口 JSON"""
        return sorted(Path(self.output_dir).glob(pattern))


# ============================================================
# 使用示例
# ============================================================

if __name__ == "__main__":
    
    exporter = WindowJSONExporter(output_dir="./window_jsons")
    
    print("="*70)
    print("Windows JSON Exporter - 测试")
    print("="*70)
    
    # 创建示例特征数据 (6 个窗口)
    windows_data = [
        {
            'timestamp': f"00:{i*30:02d}",
            'hr_mean': 95 + i*5,
            'hr_max': 120 + i*8,
            'hr_min': 70 + i*2,
            'hr_std': 10,
            'hr_recovery': 22 - i*2,
            'step_frequency': 1.8 - i*0.05,
            'step_length': 0.58 - i*0.02,
            'stride_length': 0.56 - i*0.02,
            'step_var': 25 + i*8,
            'speed': 1.05 - i*0.03,
            'rpe_score': 11 + i*0.5,
            'mhr': 150
        }
        for i in range(6)
    ]
    
    df = pd.DataFrame(windows_data)
    
    # 批量导出
    print("\n📝 批量导出 6 个窗口...")
    files = exporter.batch_export(
        windows_df=df,
        subject_id="sub_01",
        task_type="st_control",
        prefix="ST"
    )
    
    # 验证文件
    print("\n✓ 导出的文件:")
    for f in exporter.list_exported_windows():
        print(f"  {f.name}")
    
    # 读取一个 JSON 验证格式
    print("\n📖 示例 JSON 文件内容 (window_001):")
    sample_json = exporter.load_window_json(str(exporter.list_exported_windows()[0]))
    print(json.dumps(sample_json, indent=2, ensure_ascii=False)[:500] + "...")
