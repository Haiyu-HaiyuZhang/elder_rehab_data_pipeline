using SensorBridge.Config;
using SensorBridge.Devices;
using SensorBridge.Models;
using SensorBridge.Processing;
using SensorBridge.Transport;

namespace SensorBridge.Services;

public sealed class HeartRateService : IDisposable
{
    private readonly HeartRateConfig _config;
    private readonly ISensorDevice<HeartRateSample> _device;
    private readonly HeartRateProcessor _processor;
    private readonly UdpJsonPublisher<HeartRateUdpFrame> _publisher;
    private readonly SessionCounter _session = new("hr");
    private readonly object _gate = new();
    private HeartRateFeatures _latest = new(null, null, null);
    private long? _lastSampleTimestampMs;
    private bool _wasStale = true;

    public HeartRateService(HeartRateConfig config, ISensorDevice<HeartRateSample> device)
    {
        _config = config;
        _device = device;
        _processor = new HeartRateProcessor(TimeSpan.FromSeconds(Math.Max(1, config.RmssdWindowSeconds)), config.RmssdMinRrCount);
        _publisher = new UdpJsonPublisher<HeartRateUdpFrame>(config.UdpHost, config.UdpPort);
        _device.SampleReceived += OnSample;
        _device.StateChanged += OnDeviceStateChanged;
    }

    public SensorStatus Status { get; } = new();

    public async Task RunAsync(CancellationToken cancellationToken)
    {
        var deviceTask = _device.RunAsync(cancellationToken);
        var publisherTask = RunPublisherAsync(cancellationToken);
        await Task.WhenAll(deviceTask, publisherTask);
    }

    private void OnSample(HeartRateSample sample)
    {
        var features = _processor.AddSample(sample);
        Status.SetState("Streaming", $"HR: {features.HrBpm?.ToString() ?? "null"} bpm | RR: {features.RrIntervalMs?.ToString() ?? "null"} ms");
        lock (_gate)
        {
            _latest = features;
            _lastSampleTimestampMs = sample.TimestampMs;
        }
    }

    private void OnDeviceStateChanged(DeviceState state, string detail)
    {
        Status.SetState(state.ToString(), detail);
        if (state != DeviceState.Disconnected)
        {
            return;
        }

        _processor.Reset();
        lock (_gate)
        {
            _latest = new HeartRateFeatures(null, null, null);
            _lastSampleTimestampMs = null;
        }
    }

    private async Task RunPublisherAsync(CancellationToken cancellationToken)
    {
        var period = TimeSpan.FromMilliseconds(1000.0 / Math.Max(0.1, _config.PublishHz));
        using var timer = new PeriodicTimer(period);
        Console.WriteLine($"[HR] UDP -> {_config.UdpHost}:{_config.UdpPort} @ {_config.PublishHz:g} Hz");

        while (await timer.WaitForNextTickAsync(cancellationToken))
        {
            try
            {
                var frame = BuildFrame();
                await _publisher.PublishAsync(frame, cancellationToken);
                Status.IncrementPackets();
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[HR] UDP error: {ex.Message}");
            }
        }
    }

    private HeartRateUdpFrame BuildFrame()
    {
        HeartRateFeatures latest;
        long? lastTimestamp;
        lock (_gate)
        {
            latest = _latest;
            lastTimestamp = _lastSampleTimestampMs;
        }

        var now = Clock.UnixMilliseconds();
        var fresh = lastTimestamp.HasValue && now - lastTimestamp.Value <= _config.StaleTimeoutMs;
        if (!fresh)
        {
            if (!_wasStale)
            {
                Console.WriteLine("[HR] stale");
            }
            _wasStale = true;
            return new HeartRateUdpFrame("hr", _session.SessionId, _session.NextSeq(), now, 0.0, null, null, null);
        }

        if (_wasStale)
        {
            Console.WriteLine("[HR] recovered");
        }
        _wasStale = false;
        var usable = latest.HrBpm is > 0;
        return new HeartRateUdpFrame(
            "hr",
            _session.SessionId,
            _session.NextSeq(),
            now,
            usable ? 1.0 : 0.0,
            usable ? latest.HrBpm : null,
            usable ? latest.RrIntervalMs : null,
            usable ? latest.RmssdMs : null);
    }

    public void Dispose()
    {
        _publisher.Dispose();
    }
}
