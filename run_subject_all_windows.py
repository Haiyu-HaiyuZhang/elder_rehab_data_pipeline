#!/usr/bin/env python3
"""
对某一受试者跑完 DUO INTERIM 下所有 `OG_* / sub_XX` 任务目录的全部 30s 窗口，输出 JSON。

单任务示例仍可用 `process_duogait_to_json.py` 的 main()。

用法:
  python3 run_subject_all_windows.py
  python3 run_subject_all_windows.py --subject sub_01 --out-dir /path/to/json
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO / "signal_processing_pipeline"))

from process_duogait_to_json import DUOGAITProcessor  # noqa: E402


def _task_type_from_og_folder(folder_name: str) -> str:
    if folder_name.startswith("OG_"):
        return folder_name[3:]
    return folder_name


def _hr_raw_dir(base_raw: str, task_type: str) -> str:
    if task_type.startswith("dt_"):
        return os.path.join(base_raw, "OG_dt_raw")
    return os.path.join(base_raw, "OG_st_raw")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", default="sub_01")
    ap.add_argument(
        "--interim-base",
        default="/Volumes/ChouSSD/elder_datasets/DUO-GAIT/interim",
    )
    ap.add_argument(
        "--raw-base",
        default="/Volumes/ChouSSD/elder_datasets/DUO-GAIT/raw",
    )
    ap.add_argument(
        "--out-dir",
        default="/Volumes/ChouSSD/elder_datasets/DUO-GAIT/json",
    )
    args = ap.parse_args()

    pattern = os.path.join(args.interim_base, "OG_*", args.subject)
    imu_dirs = sorted(glob.glob(pattern))
    if not imu_dirs:
        print(f"No interim dirs match: {pattern}")
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    total = 0
    for imu_dir in imu_dirs:
        og_folder = os.path.basename(os.path.dirname(imu_dir))
        task_type = _task_type_from_og_folder(og_folder)
        st_csv = os.path.join(imu_dir, "ST.csv")
        if not os.path.isfile(st_csv):
            print(f"Skip (no ST.csv): {imu_dir}")
            continue
        hr_root = _hr_raw_dir(args.raw_base, task_type)
        hr_dir = os.path.join(hr_root, args.subject)
        hr_file = os.path.join(hr_dir, "heart_rate.CSV")
        if not os.path.isfile(hr_file):
            print(f"Skip (no heart_rate.CSV): {hr_file}")
            continue

        print("=" * 72)
        print(f"Task: {task_type}  IMU: {imu_dir}")
        print(f"HR:   {hr_dir}")
        print(f"Out:  {args.out_dir}")
        proc = DUOGAITProcessor(
            imu_dir,
            hr_dir,
            args.out_dir,
            args.subject,
            task_type,
        )
        proc.load_data()
        n = proc.process_windows(max_windows=None)
        total += n
        print(f"→ wrote {n} windows for {task_type}\n")

    print(f"Done. Total JSON windows written: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
