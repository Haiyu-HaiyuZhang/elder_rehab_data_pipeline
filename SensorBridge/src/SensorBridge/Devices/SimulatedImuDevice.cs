using SensorBridge.Config;
using SensorBridge.Models;
using SensorBridge.Processing;

namespace SensorBridge.Devices;

public sealed class SimulatedImuDevice : ISensorDevice<ImuSample>
{
    private readonly SimulationConfig _config;

    public SimulatedImuDevice(SimulationConfig config)
    {
        _config = config;
    }

    public event Action<ImuSample>? SampleReceived;
    public event Action<DeviceState, string>? StateChanged;

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        StateChanged?.Invoke(DeviceState.Streaming, "simulated IMU");
        var periodMs = Math.Max(1, (int)Math.Round(1000.0 / Math.Max(1, _config.ImuSampleHz)));
        var start = Clock.UnixMilliseconds();
        using var timer = new PeriodicTimer(TimeSpan.FromMilliseconds(periodMs));
        while (await timer.WaitForNextTickAsync(cancellationToken))
        {
            var now = Clock.UnixMilliseconds();
            if (IsInSimulatedOutage(now - start))
            {
                continue;
            }

            var t = (now - start) / 1000.0;
            var gait = Math.Max(0, Math.Sin(2 * Math.PI * 1.7 * t));
            SampleReceived?.Invoke(new ImuSample(
                now,
                0.04 * Math.Sin(2 * Math.PI * 1.7 * t),
                0.02 * Math.Cos(2 * Math.PI * 1.7 * t),
                1.0 + 0.22 * gait,
                3.0 * Math.Sin(2 * Math.PI * 1.7 * t),
                1.0 * Math.Cos(2 * Math.PI * 1.7 * t),
                0,
                3.0 * Math.Sin(2 * Math.PI * 0.3 * t),
                2.0 * Math.Cos(2 * Math.PI * 0.3 * t),
                0));
        }
    }

    private bool IsInSimulatedOutage(long elapsedMs)
    {
        if (_config.SimulateStaleAfterSeconds <= 0)
        {
            return false;
        }

        var outageStartMs = _config.SimulateStaleAfterSeconds * 1000L;
        if (elapsedMs <= outageStartMs)
        {
            return false;
        }

        return _config.SimulateStaleDurationSeconds <= 0 ||
            elapsedMs <= outageStartMs + _config.SimulateStaleDurationSeconds * 1000L;
    }
}
