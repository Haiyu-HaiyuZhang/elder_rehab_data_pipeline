using SensorBridge.Config;
using SensorBridge.Devices;
using SensorBridge.Models;
using SensorBridge.Services;

namespace SensorBridge;

public static class Program
{
    public static async Task<int> Main(string[] args)
    {
        Console.WriteLine("Sensor Bridge 1.0");
        var configPath = GetConfigPath(args);
        var store = new ConfigStore(configPath);
        var config = store.Load();
        ApplyArgs(config, args);

        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, eventArgs) =>
        {
            eventArgs.Cancel = true;
            cts.Cancel();
        };

        var tasks = new List<Task>();
        ImuService? imuService = null;
        HeartRateService? hrService = null;

        if (config.Imu.Enabled)
        {
            var imuDevice = CreateImuDevice(config);
            imuService = new ImuService(config.Imu, imuDevice);
            tasks.Add(Task.Run(() => imuService.RunAsync(cts.Token), cts.Token));
        }

        if (config.HeartRate.Enabled)
        {
            var hrDevice = CreateHeartRateDevice(config);
            hrService = new HeartRateService(config.HeartRate, hrDevice);
            tasks.Add(Task.Run(() => hrService.RunAsync(cts.Token), cts.Token));
        }

        tasks.Add(Task.Run(() => PrintStatusAsync(imuService, hrService, cts.Token), cts.Token));

        try
        {
            await Task.WhenAll(tasks);
            return 0;
        }
        catch (OperationCanceledException)
        {
            return 0;
        }
        finally
        {
            imuService?.Dispose();
            hrService?.Dispose();
        }
    }

    private static string GetConfigPath(string[] args)
    {
        var idx = Array.IndexOf(args, "--config");
        if (idx >= 0 && idx + 1 < args.Length)
        {
            return args[idx + 1];
        }

        return Path.Combine(AppContext.BaseDirectory, "appsettings.json");
    }

    private static void ApplyArgs(BridgeConfig config, string[] args)
    {
        if (args.Contains("--simulate", StringComparer.OrdinalIgnoreCase))
        {
            config.Simulation.Enabled = true;
            config.Imu.Simulate = true;
            config.HeartRate.Simulate = true;
        }
        if (args.Contains("--imu-simulate", StringComparer.OrdinalIgnoreCase))
        {
            config.Imu.Simulate = true;
        }
        if (args.Contains("--hr-simulate", StringComparer.OrdinalIgnoreCase))
        {
            config.HeartRate.Simulate = true;
        }
    }

    private static ISensorDevice<ImuSample> CreateImuDevice(BridgeConfig config)
    {
        if (config.Simulation.Enabled || config.Imu.Simulate)
        {
            return new SimulatedImuDevice(config.Simulation);
        }

        return new WitImuDevice(config.Imu, new WindowsWitBleClient());
    }

    private static ISensorDevice<HeartRateSample> CreateHeartRateDevice(BridgeConfig config)
    {
        if (config.Simulation.Enabled || config.HeartRate.Simulate)
        {
            return new SimulatedHeartRateDevice(config.Simulation);
        }

        return new PolarH10Device(config.HeartRate, new WindowsPolarHeartRateBleClient());
    }

    private static async Task PrintStatusAsync(ImuService? imu, HeartRateService? hr, CancellationToken cancellationToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(2));
        while (await timer.WaitForNextTickAsync(cancellationToken))
        {
            if (imu is not null)
            {
                Console.WriteLine($"[IMU] {imu.Status.State} | {imu.Status.Detail} | packets: {imu.Status.Packets}");
            }
            if (hr is not null)
            {
                Console.WriteLine($"[HR] {hr.Status.State} | {hr.Status.Detail} | packets: {hr.Status.Packets}");
            }
        }
    }
}
