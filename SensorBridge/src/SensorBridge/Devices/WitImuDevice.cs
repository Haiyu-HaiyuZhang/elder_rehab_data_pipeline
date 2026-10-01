using SensorBridge.Config;
using SensorBridge.Models;

namespace SensorBridge.Devices;

public interface IWitBleClient
{
    Task StreamAsync(ImuConfig config, Action<ImuSample> onSample, CancellationToken cancellationToken);
}

public sealed class WitImuDevice : ISensorDevice<ImuSample>
{
    private readonly ImuConfig _config;
    private readonly IWitBleClient _client;

    public WitImuDevice(ImuConfig config, IWitBleClient client)
    {
        _config = config;
        _client = client;
    }

    public event Action<ImuSample>? SampleReceived;
    public event Action<DeviceState, string>? StateChanged;

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                StateChanged?.Invoke(DeviceState.Scanning, "WIT scanning");
                StateChanged?.Invoke(DeviceState.Connecting, "WIT connecting");
                await _client.StreamAsync(_config, sample => SampleReceived?.Invoke(sample), cancellationToken);
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                StateChanged?.Invoke(DeviceState.Disconnected, $"WIT disconnected: {ex.Message}");
                await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);
            }
        }
    }
}
