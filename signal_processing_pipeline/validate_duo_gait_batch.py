"""
DUO-GAIT 批量验证脚本 - Batch Validation Script
一次性验证所有参与者的数据
"""

import json
import sys
from pathlib import Path
from tabulate import tabulate
import pandas as pd

sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

from validate_duo_gait import DUOGaitValidator


def get_all_subjects(dataset_root="/Volumes/ChouSSD/elder_datasets/DUO-GAIT"):
    """获取数据集中的所有参与者"""
    
    raw_dir = Path(dataset_root) / "raw"
    st_dir = raw_dir / "OG_st_raw"
    
    if not st_dir.exists():
        return []
    
    # 列出所有参与者目录
    subjects = []
    for item in sorted(st_dir.iterdir()):
        if item.is_dir() and item.name.startswith('sub_'):
            subjects.append(item.name)
    
    return subjects


def validate_batch(task_type="st", subjects=None, max_subjects=None):
    """
    批量验证参与者
    
    Args:
        task_type: "st" (single task) 或 "dt" (dual task)
        subjects: 要验证的参与者列表，None 表示全部
        max_subjects: 最多验证多少个参与者，None 表示全部
    
    Returns:
        dict: 验证结果汇总
    """
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + f"  DUO-GAIT 批量验证 - Batch Validation ({task_type.upper()})".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    # 初始化验证器
    validator = DUOGaitValidator()
    
    # 获取所有参与者
    if subjects is None:
        subjects = get_all_subjects()
    
    if max_subjects:
        subjects = subjects[:max_subjects]
    
    print(f"\n发现参与者: {len(subjects)} 个")
    print(f"验证列表: {', '.join(subjects[:5])}" + ("..." if len(subjects) > 5 else ""))
    
    # 验证结果汇总
    results_summary = {
        'task_type': task_type,
        'total_subjects': len(subjects),
        'successful': 0,
        'failed': 0,
        'subjects': {}
    }
    
    # 遍历每个参与者
    for idx, subject_id in enumerate(subjects, 1):
        print(f"\n[{idx}/{len(subjects)}] 验证 {subject_id}... ", end="", flush=True)
        
        try:
            results = validator.validate_subject(subject_id, task_type=task_type)
            
            if results and 'heart_rate' in results:
                results_summary['subjects'][subject_id] = {
                    'status': 'success',
                    'step_frequency_hz': results.get('step_frequency', {}).get('hz'),
                    'step_length_m': results.get('step_length', {}).get('meters'),
                    'hr_mean_bpm': results.get('heart_rate', {}).get('hr_mean_bpm'),
                    'hr_max_bpm': results.get('heart_rate', {}).get('hr_max_bpm'),
                    'hr_min_bpm': results.get('heart_rate', {}).get('hr_min_bpm'),
                }
                results_summary['successful'] += 1
                print("✓ 成功")
            else:
                results_summary['subjects'][subject_id] = {
                    'status': 'error',
                    'message': '未获得有效结果'
                }
                results_summary['failed'] += 1
                print("✗ 失败")
                
        except Exception as e:
            results_summary['subjects'][subject_id] = {
                'status': 'error',
                'message': str(e)
            }
            results_summary['failed'] += 1
            print(f"✗ 异常: {str(e)[:30]}...")
    
    return results_summary


def print_summary(results_summary):
    """打印验证摘要"""
    
    print("\n" + "█"*70)
    print("█" + " "*68 + "█")
    print("█" + f"  验证摘要 - Validation Summary".center(68) + "█")
    print("█" + " "*68 + "█")
    print("█"*70)
    
    print(f"\n任务类型: {results_summary['task_type'].upper()}")
    print(f"总参与者数: {results_summary['total_subjects']}")
    print(f"✓ 成功: {results_summary['successful']}")
    print(f"✗ 失败: {results_summary['failed']}")
    print(f"成功率: {results_summary['successful']/results_summary['total_subjects']*100:.1f}%")
    
    # 准备表格数据
    table_data = []
    for subject_id, result in results_summary['subjects'].items():
        if result['status'] == 'success':
            row = [
                subject_id,
                f"{result.get('step_frequency_hz', 'N/A'):.2f}" if isinstance(result.get('step_frequency_hz'), (int, float)) else "N/A",
                f"{result.get('step_length_m', 'N/A'):.4f}" if isinstance(result.get('step_length_m'), (int, float)) else "N/A",
                f"{result.get('hr_mean_bpm', 'N/A'):.1f}" if isinstance(result.get('hr_mean_bpm'), (int, float)) else "N/A",
                f"{result.get('hr_max_bpm', 'N/A'):.1f}" if isinstance(result.get('hr_max_bpm'), (int, float)) else "N/A",
                "✓"
            ]
        else:
            row = [
                subject_id,
                "❌",
                "❌",
                "❌",
                "❌",
                "✗"
            ]
        table_data.append(row)
    
    # 打印表格
    print("\n【详细结果】\n")
    headers = ["参与者", "步频 (Hz)", "步长 (m)", "HR Mean (bpm)", "HR Max (bpm)", "状态"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # 统计指标
    print("\n【统计信息】\n")
    
    successful_results = [r for r in results_summary['subjects'].values() if r['status'] == 'success']
    
    if successful_results:
        step_freqs = [r.get('step_frequency_hz') for r in successful_results if isinstance(r.get('step_frequency_hz'), (int, float))]
        step_lengths = [r.get('step_length_m') for r in successful_results if isinstance(r.get('step_length_m'), (int, float))]
        hr_means = [r.get('hr_mean_bpm') for r in successful_results if isinstance(r.get('hr_mean_bpm'), (int, float))]
        hr_maxs = [r.get('hr_max_bpm') for r in successful_results if isinstance(r.get('hr_max_bpm'), (int, float))]
        
        stats_data = []
        
        if step_freqs:
            stats_data.append([
                "步频 (Hz)",
                f"{min(step_freqs):.2f}",
                f"{sum(step_freqs)/len(step_freqs):.2f}",
                f"{max(step_freqs):.2f}"
            ])
        
        if step_lengths:
            stats_data.append([
                "步长 (m)",
                f"{min(step_lengths):.4f}",
                f"{sum(step_lengths)/len(step_lengths):.4f}",
                f"{max(step_lengths):.4f}"
            ])
        
        if hr_means:
            stats_data.append([
                "HR Mean (bpm)",
                f"{min(hr_means):.1f}",
                f"{sum(hr_means)/len(hr_means):.1f}",
                f"{max(hr_means):.1f}"
            ])
        
        if hr_maxs:
            stats_data.append([
                "HR Max (bpm)",
                f"{min(hr_maxs):.1f}",
                f"{sum(hr_maxs)/len(hr_maxs):.1f}",
                f"{max(hr_maxs):.1f}"
            ])
        
        stats_headers = ["指标", "最小值", "平均值", "最大值"]
        print(tabulate(stats_data, headers=stats_headers, tablefmt="grid"))
    
    print("\n" + "="*70)


def save_results(results_summary, output_file=None):
    """保存验证结果"""
    
    if output_file is None:
        output_file = f"/tmp/duo_gait_validation_{results_summary['task_type']}.json"
    
    with open(output_file, 'w') as f:
        json.dump(results_summary, f, indent=2, default=str)
    
    print(f"✓ 结果已保存到: {output_file}")
    
    return output_file


def main():
    """主函数"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description="DUO-GAIT 批量验证脚本")
    parser.add_argument('--task', default='st', choices=['st', 'dt'], help='任务类型: st(单任务) 或 dt(双任务)')
    parser.add_argument('--max', type=int, default=None, help='最多验证多少个参与者')
    parser.add_argument('--subjects', nargs='+', default=None, help='指定参与者')
    parser.add_argument('--output', default=None, help='输出文件路径')
    
    args = parser.parse_args()
    
    # 运行批量验证
    results = validate_batch(
        task_type=args.task,
        subjects=args.subjects,
        max_subjects=args.max
    )
    
    # 打印摘要
    print_summary(results)
    
    # 保存结果
    save_results(results, output_file=args.output)


if __name__ == "__main__":
    # 方便测试：直接验证前 3 个参与者
    results = validate_batch(task_type="st", max_subjects=3)
    print_summary(results)
    
    # 保存结果
    output_path = save_results(results)
