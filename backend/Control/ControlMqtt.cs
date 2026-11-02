using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api.Control;

/// <summary>Transporte de órdenes de control (publicación del tópico cmd).</summary>
public interface IComandoTransporte
{
    Task<bool> Publicar(string topico, string cuerpo, CancellationToken ct);
}

/// <summary>Publica por MQTT (broker local). Si el broker está caído devuelve false (la orden queda en ERROR).</summary>
public sealed class MqttComandoTransporte : IComandoTransporte
{
    private readonly IConfiguration _config;
    private readonly ILogger<MqttComandoTransporte> _log;

    public MqttComandoTransporte(IConfiguration config, ILogger<MqttComandoTransporte> log)
    {
        _config = config;
        _log = log;
    }

    public async Task<bool> Publicar(string topico, string cuerpo, CancellationToken ct)
    {
        var host = _config["Mqtt:Host"] ?? "127.0.0.1";
        var puerto = int.TryParse(_config["Mqtt:Port"], out var p) ? p : 1883;
        try
        {
            var factory = new MqttFactory();
            using var client = factory.CreateMqttClient();
            var opciones = new MqttClientOptionsBuilder()
                .WithTcpServer(host, puerto)
                .WithClientId($"mcp-cmd-{Guid.NewGuid():N}")
                .WithCleanSession()
                .Build();
            await client.ConnectAsync(opciones, ct);
            var msg = new MqttApplicationMessageBuilder()
                .WithTopic(topico)
                .WithPayload(cuerpo)
                .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce)
                .Build();
            await client.PublishAsync(msg, ct);
            await client.DisconnectAsync();
            return true;
        }
        catch (OperationCanceledException)
        {
            return false;
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "No se pudo publicar {Topico}", topico);
            return false;
        }
    }
}

/// <summary>Transporte en memoria (pruebas automatizadas y entornos sin broker).</summary>
public sealed class EnMemoriaTransporte : IComandoTransporte
{
    private readonly List<(string Topico, string Cuerpo, DateTimeOffset Ts)> _publicados = new();
    private readonly object _sync = new();

    public IReadOnlyList<(string Topico, string Cuerpo, DateTimeOffset Ts)> Publicados
    {
        get { lock (_sync) return _publicados.ToArray(); }
    }

    public Task<bool> Publicar(string topico, string cuerpo, CancellationToken ct)
    {
        lock (_sync) _publicados.Add((topico, cuerpo, DateTimeOffset.Now));
        return Task.FromResult(true);
    }
}

/// <summary>
/// Suscriptor MQTT de {TopicoBase}/ack y {TopicoBase}/state (salida del conector Python).
/// También barre los timeouts de las órdenes cada segundo.
/// </summary>
public sealed class ControlMqttService : BackgroundService
{
    private readonly ControlService _control;
    private readonly ControlOpciones _op;
    private readonly IConfiguration _config;
    private readonly ILogger<ControlMqttService> _log;

    public ControlMqttService(ControlService control, ControlOpciones op, IConfiguration config, ILogger<ControlMqttService> log)
    {
        _control = control;
        _op = op;
        _config = config;
        _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var consumir = Task.Run(() => Consumir(stop), CancellationToken.None);
        var barrer = Task.Run(() => Barrer(stop), CancellationToken.None);
        await Task.WhenAll(consumir, barrer);
    }

    private async Task Barrer(CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            try
            {
                _control.VerificarTimeouts();
                await Task.Delay(1000, stop);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex) { _log.LogDebug(ex, "Barrido de timeouts interrumpido"); }
        }
    }

    private async Task Consumir(CancellationToken stop)
    {
        var host = _config["Mqtt:Host"] ?? "127.0.0.1";
        var puerto = int.TryParse(_config["Mqtt:Port"], out var p) ? p : 1883;
        var ack = $"{_op.TopicoBase}/ack";
        var state = $"{_op.TopicoBase}/state";
        var factory = new MqttFactory();

        while (!stop.IsCancellationRequested)
        {
            try
            {
                using var client = factory.CreateMqttClient();

                client.ApplicationMessageReceivedAsync += e =>
                {
                    var msg = e.ApplicationMessage;
                    var tema = msg.Topic;
                    var cuerpo = msg.PayloadSegment.Count == 0
                        ? string.Empty
                        : System.Text.Encoding.UTF8.GetString(msg.PayloadSegment.Array!, msg.PayloadSegment.Offset, msg.PayloadSegment.Count);
                    if (tema.EndsWith("/ack", StringComparison.OrdinalIgnoreCase)) _control.ProcesarAck(cuerpo);
                    else if (tema.EndsWith("/state", StringComparison.OrdinalIgnoreCase)) _control.ProcesarState(cuerpo);
                    return Task.CompletedTask;
                };

                var reconectado = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                client.DisconnectedAsync += _ => { reconectado.TrySetResult(); return Task.CompletedTask; };

                var opciones = new MqttClientOptionsBuilder()
                    .WithTcpServer(host, puerto)
                    .WithClientId($"mcp-control-sub-{Environment.MachineName}")
                    .WithCleanSession()
                    .Build();

                await client.ConnectAsync(opciones, stop);
                _log.LogInformation("Control MQTT suscrito a {Ack} y {State}", ack, state);

                await client.SubscribeAsync(
                    new MqttClientSubscribeOptionsBuilder()
                        .WithTopicFilter(f => f.WithTopic(ack).WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
                        .WithTopicFilter(f => f.WithTopic(state).WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
                        .Build(),
                    stop);

                await Task.WhenAny(reconectado.Task, Task.Delay(Timeout.Infinite, stop));
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                _log.LogWarning("Control MQTT no disponible ({Mensaje}); reintento en 3 s", ex.Message);
                try { await Task.Delay(TimeSpan.FromSeconds(3), stop); }
                catch (OperationCanceledException) { break; }
            }
        }
    }
}
