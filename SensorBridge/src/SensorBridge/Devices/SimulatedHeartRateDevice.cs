using SensorBridge.Config;
using SensorBridge.Models;
using SensorBridge.Processing;

namespace SensorBridge.Devices;

public sealed class SimulatedHeartRateDevice : ISensorDevice<HeartRateSample>
{
    private readonly SimulationConfig _config;

    public SimulatedHeartRateDevice(SimulationConfig config)
    {
        _config = config;
    }

    public event Action<HeartRateSample>? SampleReceived;
    public event Action<DeviceState, string>? StateChanged;

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        StateChanged?.Invoke(DeviceState.Streaming, "simulated Polar H10");
        var periodMs = Math.Max(1, (int)Math.Round(1000.0 / Math.Max(0.1, _config.HrSampleHz)));
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
            var hr = 78 + (int)Math.Round(4 * Math.Sin(t / 10.0));
            var rr = (int)Math.Round(60000.0 / hr);
            SampleReceived?.Invoke(new HeartRateSample(now, hr, new[] { rr }));
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
