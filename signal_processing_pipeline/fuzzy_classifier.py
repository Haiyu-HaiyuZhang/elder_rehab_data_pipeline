"""
与 LLM 同事规则对齐的状态分类（Dim1–3 + 安全覆盖 + composite）。

心率缺失：有 RPE 时仅用 RPE 定运动负荷；无 RPE 时 exercise_load=unknown，
其余维度仍可由 IMU 与规则推断；复合态不因「缺 HR」自动判 under_loaded。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOAD_LEVELS = ("low", "moderate", "high", "excessive")
FATIGUE_LEVELS = ("none", "mild", "moderate", "severe")
QUALITY_LEVELS = ("good", "degraded", "poor")
COMPOSITE_LEVELS = ("normal", "under_loaded", "fatigue_risk")


def _unknown_assessment(reason: str = "Both IMU and heart-rate data are below the usable quality threshold.") -> Dict[str, Any]:
    return {
        "research_layer": {
            "exercise_load_state": "unknown",
            "fatigue_level": "unknown",
            "movement_quality": "unknown",
            "composite_state": "unknown",
            "confidence": 0.0,
            "modality_contribution": {
                "imu_weight": 0.0,
                "hr_weight": 0.0,
            },
            "reasoning": reason,
            "compensation_flags": ["data_invalid"],
            "data_reliability": "low",
        },
        "system_layer": {
            "dda_delta": 0,
            "ui_feedback": "Sensor data quality is too low for a reliable assessment.",
            "clinical_flag": "data_invalid",
        },
    }


def _mhr(age: int) -> float:
    return float(220 - int(age))


def _hr_pct(mean_hr: float, age: int) -> float:
    m = _mhr(age)
    if m <= 0:
        return 0.0
    return 100.0 * float(mean_hr) / m


def _load_level_from_hr_pct(pct: float) -> int:
    """<50 low；[50,70) moderate；[70,80) high；≥80 excessive（与 ceiling 规则一致）。"""
    if pct < 50:
        return 0
    if pct < 70:
        return 1
    if pct < 80:
        return 2
    return 3


def _load_level_from_rpe(rpe: float) -> int:
    """同事表：≤3 low, 4–6 moderate, 7–8 high, ≥9 excessive（按 CR-10 数值语义）。"""
    if rpe <= 3:
        return 0
    if rpe <= 6:
        return 1
    if rpe < 9:
        return 2
    return 3


def _load_name(level: int) -> str:
    return LOAD_LEVELS[int(np.clip(level, 0, 3))]


def _cadence_tier(hz: float) -> int:
    if 1.6 <= hz <= 2.0:
        return 0
    if (1.4 <= hz < 1.6) or (2.0 < hz <= 2.2):
        return 1
    if hz < 1.4 or hz > 2.2:
        return 2
    return 1


def _stride_tier(m: float) -> int:
    if 0.45 <= m <= 0.65:
        return 0
    if (0.35 <= m < 0.45) or (0.65 < m <= 0.75):
        return 1
    if m < 0.35 or m > 0.75:
        return 2
    return 1


def _var_tier(ms: float) -> int:
    if ms < 30:
        return 0
    if ms <= 60:
        return 1
    return 2


def _apply_relative(
    tier: int,
    cur: float,
    warm: float,
    *,
    higher_is_worse: bool,
) -> int:
    """±10% 内保持绝对档；恶化方向相对变化 ≥20% 升一级严重度。"""
    if warm is None or abs(float(warm)) < 1e-9:
        return tier
    rel = (float(cur) - float(warm)) / abs(float(warm))
    if abs(rel) <= 0.10:
        return tier
    if higher_is_worse:
        if rel >= 0.20:
            return int(min(2, tier + 1))
        return tier
    if rel <= -0.20:
        return int(min(2, tier + 1))
    return tier


def _missing(x: Optional[float]) -> bool:
    return x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x)))


def _dim3_score_sum(
    cadence_hz: float,
    stride_m: float,
    var_ms: float,
    warmup: Dict[str, Any],
) -> Tuple[int, int, int]:
    fc = _cadence_tier(cadence_hz)
    fs = _stride_tier(stride_m)
    fv = _var_tier(var_ms)

    wc = float(warmup.get("warmup_cadence_hz") or cadence_hz)
    ws = float(warmup.get("warmup_stride_m") or stride_m)
    wv = float(warmup.get("warmup_var_ms") or var_ms)

    fc = _apply_relative(fc, cadence_hz, wc, higher_is_worse=False)
    fs = _apply_relative(fs, stride_m, ws, higher_is_worse=False)
    fv = _apply_relative(fv, var_ms, wv, higher_is_worse=True)

    return fc, fs, fv


def _movement_quality_from_scores(
    cadence_hz: float,
    stride_m: float,
    var_ms: float,
    tiers: Tuple[int, int, int],
) -> str:
    fc, fs, fv = tiers
    s = fc + fs + fv
    if s <= 1:
        base = "good"
    elif s <= 3:
        base = "degraded"
    else:
        base = "poor"

    if var_ms > 80 or stride_m < 0.30:
        return "poor"
    if var_ms > 60 and stride_m < 0.35:
        return "poor"
    return base


def _fatigue_level(
    var_ms: Optional[float],
    stride_m: Optional[float],
    rpe: Optional[float],
) -> str:
    if _missing(var_ms):
        return "unknown"
    score = 0
    if float(var_ms) > 60:
        score += 2
    elif float(var_ms) >= 30:
        score += 1
    if not _missing(stride_m) and float(stride_m) < 0.40:
        score += 1
    if rpe is not None:
        rp = float(rpe)
        if rp >= 9:
            score += 2
        elif rp >= 7:
            score += 1
    if score <= 0:
        return "none"
    if score <= 2:
        return "mild"
    if score == 3:
        return "moderate"
    return "severe"


def _dim1_exercise_load(
    mean_hr: Optional[float],
    age: int,
    rpe: Optional[float],
) -> str:
    hr_ok = mean_hr is not None and not (isinstance(mean_hr, float) and np.isnan(mean_hr))
    if hr_ok:
        pct = _hr_pct(float(mean_hr), age)
        lvl = _load_level_from_hr_pct(pct)
        if rpe is not None and not (isinstance(rpe, float) and np.isnan(rpe)):
            r_lvl = _load_level_from_rpe(float(rpe))
            if abs(r_lvl - lvl) >= 2:
                lvl = max(lvl, r_lvl)
        return _load_name(lvl)
    # The frozen prompt requires HR-dependent exercise load to remain unknown
    # when mean HR is unavailable. RPE can still affect fatigue and safety, but
    # it must not be used to invent an HR load state.
    return "unknown"


def _safety_override(
    mean_hr: Optional[float],
    age: int,
    fatigue_level: str,
    movement_quality: str,
    rpe: Optional[float],
    var_ms: Optional[float],
    stride_m: Optional[float],
    warmup: Dict[str, Any],
) -> bool:
    return bool(
        _safety_flags(
            mean_hr,
            age,
            fatigue_level,
            movement_quality,
            rpe,
            var_ms,
            stride_m,
            warmup,
        )
    )


def _safety_flags(
    mean_hr: Optional[float],
    age: int,
    fatigue_level: str,
    movement_quality: str,
    rpe: Optional[float],
    var_ms: Optional[float],
    stride_m: Optional[float],
    warmup: Dict[str, Any],
) -> List[str]:
    mhr = _mhr(age)
    hr_ok = mean_hr is not None and not (isinstance(mean_hr, float) and np.isnan(mean_hr))
    flags: List[str] = []

    if hr_ok and float(mean_hr) >= 0.80 * mhr:
        flags.append("high_cardiac_load")
    if fatigue_level == "severe":
        flags.append("severe_fatigue")
    if movement_quality == "poor":
        flags.append("poor_movement_quality")
    if rpe is not None and not (isinstance(rpe, float) and np.isnan(rpe)) and float(rpe) >= 9:
        flags.append("high_rpe")
    if (
        not _missing(var_ms)
        and hr_ok
        and float(var_ms) > 80
        and float(mean_hr) > 0.70 * mhr
    ):
        flags.append("high_variability_high_hr")

    ws = warmup.get("warmup_stride_m")
    if (
        not _missing(stride_m)
        and ws is not None
        and float(ws) > 1e-6
    ):
        drop = (float(ws) - float(stride_m)) / float(ws)
        if drop >= 0.20 and fatigue_level in ("moderate", "severe"):
            flags.append("stride_drop_fatigue")

    if not _missing(var_ms) and not _missing(stride_m):
        if float(var_ms) > 60 and float(stride_m) < 0.35:
            flags.append("variability_short_stride")
    return flags


def _composite_state(
    safety: bool,
    mean_hr: Optional[float],
    age: int,
    tiers: Tuple[int, int, int],
    rpe: Optional[float],
    imu_gait_complete: bool,
) -> str:
    if safety:
        return "fatigue_risk"

    fc, fs, fv = tiers
    good_ct = sum(1 for x in (fc, fs, fv) if x == 0)
    poor_ct = sum(1 for x in (fc, fs, fv) if x == 2)

    hr_ok = mean_hr is not None and not (isinstance(mean_hr, float) and np.isnan(mean_hr))
    pct = _hr_pct(float(mean_hr), age) if hr_ok else None

    rpe_low_or_absent = rpe is None or (isinstance(rpe, float) and np.isnan(rpe)) or float(rpe) <= 3

    if not imu_gait_complete:
        return "normal"

    if (
        pct is not None
        and pct < 50
        and fc == 0
        and fs == 0
        and fv == 0
        and rpe_low_or_absent
    ):
        return "under_loaded"

    if pct is not None and 50 <= pct <= 70 and good_ct >= 2 and poor_ct == 0:
        return "normal"

    return "normal"


def _modality_contribution(
    *,
    imu_quality: float,
    hr_quality: float,
    imu_gait_complete: bool,
    mean_hr_bpm: Optional[float],
) -> Dict[str, float]:
    imu_available = imu_gait_complete and imu_quality >= 0.6
    hr_available = (not _missing(mean_hr_bpm)) and hr_quality >= 0.6

    if not imu_available and not hr_available:
        return {"imu_weight": 0.0, "hr_weight": 0.0}
    if imu_available and not hr_available:
        return {"imu_weight": 0.9, "hr_weight": 0.1}
    if hr_available and not imu_available:
        return {"imu_weight": 0.1, "hr_weight": 0.9}

    imu = max(0.0, min(1.0, float(imu_quality)))
    hr = max(0.0, min(1.0, float(hr_quality)))
    total = imu + hr
    if total <= 0:
        return {"imu_weight": 0.5, "hr_weight": 0.5}
    return {
        "imu_weight": round(imu / total, 3),
        "hr_weight": round(hr / total, 3),
    }


def _data_reliability(
    *,
    imu_quality: float,
    hr_quality: float,
    imu_gait_complete: bool,
    mean_hr_bpm: Optional[float],
) -> str:
    hr_complete = not _missing(mean_hr_bpm)
    if imu_quality < 0.6 and hr_quality < 0.6:
        return "low"
    if imu_gait_complete and hr_complete and imu_quality >= 0.8 and hr_quality >= 0.8:
        return "high"
    if (imu_gait_complete and imu_quality >= 0.6) or (hr_complete and hr_quality >= 0.6):
        return "medium"
    return "low"


def _clinical_flag(flags: List[str], composite_state: str) -> str:
    if not flags:
        return "normal"
    if "high_rpe" in flags or "high_variability_high_hr" in flags:
        return "hard_stop"
    if "high_cardiac_load" in flags:
        return "high_cardiac_load"
    if "stride_drop_fatigue" in flags or "variability_short_stride" in flags:
        return "fatigue_compensation"
    if composite_state == "fatigue_risk":
        return "hard_stop"
    return "normal"


def _dda_delta(composite_state: str, clinical_flag: str) -> int:
    if clinical_flag in ("hard_stop", "high_cardiac_load"):
        return -2
    if composite_state == "fatigue_risk":
        return -2
    if clinical_flag == "fatigue_compensation":
        return -1
    if composite_state == "under_loaded":
        return 1
    return 0


def _reasoning(
    *,
    exercise_load: str,
    fatigue_level: str,
    movement_quality: str,
    composite_state: str,
    flags: List[str],
    mean_hr_bpm: Optional[float],
    imu_gait_complete: bool,
) -> str:
    parts = [
        f"Exercise load is {exercise_load}.",
        f"Fatigue level is {fatigue_level}.",
        f"Movement quality is {movement_quality}.",
        f"Composite state is {composite_state}.",
    ]
    if _missing(mean_hr_bpm):
        parts.append("Heart-rate input is unavailable, so HR safety rules were not applied.")
    if not imu_gait_complete:
        parts.append("IMU gait inputs are incomplete, so movement quality is unknown.")
    if flags:
        parts.append("Safety flags: " + ", ".join(flags) + ".")
    return " ".join(parts)


def _ui_feedback(composite_state: str, clinical_flag: str) -> str:
    if clinical_flag == "data_invalid":
        return "Sensor data quality is too low for a reliable assessment."
    if clinical_flag == "hard_stop":
        return "Pause or reduce intensity and reassess before continuing."
    if clinical_flag == "high_cardiac_load":
        return "Heart-rate load is high; reduce intensity and monitor closely."
    if clinical_flag == "fatigue_compensation":
        return "Movement compensation is detected; reduce task difficulty."
    if composite_state == "under_loaded":
        return "Current load appears low; a small difficulty increase can be considered."
    return "Current state is within the expected training range."


def assess_exercise_state(
    *,
    mean_hr_bpm: Optional[float],
    max_hr_bpm: Optional[float],
    step_frequency_hz: Optional[float],
    step_length_m: Optional[float],
    step_time_variability_ms: Optional[float],
    warmup_baseline: Dict[str, Any],
    player_age: int,
    rpe: Optional[float],
    imu_quality: float,
    hr_quality: float,
) -> Dict[str, Any]:
    """Return the colleague prompt's two-layer assessment schema."""
    if imu_quality < 0.6 and hr_quality < 0.6:
        return _unknown_assessment()

    warmup = warmup_baseline or {}
    imu_gait_complete = not (
        _missing(step_frequency_hz)
        or _missing(step_length_m)
        or _missing(step_time_variability_ms)
    )

    if not imu_gait_complete:
        movement_quality = "unknown"
        fatigue_level = _fatigue_level(step_time_variability_ms, step_length_m, rpe)
        tiers = (1, 1, 1)
    else:
        tiers = _dim3_score_sum(
            float(step_frequency_hz),
            float(step_length_m),
            float(step_time_variability_ms),
            warmup,
        )
        movement_quality = _movement_quality_from_scores(
            float(step_frequency_hz),
            float(step_length_m),
            float(step_time_variability_ms),
            tiers,
        )
        fatigue_level = _fatigue_level(step_time_variability_ms, step_length_m, rpe)

    exercise_load = _dim1_exercise_load(mean_hr_bpm, player_age, rpe)
    flags = _safety_flags(
        mean_hr_bpm,
        player_age,
        fatigue_level,
        movement_quality,
        rpe,
        step_time_variability_ms,
        step_length_m,
        warmup,
    )
    composite_state = _composite_state(
        bool(flags), mean_hr_bpm, player_age, tiers, rpe, imu_gait_complete
    )

    contribution = _modality_contribution(
        imu_quality=imu_quality,
        hr_quality=hr_quality,
        imu_gait_complete=imu_gait_complete,
        mean_hr_bpm=mean_hr_bpm,
    )
    reliability = _data_reliability(
        imu_quality=imu_quality,
        hr_quality=hr_quality,
        imu_gait_complete=imu_gait_complete,
        mean_hr_bpm=mean_hr_bpm,
    )
    conf = float(min(1.0, max(0.0, (imu_quality + hr_quality) / 2.0)))
    if exercise_load == "unknown":
        conf *= 0.7
    if reliability == "low":
        conf *= 0.5

    clinical_flag = _clinical_flag(flags, composite_state)
    dda_delta = _dda_delta(composite_state, clinical_flag)

    return {
        "research_layer": {
            "exercise_load_state": exercise_load,
            "fatigue_level": fatigue_level,
            "movement_quality": movement_quality,
            "composite_state": composite_state,
            "confidence": conf,
            "modality_contribution": contribution,
            "reasoning": _reasoning(
                exercise_load=exercise_load,
                fatigue_level=fatigue_level,
                movement_quality=movement_quality,
                composite_state=composite_state,
                flags=flags,
                mean_hr_bpm=mean_hr_bpm,
                imu_gait_complete=imu_gait_complete,
            ),
            "compensation_flags": flags,
            "data_reliability": reliability,
        },
        "system_layer": {
            "dda_delta": dda_delta,
            "ui_feedback": _ui_feedback(composite_state, clinical_flag),
            "clinical_flag": clinical_flag,
        },
    }


def classify_exercise_state(
    *,
    mean_hr_bpm: Optional[float],
    max_hr_bpm: Optional[float],
    step_frequency_hz: Optional[float],
    step_length_m: Optional[float],
    step_time_variability_ms: Optional[float],
    warmup_baseline: Dict[str, Any],
    player_age: int,
    rpe: Optional[float],
    imu_quality: float,
    hr_quality: float,
) -> Dict[str, Any]:
    """
    返回 ground_truth 四字段 + confidence（供日志/调试，可不写入 JSON）。
    步态任一项为 null/NaN 时：动作档 unknown；步时变异缺失则疲劳 unknown；复合态不因 IMU 缺项判 under_loaded。
    """
    assessment = assess_exercise_state(
        mean_hr_bpm=mean_hr_bpm,
        max_hr_bpm=max_hr_bpm,
        step_frequency_hz=step_frequency_hz,
        step_length_m=step_length_m,
        step_time_variability_ms=step_time_variability_ms,
        warmup_baseline=warmup_baseline,
        player_age=player_age,
        rpe=rpe,
        imu_quality=imu_quality,
        hr_quality=hr_quality,
    )
    research = assessment["research_layer"]

    return {
        "exercise_load": research["exercise_load_state"],
        "fatigue_level": research["fatigue_level"],
        "movement_quality": research["movement_quality"],
        "composite_state": research["composite_state"],
        "confidence": research["confidence"],
    }


class FuzzyExerciseClassifier:
    """兼容旧接口：内部调用 classify_exercise_state。"""

    def __init__(self, age: int = 70):
        self.age = int(age)
        self.mhr = _mhr(self.age)

    def classify(
        self,
        hr_mean: Any,
        step_var: float,
        hr_recovery: Any,
        stride_length: float,
        rpe_score: Optional[float] = None,
        cadence_hz: Optional[float] = None,
        imu_quality: float = 0.85,
        hr_quality: float = 0.85,
        warmup_baseline: Optional[Dict[str, Any]] = None,
        max_hr: Any = None,
    ) -> Dict[str, Any]:
        mean_hr = None if hr_mean is None else float(hr_mean)
        if mean_hr is not None and np.isnan(mean_hr):
            mean_hr = None
        rpe = None if rpe_score is None else float(rpe_score)
        if rpe is not None and np.isnan(rpe):
            rpe = None

        mh = max_hr
        if mh is not None:
            mh = float(mh)
            if np.isnan(mh):
                mh = None

        def _fopt(x: Any) -> Optional[float]:
            if x is None:
                return None
            try:
                v = float(x)
            except (TypeError, ValueError):
                return None
            if np.isnan(v) or np.isinf(v):
                return None
            return v

        out = classify_exercise_state(
            mean_hr_bpm=mean_hr,
            max_hr_bpm=mh,
            step_frequency_hz=_fopt(cadence_hz),
            step_length_m=_fopt(stride_length),
            step_time_variability_ms=_fopt(step_var),
            warmup_baseline=warmup_baseline or {},
            player_age=self.age,
            rpe=rpe,
            imu_quality=float(imu_quality),
            hr_quality=float(hr_quality),
        )

        return {
            "exercise_load": (0.0, out["exercise_load"]),
            "fatigue_level": (0.0, out["fatigue_level"]),
            "movement_quality": (0.0, out["movement_quality"]),
            "composite_state": out["composite_state"],
            "confidence": out["confidence"],
            "reasoning": "",
        }


def create_classifier(age: int) -> FuzzyExerciseClassifier:
    return FuzzyExerciseClassifier(age=age)
