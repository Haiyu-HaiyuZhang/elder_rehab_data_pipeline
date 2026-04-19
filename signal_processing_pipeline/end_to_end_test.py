"""
端到端测试 - JSON 导出 + Fuzzy 验证

演示完整流程：
  1. 生成示例 30s 窗口特征
  2. 导出为分段编号的 JSON
  3. 应用 Fuzzy Logic 分类
  4. 输出分类结果表格
"""

import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np

print("="*70)
print("端到端测试 - JSON 导出 + Fuzzy 验证")
print("="*70)

# ============================================================
# 第 1 步：生成示例特征数据
# ============================================================

print("\n[Step 1] 生成示例 30s 窗口特征数据...")

# 模拟 12 个 30s 窗口的特征（来自单次实验）
windows_features = []
for i in range(12):
    # 模拟运动强度 progression
    intensity_factor = i / 12  # 0 → 1，逐步增加
    
    features = {
        'timestamp': f"00:{i*30:02d}",
        'hr_mean': int(70 + 50 * intensity_factor + np.random.randn() * 3),
        'hr_max': int(90 + 60 * intensity_factor + np.random.randn() * 3),
        'hr_min': int(65 + 20 * intensity_factor + np.random.randn() * 2),
        'hr_std': int(8 + 8 * intensity_factor),
        'hr_recovery': max(5, 25 - 15 * intensity_factor + np.random.randn() * 2),
        'step_frequency': 1.8 - intensity_factor * 0.1,
        'step_length': 0.60 - intensity_factor * 0.05,
        'stride_length': 0.58 - intensity_factor * 0.05,
        'step_var': int(20 + 40 * intensity_factor + np.random.randn() * 3),
        'speed': max(0.3, 1.1 - intensity_factor * 0.2),
        'rpe_score': 10 + intensity_factor * 8,
        'mhr': 150  # 220 - 70
    }
    windows_features.append(features)

df_features = pd.DataFrame(windows_features)

print(f"✓ 生成 {len(df_features)} 个窗口")
print(f"  HR 范围: {df_features['hr_mean'].min():.0f} ~ {df_features['hr_mean'].max():.0f} bpm")
print(f"  Step Var 范围: {df_features['step_var'].min():.0f} ~ {df_features['step_var'].max():.0f} ms")

# ============================================================
# 第 2 步：导出为 JSON 文件
# ============================================================

print("\n[Step 2] 导出为分段编号的 JSON...")

try:
    from windows_json_exporter import WindowJSONExporter
    
    exporter = WindowJSONExporter(output_dir="./test_window_jsons")
    
    # 批量导出
    files = exporter.batch_export(
        windows_df=df_features,
        subject_id="sub_01",
        task_type="st_control",
        prefix="ST"
    )
    
    print(f"✓ 导出 {len(files)} 个 JSON 文件到 ./test_window_jsons/")
    
except Exception as e:
    print(f"❌ 导出出错: {str(e)}")
    sys.exit(1)

# ============================================================
# 第 3 步：应用 Fuzzy Logic 验证
# ============================================================

print("\n[Step 3] 应用 Fuzzy Logic 分类...")

try:
    from validate_with_fuzzy import FuzzyValidationEngine
    
    engine = FuzzyValidationEngine(age=70, verbose=True)
    
    # 验证 JSON 目录
    results_df = engine.validate_from_directory(
        input_dir="./test_window_jsons",
        subject_id="sub_01",
        task_type="st_control"
    )
    
    if results_df.empty:
        print("❌ 未生成分类结果")
        sys.exit(1)
    
    print(f"✓ 完成 {len(results_df)} 个窗口的分类")
    
except Exception as e:
    print(f"❌ 验证出错: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================
# 第 4 步：输出分类结果表格
# ============================================================

print("\n[Step 4] 保存分类结果表格...")

output_csv = "fuzzy_results_sub_01_st_control.csv"
results_df.to_csv(output_csv, index=False)
print(f"✓ 结果已保存: {output_csv}")

# ============================================================
# 第 5 步：显示结果概览
# ============================================================

print("\n" + "="*70)
print("分类结果概览")
print("="*70)

# 生成摘要报告
report = engine.generate_summary_report(results_df)

print(f"\n📈 样本统计:")
print(f"  总窗口数: {report['total_windows']}")
print(f"  受试者: {results_df['subject_id'].iloc[0]}")
print(f"  任务类型: {results_df['task_type'].iloc[0]}")

print(f"\n📊 运动负荷分布:")
for cat, count in sorted(report['exercise_load_distribution'].items()):
    pct = (count / report['total_windows']) * 100
    bar = "█" * int(pct / 5)
    print(f"  {cat:12s}: {count:2d} ({pct:5.1f}%) {bar}")

print(f"\n📊 疲劳等级分布:")
for cat, count in sorted(report['fatigue_level_distribution'].items()):
    pct = (count / report['total_windows']) * 100
    bar = "█" * int(pct / 5)
    print(f"  {cat:12s}: {count:2d} ({pct:5.1f}%) {bar}")

print(f"\n📊 动作质量分布:")
for cat, count in sorted(report['movement_quality_distribution'].items()):
    pct = (count / report['total_windows']) * 100
    bar = "█" * int(pct / 5)
    print(f"  {cat:12s}: {count:2d} ({pct:5.1f}%) {bar}")

print(f"\n🔍 详细结果 (前5个窗口):")
print("-" * 70)
display_cols = [
    'window_id', 'hr_mean', 'step_var', 'exercise_load_category',
    'fatigue_level_category', 'movement_quality_category', 'confidence'
]
print(results_df[display_cols].head(5).to_string(index=False))

print("\n⚠️  异常检测:")
excessive = (results_df['exercise_load_category'] == 'excessive').sum()
severe = (results_df['fatigue_level_category'] == 'severe').sum()
poor = (results_df['movement_quality_category'] == 'poor').sum()

if excessive > 0:
    print(f"  ⚠️  过高负荷窗口: {excessive}")
if severe > 0:
    print(f"  ⚠️  严重疲劳窗口: {severe}")
if poor > 0:
    print(f"  ⚠️  动作质量差窗口: {poor}")
if excessive == 0 and severe == 0 and poor == 0:
    print(f"  ✓ 无异常检测")

# ============================================================
# 完成
# ============================================================

print("\n" + "="*70)
print("✅ 端到端测试完成！")
print("="*70)

print("\n📁 输出文件:")
print(f"  JSON 目录: ./test_window_jsons/")
print(f"  分类结果: {output_csv}")

print("\n💡 接下来可以:")
print(f"  1. 查看 JSON 文件: cat ./test_window_jsons/sub_01_st_control_window_ST_000.json")
print(f"  2. 查看分类结果: head -5 {output_csv}")
print(f"  3. 用 LLM 处理 JSON 语料来自动生成标签")

print("\n✨ 完整流程验证成功！")
