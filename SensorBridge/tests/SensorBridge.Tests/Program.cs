using System.Buffers.Binary;
using System.Text.Json;
using SensorBridge.Models;
using SensorBridge.Processing;
using SensorBridge.Transport;

var tests = new (string Name, Action Body)[]
{
    ("JSON nulls are preserved", JsonNullsArePreserved),
    ("Polar parser handles 8-bit HR and multiple RR intervals", PolarParserHandlesMultipleRr),
    ("Polar parser handles 16-bit HR", PolarParserHandles16BitHr),
    ("Polar contact loss produces unavailable features", PolarContactLossProducesUnavailableFeatures),
    ("RMSSD uses rolling RR intervals", RmssdUsesRollingWindow),
    ("WIT parser waits for an atomic frame and applies official scaling", WitParserIsAtomicAndScaled),
    ("IMU processor preserves the established 30-second window metrics", ImuProcessorPreservesWindowMetrics),
    ("Session counters are independent and monotonic", SessionCountersAreIndependent),
    ("IMU stale frame shape keeps sensor fields null", ImuStaleFrameShape),
};

var failures = 0;
foreach (var test in tests)
{
    try
    {
        test.Body();
        Console.WriteLine($"PASS {test.Name}");
    }
    catch (Exception ex)
    {
        failures++;
        Console.WriteLine($"FAIL {test.Name}: {ex.Message}");
    }
}

return failures == 0 ? 0 : 1;

static void JsonNullsArePreserved()
{
    var frame = new ImuUdpFrame("imu", "imu-test", 1, 1790670000000, 0.0, null, null, null, null, null, null);
    var json = JsonSerializer.Serialize(frame);
    AssertContains(json, "\"cadence_hz\":null");
    AssertContains(json, "\"step_time_cv\":null");
    AssertDoesNotContain(json, "\"cadence_hz\":0");
}

static void PolarParserHandlesMultipleRr()
{
    var payload = new byte[]
    {
        0x10,
        118,
        0x08, 0x02,
        0x10, 0x02
    };
    var sample = HeartRateMeasurementParser.Parse(payload, 10);
    AssertEqual(118, sample.HrBpm.GetValueOrDefault(), "hr");
    AssertEqual(2, sample.RrIntervalsMs.Count, "rr count");
    AssertEqual(508, sample.RrIntervalsMs[0], "rr 1");
    AssertEqual(516, sample.RrIntervalsMs[1], "rr 2");
}

static void PolarParserHandles16BitHr()
{
    var payload = new byte[] { 0x01, 0x2C, 0x01 };
    var sample = HeartRateMeasurementParser.Parse(payload, 10);
    AssertEqual(300, sample.HrBpm.GetValueOrDefault(), "16-bit hr");
}

static void PolarContactLossProducesUnavailableFeatures()
{
    var sample = HeartRateMeasurementParser.Parse(new byte[] { 0x04, 80 }, 10);
    AssertEqual(false, sample.SensorContactDetected.GetValueOrDefault(true), "contact detected");
    var features = new HeartRateProcessor(TimeSpan.FromSeconds(60), 3).AddSample(sample);
    AssertNull(features.HrBpm, "hr while not worn");
    AssertNull(features.RrIntervalMs, "rr while not worn");
    AssertNull(features.RmssdMs, "rmssd while not worn");
}

static void RmssdUsesRollingWindow()
{
    var processor = new HeartRateProcessor(TimeSpan.FromSeconds(60), 3);
    var first = processor.AddSample(new HeartRateSample(1000, 80, new[] { 800 }));
    AssertNull(first.RmssdMs, "rmssd before minimum rr count");
    processor.AddSample(new HeartRateSample(2000, 80, new[] { 810 }));
    var third = processor.AddSample(new HeartRateSample(3000, 80, new[] { 790 }));
    AssertEqual(15.8, third.RmssdMs.GetValueOrDefault(), "rmssd");
    var invalidRr = processor.AddSample(new HeartRateSample(4000, 80, new[] { 10, 4000 }));
    AssertEqual(790, invalidRr.RrIntervalMs.GetValueOrDefault(), "latest valid rr");
    AssertEqual(15.8, invalidRr.RmssdMs.GetValueOrDefault(), "invalid rr excluded from rmssd");
}

static void WitParserIsAtomicAndScaled()
{
    var frame = new byte[20];
    frame[0] = 0x55;
    frame[1] = 0x61;
    var raw = new short[] { 16384, -16384, 2048, 16384, -16384, 8192, 16384, -16384, 4096 };
    for (var i = 0; i < raw.Length; i++)
    {
        BinaryPrimitives.WriteInt16LittleEndian(frame.AsSpan(2 + i * 2, 2), raw[i]);
    }

    var parser = new WitBwt901PacketParser();
    AssertEqual(0, parser.Append(frame.AsSpan(0, 7), 100).Count, "partial frame count");
    var samples = parser.Append(frame.AsSpan(7), 101);
    AssertEqual(1, samples.Count, "complete frame count");
    AssertEqual(8.0, samples[0].AccX, "acc scaling");
    AssertEqual(-8.0, samples[0].AccY, "negative acc scaling");
    AssertEqual(1000.0, samples[0].GyroX, "gyro scaling");
    AssertEqual(-90.0, samples[0].AngleY, "angle scaling");
    AssertEqual(101L, samples[0].TimestampMs, "atomic frame timestamp");
}

static void ImuProcessorPreservesWindowMetrics()
{
    var processor = new ImuFeatureProcessor(TimeSpan.FromSeconds(30));
    ImuFeatures? features = null;
    for (var i = 0; i <= 3000; i++)
    {
        var t = i / 100.0;
        var gait = Math.Max(0, Math.Sin(2 * Math.PI * 1.7 * t));
        features = processor.AddSample(new ImuSample(
            i * 10L,
            0.04 * Math.Sin(2 * Math.PI * 1.7 * t),
            0.02 * Math.Cos(2 * Math.PI * 1.7 * t),
            1.0 + 0.22 * gait,
            0, 0, 0, 0, 0, 0));
    }

    AssertNear(1.70, features!.CadenceHz.GetValueOrDefault(), 0.02, "cadence");
    AssertNear(1.23, features.StepLengthM.GetValueOrDefault(), 0.02, "step length");
    AssertNear(0.0065, features.StepTimeCv.GetValueOrDefault(), 0.003, "step-time CV");
    AssertNull(features.StrideSymmetry, "unsupported stride symmetry");
    AssertNull(features.TrunkSwayDeg, "unsupported trunk sway");
    AssertNull(features.IsWalking, "unsupported walking flag");
}

static void SessionCountersAreIndependent()
{
    var imu = new SessionCounter("imu");
    var hr = new SessionCounter("hr");
    AssertEqual(1L, imu.NextSeq(), "imu seq 1");
    AssertEqual(2L, imu.NextSeq(), "imu seq 2");
    AssertEqual(1L, hr.NextSeq(), "hr seq 1");
    if (!imu.SessionId.StartsWith("imu-") || !hr.SessionId.StartsWith("hr-") || imu.SessionId == hr.SessionId)
    {
        throw new InvalidOperationException("session ids are not independent");
    }
}

static void ImuStaleFrameShape()
{
    var frame = new ImuUdpFrame("imu", "imu-test", 42, 1790670000000, 0.0, null, null, null, null, null, null);
    AssertEqual(0.0, frame.Quality, "quality");
    AssertNull(frame.CadenceHz, "cadence");
    AssertNull(frame.StepLengthM, "step length");
    AssertNull(frame.StepTimeCv, "step cv");
    AssertNull(frame.IsWalking, "is walking");
}

static void AssertEqual<T>(T expected, T actual, string name)
{
    if (!EqualityComparer<T>.Default.Equals(expected, actual))
    {
        throw new InvalidOperationException($"{name}: expected {expected}, got {actual}");
    }
}

static void AssertNull<T>(T? actual, string name)
{
    if (actual is not null)
    {
        throw new InvalidOperationException($"{name}: expected null, got {actual}");
    }
}

static void AssertNear(double expected, double actual, double tolerance, string name)
{
    if (Math.Abs(expected - actual) > tolerance)
    {
        throw new InvalidOperationException($"{name}: expected {expected} +/- {tolerance}, got {actual}");
    }
}

static void AssertContains(string text, string value)
{
    if (!text.Contains(value, StringComparison.Ordinal))
    {
        throw new InvalidOperationException($"expected JSON to contain {value}: {text}");
    }
}

static void AssertDoesNotContain(string text, string value)
{
    if (text.Contains(value, StringComparison.Ordinal))
    {
        throw new InvalidOperationException($"expected JSON not to contain {value}: {text}");
    }
}
