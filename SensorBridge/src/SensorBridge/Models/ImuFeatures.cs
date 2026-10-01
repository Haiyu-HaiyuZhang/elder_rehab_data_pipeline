namespace SensorBridge.Models;

public sealed record ImuFeatures(
    double? CadenceHz,
    double? StepLengthM,
    double? StepTimeCv,
    double? StrideSymmetry,
    double? TrunkSwayDeg,
    bool? IsWalking);
