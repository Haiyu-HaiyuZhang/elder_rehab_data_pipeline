"""
步频算法诊断脚本 - 验证 3Hz 饱和问题

检查是否真的检测到了 3Hz，或者是被 clip 限制的
"""

import numpy as np
import pandas as pd
from scipy.signal import find_peaks
import sys
sys.path.insert(0, '/Users/zhanghaiyu/workspace/elder_rehab/signal_processing_pipeline')

import config

def diagnose_step_frequency(subject_id="sub_01", task_type="st", window_id=0):
    """
    诊断单个窗口的步频计算
    
    输出：
    - 检测到的峰值数量（未clip）
    - 计算的原始步频（未clip）
    - clip后的步频（现在输出的值）
    - 左脚vs右脚的比较
    """
    
    from pathlib import Path
    
    dataset_root = Path("/Volumes/ChouSSD/elder_datasets/DUO-GAIT")
    raw_dir = dataset_root / "raw"
    
    if task_type == "st":
        data_dir = raw_dir / "OG_st_raw" / subject_id
    else:
        data_dir = raw_dir / "OG_dt_raw" / subject_id
    
    print(f"📊 诊断 {subject_id} ({task_type.upper()}) - 窗口 {window_id}\n")
    
    # 加载 IMU 数据
    lf_data = pd.read_csv(data_dir / 'LF.csv', skiprows=5, low_memory=False)
    rf_data = pd.read_csv(data_dir / 'RF.csv', skiprows=5, low_memory=False)
    
    # 转换为数值
    for col in ['Accel X', 'Accel Y', 'Accel Z']:
        lf_data[col] = pd.to_numeric(lf_data[col], errors='coerce')
        rf_data[col] = pd.to_numeric(rf_data[col], errors='coerce')
    
    # 提取加速度
    acc_x_lf = lf_data['Accel X'].dropna().values
    acc_y_lf = lf_data['Accel Y'].dropna().values
    acc_z_lf = lf_data['Accel Z'].dropna().values
    
    acc_x_rf = rf_data['Accel X'].dropna().values
    acc_y_rf = rf_data['Accel Y'].dropna().values
    acc_z_rf = rf_data['Accel Z'].dropna().values
    
    # 计算合向量
    acc_mag_lf = np.sqrt(acc_x_lf**2 + acc_y_lf**2 + acc_z_lf**2)
    acc_mag_rf = np.sqrt(acc_x_rf**2 + acc_y_rf**2 + acc_z_rf**2)
    
    # 提取窗口
    window_samples = int(config.DUO_GAIT_SAMPLE_RATE * config.WINDOW_LENGTH_SEC)
    start_idx = window_id * window_samples
    end_idx = start_idx + window_samples
    
    if end_idx > len(acc_mag_lf):
        print(f"❌ 窗口 {window_id} 超出数据范围")
        return
    
    window_lf = acc_mag_lf[start_idx:end_idx]
    window_rf = acc_mag_rf[start_idx:end_idx]
    
    print(f"窗口时间范围: {start_idx/config.DUO_GAIT_SAMPLE_RATE:.0f}s - {end_idx/config.DUO_GAIT_SAMPLE_RATE:.0f}s")
    print(f"窗口样本数: {len(window_lf)}")
    print()
    
    # 峰值检测参数
    min_distance_samples = int(config.MIN_PEAK_DISTANCE_SEC * config.DUO_GAIT_SAMPLE_RATE)
    noise_std_lf = np.std(window_lf)
    noise_std_rf = np.std(window_rf)
    peak_height_lf = config.PEAK_HEIGHT_MULTIPLIER * noise_std_lf
    peak_height_rf = config.PEAK_HEIGHT_MULTIPLIER * noise_std_rf
    
    # 左脚峰值检测
    peaks_lf, _ = find_peaks(
        window_lf,
        distance=min_distance_samples,
        height=peak_height_lf,
        prominence=noise_std_lf * 0.5
    )
    
    # 右脚峰值检测
    peaks_rf, _ = find_peaks(
        window_rf,
        distance=min_distance_samples,
        height=peak_height_rf,
        prominence=noise_std_rf * 0.5
    )
    
    # 计算步频（未 clip）
    window_duration_sec = config.WINDOW_LENGTH_SEC
    
    step_freq_lf_raw = len(peaks_lf) / window_duration_sec
    step_freq_rf_raw = len(peaks_rf) / window_duration_sec
    step_freq_avg_raw = (step_freq_lf_raw + step_freq_rf_raw) / 2
    
    # 计算步频（clip后）
    step_freq_lf_clipped = np.clip(
        step_freq_lf_raw,
        config.STEP_FREQUENCY_MIN_HZ,
        config.STEP_FREQUENCY_MAX_HZ
    )
    step_freq_rf_clipped = np.clip(
        step_freq_rf_raw,
        config.STEP_FREQUENCY_MIN_HZ,
        config.STEP_FREQUENCY_MAX_HZ
    )
    step_freq_avg_clipped = np.clip(
        step_freq_avg_raw,
        config.STEP_FREQUENCY_MIN_HZ,
        config.STEP_FREQUENCY_MAX_HZ
    )
    
    # 打印诊断结果
    print("=" * 70)
    print("左脚 (LF) 分析")
    print("=" * 70)
    print(f"检测到的峰值数: {len(peaks_lf)} 个")
    print(f"噪声标准差: {noise_std_lf:.4f}")
    print(f"峰值高度阈值: {peak_height_lf:.4f}")
    print(f"")
    print(f"步频（未clip）: {step_freq_lf_raw:.3f} Hz")
    print(f"步频（已clip）: {step_freq_lf_clipped:.3f} Hz")
    if step_freq_lf_raw > config.STEP_FREQUENCY_MAX_HZ:
        print(f"  ⚠️ 被截断了! 原值 {step_freq_lf_raw:.3f} Hz > 上限 {config.STEP_FREQUENCY_MAX_HZ} Hz")
    print()
    
    print("=" * 70)
    print("右脚 (RF) 分析")
    print("=" * 70)
    print(f"检测到的峰值数: {len(peaks_rf)} 个")
    print(f"噪声标准差: {noise_std_rf:.4f}")
    print(f"峰值高度阈值: {peak_height_rf:.4f}")
    print(f"")
    print(f"步频（未clip）: {step_freq_rf_raw:.3f} Hz")
    print(f"步频（已clip）: {step_freq_rf_clipped:.3f} Hz")
    if step_freq_rf_raw > config.STEP_FREQUENCY_MAX_HZ:
        print(f"  ⚠️ 被截断了! 原值 {step_freq_rf_raw:.3f} Hz > 上限 {config.STEP_FREQUENCY_MAX_HZ} Hz")
    print()
    
    print("=" * 70)
    print("综合分析")
    print("=" * 70)
    print(f"平均步频（未clip）: {step_freq_avg_raw:.3f} Hz")
    print(f"平均步频（已clip）: {step_freq_avg_clipped:.3f} Hz")
    print(f"左右脚差异: {abs(step_freq_lf_raw - step_freq_rf_raw):.3f} Hz")
    
    if abs(step_freq_lf_raw - step_freq_rf_raw) > 0.5:
        print(f"  ⚠️ 左右脚步频差异较大（> 0.5 Hz），可能左脚峰值检测有问题")
    else:
        print(f"  ✓ 左右脚步频基本一致，峰值检测合理")
    
    print()
    
    # 推荐
    print("=" * 70)
    print("诊断结论")
    print("=" * 70)
    
    if step_freq_avg_raw > config.STEP_FREQUENCY_MAX_HZ:
        print(f"❌ 步频被 clip 限制")
        print(f"   真实步频: {step_freq_avg_raw:.3f} Hz")
        print(f"   输出步频: {step_freq_avg_clipped:.3f} Hz")
        print(f"   ")
        print(f"💡 建议: 提高 STEP_FREQUENCY_MAX_HZ（目前 {config.STEP_FREQUENCY_MAX_HZ} Hz）")
        print(f"   或检查峰值检测参数是否过于灵敏")
    else:
        print(f"✓ 步频未被 clip，检测正常")
        print(f"   计算步频: {step_freq_avg_raw:.3f} Hz")
    
    print()
    
    # 打印前 5 个峰值位置
    print("=" * 70)
    print("峰值位置验证（样本索引）")
    print("=" * 70)
    print(f"LF 前 5 个峰值: {peaks_lf[:5]}")
    print(f"LF 峰值间距（样本）: {np.diff(peaks_lf[:5]) if len(peaks_lf) > 4 else 'N/A'}")
    print(f"LF 峰值间距（秒）: {np.diff(peaks_lf[:5]) / config.DUO_GAIT_SAMPLE_RATE if len(peaks_lf) > 4 else 'N/A'}")
    print()
    print(f"RF 前 5 个峰值: {peaks_rf[:5]}")
    print(f"RF 峰值间距（样本）: {np.diff(peaks_rf[:5]) if len(peaks_rf) > 4 else 'N/A'}")
    print(f"RF 峰值间距（秒）: {np.diff(peaks_rf[:5]) / config.DUO_GAIT_SAMPLE_RATE if len(peaks_rf) > 4 else 'N/A'}")


if __name__ == "__main__":
    # 诊断窗口 0（最开始）
    print("\n🔍 诊断第一个 30 秒窗口\n")
    diagnose_step_frequency(subject_id="sub_01", task_type="st", window_id=0)
    
    print("\n" + "=" * 70)
    print("\n🔍 诊断中间的窗口\n")
    diagnose_step_frequency(subject_id="sub_01", task_type="st", window_id=20)
    
    print("\n" + "=" * 70)
    print("\n🔍 诊断最后的窗口\n")
    diagnose_step_frequency(subject_id="sub_01", task_type="st", window_id=85)
