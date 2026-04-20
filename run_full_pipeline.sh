#!/bin/bash
# 完整的 DUO-GAIT 处理流程脚本
# 功能：从原始数据 → JSON 窗口 → Fuzzy 分类 → CSV 结果

set -e  # 任何命令失败就停止

# ============================================================
# 配置
# ============================================================
WORKSPACE="/Users/zhanghaiyu/workspace/elder_rehab"
RAW_DATA_PATH="/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw"
JSON_OUTPUT_DIR="/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json"
RESULTS_OUTPUT_DIR="/Volumes/ChouSSD/elder_datasets/DUO-GAIT/results"

# 默认受试者 ID（可通过命令行参数覆盖）
SUBJECT_ID="${1:-sub_01}"
TASK_TYPE="${2:-st}"

# ============================================================
# 颜色输出
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================
# 函数定义
# ============================================================

print_section() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

print_step() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# ============================================================
# 主流程
# ============================================================

print_section "🚀 DUO-GAIT 完整处理流程"
echo "Subject: $SUBJECT_ID"
echo "Task: $TASK_TYPE"
echo "Workspace: $WORKSPACE"

cd "$WORKSPACE"

# 步骤 1: 检查原始数据
print_section "步骤 1/3: 检查原始数据"
if [ -f "${RAW_DATA_PATH}/${SUBJECT_ID}/ST.csv" ]; then
    print_step "找到原始数据: ST.csv"
    ROWS=$(wc -l < "${RAW_DATA_PATH}/${SUBJECT_ID}/ST.csv")
    echo "          行数: $ROWS"
else
    print_error "找不到原始数据: ${RAW_DATA_PATH}/${SUBJECT_ID}/ST.csv"
    exit 1
fi

# 步骤 2: 生成 JSON 窗口
print_section "步骤 2/3: 生成 JSON 窗口（30秒滑动窗口）"
echo "运行: python3 process_duogait_to_json.py --subject ${SUBJECT_ID} --task ${TASK_TYPE}"

python3 process_duogait_to_json.py \
    --subject "$SUBJECT_ID" \
    --task "$TASK_TYPE" \
    --output_dir "$JSON_OUTPUT_DIR" \
    --verbose

if [ $? -eq 0 ]; then
    JSON_COUNT=$(ls -1 "${JSON_OUTPUT_DIR}/${SUBJECT_ID}_${TASK_TYPE}_window_*.json" 2>/dev/null | wc -l)
    print_step "JSON 生成完成: $JSON_COUNT 个窗口"
else
    print_error "JSON 生成失败"
    exit 1
fi

# 步骤 3: 应用 Fuzzy 分类
print_section "步骤 3/3: 应用 Fuzzy Logic 分类"
echo "运行: python3 -m signal_processing_pipeline.validate_with_fuzzy"

mkdir -p "$RESULTS_OUTPUT_DIR"

python3 << 'PYTHON_SCRIPT'
import sys
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

from validate_with_fuzzy import FuzzyValidationEngine, get_subject_age_from_info
from pathlib import Path
import pandas as pd

subject_id = f"{sys.argv[1]}"
task_type = f"{sys.argv[2]}"

# 获取年龄
age = get_subject_age_from_info(subject_id)
if age is None:
    print(f"⚠️  找不到年龄，使用默认值 70")
    age = 70

print(f"📊 Subject: {subject_id}, Age: {age}, Task: {task_type}")

# 初始化引擎
engine = FuzzyValidationEngine(age=age, verbose=False)

# 获取 JSON 文件
json_dir = Path('/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json/')
json_files = sorted([f for f in json_dir.glob(f'{subject_id}_{task_type}_window_*.json')])

if not json_files:
    print(f"❌ 找不到 JSON 文件: {subject_id}_{task_type}_window_*.json")
    sys.exit(1)

print(f"📋 找到 {len(json_files)} 个窗口文件")

# 批量分类
results_df = engine.validate_batch_from_jsons(json_files)

# 输出统计
print(f"\n✅ 分类完成！共 {len(results_df)} 个窗口")
print(f"\n📊 分类统计:")
print(f"\nExercise Load:")
print(results_df['exercise_load_category'].value_counts())
print(f"\nFatigue Level:")
print(results_df['fatigue_level_category'].value_counts())
print(f"\nMovement Quality:")
print(results_df['movement_quality_category'].value_counts())

# 保存结果
output_file = f'/Volumes/ChouSSD/elder_datasets/DUO-GAIT/results/fuzzy_results_{subject_id}_{task_type}.csv'
results_df.to_csv(output_file, index=False)
print(f"\n💾 结果已保存到: {output_file}")

# 显示样本
print(f"\n📋 前 5 个窗口:")
cols = ['window_id', 'cadence_hz', 'stride_length', 'step_var_ms', 
        'exercise_load_category', 'fatigue_level_category', 
        'movement_quality_category', 'confidence']
print(results_df[cols].head().to_string())

PYTHON_SCRIPT
"$SUBJECT_ID" "$TASK_TYPE"

if [ $? -eq 0 ]; then
    print_step "分类完成"
else
    print_error "分类失败"
    exit 1
fi

# 最终总结
print_section "✨ 流程完成"
echo -e "${GREEN}✓ 所有步骤执行成功${NC}"
echo ""
echo "📊 输出文件:"
echo "  • JSON 窗口: ${JSON_OUTPUT_DIR}/${SUBJECT_ID}_${TASK_TYPE}_window_*.json"
echo "  • 分类结果: ${RESULTS_OUTPUT_DIR}/fuzzy_results_${SUBJECT_ID}_${TASK_TYPE}.csv"
echo ""
echo "🎯 下一步:"
echo "  • 查看 CSV 结果: open ${RESULTS_OUTPUT_DIR}/fuzzy_results_${SUBJECT_ID}_${TASK_TYPE}.csv"
echo "  • 或使用命令: head -20 ${RESULTS_OUTPUT_DIR}/fuzzy_results_${SUBJECT_ID}_${TASK_TYPE}.csv"
