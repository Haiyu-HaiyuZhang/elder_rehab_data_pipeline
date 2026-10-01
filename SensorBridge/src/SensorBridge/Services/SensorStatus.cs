namespace SensorBridge.Services;

public sealed class SensorStatus
{
    private long _packets;

    public string State { get; private set; } = "Disconnected";
    public string Detail { get; private set; } = "";
    public long Packets => Interlocked.Read(ref _packets);

    public void SetState(string state, string detail)
    {
        State = state;
        Detail = detail;
    }

    public void IncrementPackets()
    {
        Interlocked.Increment(ref _packets);
    }
}
