# SensorBridge

Windows-only .NET 8 bridge for the frozen local UDP sensor protocol.

## Run in simulation mode

```powershell
dotnet run --project .\src\SensorBridge\SensorBridge.csproj -- --simulate
```

This sends IMU frames to `127.0.0.1:9101` and HR frames to `127.0.0.1:9102` without physical sensors.

The production IMU feature window is 30 seconds, so IMU frames intentionally use `quality: 0` and null features until the first complete window is available.

To test stale behavior without hardware, set `simulation.simulate_stale_after_seconds` to a positive value. Set `simulation.simulate_stale_duration_seconds` to resume samples after a fixed outage; leave it at `0` to stay stale for the rest of the run. Session IDs remain unchanged and sequence numbers continue across the simulated outage.

## Test

```powershell
dotnet run --project .\tests\SensorBridge.Tests\SensorBridge.Tests.csproj
```

The test project has no NuGet test-runner dependency. It exits with code `0` on success and non-zero on failure.

## Publish

```powershell
.\publish-win-x64.ps1
```

Equivalent command:

```powershell
dotnet publish .\src\SensorBridge\SensorBridge.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

The clean handoff directory is `release/win-x64/` and contains `SensorBridge.exe` and `appsettings.json`.

## Hardware status

Polar H10 uses the standard BLE Heart Rate Service (`0x180D`) and Heart Rate Measurement characteristic (`0x2A37`) through `Windows.Devices.Bluetooth`. It does not enable Polar SDK mode.

WIT IMU uses Windows BLE directly with the service/notify UUIDs, 20-byte framing, and numeric scaling published in WITMOTION's official BWT901 BLE 5.0 Windows C# sample (reviewed at commit `9efaab0fdd6a06dc807bf80402e58aa91b431c6f`). The adapter scans for names containing the configured `imu.device_name` (default `WT`), subscribes to notifications, buffers split notifications, and creates one immutable sample only after a complete frame is available. No vendor source or DLL is copied into this repository.

If `device_id` is blank the bridge scans. A configured WIT ID can be a Windows BLE device ID or a hexadecimal Bluetooth address; the Polar ID is the Windows BLE device ID reported by discovery.

Both clients monitor Windows connection status. A disconnect clears the sensor's processing state and enters its own retry loop without stopping the other BLE client or either UDP publisher.

## IMU algorithm contract

The C# processor ports the current Python chest-IMU definition: three-axis magnitude, DC removal, absolute value, second-order 4 Hz Butterworth low-pass, the same `2.5 × SD` height / `0.5 × threshold` prominence / `0.4 s` distance peak rules, and valid ISIs in `(0.3, 2.0)` seconds. It uses a rolling 30-second window and refreshes latest features at up to 10 Hz.

`step_time_cv` is calculated directly as population `SD(ISI) / mean(ISI)` and is not a percentage. `stride_symmetry`, `trunk_sway_deg`, and `is_walking` remain `null` because the existing local algorithm does not define them.

## Real-time assessment boundary

SensorBridge intentionally publishes `step_time_cv`. The offline assessment function accepts `step_time_variability_ms` and applies thresholds expressed in milliseconds. No approved CV-to-millisecond adapter is implemented, so `step_time_cv` must not be passed directly into `assess_exercise_state()`.

The Python UDP receiver currently validates, tracks, and optionally logs SensorBridge frames only. It does not aggregate IMU/HR frames into assessment windows and does not invoke `assess_exercise_state()`. SensorBridge therefore provides the stable sensor transport layer; it does not claim to provide live assessment output.

## Hardware acceptance still required

The repository has been cross-built and simulation-tested on macOS. Before field deployment, run the executable on the target Windows x64 machine with the actual WT9011DCL-BT50 and Polar H10, confirm the configured device names/IDs, and perform the physical disconnect/reconnect checklist. WIT's public sample repository has no explicit source redistribution license; this implementation therefore uses only the published protocol facts and should still be checked against the vendor's current device documentation.
