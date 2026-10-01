using SensorBridge.Models;

namespace SensorBridge.Processing;

public static class HeartRateMeasurementParser
{
    public static HeartRateSample Parse(byte[] payload, long timestampMs)
    {
        if (payload.Length < 2)
        {
            throw new ArgumentException("Heart Rate Measurement payload is too short.", nameof(payload));
        }

        var index = 0;
        var flags = payload[index++];
        var is16BitHr = (flags & 0x01) != 0;
        var sensorContactSupported = (flags & 0x04) != 0;
        var sensorContactDetected = (flags & 0x02) != 0;
        var hasEnergyExpended = (flags & 0x08) != 0;
        var hasRr = (flags & 0x10) != 0;

        int hr;
        if (is16BitHr)
        {
            EnsureLength(payload, index, 2);
            hr = payload[index] | (payload[index + 1] << 8);
            index += 2;
        }
        else
        {
            hr = payload[index++];
        }

        if (hasEnergyExpended)
        {
            EnsureLength(payload, index, 2);
            index += 2;
        }

        var rr = new List<int>();
        if (hasRr)
        {
            while (index + 1 < payload.Length)
            {
                var raw = payload[index] | (payload[index + 1] << 8);
                rr.Add((int)Math.Round(raw * 1000.0 / 1024.0, MidpointRounding.AwayFromZero));
                index += 2;
            }
        }

        return new HeartRateSample(
            timestampMs,
            hr,
            rr,
            sensorContactSupported ? sensorContactDetected : null);
    }

    private static void EnsureLength(byte[] payload, int index, int count)
    {
        if (payload.Length < index + count)
        {
            throw new ArgumentException("Heart Rate Measurement payload is truncated.", nameof(payload));
        }
    }
}
