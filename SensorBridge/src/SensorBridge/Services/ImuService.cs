using SensorBridge.Config;
using SensorBridge.Devices;
using SensorBridge.Models;
using SensorBridge.Processing;
using SensorBridge.Transport;

namespace SensorBridge.Services;

public sealed class ImuService : IDisposable
{
    private readonly ImuConfig _config;
    private readonly ISensorDevice<ImuSample> _device;
    private readonly ImuFeatureProcessor _processor;
    private readonly UdpJsonPublisher<ImuUdpFrame> _publisher;
    private readonly SessionCounter _session = new("imu");
    private readonly object _gate = new();
    private ImuFeatures? _latest;
    private long? _lastSampleTimestampMs;
    private bool _wasStale = true;

    public ImuService(ImuConfig config, ISensorDevice<ImuSample> device)
    {
        _config = config;
        _device = device;
        _processor = new ImuFeatureProcessor(TimeSpan.FromSeconds(Math.Max(1, config.FeatureWindowSeconds)));
        _publisher = new UdpJsonPublisher<ImuUdpFrame>(config.UdpHost, config.UdpPort);
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

    private void OnSample(ImuSample sample)
    {
        bool resetForGap;
        lock (_gate)
        {
            resetForGap = _lastSampleTimestampMs.HasValue &&
                sample.TimestampMs - _lastSampleTimestampMs.Value > _config.StaleTimeoutMs;
        }
        if (resetForGap)
        {
            _processor.Reset();
        }

        var features = _processor.AddSample(sample);
        Status.SetState("Streaming", "IMU samples received");
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
            _latest = null;
            _lastSampleTimestampMs = null;
        }
    }

    private async Task RunPublisherAsync(CancellationToken cancellationToken)
    {
        var period = TimeSpan.FromMilliseconds(1000.0 / Math.Max(0.1, _config.PublishHz));
        using var timer = new PeriodicTimer(period);
        Console.WriteLine($"[IMU] UDP -> {_config.UdpHost}:{_config.UdpPort} @ {_config.PublishHz:g} Hz");

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
                Console.WriteLine($"[IMU] UDP error: {ex.Message}");
            }
        }
    }

    private ImuUdpFrame BuildFrame()
    {
        ImuFeatures? latest;
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
                Console.WriteLine("[IMU] stale");
            }
            _wasStale = true;
            return new ImuUdpFrame("imu", _session.SessionId, _session.NextSeq(), now, 0.0, null, null, null, null, null, null);
        }

        if (_wasStale)
        {
            Console.WriteLine("[IMU] recovered");
        }
        _wasStale = false;
        var usable = latest is not null && latest.CadenceHz.HasValue;
        return new ImuUdpFrame(
            "imu",
            _session.SessionId,
            _session.NextSeq(),
            now,
            usable ? 1.0 : 0.0,
            usable ? latest!.CadenceHz : null,
            usable ? latest!.StepLengthM : null,
            usable ? latest!.StepTimeCv : null,
            usable ? latest!.StrideSymmetry : null,
            usable ? latest!.TrunkSwayDeg : null,
            usable ? latest!.IsWalking : null);
    }

    public void Dispose()
    {
        _publisher.Dispose();
    }
}
