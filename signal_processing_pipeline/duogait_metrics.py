"""
DUO-GAIT 辅助指标：双足 INTERIM IMU（LF/RF）自算步频/步长/步时变异。
主流程 JSON 不依赖 DUO processed（算法不透明）；processed 仅用于 validate_duogait_metrics 离线对照。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import config as _cfg

    _STRIDE_SCALE = float(getattr(_cfg, "STRIDE_LEN_OUTPUT_SCALE", 1.0))
except Exception:
    _STRIDE_SCALE = 1.0


def interim_subject_dir_to_processed_dir(interim_subject_dir: str) -> str:
    return interim_subject_dir.replace("/interim/", "/processed/")


def _norm_cols(df: pd.DataFrame) -> Dict[str, str]:
    return {c.lower().strip(): c for c in df.columns}


def _col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    m = _norm_cols(df)
    for name in candidates:
        key = name.lower()
        if key in m:
            return m[key]
    return None


def load_foot_core_params(processed_subject_dir: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    left_path = os.path.join(processed_subject_dir, "left_foot_core_params.csv")
    right_path = os.path.join(processed_subject_dir, "right_foot_core_params.csv")
    left_df = pd.read_csv(left_path) if os.path.isfile(left_path) else None
    right_df = pd.read_csv(right_path) if os.path.isfile(right_path) else None
    return left_df, right_df


def window_metrics_from_processed_tables(
    left_df: Optional[pd.DataFrame],
    right_df: Optional[pd.DataFrame],
    t_start: float,
    t_end: float,
) -> Optional[Dict[str, Any]]:
    """
    使用官方 processed 足部逐步表，在 [t_start, t_end) 秒内聚合指标。
    时间列优先 'timestamps'（秒，相对任务起点）。
    """
    frames = [d for d in (left_df, right_df) if d is not None and len(d) > 0]
    if not frames:
        return None

    tcol = None
    for d in frames:
        tcol = _col(d, "timestamps", "timestamp", "time")
        if tcol:
            break
    if not tcol:
        return None

    lengths: list = []
    times: list = []
    cadences: list = []

    for d in frames:
        tc = _col(d, "timestamps", "timestamp", "time")
        if not tc:
            continue
        t = pd.to_numeric(d[tc], errors="coerce")
        mask = (t >= t_start) & (t < t_end)
        sub = d.loc[mask]
        if sub.empty:
            continue
        lc = _col(sub, "stride_lengths", "stride_length", "stridelength")
        if lc:
            lengths.extend(pd.to_numeric(sub[lc], errors="coerce").dropna().tolist())
        stc = _col(sub, "stride_times", "stride_time", "steptime")
        if stc:
            times.extend(pd.to_numeric(sub[stc], errors="coerce").dropna().tolist())
        cc = _col(sub, "cadence", "cadence_spm")
        if cc:
            cadences.extend(pd.to_numeric(sub[cc], errors="coerce").dropna().tolist())

    out: Dict[str, Any] = {}
    if lengths:
        out["step_length_m"] = float(np.clip(np.mean(lengths), 0.2, 2.0))
    if times:
        arr = np.array(times)
        arr = arr[(arr > 0.2) & (arr < 3.0)]
        if len(arr) > 0:
            out["step_frequency_hz"] = float(np.clip(1.0 / np.mean(arr), 0.4, 3.0))
            out["step_time_variability_ms"] = float(np.clip(np.std(arr) * 1000.0, 0.0, 200.0))
    if cadences and "step_frequency_hz" not in out:
        cmean = float(np.mean(cadences))
        out["step_frequency_hz"] = float(np.clip(cmean / 60.0, 0.4, 3.0))

    return out if out else None


def _accel_triplet(df: pd.DataFrame) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
    """从 DUO CSV 中取三轴加速度与采样率（由 Time 列差分估计）。"""
    cols = _norm_cols(df)
    time_key = None
    for k in ("time", "time(s)", "timestamp"):
        if k in cols:
            time_key = cols[k]
            break
    if time_key is None:
        return None
    t = pd.to_numeric(df[time_key], errors="coerce").values
    t_valid = t[~np.isnan(t)]
    if len(t_valid) < 2:
        fs = 128.0
    else:
        dt = float(np.nanmedian(np.diff(t_valid)))
        fs = 1.0 / dt if dt > 1e-6 else 128.0

    ax_key = ay_key = az_key = None
    for pat in (
        ("accelx", "accely", "accelz"),
        ("accx", "accy", "accz"),
    ):
        if all(p in cols for p in pat):
            ax_key, ay_key, az_key = cols[pat[0]], cols[pat[1]], cols[pat[2]]
            break
    if ax_key is None:
        ax_key = _col(df, "accx", "accelx", "accel x(m/s²)", "accel x")
        ay_key = _col(df, "accy", "accely", "accel y(m/s²)", "accel y")
        az_key = _col(df, "accz", "accelz", "accel z(m/s²)", "accel z")
    if not (ax_key and ay_key and az_key):
        return None

    ax = pd.to_numeric(df[ax_key], errors="coerce").values
    ay = pd.to_numeric(df[ay_key], errors="coerce").values
    az = pd.to_numeric(df[az_key], errors="coerce").values
    return ax, ay, az, float(fs)


def _dynamic_accel_rms(df: Optional[pd.DataFrame]) -> Optional[float]:
    if df is None or len(df) < 30:
        return None
    triplet = _accel_triplet(df)
    if triplet is None:
        return None
    ax, ay, az, _fs = triplet
    mag = np.sqrt(ax ** 2 + ay ** 2 + az ** 2)
    mag = mag - np.nanmean(mag)
    return float(np.sqrt(np.nanmean(mag ** 2)))


def stride_from_cadence_height_and_feet(
    cadence_hz: float,
    height_m: Optional[float],
    lf_df: Optional[pd.DataFrame],
    rf_df: Optional[pd.DataFrame],
    chest_stride_m: float,
) -> float:
    """
    步长：以胸戴估计为锚，用身高+步频给出物理量级，再用双足加速度动态幅度做小幅修正。
    不合并左右足峰值算步频（避免把左右触地混成一串导致 ISI 失真）。
    """
    c = float(np.clip(cadence_hz, 0.5, 2.8))
    if height_m and height_m > 1.0:
        v_walk = float(np.clip(0.35 * np.sqrt(height_m) * (c / 1.5) ** 0.4, 0.4, 2.0))
        base = float(np.clip(v_walk / max(c, 0.5), 0.42, 1.58))
    else:
        base = float(np.clip(1.05 / max(c, 0.55), 0.48, 1.5))

    nudges = [x for x in (_dynamic_accel_rms(lf_df), _dynamic_accel_rms(rf_df)) if x is not None]
    if nudges:
        rms_mean = float(np.mean(nudges))
        # 经验：足部动态加速度 RMS 约 0.15–0.6 m/s² 量级时映射到 ±几厘米
        nudge = float(np.clip((rms_mean - 0.28) * 0.25, -0.06, 0.06))
        base = float(np.clip(base + nudge, 0.40, 1.55))

    # 与胸戴强度映射不要偏离过大，避免单传感器漂移
    anchor = float(np.clip(chest_stride_m, 0.35, 1.55))
    blended = 0.55 * base + 0.45 * anchor
    blended *= _STRIDE_SCALE
    return float(np.clip(blended, 0.38, 1.55))
