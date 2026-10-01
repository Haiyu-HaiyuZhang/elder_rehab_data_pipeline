namespace SensorBridge.Processing;

public static class Clock
{
    public static long UnixMilliseconds()
    {
        return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    }
}
