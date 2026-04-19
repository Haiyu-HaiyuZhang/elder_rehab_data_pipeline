"""
Process Windows with Fuzzy Classification

从 30s 窗口特征数据读取，使用 Mamdani 模糊推理系统生成分类标签。

Usage:
    python process_windows_fuzzy.py \
        --input features_windows.csv \
        --output output_labels.csv \
        --subject sub_01 \
        --age 70
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List
import sys

import pandas as pd
import numpy as np

from fuzzy_classifier import FuzzyExerciseClassifier, classify_batch


def load_windows_features(input_path: str) -> pd.DataFrame:
    """
    从 CSV 加载窗口特征数据
    
    预期列：
      - timestamp (或 window_id)
      - hr_mean
      - step_var (或 step_frequency_std)
      - hr_recovery
      - stride_length
      - rpe_score (可选，默认 12)
    """
    df = pd.read_csv(input_path)
    
    # 列名规范化
    column_mapping = {
        'step_frequency_std': 'step_var',
        'step_freq_std': 'step_var',
        'stride_avg': 'stride_length',
        'stride': 'stride_length',
        'hr_recov': 'hr_recovery',
        'window_id': 'timestamp'
    }
    
    for old_name, new_name in column_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df.rename(columns={old_name: new_name}, inplace=True)
    
    # 检查必需列
    required_cols = ['hr_mean', 'step_var', 'hr_recovery', 'stride_length']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        raise ValueError(f"缺少必要列: {missing_cols}. 可用列: {list(df.columns)}")
    
    # 处理缺失的 RPE 列
    if 'rpe_score' not in df.columns:
        print("⚠️  警告: 找不到 'rpe_score' 列，将使用默认值 12（中等）")
        df['rpe_score'] = 12
    
    # 处理缺失的 timestamp 列
    if 'timestamp' not in df.columns:
        df['timestamp'] = [f"window_{i}" for i in range(len(df))]
    
    return df


def apply_fuzzy_classification(
    features_df: pd.DataFrame,
    age: int,
    output_path: str,
    verbose: bool = True
) -> pd.DataFrame:
    """
    对每个窗口应用模糊分类
    
    Args:
        features_df: 特征数据框
        age: 受试者年龄
        output_path: 输出 CSV 路径
        verbose: 是否打印进度信息
    
    Returns:
        分类结果数据框
    """
    
    # 创建分类器
    classifier = FuzzyExerciseClassifier(age=age)
    
    if verbose:
        print(f"✓ 分类器已创建 (年龄: {age}, MHR: {classifier.mhr:.0f} bpm)")
        print(f"✓ 处理 {len(features_df)} 个窗口...\n")
    
    # 建立结果列表
    results = []
    
    for idx, row in features_df.iterrows():
        try:
            # 提取特征
            window_data = {
                'timestamp': row['timestamp'],
                'hr_mean': float(row['hr_mean']),
                'step_var': float(row['step_var']),
                'hr_recovery': float(row['hr_recovery']),
                'stride_length': float(row['stride_length']),
                'rpe_score': float(row.get('rpe_score', 12))
            }
            
            # 分类
            classification = classifier.classify(
                hr_mean=window_data['hr_mean'],
                step_var=window_data['step_var'],
                hr_recovery=window_data['hr_recovery'],
                stride_length=window_data['stride_length'],
                rpe_score=window_data['rpe_score']
            )
            
            # 构建结果行
            result_row = {
                'timestamp': window_data['timestamp'],
                'hr_mean': window_data['hr_mean'],
                'step_var': window_data['step_var'],
                'hr_recovery': window_data['hr_recovery'],
                'stride_length': window_data['stride_length'],
                'rpe_score': window_data['rpe_score'],
                'exercise_load_value': classification['exercise_load'][0],
                'exercise_load_category': classification['exercise_load'][1],
                'fatigue_level_value': classification['fatigue_level'][0],
                'fatigue_level_category': classification['fatigue_level'][1],
                'movement_quality_value': classification['movement_quality'][0],
                'movement_quality_category': classification['movement_quality'][1],
                'confidence': classification['confidence'],
                'reasoning': classification['reasoning']
            }
            
            results.append(result_row)
            
            if verbose and (idx + 1) % max(1, len(features_df) // 10) == 0:
                print(f"  [进度] {idx + 1}/{len(features_df)} 窗口已处理")
        
        except Exception as e:
            print(f"⚠️  错误处理窗口 {idx}: {str(e)}")
            continue
    
    # 转换为数据框
    results_df = pd.DataFrame(results)
    
    # 保存到 CSV
    results_df.to_csv(output_path, index=False)
    
    if verbose:
        print(f"\n✓ 分类完成！")
        print(f"  总窗口数: {len(results_df)}")
        print(f"  输出文件: {output_path}")
    
    return results_df


def generate_summary_report(results_df: pd.DataFrame, output_dir: str = None):
    """
    生成分类结果的摘要报告
    
    Args:
        results_df: 分类结果数据框
        output_dir: 输出目录（可选）
    """
    
    print("\n" + "="*70)
    print("分类结果摘要报告")
    print("="*70)
    
    # 负荷分布
    print("\n📊 运动负荷分布:")
    load_counts = results_df['exercise_load_category'].value_counts()
    for category, count in load_counts.items():
        percentage = (count / len(results_df)) * 100
        print(f"  {category:12s}: {count:3d} 窗口 ({percentage:5.1f}%)")
    
    # 疲劳分布
    print("\n📊 疲劳等级分布:")
    fatigue_counts = results_df['fatigue_level_category'].value_counts()
    for category, count in fatigue_counts.items():
        percentage = (count / len(results_df)) * 100
        print(f"  {category:12s}: {count:3d} 窗口 ({percentage:5.1f}%)")
    
    # 动作质量分布
    print("\n📊 动作质量分布:")
    quality_counts = results_df['movement_quality_category'].value_counts()
    for category, count in quality_counts.items():
        percentage = (count / len(results_df)) * 100
        print(f"  {category:12s}: {count:3d} 窗口 ({percentage:5.1f}%)")
    
    # 置信度统计
    print("\n📊 分类置信度统计:")
    print(f"  平均置信度: {results_df['confidence'].mean():.3f}")
    print(f"  最小置信度: {results_df['confidence'].min():.3f}")
    print(f"  最大置信度: {results_df['confidence'].max():.3f}")
    
    # 检测警告情况
    print("\n⚠️  异常检测:")
    
    excessive_load = len(results_df[results_df['exercise_load_category'] == 'excessive'])
    if excessive_load > 0:
        print(f"  • 过高负荷窗口: {excessive_load} ({excessive_load/len(results_df)*100:.1f}%)")
    
    severe_fatigue = len(results_df[results_df['fatigue_level_category'] == 'severe'])
    if severe_fatigue > 0:
        print(f"  • 严重疲劳窗口: {severe_fatigue} ({severe_fatigue/len(results_df)*100:.1f}%)")
    
    poor_quality = len(results_df[results_df['movement_quality_category'] == 'poor'])
    if poor_quality > 0:
        print(f"  • 动作质量差窗口: {poor_quality} ({poor_quality/len(results_df)*100:.1f}%)")
    
    low_confidence = len(results_df[results_df['confidence'] < 0.6])
    if low_confidence > 0:
        print(f"  • 低置信度窗口 (<0.6): {low_confidence} ({low_confidence/len(results_df)*100:.1f}%)")
    
    if output_dir:
        report_path = Path(output_dir) / 'classification_summary.txt'
        with open(report_path, 'w') as f:
            f.write("DUO-GAIT 模糊分类结果摘要\n")
            f.write("="*70 + "\n\n")
            
            f.write("运动负荷分布:\n")
            for category, count in load_counts.items():
                percentage = (count / len(results_df)) * 100
                f.write(f"  {category:12s}: {count:3d} ({percentage:5.1f}%)\n")
            
            f.write("\n疲劳等级分布:\n")
            for category, count in fatigue_counts.items():
                percentage = (count / len(results_df)) * 100
                f.write(f"  {category:12s}: {count:3d} ({percentage:5.1f}%)\n")
            
            f.write("\n动作质量分布:\n")
            for category, count in quality_counts.items():
                percentage = (count / len(results_df)) * 100
                f.write(f"  {category:12s}: {count:3d} ({percentage:5.1f}%)\n")
        
        print(f"\n✓ 摘要报告已保存: {report_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Mamdani 模糊推理系统 - 运动分类'
    )
    
    parser.add_argument(
        '--input', '-i',
        type=str,
        required=True,
        help='输入特征 CSV 文件路径'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='输出分类标签 CSV 文件路径 (默认: output_labels.csv)'
    )
    
    parser.add_argument(
        '--subject', '-s',
        type=str,
        default='unknown',
        help='受试者 ID (用于元数据)'
    )
    
    parser.add_argument(
        '--age', '-a',
        type=int,
        required=True,
        help='受试者年龄（用于计算 MHR）'
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
        input_name = Path(args.input).stem
        args.output = f"{input_name}_classified.csv"
    
    print("="*70)
    print("Mamdani 模糊推理系统 - 运动分类处理")
    print("="*70)
    print(f"\n参数:")
    print(f"  输入文件: {args.input}")
    print(f"  输出文件: {args.output}")
    print(f"  受试者: {args.subject}")
    print(f"  年龄: {args.age} 岁")
    
    try:
        # 加载特征数据
        print(f"\n📖 加载特征数据...")
        features_df = load_windows_features(args.input)
        print(f"  ✓ 已加载 {len(features_df)} 个窗口")
        print(f"  列: {list(features_df.columns)}")
        
        # 检查数据质量
        print(f"\n🔍 数据质量检查...")
        for col in ['hr_mean', 'step_var', 'hr_recovery', 'stride_length']:
            print(f"  {col:15s}: [{features_df[col].min():.2f}, {features_df[col].max():.2f}]")
        
        # 应用模糊分类
        print(f"\n🧠 应用模糊分类...")
        results_df = apply_fuzzy_classification(
            features_df,
            age=args.age,
            output_path=args.output,
            verbose=not args.quiet
        )
        
        # 生成摘要报告
        if args.report:
            output_dir = Path(args.output).parent
            generate_summary_report(results_df, output_dir=output_dir)
        elif not args.quiet:
            generate_summary_report(results_df)
        
        print(f"\n✅ 处理完成!")
        print(f"  结果保存到: {args.output}")
        
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
