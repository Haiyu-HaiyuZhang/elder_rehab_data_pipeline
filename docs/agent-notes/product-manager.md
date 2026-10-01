# Product Manager Notes

## 2026-10-01 — Local handoff and Windows Sensor Bridge

### Goal

- Align the local rule classifier with the colleague-owned two-layer assessment prompt described in `CODEX_HANDOFF.md`.
- Add a double-clickable Windows x64 Sensor Bridge that keeps two stable UDP streams alive while WIT IMU and Polar H10 connectivity changes.
- Preserve the existing offline IMU metric definitions; unavailable values remain `null`, never fabricated zeroes.

### Scope and decisions

- Existing Python offline processing remains the source of truth for current metric mathematics.
- Unity is out of scope and will not be modified.
- The bridge is a new .NET 8 Windows project with BLE acquisition, processing, and UDP publishing separated by interfaces/services.
- IMU and HR have independent process-lifetime session IDs and sequence counters.
- UDP publishers run independently of BLE connections. Stale or unavailable sources publish `quality: 0` with all sensor fields `null`.
- Hardware-independent simulation is required for protocol and lifecycle verification.
- WIT integration must use the official Windows sample/SDK where distributable and compatible; any remaining vendor dependency must be stated explicitly rather than hidden behind a simulated implementation.

### Milestones / verification

1. Repository and vendor-SDK audit: record actual algorithm inputs, sample/window requirements, dependencies, and integration constraints.
2. Prompt alignment: complete two-layer schema and boundary/missing-data tests pass.
3. Sensor Bridge: build succeeds; parser, RMSSD, stale/null, session/seq, and UDP serialization tests pass.
4. Simulation: both UDP streams continue at configured frequencies and transition between fresh and stale frames without changing session IDs or resetting sequence counters.
5. Release: `win-x64` self-contained publish completes and its exact output path and required sidecar files are documented.

### Open hardware-dependent checks

- Confirm the exact WIT device name/identifier and official DLL/runtime files used by the target WT9011DCL-BT50 unit.
- Confirm live Polar H10 pairing and GATT notification behavior on the target Windows machine.
- Run unplug/reconnect acceptance tests with both physical devices; these cannot be truthfully completed on a Mac without the hardware.

### Current status

- Prompt alignment is implemented with two-layer output, structured safety flags, modality contribution, data reliability, missing-HR behavior, and invalid-data fallback tests.
- A .NET 8 Windows Sensor Bridge now implements real WIT and Polar Windows BLE adapters, isolated processors/services, fixed-rate UDP, stale/null handling, independent session/sequence state, automatic reconnect loops, simulation, tests, and `win-x64` self-contained publishing.
- End-to-end simulation verified valid → stale/null → recovered UDP transitions with stable session IDs and continuous sequences.
- Live assessment remains intentionally out of scope for this delivery: the transport emits `step_time_cv`, the classifier requires `step_time_variability_ms`, and no approved conversion/aggregation adapter exists yet. `receive_sensor_stream.py` validates and records frames but does not invoke the classifier.
- Remaining acceptance is hardware-dependent: run the published build on the target Windows x64 machine with the exact WIT and Polar units and perform physical disconnect/reconnect tests.
