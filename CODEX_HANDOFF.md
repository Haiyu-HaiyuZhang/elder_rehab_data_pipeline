# Codex Handoff: Elder Rehabilitation Pipeline

> This document is an implementation handoff for Codex. Existing project specifications and frozen design documents are authoritative and should not be rewritten casually.

## 1. Current Repository State

- Branch: `main`
- Last known local commit: `66b5340`
- The repository contains the offline DUO-GAIT pipeline and a local UDP receiver for the agreed sensor protocol.
- Do not add raw datasets, generated JSON exports, logs, external-drive paths, or research PDFs to the repository.
- Existing project documentation is considered frozen for the current handoff. Make focused code changes and update this handoff only when describing new decisions.

## 2. Existing Mature Pipeline

### Offline path

```text
DUO-GAIT INTERIM IMU + RAW heart_rate.CSV
        -> process_duogait_to_json.py
        -> 30-second window features
        -> fuzzy ground_truth
        -> JSON files for offline LLM evaluation
```

Main files:

- `process_duogait_to_json.py`: primary offline processor.
- `batch_process_all.py`: batch processor with configurable `--interim-base`, `--raw-base`, and `--out-dir`.
- `run_subject_all_windows.py`: process every available task for one subject.
- `validate_duogait_metrics.py`: optional comparison with DUO-GAIT `processed/`; not a source of truth for the main JSON path.
- `signal_processing_pipeline/config.py`: sampling, threshold, stride scaling, and fallback configuration.
- `signal_processing_pipeline/duogait_metrics.py`: optional LF/RF foot-IMU stride correction.
- `signal_processing_pipeline/fuzzy_classifier.py`: current rule classifier.

### Current offline feature definitions

- `step_frequency_hz`: calculated from ST three-axis acceleration peak intervals.
- `step_length_m`: chest-IMU anchor plus optional LF/RF adjustment and heuristic scaling.
- `step_time_variability_ms`: standard deviation of inter-step intervals in milliseconds.
- `mean_hr_bpm`: 30-second window HR mean.
- `max_hr_bpm`: 30-second window HR maximum.
- `rpe`: currently `null`; DUO-GAIT does not provide the required Borg CR-10 value.

Important metric distinction:

```text
step_time_variability_ms = SD(ISI) * 1000
step_time_cv = SD(ISI) / mean(ISI)
```

These are different quantities and must not share the same thresholds without an explicit conversion or a revised rule set.

## 3. Frozen Sensor Transport Protocol

The runtime sensor process sends feature frames, not raw IMU samples:

- IMU: UDP `127.0.0.1:9101`, recommended 5-10 Hz.
- Polar H10 HR: UDP `127.0.0.1:9102`, recommended 1 Hz.
- One independent UTF-8 JSON datagram per frame; no fragmentation, handshake, or acknowledgement.
- Every frame has `type`, `session_id`, `seq`, `timestamp_ms`, and `quality`.
- `seq` starts at 1 and increments within a process session.
- A new `session_id` is generated after sensor-process restart.
- Missing sensor values are `null`, never a fabricated zero.
- When a sensor is not worn, the process continues sending frames with `quality: 0` and all sensor-specific values set to `null`.

The local receiver is:

```bash
python3 receive_sensor_stream.py --jsonl /tmp/sensor-stream.jsonl
```

It validates required fields, finite numeric values, quality range, `quality=0` null semantics, sequence gaps, out-of-order frames, session changes, timestamp reversal, and stale streams. The receiver currently validates and logs frames; it does not yet convert live frames into the offline JSON schema or invoke the classifier.

## 4. Agreed Assessment Prompt

The colleague's prompt defines a strict two-layer output:

```json
{
  "research_layer": {
    "exercise_load_state": "low|moderate|high|excessive",
    "fatigue_level": "none|mild|moderate|severe",
    "movement_quality": "good|degraded|poor",
    "composite_state": "normal|under_loaded|fatigue_risk",
    "confidence": 0.0,
    "modality_contribution": {
      "imu_weight": 0.0,
      "hr_weight": 0.0
    },
    "reasoning": "...",
    "compensation_flags": [],
    "data_reliability": "high|medium|low"
  },
  "system_layer": {
    "dda_delta": -2,
    "ui_feedback": "...",
    "clinical_flag": "normal|fatigue_compensation|high_cardiac_load|hard_stop|data_invalid"
  }
}
```

The authoritative rule details are:

- `MHR = 220 - age` for the current frozen rule set.
- HR load: `<50%` low, `50-<70%` moderate, `70-<80%` high, `>=80%` excessive.
- Movement quality uses absolute cadence, step length, and step-time-variability tiers, then sums three scores: good `0`, degraded `1`, poor `2`; sum `<=1` good, `2-3` degraded, `>=4` poor.
- Relative deterioration of `>=20%` from warmup upgrades severity by one level; values within `+/-10%` retain the absolute tier.
- Fatigue score uses variability, short step length, and optional RPE.
- Any safety override produces `composite_state: fatigue_risk`.
- HR-dependent safety rules only apply when HR is available.
- If `mean_hr_bpm` is `null`, `exercise_load` must be `unknown`; do not infer or assume HR and do not trigger HR-based safety rules.
- If both modalities are below quality `0.6`, the result is invalid: all dimensions are `unknown`, `dda_delta` is `0`, and `clinical_flag` is `data_invalid`.
- A missing HR modality should have low HR contribution, no more than `0.2`; reasoning should rely on IMU and fatigue signals only.
- A classifier or input-validation failure must never default to a reassuring normal state.

## 5. Confirmed Inconsistencies

The current code is not yet an implementation of the full two-layer prompt.

### Output schema mismatch

Current `fuzzy_classifier.py` returns the legacy fields:

```json
{
  "exercise_load": "...",
  "fatigue_level": "...",
  "movement_quality": "...",
  "composite_state": "...",
  "confidence": 0.0,
  "reasoning": ""
}
```

`process_duogait_to_json.py` writes these under the legacy `ground_truth` object. It does not produce `research_layer` or `system_layer`, and it lacks:

- `exercise_load_state` naming used by the prompt
- `modality_contribution`
- `data_reliability`
- `compensation_flags`
- `dda_delta`
- `ui_feedback`
- `clinical_flag`
- meaningful rule-based `reasoning`

### Safety and missing-data mismatch

- `_safety_override()` returns only a boolean, so the reason for the override is lost.
- The current double-low-quality path returns `composite_state: normal`; the frozen prompt requires an invalid-data result.
- The current classifier does not calculate HR/IMU modality weights.
- The current exception fallback in `create_window_json()` returns `moderate/none/good/normal`, which is unsafe and contradicts the invalid-data policy.

### Metric mismatch

The live protocol sends `step_time_cv`, while the offline prompt thresholds `step_time_variability_ms` in milliseconds. The integration must either:

1. convert live CV to a calibrated millisecond variability value before classification, or
2. change the prompt and all threshold logic to CV thresholds.

Do not silently pass `step_time_cv` into millisecond rules.

### Recovery history

An earlier rule version mentioned a heart-rate recovery score. The current frozen design removed it because a single 30-second window cannot calculate recovery reliably. Do not reintroduce `hr_recovery` unless the design is explicitly unfrozen and a post-exercise observation window is specified.

## 6. Responsibility Assessment

This is primarily a version-synchronization and implementation-completeness issue:

- The original physiological rule direction is broadly consistent: target HR 50-70% MHR, increased gait variability/shortening as risk signals, and safety overrides for high load or deteriorating movement.
- The current implementation correctly covers much of the old Dim 1-3 label logic.
- The implementation did not follow through when the design evolved to the two-layer prompt and live protocol.
- The prompt and live protocol also changed the variability representation from milliseconds to CV without completing the interface contract.

Therefore, the main corrective responsibility is to align the classifier, output schema, and live adapter. It is not appropriate to blame the original HR/IMU rule proposal alone.

## 7. Recommended Codex Work Order

1. Add a pure assessment function that returns the complete two-layer schema without network or file I/O.
2. Refactor safety evaluation to return structured reasons and flags, not only a boolean.
3. Implement explicit modality weights and reliability levels.
4. Implement missing-HR behavior and the both-low-quality `data_invalid` behavior.
5. Replace the reassuring exception fallback with an invalid-data result.
6. Decide and document the live variability conversion before connecting live frames to the classifier.
7. Add focused tests for every boundary: 50%, 70%, 80% MHR; 30/60/80 ms variability; 20% warmup drop; RPE 7/9; missing HR; low quality; malformed input.
8. Add a separate live adapter that aggregates UDP feature frames into the classifier input window. Keep the existing offline processor and frozen project specifications unchanged.
9. Only after tests pass, decide whether legacy `ground_truth` remains as a compatibility field or is replaced by the two-layer output.

## 8. Do Not Do Yet

- Do not change the frozen project specification just to hide implementation differences.
- Do not treat `max_hr_bpm` as a replacement for `mean_hr_bpm` in the load rule unless explicitly approved.
- Do not calculate HR recovery from one 30-second frame.
- Do not interpret `step_time_cv` using millisecond thresholds.
- Do not use missing values as zero.
- Do not default classifier failures to `normal`.
- Do not commit external-drive data, JSON exports, UDP logs, or credentials.

## 9. 2026-10-01 Implementation Update

- `assess_exercise_state()` now produces the complete `research_layer` / `system_layer` schema. The old Python classifier functions remain as compatibility wrappers.
- Offline `ground_truth` now contains the two-layer assessment. Double-low-quality and classifier failure paths produce `data_invalid`, never a reassuring normal fallback.
- `SensorBridge/` is a .NET 8 Windows x64 console application with separate WIT/Polar device adapters, processors, services, and fixed-rate UDP publishers.
- WIT uses the official sample's published BLE UUIDs, 20-byte BWT901 frame layout, and scale factors through the Windows BLE API. No vendor source or DLL is copied into this repository.
- Polar uses the standard Heart Rate Service and handles 8/16-bit HR, multiple RR intervals, sensor contact, and rolling-window RMSSD.
- The bridge keeps UDP alive during initialization, disconnect, not-worn, and stale states by emitting `quality: 0` with null sensor fields. Session IDs and sequence counters are independent per stream and survive reconnects.
- Simulation and protocol tests cover valid/stale/recovered frames, null serialization, WIT framing/scaling, Polar parsing/contact, RMSSD, and 30-second IMU metric behavior.
- A self-contained `win-x64` publish is generated by `SensorBridge/publish-win-x64.ps1`.
- The live protocol still publishes `step_time_cv`, while `assess_exercise_state()` still accepts `step_time_variability_ms`. No CV-to-millisecond assessment adapter has been approved or implemented; these fields must not be connected directly.
- `receive_sensor_stream.py` remains a validator/state tracker/logger. It does not aggregate live IMU/HR frames into assessment windows and does not call `assess_exercise_state()`.

Still required before field deployment: run the published executable on the target Windows x64 machine with the actual WT9011DCL-BT50 and Polar H10, then execute the physical disconnect/reconnect acceptance checklist. The WIT public example repository has no explicit source redistribution license; confirm current vendor protocol/support terms before commercial deployment.
