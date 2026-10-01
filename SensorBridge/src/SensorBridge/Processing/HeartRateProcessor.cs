using SensorBridge.Models;

namespace SensorBridge.Processing;

public sealed class HeartRateProcessor
{
    private readonly TimeSpan _window;
    private readonly int _minRrCount;
    private readonly object _gate = new();
    private readonly Queue<(long TimestampMs, int RrMs)> _rrWindow = new();
    private HeartRateFeatures _latest = new(null, null, null);

    public HeartRateProcessor(TimeSpan window, int minRrCount)
    {
        _window = window;
        _minRrCount = Math.Max(2, minRrCount);
    }

    public HeartRateFeatures Latest
    {
        get
        {
            lock (_gate)
            {
                return _latest;
            }
        }
    }

    public HeartRateFeatures AddSample(HeartRateSample sample)
    {
        lock (_gate)
        {
            if (sample.SensorContactDetected == false || sample.HrBpm is null or <= 0)
            {
                _rrWindow.Clear();
                _latest = new HeartRateFeatures(null, null, null);
                return _latest;
            }

            var validRr = sample.RrIntervalsMs.Where(rr => rr is >= 250 and <= 2500).ToArray();
            foreach (var rr in validRr)
            {
                _rrWindow.Enqueue((sample.TimestampMs, rr));
            }

            var cutoff = sample.TimestampMs - (long)_window.TotalMilliseconds;
            while (_rrWindow.Count > 0 && _rrWindow.Peek().TimestampMs < cutoff)
            {
                _rrWindow.Dequeue();
            }

            var latestRr = validRr.LastOrDefault();
            _latest = new HeartRateFeatures(
                sample.HrBpm,
                latestRr > 0 ? latestRr : _latest.RrIntervalMs,
                ComputeRmssd());
            return _latest;
        }
    }

    public void Reset()
    {
        lock (_gate)
        {
            _rrWindow.Clear();
            _latest = new HeartRateFeatures(null, null, null);
        }
    }

    private double? ComputeRmssd()
    {
        var rr = _rrWindow.Select(x => x.RrMs).ToArray();
        if (rr.Length < _minRrCount)
        {
            return null;
        }

        var squaredDiffs = new List<double>();
        for (var i = 1; i < rr.Length; i++)
        {
            var diff = rr[i] - rr[i - 1];
            squaredDiffs.Add(diff * diff);
        }

        if (squaredDiffs.Count == 0)
        {
            return null;
        }

        return Math.Round(Math.Sqrt(squaredDiffs.Average()), 1, MidpointRounding.AwayFromZero);
    }
}
