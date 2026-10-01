namespace SensorBridge.Config;

public sealed class BridgeConfig
{
    public ImuConfig Imu { get; set; } = new();
    public HeartRateConfig HeartRate { get; set; } = new();
    public SimulationConfig Simulation { get; set; } = new();
}

public sealed class ImuConfig
{
    public bool Enabled { get; set; } = true;
    public bool Simulate { get; set; }
    public string DeviceName { get; set; } = "";
    public string DeviceId { get; set; } = "";
    public string UdpHost { get; set; } = "127.0.0.1";
    public int UdpPort { get; set; } = 9101;
    public double PublishHz { get; set; } = 10;
    public int StaleTimeoutMs { get; set; } = 1000;
    public int FeatureWindowSeconds { get; set; } = 30;
    public int ScanTimeoutMs { get; set; } = 10000;
}

public sealed class HeartRateConfig
{
    public bool Enabled { get; set; } = true;
    public bool Simulate { get; set; }
    public string DeviceName { get; set; } = "";
    public string DeviceId { get; set; } = "";
    public string UdpHost { get; set; } = "127.0.0.1";
    public int UdpPort { get; set; } = 9102;
    public double PublishHz { get; set; } = 1;
    public int RmssdWindowSeconds { get; set; } = 60;
    public int RmssdMinRrCount { get; set; } = 3;
    public int StaleTimeoutMs { get; set; } = 3000;
    public int ScanTimeoutMs { get; set; } = 10000;
}

public sealed class SimulationConfig
{
    public bool Enabled { get; set; }
    public double ImuSampleHz { get; set; } = 100;
    public double HrSampleHz { get; set; } = 1;
    public int SimulateStaleAfterSeconds { get; set; }
    public int SimulateStaleDurationSeconds { get; set; }
}
