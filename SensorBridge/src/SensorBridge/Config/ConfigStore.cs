using System.Text.Json;
using System.Text.Json.Serialization;

namespace SensorBridge.Config;

public sealed class ConfigStore
{
    private readonly string _path;
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.Never
    };

    public ConfigStore(string path)
    {
        _path = path;
    }

    public BridgeConfig Load()
    {
        if (!File.Exists(_path))
        {
            var defaults = new BridgeConfig();
            Save(defaults);
            return defaults;
        }

        var json = File.ReadAllText(_path);
        return JsonSerializer.Deserialize<BridgeConfig>(json, _jsonOptions) ?? new BridgeConfig();
    }

    public void Save(BridgeConfig config)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(_path));
        if (!string.IsNullOrEmpty(dir))
        {
            Directory.CreateDirectory(dir);
        }

        File.WriteAllText(_path, JsonSerializer.Serialize(config, _jsonOptions));
    }

    public void SaveKnownImu(string deviceId, string deviceName)
    {
        var config = Load();
        config.Imu.DeviceId = deviceId;
        config.Imu.DeviceName = deviceName;
        Save(config);
    }

    public void SaveKnownHeartRate(string deviceId, string deviceName)
    {
        var config = Load();
        config.HeartRate.DeviceId = deviceId;
        config.HeartRate.DeviceName = deviceName;
        Save(config);
    }
}
