using System.Text.Json.Serialization;

namespace SensorBridge.Models;

public sealed record HeartRateUdpFrame(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("session_id")] string SessionId,
    [property: JsonPropertyName("seq")] long Seq,
    [property: JsonPropertyName("timestamp_ms")] long TimestampMs,
    [property: JsonPropertyName("quality")] double Quality,
    [property: JsonPropertyName("hr_bpm")] int? HrBpm,
    [property: JsonPropertyName("rr_interval_ms")] int? RrIntervalMs,
    [property: JsonPropertyName("rmssd_ms")] double? RmssdMs);
