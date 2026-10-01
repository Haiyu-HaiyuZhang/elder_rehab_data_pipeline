using SensorBridge.Config;
using SensorBridge.Models;
using SensorBridge.Processing;
using Windows.Devices.Bluetooth;
using Windows.Devices.Bluetooth.GenericAttributeProfile;
using Windows.Devices.Enumeration;
using Windows.Storage.Streams;

namespace SensorBridge.Devices;

public sealed class WindowsPolarHeartRateBleClient : IHeartRateBleClient
{
    private static readonly Guid HeartRateServiceUuid = BluetoothUuidHelper.FromShortId(0x180D);
    private static readonly Guid HeartRateMeasurementUuid = BluetoothUuidHelper.FromShortId(0x2A37);

    public async Task StreamAsync(HeartRateConfig config, Action<HeartRateSample> onSample, CancellationToken cancellationToken)
    {
        using var device = await OpenDeviceAsync(config, cancellationToken)
            ?? throw new InvalidOperationException("Unable to open Polar H10 BLE device.");

        var serviceResult = await device.GetGattServicesForUuidAsync(HeartRateServiceUuid, BluetoothCacheMode.Uncached);
        if (serviceResult.Status != GattCommunicationStatus.Success || serviceResult.Services.Count == 0)
        {
            throw new InvalidOperationException("Heart Rate Service 0x180D was not found.");
        }

        using var service = serviceResult.Services[0];
        var characteristicResult = await service.GetCharacteristicsForUuidAsync(HeartRateMeasurementUuid, BluetoothCacheMode.Uncached);
        if (characteristicResult.Status != GattCommunicationStatus.Success || characteristicResult.Characteristics.Count == 0)
        {
            throw new InvalidOperationException("Heart Rate Measurement characteristic 0x2A37 was not found.");
        }

        var characteristic = characteristicResult.Characteristics[0];
        var disconnected = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void ConnectionStatusChanged(BluetoothLEDevice sender, object args)
        {
            if (sender.ConnectionStatus == BluetoothConnectionStatus.Disconnected)
            {
                disconnected.TrySetResult();
            }
        }

        void Handler(GattCharacteristic sender, GattValueChangedEventArgs args)
        {
            var bytes = new byte[(int)args.CharacteristicValue.Length];
            using var reader = DataReader.FromBuffer(args.CharacteristicValue);
            reader.ReadBytes(bytes);
            try
            {
                onSample(HeartRateMeasurementParser.Parse(bytes, Clock.UnixMilliseconds()));
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[HR] Polar packet error: {ex.Message}");
            }
        }

        device.ConnectionStatusChanged += ConnectionStatusChanged;
        characteristic.ValueChanged += Handler;
        var status = await characteristic.WriteClientCharacteristicConfigurationDescriptorAsync(
            GattClientCharacteristicConfigurationDescriptorValue.Notify);
        if (status != GattCommunicationStatus.Success)
        {
            characteristic.ValueChanged -= Handler;
            device.ConnectionStatusChanged -= ConnectionStatusChanged;
            throw new InvalidOperationException("Failed to subscribe to Heart Rate Measurement notifications.");
        }

        try
        {
            await disconnected.Task.WaitAsync(cancellationToken);
            throw new IOException("Polar H10 BLE device disconnected.");
        }
        finally
        {
            characteristic.ValueChanged -= Handler;
            device.ConnectionStatusChanged -= ConnectionStatusChanged;
            try
            {
                await characteristic.WriteClientCharacteristicConfigurationDescriptorAsync(
                    GattClientCharacteristicConfigurationDescriptorValue.None);
            }
            catch
            {
                // The reconnect loop handles a device that disappeared before cleanup.
            }
        }
    }

    private static async Task<BluetoothLEDevice?> OpenDeviceAsync(
        HeartRateConfig config,
        CancellationToken cancellationToken)
    {
        if (!string.IsNullOrWhiteSpace(config.DeviceId))
        {
            try
            {
                var known = await BluetoothLEDevice.FromIdAsync(config.DeviceId);
                if (known is not null)
                {
                    return known;
                }
            }
            catch
            {
                // A stale Windows device ID falls back to a new scan.
            }
        }

        var discoveredId = await ScanForPolarDeviceAsync(config, cancellationToken);
        return await BluetoothLEDevice.FromIdAsync(discoveredId);
    }

    private static async Task<string> ScanForPolarDeviceAsync(HeartRateConfig config, CancellationToken cancellationToken)
    {
        var expectedName = string.IsNullOrWhiteSpace(config.DeviceName) ? "Polar H10" : config.DeviceName;
        var timeout = TimeSpan.FromMilliseconds(Math.Max(1000, config.ScanTimeoutMs));
        var watchers = new[]
        {
            DeviceInformation.CreateWatcher(BluetoothLEDevice.GetDeviceSelectorFromPairingState(true)),
            DeviceInformation.CreateWatcher(BluetoothLEDevice.GetDeviceSelectorFromPairingState(false))
        };
        var found = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);

        void OnAdded(DeviceWatcher sender, DeviceInformation info)
        {
            var name = info.Name ?? "";
            if (name.Contains(expectedName, StringComparison.OrdinalIgnoreCase) ||
                name.Contains("Polar H10", StringComparison.OrdinalIgnoreCase))
            {
                found.TrySetResult(info.Id);
            }
        }

        foreach (var watcher in watchers)
        {
            watcher.Added += OnAdded;
            watcher.Start();
        }
        try
        {
            using var timeoutCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            var delay = Task.Delay(timeout, timeoutCts.Token);
            var completed = await Task.WhenAny(found.Task, delay);
            if (completed == found.Task)
            {
                timeoutCts.Cancel();
                return await found.Task;
            }

            throw new TimeoutException("No Polar H10 device was discovered.");
        }
        finally
        {
            foreach (var watcher in watchers)
            {
                watcher.Added -= OnAdded;
                if (watcher.Status is DeviceWatcherStatus.Started or DeviceWatcherStatus.EnumerationCompleted)
                {
                    watcher.Stop();
                }
            }
        }
    }
}
