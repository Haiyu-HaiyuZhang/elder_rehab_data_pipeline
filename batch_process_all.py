#!/usr/bin/env python3
"""
批量处理所有受试者的所有任务类型数据
生成完整的 JSON 窗口集合（监控版本）
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# 允许从任意工作目录运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from process_duogait_to_json import DUOGAITProcessor

# 受试者列表
SUBJECTS = [
    'sub_01', 'sub_02', 'sub_03', 'sub_05', 'sub_06', 'sub_07', 'sub_08', 'sub_09',
    'sub_10', 'sub_11', 'sub_12', 'sub_13', 'sub_14', 'sub_15', 'sub_17', 'sub_18'
]

# 任务类型列表
TASKS = [
    'OG_st_control',
    'OG_st_fatigue',
    'OG_st_sit_to_stand',
    'OG_dt_control',
    'OG_dt_fatigue',
    'OG_dt_sit_to_stand',
]

# 路径配置
BASE_INTERIM_DIR = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim'
BASE_RAW_DIR = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw'
OUTPUT_DIR = '/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/'


def get_raw_path(task_type):
    """根据任务类型确定 RAW 路径前缀"""
    if task_type.startswith('OG_st'):
        return os.path.join(BASE_RAW_DIR, 'OG_st_raw')
    elif task_type.startswith('OG_dt'):
        return os.path.join(BASE_RAW_DIR, 'OG_dt_raw')
    else:
        return None


def check_data_exists(subject_id, task_type):
    """检查指定受试者和任务类型的数据是否存在"""
    interim_path = os.path.join(BASE_INTERIM_DIR, task_type, subject_id, 'ST.csv')
    raw_base = get_raw_path(task_type)
    raw_path = os.path.join(raw_base, subject_id, 'heart_rate.CSV')

    return os.path.exists(interim_path) and os.path.exists(raw_path)


def process_subject_task(subject_id, task_type, verbose=False):
    """处理单个受试者的单个任务"""

    raw_base = get_raw_path(task_type)
    if raw_base is None:
        return False, "Invalid task type"

    interim_path = os.path.join(BASE_INTERIM_DIR, task_type, subject_id)
    raw_path = os.path.join(raw_base, subject_id)

    # 检查数据存在性
    if not check_data_exists(subject_id, task_type):
        return False, "Data not found"

    try:
        processor = DUOGAITProcessor(
            imu_data_dir=interim_path,
            hr_data_dir=raw_path,
            output_dir=OUTPUT_DIR,
            subject_id=subject_id,
            task_type=task_type
        )
        processor.process_windows()
        return True, "Success"
    except Exception as e:
        if verbose:
            import traceback
            traceback.print_exc()
        return False, str(e)


def main():
    global BASE_INTERIM_DIR, BASE_RAW_DIR, OUTPUT_DIR

    import argparse

    parser = argparse.ArgumentParser(description='批量处理 DUO-GAIT 数据集')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不生成文件')
    parser.add_argument('--subjects', nargs='+', help='指定受试者，e.g. sub_01 sub_02')
    parser.add_argument('--tasks', nargs='+', help='指定任务，e.g. OG_st_control OG_st_fatigue')
    parser.add_argument('--skip-existing', action='store_true', help='跳过已存在的输出')
    parser.add_argument('--verbose', action='store_true', help='详细输出')
    parser.add_argument(
        '--interim-base',
        default=BASE_INTERIM_DIR,
        help='INTERIM 数据根目录',
    )
    parser.add_argument(
        '--raw-base',
        default=BASE_RAW_DIR,
        help='RAW 数据根目录',
    )
    parser.add_argument(
        '--out-dir',
        default=OUTPUT_DIR,
        help='JSON 输出目录',
    )

    args = parser.parse_args()

    BASE_INTERIM_DIR = args.interim_base
    BASE_RAW_DIR = args.raw_base
    OUTPUT_DIR = args.out_dir

    # 确定要处理的受试者和任务
    subjects = args.subjects if args.subjects else SUBJECTS
    tasks = args.tasks if args.tasks else TASKS

    # 统计信息
    total_combos = len(subjects) * len(tasks)
    print("=" * 90)
    print(f"DUO-GAIT 批量处理器 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 90)
    print(f"受试者数: {len(subjects)}")
    print(f"任务类型数: {len(tasks)}")
    print(f"总组合数: {total_combos}")
    print(f"模式: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    print("=" * 90)
    print()

    # 创建输出目录
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 处理统计
    success_count = 0
    skip_count = 0
    fail_count = 0
    fail_details = []

    # 迭代所有组合
    task_total = len(tasks)
    for task_idx, task_type in enumerate(tasks, 1):
        print(f"\n[任务 {task_idx}/{task_total}] {task_type}")
        print("-" * 90)

        sub_total = len(subjects)
        for sub_idx, subject_id in enumerate(subjects, 1):
            # 检查是否应该跳过
            if args.skip_existing:
                sample_output = os.path.join(OUTPUT_DIR, f"{subject_id}_{task_type}_window_0000.json")
                if os.path.exists(sample_output):
                    print(f"  [{sub_idx:2d}/{sub_total}] {subject_id:<8} - ⊘ 跳过（已存在）", flush=True)
                    skip_count += 1
                    continue

            # 检查数据是否存在
            if not check_data_exists(subject_id, task_type):
                print(f"  [{sub_idx:2d}/{sub_total}] {subject_id:<8} - ⊘ 数据不存在", flush=True)
                skip_count += 1
                continue

            # 处理
            if args.dry_run:
                print(f"  [{sub_idx:2d}/{sub_total}] {subject_id:<8} - ▶ DRY RUN", flush=True)
                success_count += 1
            else:
                success, msg = process_subject_task(subject_id, task_type, args.verbose)

                if success:
                    print(f"  [{sub_idx:2d}/{sub_total}] {subject_id:<8} - ✓ {msg}", flush=True)
                    success_count += 1
                else:
                    print(f"  [{sub_idx:2d}/{sub_total}] {subject_id:<8} - ✗ {msg}", flush=True)
                    fail_count += 1
                    fail_details.append((subject_id, task_type, msg))

    # 输出总结
    print("\n" + "=" * 90)
    print("处理完成")
    print("=" * 90)
    print(f"成功: {success_count}")
    print(f"跳过: {skip_count}")
    print(f"失败: {fail_count}")
    print()

    if fail_details:
        print("失败详情:")
        for subject, task, msg in fail_details:
            print(f"  - {subject} / {task}: {msg}")
        print()

    # 输出统计
    json_dir = Path(OUTPUT_DIR)
    json_files = list(json_dir.glob('*.json'))
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"总 JSON 文件数: {len(json_files)}")
    print()

    # 显示样本
    if json_files:
        print("样本文件:")
        for f in sorted(json_files)[:5]:
            print(f"  - {f.name}")
        if len(json_files) > 5:
            print(f"  ... 及其他 {len(json_files)-5} 个文件")
        print()


if __name__ == '__main__':
    main()
