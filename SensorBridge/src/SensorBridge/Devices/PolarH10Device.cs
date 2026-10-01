using SensorBridge.Config;
using SensorBridge.Models;

namespace SensorBridge.Devices;

public interface IHeartRateBleClient
{
    Task StreamAsync(HeartRateConfig config, Action<HeartRateSample> onSample, CancellationToken cancellationToken);
}

public sealed class PolarH10Device : ISensorDevice<HeartRateSample>
{
    private readonly HeartRateConfig _config;
    private readonly IHeartRateBleClient _client;

    public PolarH10Device(HeartRateConfig config, IHeartRateBleClient client)
    {
        _config = config;
        _client = client;
    }

    public event Action<HeartRateSample>? SampleReceived;
    public event Action<DeviceState, string>? StateChanged;

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                StateChanged?.Invoke(DeviceState.Scanning, "Polar H10 scanning");
                StateChanged?.Invoke(DeviceState.Connecting, "Polar H10 connecting");
                await _client.StreamAsync(_config, sample => SampleReceived?.Invoke(sample), cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                StateChanged?.Invoke(DeviceState.Disconnected, $"Polar H10 disconnected: {ex.Message}");
                await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);
            }
        }
    }
}
