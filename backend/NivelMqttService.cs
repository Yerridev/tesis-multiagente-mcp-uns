using Microsoft.AspNetCore.SignalR;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api;

/// <summary>
/// Suscriptor MQTT (solo lectura) del módulo de nivel MCN-09.
/// Se suscribe al UNS de la tesis (conector edge ML1100) y difunde los datos
/// reales por SignalR ("nivelSenales") cada segundo, sin reconstruir nada en el cliente.
/// </summary>
public sealed class NivelMqttService : BackgroundService
{
    private readonly NivelState _state;
    private readonly PlantState _plant;
    private readonly IHubContext<PlantHub> _hub;
    private readonly IConfiguration _config;
    private readonly ILogger<NivelMqttService> _log;

    public NivelMqttService(NivelState state, PlantState plant, IHubContext<PlantHub> hub, IConfiguration config, ILogger<NivelMqttService> log)
    {
        _state = state;
        _plant = plant;
        _hub = hub;
        _config = config;
        _log = log;
    }

    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var consumo = Task.Run(() => ConsumirMensajes(stop), CancellationToken.None);
        var difusion = Task.Run(() => Difundir(stop), CancellationToken.None);
        await Task.WhenAll(consumo, difusion);
    }

    private async Task ConsumirMensajes(CancellationToken stop)
    {
        var host = _config["Mqtt:Host"] ?? "127.0.0.1";
        var puerto = int.TryParse(_config["Mqtt:Port"], out var p) ? p : 1883;
        var topico = _config["Mqtt:NivelTopico"] ?? (NivelState.Base + "/#");

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
                    _state.Aplicar(tema, cuerpo);
                    return Task.CompletedTask;
                };

                var reconectado = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                client.DisconnectedAsync += _ =>
                {
                    _state.MqttConectado = false;
                    reconectado.TrySetResult();
                    return Task.CompletedTask;
                };

                var opciones = new MqttClientOptionsBuilder()
                    .WithTcpServer(host, puerto)
                    .WithClientId($"mcp-industrial-nivel-{Environment.MachineName}")
                    .WithCleanSession()
                    .Build();

                await client.ConnectAsync(opciones, stop);
                _state.MqttConectado = true;
                _log.LogInformation("MQTT conectado en {Host}:{Puerto}; suscrito a {Topico}", host, puerto, topico);

                await client.SubscribeAsync(
                    new MqttClientSubscribeOptionsBuilder()
                        .WithTopicFilter(f => f.WithTopic(topico).WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
                        .Build(),
                    stop);

                await Task.WhenAny(reconectado.Task, Task.Delay(Timeout.Infinite, stop));
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _state.MqttConectado = false;
                _log.LogWarning("MQTT no disponible ({Mensaje}); reintento en 3 s", ex.Message);
                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(3), stop);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
            }
        }
    }

    private async Task Difundir(CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            try
            {
                _plant.AplicarNivel(_state);
                await _hub.Clients.All.SendAsync("nivelSenales", _state.Snapshot(), stop);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _log.LogDebug(ex, "Difusión de nivel interrumpida");
            }

            try
            {
                await Task.Delay(1000, stop);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }
    }
}
