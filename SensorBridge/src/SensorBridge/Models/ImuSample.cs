namespace SensorBridge.Models;

public sealed record ImuSample(
    long TimestampMs,
    double AccX,
    double AccY,
    double AccZ,
    double GyroX,
    double GyroY,
    double GyroZ,
    double? AngleX,
    double? AngleY,
    double? AngleZ);
