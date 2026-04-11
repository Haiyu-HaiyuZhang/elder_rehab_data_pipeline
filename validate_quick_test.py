"""
快速测试模板 - DUO-GAIT 多受试者验证

使用说明：
1. 修改下面的 SUBJECTS 列表选择要测试的受试者
2. 运行脚本：python validate_quick_test.py
3. 查看控制台输出的验证结果表格

示例：
    SUBJECTS = ["sub_02", "sub_07"]  # 测试这两个受试者
"""

import sys
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

from validate_multi_subjects import MultiSubjectValidator

# ============================================================
# 【修改这里】选择要测试的受试者
# ============================================================

# 选项1：快速测试 - 3 个受试者
SUBJECTS = ["sub_02", "sub_07", "sub_10"]

# 选项2：ST vs DT 对比 - 6 个受试者（可解注以使用）
# SUBJECTS = ["sub_02", "sub_03", "sub_04", "sub_06", "sub_07", "sub_08"]

# 选项3：完整测试 - 所有 16 个受试者（可解注以使用）
# SUBJECTS = ["sub_01", "sub_02", "sub_03", "sub_05", "sub_06", "sub_07", 
#             "sub_08", "sub_09", "sub_10", "sub_11", "sub_12", "sub_13", 
#             "sub_14", "sub_15", "sub_17", "sub_18"]

# ============================================================

def main():
    import logging
    from datetime import datetime
    
    print(f"\n{'='*80}")
    print(f"  DUO-GAIT 多受试者快速验证")
    print(f"{'='*80}\n")
    print(f"测试受试者: {', '.join(SUBJECTS)}")
    print(f"测试任务: ST (单任务) 和 DT (双任务)")
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    # 创建验证器
    validator = MultiSubjectValidator()
    
    # 运行批量验证
    print("正在处理... (这可能需要几分钟)\n")
    all_results = validator.run_multi_subject_validation(
        subject_list=SUBJECTS,
        task_types=["st", "dt"]
    )
    
    # 打印心率验证汇总
    validator.print_hr_validation_summary()
    
    # 保存结果
    print()
    validator.save_results(all_results, output_prefix="quick_test")
    
    print(f"\n{'='*80}")
    print(f"  验证完成！")
    print(f"{'='*80}\n")
    
    # 统计信息
    baseline_errors = [r['baseline_error_pct'] for r in validator.hr_validation_results if 'baseline_error_pct' in r]
    fatigue_errors = [r['fatigue_error_pct'] for r in validator.hr_validation_results if 'fatigue_error_pct' in r]
    
    print(f"📊 验证统计：")
    print(f"  - 总测试数：{len(SUBJECTS)} 个受试者 × 2 个任务 = {len(SUBJECTS)*2} 项")
    print(f"  - 成功验证：{len(validator.hr_validation_results)} 项")
    
    if baseline_errors:
        import numpy as np
        print(f"  - Baseline 误差范围：{min(baseline_errors):.1f}% ~ {max(baseline_errors):.1f}%")
        print(f"    (平均: {np.mean(baseline_errors):.1f}%)")
    
    if fatigue_errors:
        import numpy as np
        print(f"  - Fatigue 误差范围：{min(fatigue_errors):.1f}% ~ {max(fatigue_errors):.1f}%")
        print(f"    (平均: {np.mean(fatigue_errors):.1f}%)")
    
    print(f"\n💾 输出文件：")
    print(f"  - quick_test_validation_results.json")
    print(f"  - quick_test_hr_validation_summary.json")
    

if __name__ == "__main__":
    main()
