using System.Buffers.Binary;
using SensorBridge.Models;

namespace SensorBridge.Processing;

/// <summary>
/// Parses the BWT901 BLE 5.0 notification stream documented by WIT's official
/// Windows sample. A sample is emitted only after one complete 20-byte frame
/// has arrived, so consumers never observe a mixture of two device frames.
/// </summary>
public sealed class WitBwt901PacketParser
{
    private const int FrameLength = 20;
    private readonly object _gate = new();
    private readonly List<byte> _buffer = new();

    public IReadOnlyList<ImuSample> Append(ReadOnlySpan<byte> bytes, long timestampMs)
    {
        lock (_gate)
        {
            for (var i = 0; i < bytes.Length; i++)
            {
                _buffer.Add(bytes[i]);
            }

            var samples = new List<ImuSample>();
            while (TryTakeFrame(out var frame))
            {
                samples.Add(ParseFrame(frame, timestampMs));
            }
            return samples;
        }
    }

    private bool TryTakeFrame(out byte[] frame)
    {
        frame = Array.Empty<byte>();
        while (_buffer.Count >= 2 && (_buffer[0] != 0x55 || _buffer[1] != 0x61))
        {
            _buffer.RemoveAt(0);
        }

        if (_buffer.Count < FrameLength)
        {
            return false;
        }

        frame = _buffer.GetRange(0, FrameLength).ToArray();
        _buffer.RemoveRange(0, FrameLength);
        return true;
    }

    private static ImuSample ParseFrame(ReadOnlySpan<byte> frame, long timestampMs)
    {
        if (frame.Length != FrameLength || frame[0] != 0x55 || frame[1] != 0x61)
        {
            throw new ArgumentException("Invalid BWT901 BLE frame.", nameof(frame));
        }

        Span<short> raw = stackalloc short[9];
        for (var i = 0; i < raw.Length; i++)
        {
            raw[i] = BinaryPrimitives.ReadInt16LittleEndian(frame.Slice(2 + i * 2, 2));
        }

        static double Scale(short value, double range) => value / 32768.0 * range;

        return new ImuSample(
            timestampMs,
            Scale(raw[0], 16.0),
            Scale(raw[1], 16.0),
            Scale(raw[2], 16.0),
            Scale(raw[3], 2000.0),
            Scale(raw[4], 2000.0),
            Scale(raw[5], 2000.0),
            Scale(raw[6], 180.0),
            Scale(raw[7], 180.0),
            Scale(raw[8], 180.0));
    }
}
