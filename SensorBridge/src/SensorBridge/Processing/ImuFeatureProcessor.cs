using SensorBridge.Models;

namespace SensorBridge.Processing;

/// <summary>
/// Streaming adapter for the existing offline gait algorithm. It keeps a
/// rolling window but preserves the established magnitude, Butterworth,
/// peak-threshold, prominence, distance, and ISI mathematics.
/// </summary>
public sealed class ImuFeatureProcessor
{
    private readonly TimeSpan _window;
    private readonly object _gate = new();
    private readonly Queue<ImuSample> _samples = new();
    private ImuFeatures? _latest;
    private long? _lastComputedTimestampMs;

    public ImuFeatureProcessor(TimeSpan window)
    {
        _window = window;
    }

    public ImuFeatures? Latest
    {
        get
        {
            lock (_gate)
            {
                return _latest;
            }
        }
    }

    public ImuFeatures AddSample(ImuSample sample)
    {
        lock (_gate)
        {
            _samples.Enqueue(sample);
            var cutoff = sample.TimestampMs - (long)_window.TotalMilliseconds;
            while (_samples.Count > 0 && _samples.Peek().TimestampMs < cutoff)
            {
                _samples.Dequeue();
            }

            var snapshot = _samples.ToArray();
            var coveredMs = snapshot.Length < 2 ? 0 : snapshot[^1].TimestampMs - snapshot[0].TimestampMs;
            if (coveredMs < _window.TotalMilliseconds * 0.95)
            {
                _latest = Empty();
                return _latest;
            }

            // Raw BLE acquisition can be 100/200 Hz, while feature publication
            // is 10 Hz. Recomputing an entire 30 s window faster than 10 Hz adds
            // CPU load without changing any externally observable frame.
            if (!_lastComputedTimestampMs.HasValue ||
                sample.TimestampMs - _lastComputedTimestampMs.Value >= 100)
            {
                _latest = Compute(snapshot);
                _lastComputedTimestampMs = sample.TimestampMs;
            }
            return _latest ?? Empty();
        }
    }

    public void Reset()
    {
        lock (_gate)
        {
            _samples.Clear();
            _latest = null;
            _lastComputedTimestampMs = null;
        }
    }

    internal static ImuFeatures Compute(IReadOnlyList<ImuSample> samples)
    {
        if (samples.Count < 20)
        {
            return Empty();
        }

        var finite = samples.Where(sample =>
            double.IsFinite(sample.AccX) && double.IsFinite(sample.AccY) && double.IsFinite(sample.AccZ)).ToArray();
        if (finite.Length < 20)
        {
            return Empty();
        }

        var sampleRate = EstimateSampleRate(finite);
        var magnitudes = finite
            .Select(sample => Math.Sqrt(
                sample.AccX * sample.AccX + sample.AccY * sample.AccY + sample.AccZ * sample.AccZ))
            .ToArray();
        var meanMagnitude = magnitudes.Average();
        var centeredAbsolute = magnitudes.Select(value => Math.Abs(value - meanMagnitude)).ToArray();
        var filtered = LowPassZeroPhase(centeredAbsolute, sampleRate);

        var peakThreshold = StandardDeviation(filtered) * 2.5;
        if (!double.IsFinite(peakThreshold) || peakThreshold <= 0)
        {
            return Empty();
        }

        var minDistance = Math.Max(1, (int)(0.4 * sampleRate));
        var peaks = FindPeaks(filtered, peakThreshold, minDistance, peakThreshold * 0.5);
        if (peaks.Count < 2)
        {
            return Empty();
        }

        var intervals = new List<double>();
        for (var i = 1; i < peaks.Count; i++)
        {
            // The existing algorithm derives time from peak index / sample rate.
            var seconds = (peaks[i] - peaks[i - 1]) / sampleRate;
            if (seconds is > 0.3 and < 2.0)
            {
                intervals.Add(seconds);
            }
        }

        if (intervals.Count == 0)
        {
            return Empty();
        }

        var meanInterval = intervals.Average();
        var intervalStd = StandardDeviation(intervals);
        var cadenceHz = 1.0 / meanInterval;
        var stepTimeCv = intervalStd / meanInterval;
        var stepLengthM = EstimateStepLength(finite);

        return new ImuFeatures(
            CadenceHz: Round(cadenceHz, 2),
            StepLengthM: Round(stepLengthM, 2),
            StepTimeCv: Round(stepTimeCv, 4),
            StrideSymmetry: null,
            TrunkSwayDeg: null,
            IsWalking: null);
    }

    private static ImuFeatures Empty() => new(null, null, null, null, null, null);

    private static double EstimateSampleRate(IReadOnlyList<ImuSample> samples)
    {
        var deltas = new List<long>(samples.Count - 1);
        for (var i = 1; i < samples.Count; i++)
        {
            var delta = samples[i].TimestampMs - samples[i - 1].TimestampMs;
            if (delta > 0)
            {
                deltas.Add(delta);
            }
        }

        if (deltas.Count == 0)
        {
            return 100.0;
        }

        deltas.Sort();
        var medianMs = deltas[deltas.Count / 2];
        return Math.Clamp(1000.0 / medianMs, 1.0, 1000.0);
    }

    private static double[] LowPassZeroPhase(double[] input, double sampleRate)
    {
        var nyquist = sampleRate / 2.0;
        var cutoff = Math.Min(4.0, nyquist * 0.8);
        if (cutoff < 1.0)
        {
            cutoff = 1.0;
        }
        if (cutoff >= nyquist || input.Length < 10)
        {
            return input;
        }

        // Second-order Butterworth coefficients after a bilinear transform,
        // equivalent to scipy.signal.butter(2, cutoff / nyquist, "low").
        var k = Math.Tan(Math.PI * cutoff / sampleRate);
        var norm = 1.0 / (1.0 + Math.Sqrt(2.0) * k + k * k);
        var b0 = k * k * norm;
        var b1 = 2.0 * b0;
        var b2 = b0;
        var a1 = 2.0 * (k * k - 1.0) * norm;
        var a2 = (1.0 - Math.Sqrt(2.0) * k + k * k) * norm;

        var forward = FilterWithSteadyState(input, b0, b1, b2, a1, a2);
        Array.Reverse(forward);
        var backward = FilterWithSteadyState(forward, b0, b1, b2, a1, a2);
        Array.Reverse(backward);
        return backward;
    }

    private static double[] FilterWithSteadyState(
        IReadOnlyList<double> input,
        double b0,
        double b1,
        double b2,
        double a1,
        double a2)
    {
        var output = new double[input.Count];
        var x1 = input[0];
        var x2 = input[0];
        var y1 = input[0];
        var y2 = input[0];
        for (var i = 0; i < input.Count; i++)
        {
            var x0 = input[i];
            var y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
            output[i] = y0;
            x2 = x1;
            x1 = x0;
            y2 = y1;
            y1 = y0;
        }
        return output;
    }

    private static List<int> FindPeaks(
        IReadOnlyList<double> values,
        double minimumHeight,
        int minimumDistance,
        double minimumProminence)
    {
        var candidates = new List<int>();
        for (var i = 1; i < values.Count - 1; i++)
        {
            if (values[i] >= minimumHeight && values[i] > values[i - 1] && values[i] >= values[i + 1] &&
                Prominence(values, i) >= minimumProminence)
            {
                candidates.Add(i);
            }
        }

        // scipy.signal.find_peaks resolves the distance constraint by retaining
        // the taller candidate first.
        var selected = new List<int>();
        foreach (var candidate in candidates.OrderByDescending(index => values[index]))
        {
            if (selected.All(index => Math.Abs(index - candidate) >= minimumDistance))
            {
                selected.Add(candidate);
            }
        }
        selected.Sort();
        return selected;
    }

    private static double Prominence(IReadOnlyList<double> values, int peak)
    {
        var peakValue = values[peak];
        var leftMinimum = peakValue;
        for (var i = peak - 1; i >= 0; i--)
        {
            if (values[i] > peakValue)
            {
                break;
            }
            leftMinimum = Math.Min(leftMinimum, values[i]);
        }

        var rightMinimum = peakValue;
        for (var i = peak + 1; i < values.Count; i++)
        {
            if (values[i] > peakValue)
            {
                break;
            }
            rightMinimum = Math.Min(rightMinimum, values[i]);
        }

        return peakValue - Math.Max(leftMinimum, rightMinimum);
    }

    private static double EstimateStepLength(IEnumerable<ImuSample> samples)
    {
        var squaredDynamicMagnitude = samples.Select(sample =>
        {
            var z = sample.AccZ - 1.0;
            var dynamicMagnitude = Math.Sqrt(
                sample.AccX * sample.AccX + sample.AccY * sample.AccY + z * z);
            return dynamicMagnitude * dynamicMagnitude;
        });
        var intensity = Math.Sqrt(squaredDynamicMagnitude.Average());
        return 1.0 + intensity / 0.2 * 0.4;
    }

    private static double StandardDeviation(IEnumerable<double> values)
    {
        var array = values.ToArray();
        if (array.Length == 0)
        {
            return 0;
        }

        var mean = array.Average();
        return Math.Sqrt(array.Select(value => (value - mean) * (value - mean)).Average());
    }

    private static double Round(double value, int digits) =>
        Math.Round(value, digits, MidpointRounding.ToEven);
}
