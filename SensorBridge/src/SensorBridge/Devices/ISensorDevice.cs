using SensorBridge.Models;

namespace SensorBridge.Devices;

public interface ISensorDevice<TSample>
{
    event Action<TSample>? SampleReceived;
    event Action<DeviceState, string>? StateChanged;
    Task RunAsync(CancellationToken cancellationToken);
}
