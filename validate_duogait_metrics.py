#!/usr/bin/env python3
"""
可选：将「逐窗 processed 足部表」与 aggregate_params 对比（仅离线验收，不参与主流程 JSON）。

用法:
  python3 validate_duogait_metrics.py \\
    --interim-dir /path/to/interim/OG_st_control/sub_01 \\
    --aggregate /path/to/processed/OG_st_control/sub_01/aggregate_params.csv

不指定 aggregate 时，会尝试 interim 同任务的 processed 目录。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO / "signal_processing_pipeline"))
from duogait_metrics import interim_subject_dir_to_processed_dir, load_foot_core_params, window_metrics_from_processed_tables


def _pick(df: pd.DataFrame, *names: str) -> str | None:
    cols = {c.lower().replace(" ", "_"): c for c in df.columns}
    for n in names:
        k = n.lower().replace(" ", "_")
        if k in cols:
            return cols[k]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare windowed metrics vs DUO processed aggregate")
    ap.add_argument("--interim-dir", required=True, help="e.g. .../interim/OG_st_control/sub_01")
    ap.add_argument("--aggregate", default="", help="aggregate_params.csv path")
    ap.add_argument("--windows", type=int, default=12, help="number of 30s windows to sample")
    args = ap.parse_args()

    interim_dir = args.interim_dir.rstrip("/")
    agg_path = args.aggregate.strip()
    if not agg_path:
        proc_dir = interim_subject_dir_to_processed_dir(interim_dir)
        cand = os.path.join(proc_dir, "aggregate_params.csv")
        agg_path = cand if os.path.isfile(cand) else ""

    if not agg_path or not os.path.isfile(agg_path):
        print("No aggregate_params.csv; nothing to compare.")
        return 1

    st_path = os.path.join(interim_dir, "ST.csv")
    if not os.path.isfile(st_path):
        print(f"Missing ST.csv under {interim_dir}")
        return 1

    st = pd.read_csv(st_path, index_col=0)
    time_col = "Time" if "Time" in st.columns else None
    if time_col:
        t = pd.to_numeric(st[time_col], errors="coerce").values
        dt = float(np.nanmedian(np.diff(t[~np.isnan(t)]))) if len(t) > 1 else 1 / 128
        fs = 1.0 / dt if dt > 1e-9 else 128.0
    else:
        fs = 128.0

    agg = pd.read_csv(agg_path, nrows=1)
    col_stride = _pick(agg, "stride_lengths_avg", "stride_length_avg")
    col_cad = _pick(agg, "cadence_avg", "cadence")
    ref_stride = float(agg.iloc[0][col_stride]) if col_stride else None
    ref_cad_hz = float(agg.iloc[0][col_cad]) / 60.0 if col_cad else None

    proc_dir = interim_subject_dir_to_processed_dir(interim_dir)
    left_df, right_df = load_foot_core_params(proc_dir)

    samples_per = int(30 * fs)
    nwin = min(args.windows, max(1, len(st) // samples_per))
    errs_stride = []
    errs_cad = []

    for i in range(nwin):
        t0 = i * 30.0
        t1 = (i + 1) * 30.0
        pm = window_metrics_from_processed_tables(left_df, right_df, t0, t1)
        if not pm:
            continue
        if ref_stride and "step_length_m" in pm:
            errs_stride.append(abs(pm["step_length_m"] - ref_stride) / ref_stride)
        if ref_cad_hz and "step_frequency_hz" in pm:
            errs_cad.append(abs(pm["step_frequency_hz"] - ref_cad_hz) / max(ref_cad_hz, 1e-6))

    print(f"Compared {len(errs_stride)} windows with per-window processed means vs aggregate row.")
    if errs_stride:
        print(f"  stride_length rel error: mean={np.mean(errs_stride):.3f} max={np.max(errs_stride):.3f}")
    if errs_cad:
        print(f"  cadence_hz rel error:      mean={np.mean(errs_cad):.3f} max={np.max(errs_cad):.3f}")
    print("Note: aggregate is whole-task mean; per-window mean will not match exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
