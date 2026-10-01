namespace SensorBridge.Models;

public sealed record HeartRateFeatures(
    int? HrBpm,
    int? RrIntervalMs,
    double? RmssdMs);
