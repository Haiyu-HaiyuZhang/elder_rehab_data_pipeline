namespace SensorBridge.Models;

public sealed record HeartRateSample(
    long TimestampMs,
    int? HrBpm,
    IReadOnlyList<int> RrIntervalsMs,
    bool? SensorContactDetected = null);
