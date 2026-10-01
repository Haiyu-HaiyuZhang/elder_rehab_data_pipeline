# Backend Notes

## 2026-10-01 — SensorBridge Windows UDP bridge

### Task summary

- Added a new `SensorBridge/` .NET 8 Windows project for the requested local sensor bridge.
- Kept the existing Python offline DUO-GAIT pipeline and Unity untouched.

### Files or systems touched

- `SensorBridge/src/SensorBridge/`: app entry point, config, device boundaries, processing, models, services, and UDP transport.
- `SensorBridge/tests/SensorBridge.Tests/`: no-external-dependency console tests for protocol-critical behavior.
- `SensorBridge/publish-win-x64.ps1` and `SensorBridge/README.md`: Windows run/test/publish instructions.

### Decisions made

- IMU/HR session IDs and sequence counters are separate process-lifetime objects.
- UDP publishers run on fixed independent timers and do not depend on BLE connection lifetime.
- Stale or unavailable streams publish `quality = 0.0` and all sensor-specific fields as `null`.
- Polar H10 uses Windows standard BLE Heart Rate Service `0x180D` and characteristic `0x2A37`; parser handles 8-bit HR, 16-bit HR, optional energy expended, and multiple RR intervals per notification.
- RMSSD uses a rolling RR window and remains `null` until the configured minimum RR count is present.
- WIT uses a Windows BLE `IWitBleClient` implementation. It ports only the official sample's public GATT UUIDs, 20-byte stream framing, and scale factors; notifications are buffered until a complete immutable sample is available, avoiding the official sample's torn-record timing issue.
- The C# IMU processor keeps a 30-second rolling window and follows the existing Python magnitude, second-order Butterworth low-pass, height/prominence/distance peak rules, valid ISI range, population SD, and chest-anchor step-length definition. `step_time_cv = SD(ISI) / mean(ISI)` is computed from unrounded intervals. Unsupported fields stay `null`.
- Polar contact-status flags and HR=0 are treated as not worn. Both Windows BLE clients monitor disconnects, clear processor state, and enter independent retry loops.
- Simulation can inject a finite outage and recover, allowing stale/null/session/sequence behavior to be tested without hardware.

### Verification performed

- Static repository audit found no pre-existing C#/.NET project and no bundled WIT SDK.
- Ran tests with temporary SDK `/private/tmp/elder-rehab-dotnet8/dotnet`:
  - JSON nulls are preserved and not serialized as zero.
  - Polar parser handles multiple RR intervals and 16-bit HR.
  - RMSSD calculation respects minimum data count.
  - Polar contact loss clears HR/RR/RMSSD.
  - WIT fragmented notifications emit only complete atomic frames and use the official scaling.
  - A deterministic 30-second simulated gait window matches the Python algorithm's cadence and step-length results and validates CV as a ratio.
  - IMU/HR session counters are independent.
  - Stale IMU frame shape uses `quality = 0` and null fields.
- `dotnet build SensorBridge/src/SensorBridge/SensorBridge.csproj -c Release` passed with 0 warnings and 0 errors.
- `dotnet publish SensorBridge/src/SensorBridge/SensorBridge.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true` produced `SensorBridge.exe` plus `appsettings.json` under `SensorBridge/src/SensorBridge/bin/Release/net8.0-windows10.0.19041.0/win-x64/publish/`.
- End-to-end simulation plus `receive_sensor_stream.py` received 291 IMU and 29 HR frames with no invalid, dropped, or out-of-order frames. A finite simulated outage produced `quality=0`/all-null frames, then recovered using the same session IDs with continuously increasing sequence numbers.

### Risks and follow-up work

- Hardware validation remains open for WIT and Polar H10 on the target Windows machine.
- The live UDP protocol exposes `step_time_cv`, but the assessment API consumes `step_time_variability_ms`; no approved conversion is implemented. Never route CV directly into the classifier's millisecond thresholds.
- `receive_sensor_stream.py` is still only a protocol validator/state tracker/logger. A future live adapter must define aggregation/time alignment, perform the approved variability conversion, and then call `assess_exercise_state()`.
- The official WIT repository reviewed at commit `9efaab0fdd6a06dc807bf80402e58aa91b431c6f` has no explicit source redistribution license. No vendor source is copied here; confirm current protocol/support terms with WITMOTION before commercial deployment.
- The Butterworth implementation is a clean C# port of the same filter order/cutoff, and deterministic window metrics are covered, but broader Python/C# golden-data parity should be run on captured target-device sessions before clinical use.
