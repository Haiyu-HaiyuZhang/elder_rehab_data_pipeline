using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SensorBridge.Transport;

public sealed class UdpJsonPublisher<TFrame> : IDisposable
{
    private readonly UdpClient _udp = new();
    private readonly string _host;
    private readonly int _port;
    private readonly JsonSerializerOptions _jsonOptions = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.Never
    };

    public UdpJsonPublisher(string host, int port)
    {
        _host = host;
        _port = port;
    }

    public async Task PublishAsync(TFrame frame, CancellationToken cancellationToken)
    {
        var json = JsonSerializer.Serialize(frame, _jsonOptions);
        var bytes = Encoding.UTF8.GetBytes(json);
        if (bytes.Length > 1200)
        {
            throw new InvalidOperationException($"UDP frame is too large: {bytes.Length} bytes.");
        }

        cancellationToken.ThrowIfCancellationRequested();
        await _udp.SendAsync(bytes, bytes.Length, _host, _port);
    }

    public void Dispose()
    {
        _udp.Dispose();
    }
}
