using System.Text.Json.Serialization;

namespace SensorBridge.Models;

public sealed record ImuUdpFrame(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("session_id")] string SessionId,
    [property: JsonPropertyName("seq")] long Seq,
    [property: JsonPropertyName("timestamp_ms")] long TimestampMs,
    [property: JsonPropertyName("quality")] double Quality,
    [property: JsonPropertyName("cadence_hz")] double? CadenceHz,
    [property: JsonPropertyName("step_length_m")] double? StepLengthM,
    [property: JsonPropertyName("step_time_cv")] double? StepTimeCv,
    [property: JsonPropertyName("stride_symmetry")] double? StrideSymmetry,
    [property: JsonPropertyName("trunk_sway_deg")] double? TrunkSwayDeg,
    [property: JsonPropertyName("is_walking")] bool? IsWalking);
