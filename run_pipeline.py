#!/usr/bin/env python3
"""
完整的 DUO-GAIT 处理流程脚本
功能：原始数据 → JSON 窗口 → Fuzzy 分类 → CSV 结果

Usage:
    python3 run_pipeline.py sub_01 st
    python3 run_pipeline.py sub_02 control
"""

import sys
import os
import argparse
from pathlib import Path
import pandas as pd

# ============================================================
# 配置
# ============================================================
WORKSPACE = Path("/Users/zhanghaiyu/workspace/elder_rehab")

# 根据任务类型定义 interim 和 raw 目录映射
TASK_TYPE_MAPPING = {
    'st': {
        'interim': Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control"),
        'raw': Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw")
    },
    'control': {
        'interim': Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_st_control"),
        'raw': Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_st_raw")
    },
    'dt': {
        'interim': Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim/OG_dt_control"),
        'raw': Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw/OG_dt_raw")
    }
}

JSON_OUTPUT_DIR = Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json")
RESULTS_OUTPUT_DIR = Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT/results")

# 确保输出目录存在
RESULTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# 颜色定义
# ============================================================
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(msg):
    print(f"\n{Colors.BLUE}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BLUE}{msg}{Colors.ENDC}")
    print(f"{Colors.BLUE}{'='*70}{Colors.ENDC}\n")

def print_step(msg):
    print(f"{Colors.GREEN}✓{Colors.ENDC} {msg}")

def print_info(msg):
    print(f"{Colors.CYAN}ℹ{Colors.ENDC} {msg}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠{Colors.ENDC} {msg}")

def print_error(msg):
    print(f"{Colors.RED}✗{Colors.ENDC} {msg}")

# ============================================================
# 步骤 1: 验证原始数据
# ============================================================
def verify_raw_data(subject_id, task_type):
    print_header(f"步骤 1/3: 验证原始数据")
    
    # 根据任务类型获取正确的目录
    if task_type not in TASK_TYPE_MAPPING:
        print_error(f"未知的任务类型: {task_type}")
        return False
    
    paths = TASK_TYPE_MAPPING[task_type]
    interim_dir = paths['interim'] / subject_id
    raw_dir = paths['raw'] / subject_id
    
    st_file = interim_dir / "ST.csv"
    hr_file = raw_dir / "heart_rate.CSV"
    
    if not st_file.exists():
        print_error(f"找不到: {st_file}")
        return False
    
    print_step(f"找到 ST.csv (from interim)")
    print_info(f"  路径: {st_file}")
    
    # 检查行数
    with open(st_file) as f:
        rows = sum(1 for _ in f) - 1  # 减去标题行
    
    print_info(f"  IMU 数据行数: {rows}")
    
    if hr_file.exists():
        with open(hr_file) as f:
            hr_rows = sum(1 for _ in f) - 1
        print_info(f"  HR 数据行数 (from raw): {hr_rows}")
    else:
        print_warning(f"找不到 heart_rate.CSV at {hr_file}")
    
    return True

# ============================================================
# 步骤 2: 生成 JSON 窗口
# ============================================================
def generate_json_windows(subject_id, task_type):
    print_header(f"步骤 2/3: 生成 JSON 窗口")
    
    print_info("运行 process_duogait_to_json.py...")
    
    os.chdir(WORKSPACE)
    
    # 导入生成脚本
    sys.path.insert(0, str(WORKSPACE))
    from process_duogait_to_json import DUOGAITProcessor
    
    # 根据任务类型获取正确的目录
    if task_type not in TASK_TYPE_MAPPING:
        print_error(f"未知的任务类型: {task_type}")
        return False
    
    paths = TASK_TYPE_MAPPING[task_type]
    imu_data_dir = paths['interim'] / subject_id
    hr_data_dir = paths['raw'] / subject_id
    
    processor = DUOGAITProcessor(
        imu_data_dir=str(imu_data_dir),
        hr_data_dir=str(hr_data_dir),
        output_dir=str(JSON_OUTPUT_DIR),
        subject_id=subject_id
    )
    
    processor.load_data()
    processor.process_windows()
    
    # 检查生成结果
    pattern = f"{subject_id}_{task_type}_window_*.json"
    json_files = sorted(JSON_OUTPUT_DIR.glob(pattern))
    
    if not json_files:
        print_error(f"找不到生成的 JSON 文件: {pattern}")
        return False
    
    print_step(f"JSON 生成完成: {len(json_files)} 个窗口")
    print_info(f"  范围: {json_files[0].name} 到 {json_files[-1].name}")
    
    return len(json_files)

# ============================================================
# 步骤 3: 应用 Fuzzy 分类
# ============================================================
def apply_fuzzy_classification(subject_id, task_type):
    print_header(f"步骤 3/3: 应用 Fuzzy Logic 分类 (LLM 对齐)")
    
    os.chdir(WORKSPACE)
    sys.path.insert(0, str(WORKSPACE / "signal_processing_pipeline"))
    
    from validate_with_fuzzy import FuzzyValidationEngine, get_subject_age_from_info
    
    # 获取年龄
    age = get_subject_age_from_info(subject_id)
    if age is None:
        print_warning(f"找不到年龄信息，使用默认值 70")
        age = 70
    else:
        print_step(f"从 subject_info.csv 读取年龄: {age}")
    
    mhr = 220 - age
    print_info(f"  MHR = 220 - {age} = {mhr} bpm")
    
    # 初始化分类引擎
    engine = FuzzyValidationEngine(age=age, verbose=False)
    
    # 获取 JSON 文件
    pattern = f"{subject_id}_{task_type}_window_*.json"
    json_files = sorted(JSON_OUTPUT_DIR.glob(pattern))
    
    if not json_files:
        print_error(f"找不到 JSON 文件: {pattern}")
        return False
    
    print_info(f"处理 {len(json_files)} 个窗口...")
    
    # 批量分类
    results_df = engine.validate_batch_from_jsons(json_files)
    
    if results_df.empty:
        print_error("分类失败，没有结果")
        return False
    
    print_step(f"分类完成: {len(results_df)} 个窗口")
    
    # 显示统计
    print_info("\n📊 分类分布:")
    
    print("\n  Exercise Load:")
    for cat, count in results_df['exercise_load_category'].value_counts().sort_index().items():
        pct = (count / len(results_df) * 100)
        print(f"    • {cat:12s}: {count:3d} ({pct:5.1f}%)")
    
    print("\n  Fatigue Level:")
    for cat, count in results_df['fatigue_level_category'].value_counts().sort_index().items():
        pct = (count / len(results_df) * 100)
        print(f"    • {cat:12s}: {count:3d} ({pct:5.1f}%)")
    
    print("\n  Movement Quality (Dim 3 - LLM Aligned):")
    for cat in ['good', 'degraded', 'poor']:
        count = (results_df['movement_quality_category'] == cat).sum()
        pct = (count / len(results_df) * 100)
        print(f"    • {cat:12s}: {count:3d} ({pct:5.1f}%)")
    
    # 保存结果
    output_file = RESULTS_OUTPUT_DIR / f"fuzzy_results_{subject_id}_{task_type}.csv"
    results_df.to_csv(output_file, index=False)
    print_step(f"结果已保存到: {output_file}")
    
    # 显示样本
    print_info("\n前 5 个窗口的分类结果:")
    cols = ['window_id', 'cadence_hz', 'stride_length', 'step_var_ms',
            'exercise_load_category', 'fatigue_level_category',
            'movement_quality_category', 'confidence']
    
    sample = results_df[cols].head()
    print("\n" + sample.to_string(index=False))
    
    return output_file

# ============================================================
# 主函数
# ============================================================
def main():
    parser = argparse.ArgumentParser(
        description="DUO-GAIT 完整处理流程：原始数据 → JSON → Fuzzy 分类"
    )
    parser.add_argument('subject', nargs='?', default='sub_01',
                        help='受试者 ID (default: sub_01)')
    parser.add_argument('task', nargs='?', default='st',
                        help='任务类型 (default: st)')
    parser.add_argument('--skip-json', action='store_true',
                        help='跳过 JSON 生成，直接使用现有文件')
    
    args = parser.parse_args()
    
    print_header(f"🚀 DUO-GAIT 完整处理流程")
    print_info(f"Subject: {args.subject}")
    print_info(f"Task: {args.task}")
    print_info(f"Workspace: {WORKSPACE}")
    
    # 步骤 1: 验证原始数据
    if not verify_raw_data(args.subject, args.task):
        print_error("原始数据验证失败，停止")
        sys.exit(1)
    
    # 步骤 2: 生成 JSON（可选跳过）
    json_count = None
    if not args.skip_json:
        json_count = generate_json_windows(args.subject, args.task)
        if not json_count:
            print_error("JSON 生成失败，停止")
            sys.exit(1)
    else:
        print_warning("跳过 JSON 生成")
    
    # 步骤 3: 应用 Fuzzy 分类
    output_file = apply_fuzzy_classification(args.subject, args.task)
    if not output_file:
        print_error("Fuzzy 分类失败")
        sys.exit(1)
    
    # 完成！
    print_header("✨ 流程完成")
    print_step("所有步骤执行成功")
    print(f"\n📊 输出文件:")
    print(f"  • 分类结果 CSV: {output_file}")
    if json_count:
        print(f"  • JSON 窗口数: {json_count}")
        print(f"  • JSON 目录: {JSON_OUTPUT_DIR}")
    print(f"\n🎯 下一步:")
    print(f"  • 查看结果: open {output_file}")
    print(f"  • 或使用命令: head -20 {output_file} | column -t -s,")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print_error(f"执行出错: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
