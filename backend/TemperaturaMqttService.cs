using Microsoft.AspNetCore.SignalR;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api;

/// <summary>Puente de solo lectura UNS/MQTT -> REST/SignalR para MCT-09.</summary>
public sealed class TemperaturaMqttService : BackgroundService
{
    private readonly TemperaturaState _state;
    private readonly PlantState _plant;
    private readonly IHubContext<PlantHub> _hub;
    private readonly IConfiguration _config;
    private readonly ILogger<TemperaturaMqttService> _log;
    public TemperaturaMqttService(TemperaturaState state, PlantState plant, IHubContext<PlantHub> hub,
        IConfiguration config, ILogger<TemperaturaMqttService> log)
        => (_state, _plant, _hub, _config, _log) = (state, plant, hub, config, log);
    protected override async Task ExecuteAsync(CancellationToken stop) => await Task.WhenAll(Consumir(stop), Difundir(stop));

    private async Task Consumir(CancellationToken stop)
    {
        var host = _config["Mqtt:Host"] ?? "127.0.0.1";
        var port = int.TryParse(_config["Mqtt:Port"], out var p) ? p : 1883;
        var topic = _config["Mqtt:TemperaturaTopico"] ?? TemperaturaState.Base + "/#";
        var factory = new MqttFactory();
        while (!stop.IsCancellationRequested)
        {
            try
            {
                using var client = factory.CreateMqttClient();
                var disconnected = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                client.ApplicationMessageReceivedAsync += e =>
                {
                    var m = e.ApplicationMessage;
                    var body = m.PayloadSegment.Count == 0 ? string.Empty :
                        System.Text.Encoding.UTF8.GetString(m.PayloadSegment.Array!, m.PayloadSegment.Offset, m.PayloadSegment.Count);
                    _state.Aplicar(m.Topic, body);
                    _plant.AplicarTemperatura(_state);
                    return Task.CompletedTask;
                };
                client.DisconnectedAsync += _ => { _state.MqttConectado = false; disconnected.TrySetResult(); return Task.CompletedTask; };
                var options = new MqttClientOptionsBuilder().WithTcpServer(host, port)
                    .WithClientId($"mcp-industrial-temperatura-{Environment.MachineName}").WithCleanSession().Build();
                await client.ConnectAsync(options, stop);
                _state.MqttConectado = true;
                await client.SubscribeAsync(new MqttClientSubscribeOptionsBuilder()
                    .WithTopicFilter(f => f.WithTopic(topic).WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce)).Build(), stop);
                await Task.WhenAny(disconnected.Task, Task.Delay(Timeout.Infinite, stop));
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                _state.MqttConectado = false;
                _log.LogWarning("MQTT Temperatura no disponible ({Mensaje}); reintento en 3 s", ex.Message);
                try { await Task.Delay(3000, stop); } catch (OperationCanceledException) { break; }
            }
        }
    }

    private async Task Difundir(CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            try { await _hub.Clients.All.SendAsync("temperaturaSenales", _state.Snapshot(), stop); }
            catch (OperationCanceledException) { break; }
            catch (Exception ex) { _log.LogDebug(ex, "Difusion de Temperatura interrumpida"); }
            try { await Task.Delay(1000, stop); } catch (OperationCanceledException) { break; }
        }
    }
}
