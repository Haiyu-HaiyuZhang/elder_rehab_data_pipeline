"""
Fuzzy Logic Validation Engine - 将 JSON 窗口数据应用 Fuzzy 分类

读取分段编号的 JSON 窗口，应用 Mamdani 模糊推理系统，
输出分类结果表格（窗口ID对应分类标签）。

Usage:
    python validate_with_fuzzy.py \\
        --input_dir ./window_jsons \\
        --subject sub_01 \\
        --task st_control \\
        --age 70 \\
        --output results.csv \\
        --report
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd

from fuzzy_classifier import FuzzyExerciseClassifier


def get_subject_age_from_info(subject_id):
    """从 subject_info.csv 读取受试者年龄"""
    try:
        subject_info_path = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/subject_info.csv'
        info_df = pd.read_csv(subject_info_path)
        
        subject_row = info_df[info_df['sub'] == subject_id]
        if not subject_row.empty:
            age = subject_row['age'].values[0]
            return int(age)
    except:
        pass
    
    return None


class FuzzyValidationEngine:
    """模糊逻辑验证引擎"""
    
    def __init__(self, age: int, verbose: bool = True):
        """
        初始化验证引擎
        
        Args:
            age: 受试者年龄（用于 MHR 计算）
            verbose: 是否打印详细输出
        """
        self.age = age
        self.mhr = 220 - age
        self.classifier = FuzzyExerciseClassifier(age=age)
        self.verbose = verbose
    
    def validate_single_window(self, window_json: Dict) -> Dict:
        """
        对单个窗口应用模糊分类（对齐 LLM 规则）
        
        Args:
            window_json: 窗口 JSON 字典（结构：metadata, imu, heart_rate）
        
        Returns:
            分类结果字典
        """
        
        # 提取元数据
        metadata = window_json.get('metadata', {})
        window_id = metadata.get('window_id', 'unknown')
        subject_id = metadata.get('player_id', 'unknown')
        session_id = metadata.get('session_id', 'unknown')
        # 从 session_id 提取 task_type（如 "st"、"control" 等）
        task_type = session_id.split('_')[-1] if session_id != 'unknown' else 'unknown'
        
        # 提取 IMU 特征（新的 JSON 结构）
        imu = window_json.get('imu', {})
        imu_features = imu.get('features', {})
        
        cadence_hz = float(imu_features.get('step_frequency_hz', 1.8))
        stride_length = float(imu_features.get('step_length_m', 0.5))
        step_var = float(imu_features.get('step_time_variability_ms', 45))
        imu_quality = float(imu.get('data_quality', 0.85))
        
        # 提取心率特征
        heart_rate = window_json.get('heart_rate', {})
        hr_features = heart_rate.get('features', {})
        
        hr_mean = float(hr_features.get('hr_mean_bpm', 80))
        hr_recovery = float(hr_features.get('hr_recovery_bpm_per_min', 10))
        hr_quality = float(heart_rate.get('data_quality', 0.85))
        
        # RPE 如果有的话
        rpe_score = float(window_json.get('rpe_score', 12))
        
        # 数据验证和范围检查
        if hr_mean < 40 or hr_mean > 180:
            logger_msg = f"⚠️  窗口 {window_id}: HR 异常 ({hr_mean:.0f} bpm)"
            if self.verbose:
                print(logger_msg)
        
        # 应用模糊分类（传入所有必需参数）
        try:
            classification = self.classifier.classify(
                hr_mean=hr_mean,
                step_var=step_var,
                hr_recovery=hr_recovery,
                stride_length=stride_length,
                rpe_score=rpe_score,
                cadence_hz=cadence_hz,
                imu_quality=imu_quality,
                hr_quality=hr_quality
            )
        except Exception as e:
            print(f"❌ 错误分类窗口 {window_id}: {str(e)}")
            classification = {
                'exercise_load': (0, 'unknown'),
                'fatigue_level': (0, 'unknown'),
                'movement_quality': (0, 'unknown'),
                'confidence': 0.0,
                'reasoning': f"Error: {str(e)}"
            }
        
        # 构建结果
        result = {
            'window_id': window_id,
            'subject_id': subject_id,
            'task_type': task_type,
            'timestamp': metadata.get('timestamp', ''),
            
            # 原始特征（IMU）
            'cadence_hz': cadence_hz,
            'stride_length': stride_length,
            'step_var_ms': step_var,
            
            # 原始特征（HR）
            'hr_mean': hr_mean,
            'hr_recovery': hr_recovery,
            'rpe_score': rpe_score,
            
            # 分类结果
            'exercise_load_score': classification['exercise_load'][0],
            'exercise_load_category': classification['exercise_load'][1],
            'fatigue_level_score': classification['fatigue_level'][0],
            'fatigue_level_category': classification['fatigue_level'][1],
            'movement_quality_score': classification['movement_quality'][0],
            'movement_quality_category': classification['movement_quality'][1],
            
            # 数据质量标志
            'imu_quality': imu_quality,
            'hr_quality': hr_quality,
            'imu_quality_flag': 'low' if imu_quality < 0.6 else 'high',
            'hr_quality_flag': 'low' if hr_quality < 0.6 else 'high',
            
            # 元数据
            'confidence': classification['confidence'],
            'mhr': self.mhr,
            'hr_percent_mhr': (hr_mean / self.mhr * 100) if self.mhr > 0 else 0,
            'reasoning': classification['reasoning']
        }
        
        return result
    
    def validate_batch_from_jsons(
        self,
        json_files: List[Path]
    ) -> pd.DataFrame:
        """
        批量验证 JSON 文件
        
        Args:
            json_files: JSON 文件路径列表
        
        Returns:
            分类结果 DataFrame
        """
        
        results = []
        
        for i, json_file in enumerate(json_files, 1):
            if self.verbose and i % max(1, len(json_files) // 10) == 0:
                print(f"  [进度] {i}/{len(json_files)} 窗口已分类")
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    window_json = json.load(f)
                
                result = self.validate_single_window(window_json)
                results.append(result)
            
            except Exception as e:
                print(f"⚠️  错误读取 {json_file.name}: {str(e)}")
                continue
        
        return pd.DataFrame(results)
    
    def validate_from_directory(
        self,
        input_dir: str,
        subject_id: str = None,
        task_type: str = None,
        pattern: str = "*.json"
    ) -> pd.DataFrame:
        """
        从目录批量验证 JSON 文件
        
        Args:
            input_dir: JSON 文件目录
            subject_id: 可选筛选受试者
            task_type: 可选筛选任务类型
            pattern: 文件名匹配模式
        
        Returns:
            分类结果 DataFrame
        """
        
        input_path = Path(input_dir)
        json_files = sorted(input_path.glob(pattern))
        
        # 筛选文件
        if subject_id or task_type:
            filtered = []
            for f in json_files:
                if subject_id and subject_id not in f.name:
                    continue
                if task_type and task_type not in f.name:
                    continue
                filtered.append(f)
            json_files = filtered
        
        if not json_files:
            print(f"❌ 未找到匹配的 JSON 文件")
            return pd.DataFrame()
        
        if self.verbose:
            print(f"✓ 找到 {len(json_files)} 个 JSON 文件")
        
        return self.validate_batch_from_jsons(json_files)
    
    def generate_summary_report(self, results_df: pd.DataFrame) -> Dict:
        """
        生成摘要报告
        
        Args:
            results_df: 分类结果 DataFrame
        
        Returns:
            报告字典
        """
        
        report = {
            'total_windows': len(results_df),
            'subject_count': results_df['subject_id'].nunique(),
            'task_types': results_df['task_type'].unique().tolist(),
            
            'exercise_load_distribution': {
                cat: int(count)
                for cat, count in results_df['exercise_load_category'].value_counts().items()
            },
            
            'fatigue_level_distribution': {
                cat: int(count)
                for cat, count in results_df['fatigue_level_category'].value_counts().items()
            },
            
            'movement_quality_distribution': {
                cat: int(count)
                for cat, count in results_df['movement_quality_category'].value_counts().items()
            },
            
            'confidence_stats': {
                'mean': float(results_df['confidence'].mean()),
                'min': float(results_df['confidence'].min()),
                'max': float(results_df['confidence'].max()),
                'low_confidence_count': int((results_df['confidence'] < 0.6).sum())
            },
            
            'anomalies': {
                'excessive_load': int((results_df['exercise_load_category'] == 'excessive').sum()),
                'severe_fatigue': int((results_df['fatigue_level_category'] == 'severe').sum()),
                'poor_quality': int((results_df['movement_quality_category'] == 'poor').sum()),
                'high_hr': int((results_df['hr_percent_mhr'] > 110).sum())
            }
        }
        
        return report


def main():
    parser = argparse.ArgumentParser(
        description='Fuzzy Logic 验证引擎 - 对 JSON 窗口应用模糊分类'
    )
    
    parser.add_argument(
        '--input_dir', '-i',
        type=str,
        required=True,
        help='JSON 窗口文件目录'
    )
    
    parser.add_argument(
        '--subject', '-s',
        type=str,
        help='筛选特定受试者 (可选)'
    )
    
    parser.add_argument(
        '--task',
        type=str,
        help='筛选特定任务类型 (可选)'
    )
    
    parser.add_argument(
        '--age', '-a',
        type=int,
        required=False,
        help='受试者年龄（用于 MHR 计算。若不提供且指定了 --subject，将自动从 subject_info.csv 读取）'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='输出分类结果 CSV 文件路径'
    )
    
    parser.add_argument(
        '--report', '-r',
        action='store_true',
        help='生成摘要报告'
    )
    
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='抑制详细输出'
    )
    
    args = parser.parse_args()
    
    # 设置默认输出路径
    if args.output is None:
        task_suffix = f"_{args.task}" if args.task else ""
        args.output = f"fuzzy_results_{args.subject}{task_suffix}.csv"
    
    print("="*70)
    print("Fuzzy Logic 验证引擎")
    print("="*70)
    print(f"\n参数:")
    print(f"  输入目录: {args.input_dir}")
    print(f"  受试者: {args.subject or '(全部)'}")
    print(f"  任务: {args.task or '(全部)'}")
    print(f"  年龄: {args.age} 岁 (MHR = {220-args.age})")
    print(f"  输出: {args.output}")
    
    try:
        # 创建验证引擎
        engine = FuzzyValidationEngine(age=args.age, verbose=not args.quiet)
        
        # 验证 JSON 文件
        print(f"\n📂 从目录读取 JSON 文件...")
        results_df = engine.validate_from_directory(
            input_dir=args.input_dir,
            subject_id=args.subject,
            task_type=args.task
        )
        
        if results_df.empty:
            print("❌ 没有有效的分类结果")
            sys.exit(1)
        
        # 保存结果
        print(f"\n💾 保存结果...")
        results_df.to_csv(args.output, index=False)
        print(f"✓ 已保存: {args.output}")
        
        # 生成报告
        if args.report:
            print(f"\n📊 生成摘要报告...")
            report = engine.generate_summary_report(results_df)
            
            print("\n" + "="*70)
            print("分类结果摘要")
            print("="*70)
            
            print(f"\n📈 样本统计:")
            print(f"  总窗口数: {report['total_windows']}")
            print(f"  受试者数: {report['subject_count']}")
            print(f"  任务类型: {', '.join(report['task_types'])}")
            
            print(f"\n📊 运动负荷分布:")
            for cat, count in report['exercise_load_distribution'].items():
                pct = (count / report['total_windows']) * 100
                print(f"  {cat:12s}: {count:3d} ({pct:5.1f}%)")
            
            print(f"\n📊 疲劳等级分布:")
            for cat, count in report['fatigue_level_distribution'].items():
                pct = (count / report['total_windows']) * 100
                print(f"  {cat:12s}: {count:3d} ({pct:5.1f}%)")
            
            print(f"\n📊 动作质量分布:")
            for cat, count in report['movement_quality_distribution'].items():
                pct = (count / report['total_windows']) * 100
                print(f"  {cat:12s}: {count:3d} ({pct:5.1f}%)")
            
            print(f"\n📊 置信度统计:")
            print(f"  平均: {report['confidence_stats']['mean']:.3f}")
            print(f"  范围: [{report['confidence_stats']['min']:.3f}, {report['confidence_stats']['max']:.3f}]")
            print(f"  低置信度: {report['confidence_stats']['low_confidence_count']} 窗口")
            
            print(f"\n⚠️  异常检测:")
            for key, count in report['anomalies'].items():
                if count > 0:
                    print(f"  {key}: {count} 窗口")
        
        print(f"\n✅ 验证完成！")
    
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
