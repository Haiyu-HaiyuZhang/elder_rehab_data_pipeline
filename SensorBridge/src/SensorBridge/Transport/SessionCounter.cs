namespace SensorBridge.Transport;

public sealed class SessionCounter
{
    private long _seq;

    public SessionCounter(string prefix)
    {
        SessionId = $"{prefix}-{Guid.NewGuid():N}"[..(prefix.Length + 1 + 8)];
    }

    public string SessionId { get; }

    public long NextSeq()
    {
        return Interlocked.Increment(ref _seq);
    }
}
