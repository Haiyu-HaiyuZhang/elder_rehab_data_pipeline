using SensorBridge.Config;
using SensorBridge.Models;
using SensorBridge.Processing;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.Advertisement;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Storage.Streams;

namespace SensorBridge.Devices;

/// <summary>
/// Windows BLE adapter for WT9011DCL-BT50 / BWT901 BLE 5.0 devices.
/// UUIDs, frame layout, and scaling follow WITMOTION's official BWT901 BLE 5.0
/// Windows C# sample at commit 9efaab0fdd6a06dc807bf80402e58aa91b431c6f.
/// </summary>
public sealed class WindowsWitBleClient : IWitBleClient
{
    private static readonly Guid ServiceUuid = Guid.Parse("0000ffe5-0000-1000-8000-00805f9a34fb");
    private static readonly Guid NotifyUuid = Guid.Parse("0000ffe4-0000-1000-8000-00805f9a34fb");

    public async Task StreamAsync(ImuConfig config, Action<ImuSample> onSample, CancellationToken cancellationToken)
    {
        using var device = await OpenDeviceAsync(config, cancellationToken)
            ?? throw new InvalidOperationException("Unable to open the WIT BLE device.");

        var serviceResult = await device.GetGattServicesForUuidAsync(ServiceUuid, BluetoothCacheMode.Uncached);
        if (serviceResult.Status != GattCommunicationStatus.Success || serviceResult.Services.Count == 0)
        {
            throw new InvalidOperationException($"WIT service {ServiceUuid} was not found ({serviceResult.Status}).");
        }

        using var service = serviceResult.Services[0];
        var characteristicResult = await service.GetCharacteristicsForUuidAsync(NotifyUuid, BluetoothCacheMode.Uncached);
        if (characteristicResult.Status != GattCommunicationStatus.Success || characteristicResult.Characteristics.Count == 0)
        {
            throw new InvalidOperationException($"WIT notify characteristic {NotifyUuid} was not found ({characteristicResult.Status}).");
        }

        var characteristic = characteristicResult.Characteristics[0];
        var parser = new WitBwt901PacketParser();
        var disconnected = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);

        void OnConnectionStatusChanged(BluetoothLEDevice sender, object args)
        {
            if (sender.ConnectionStatus == BluetoothConnectionStatus.Disconnected)
            {
                disconnected.TrySetResult();
            }
        }

        void OnValueChanged(GattCharacteristic sender, GattValueChangedEventArgs args)
        {
            try
            {
                var bytes = new byte[(int)args.CharacteristicValue.Length];
                using var reader = DataReader.FromBuffer(args.CharacteristicValue);
                reader.ReadBytes(bytes);
                foreach (var sample in parser.Append(bytes, Clock.UnixMilliseconds()))
                {
                    onSample(sample);
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[IMU] WIT packet error: {ex.Message}");
            }
        }

        device.ConnectionStatusChanged += OnConnectionStatusChanged;
        characteristic.ValueChanged += OnValueChanged;
        var status = await characteristic.WriteClientCharacteristicConfigurationDescriptorAsync(
            GattClientCharacteristicConfigurationDescriptorValue.Notify);
        if (status != GattCommunicationStatus.Success)
        {
            characteristic.ValueChanged -= OnValueChanged;
            device.ConnectionStatusChanged -= OnConnectionStatusChanged;
            throw new InvalidOperationException($"Failed to subscribe to WIT notifications ({status}).");
        }

        try
        {
            await disconnected.Task.WaitAsync(cancellationToken);
            throw new IOException("WIT BLE device disconnected.");
        }
        finally
        {
            characteristic.ValueChanged -= OnValueChanged;
            device.ConnectionStatusChanged -= OnConnectionStatusChanged;
            try
            {
                await characteristic.WriteClientCharacteristicConfigurationDescriptorAsync(
                    GattClientCharacteristicConfigurationDescriptorValue.None);
            }
            catch
            {
                // The device can disappear before CCCD cleanup; the reconnect loop owns recovery.
            }
        }
    }

    private static async Task<BluetoothLEDevice?> OpenDeviceAsync(ImuConfig config, CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(config.DeviceId))
        {
            var configured = await OpenKnownDeviceAsync(config.DeviceId);
            if (configured is not null)
            {
                return configured;
            }
        }

        var expectedName = string.IsNullOrWhiteSpace(config.DeviceName) ? "WT" : config.DeviceName;
        var found = new TaskCompletionSource<(ulong Address, string Name)>(TaskCreationOptions.RunContinuationsAsynchronously);
        var watcher = new BluetoothLEAdvertisementWatcher
        {
            ScanningMode = BluetoothLEScanningMode.Active
        };

        void OnReceived(BluetoothLEAdvertisementWatcher sender, BluetoothLEAdvertisementReceivedEventArgs args)
        {
            var name = args.Advertisement.LocalName ?? string.Empty;
            if (name.Contains(expectedName, StringComparison.OrdinalIgnoreCase))
            {
                found.TrySetResult((args.BluetoothAddress, name));
            }
        }

        watcher.Received += OnReceived;
        watcher.Start();
        try
        {
            var timeout = TimeSpan.FromMilliseconds(Math.Max(1000, config.ScanTimeoutMs));
            var result = await found.Task.WaitAsync(timeout, cancellationToken);
            return await BluetoothLEDevice.FromBluetoothAddressAsync(result.Address);
        }
        finally
        {
            watcher.Received -= OnReceived;
            watcher.Stop();
        }
    }

    private static async Task<BluetoothLEDevice?> OpenKnownDeviceAsync(string deviceId)
    {
        try
        {
            var byId = await BluetoothLEDevice.FromIdAsync(deviceId);
            if (byId is not null)
            {
                return byId;
            }
        }
        catch
        {
            // A saved Bluetooth address is not a Windows DeviceInformation ID.
        }

        var normalized = deviceId.Replace(":", string.Empty, StringComparison.Ordinal)
            .Replace("-", string.Empty, StringComparison.Ordinal);
        return ulong.TryParse(normalized, System.Globalization.NumberStyles.HexNumber, null, out var address)
            ? await BluetoothLEDevice.FromBluetoothAddressAsync(address)
            : null;
    }
}
