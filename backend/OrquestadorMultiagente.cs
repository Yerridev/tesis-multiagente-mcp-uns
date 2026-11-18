using System.Text;
using System.Text.Json;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api;

/// <summary>
/// Puente del chat web hacia el SISTEMA MULTIAGENTE MCP en Python (bat 31): publica la pregunta en
/// {UNS}/agentes/orquestador/solicitud y espera la respuesta en .../respuesta. El orquestador publica
/// su estado retenido en .../estado (en_linea / fuera_de_linea), así se sabe al instante si está corriendo.
/// </summary>
public sealed class OrquestadorMultiagente(IConfiguration cfg, ILogger<OrquestadorMultiagente> log)
{
    private const string Topico = "uss/campus/lab-automatizacion/sl01la07/agentes/orquestador";
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    private string Host => cfg["Mqtt:AgentesHost"] ?? cfg["Mqtt:CaudalControlHost"] ?? cfg["Mqtt:Host"] ?? "127.0.0.1";
    private int Puerto => int.TryParse(cfg["Mqtt:AgentesPort"], out var p) ? p : 1883;
    private int Espera => int.TryParse(cfg["Agente:MultiagenteTimeoutSegundos"], out var s) ? s : 150;

    /// <summary>Catálogo retenido que publica el orquestador cada 15 s: servidores MCP, sus herramientas (list_tools) y últimas llamadas.</summary>
    public async Task<JsonElement?> CatalogoAsync(CancellationToken ct)
    {
        var tcs = new TaskCompletionSource<JsonElement?>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cli = new MqttFactory().CreateMqttClient();
        cli.ApplicationMessageReceivedAsync += e =>
        {
            try
            {
                var seg = e.ApplicationMessage.PayloadSegment;
                using var doc = JsonDocument.Parse(Encoding.UTF8.GetString(seg.Array!, seg.Offset, seg.Count));
                tcs.TrySetResult(doc.RootElement.Clone());
            }
            catch { tcs.TrySetResult(null); }
            return Task.CompletedTask;
        };
        try
        {
            await cli.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(Host, Puerto)
                .WithClientId($"backend-catalogo-{Guid.NewGuid():N}"[..30]).WithCleanSession().WithTimeout(TimeSpan.FromSeconds(2)).Build(), ct);
            await cli.SubscribeAsync($"{Topico.Replace("/orquestador", "")}/catalogo", MqttQualityOfServiceLevel.AtLeastOnce, ct);
            return await Task.WhenAny(tcs.Task, Task.Delay(1500, ct)) == tcs.Task ? tcs.Task.Result : null;
        }
        catch { return null; }
        finally { if (cli.IsConnected) await cli.DisconnectAsync(); }
    }

    /// <summary>¿Está corriendo el orquestador? (lee su estado retenido; máx. ~1,5 s)</summary>
    public async Task<bool> EnLineaAsync(CancellationToken ct)
    {
        var enLinea = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cli = new MqttFactory().CreateMqttClient();
        cli.ApplicationMessageReceivedAsync += e =>
        {
            try
            {
                var seg = e.ApplicationMessage.PayloadSegment;
                using var doc = JsonDocument.Parse(Encoding.UTF8.GetString(seg.Array!, seg.Offset, seg.Count));
                enLinea.TrySetResult(doc.RootElement.TryGetProperty("estado", out var est) && est.GetString() == "en_linea");
            }
            catch { enLinea.TrySetResult(false); }
            return Task.CompletedTask;
        };
        try
        {
            await cli.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(Host, Puerto)
                .WithClientId($"backend-estado-{Guid.NewGuid():N}"[..28]).WithCleanSession().WithTimeout(TimeSpan.FromSeconds(2)).Build(), ct);
            await cli.SubscribeAsync($"{Topico}/estado", MqttQualityOfServiceLevel.AtLeastOnce, ct);
            return await Task.WhenAny(enLinea.Task, Task.Delay(1500, ct)) == enLinea.Task && enLinea.Task.Result;
        }
        catch { return false; }
        finally { if (cli.IsConnected) await cli.DisconnectAsync(); }
    }

    /// <summary>null si el sistema multiagente no está corriendo o no respondió a tiempo.</summary>
    public async Task<AgentReply?> PreguntarAsync(string pregunta, IReadOnlyList<TurnoChat>? historial, string? modelo, string? usuario, CancellationToken ct)
    {
        var id = Guid.NewGuid().ToString("N")[..12];
        var enLinea = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        var respuesta = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cli = new MqttFactory().CreateMqttClient();
        cli.ApplicationMessageReceivedAsync += e =>
        {
            try
            {
                var seg = e.ApplicationMessage.PayloadSegment;
                using var doc = JsonDocument.Parse(Encoding.UTF8.GetString(seg.Array!, seg.Offset, seg.Count));
                var r = doc.RootElement.Clone();
                if (e.ApplicationMessage.Topic.EndsWith("/estado"))
                    enLinea.TrySetResult(r.TryGetProperty("estado", out var est) && est.GetString() == "en_linea");
                else if (r.TryGetProperty("id_solicitud", out var ids) && ids.GetString() == id)
                    respuesta.TrySetResult(r);
            }
            catch { /* mensaje ajeno o mal formado */ }
            return Task.CompletedTask;
        };
        try
        {
            await cli.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(Host, Puerto)
                .WithClientId($"backend-chat-{id}").WithCleanSession().Build(), ct);
            await cli.SubscribeAsync(new MqttClientSubscribeOptionsBuilder()
                .WithTopicFilter(f => f.WithTopic($"{Topico}/estado").WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
                .WithTopicFilter(f => f.WithTopic($"{Topico}/respuesta").WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce))
                .Build(), ct);
            // el estado es retenido: llega de inmediato si el orquestador corre o corrió alguna vez
            if (await Task.WhenAny(enLinea.Task, Task.Delay(2000, ct)) != enLinea.Task || !enLinea.Task.Result)
                return null;

            var cuerpo = JsonSerializer.Serialize(new
            {
                id, pregunta, origen = $"chat-web:{usuario ?? "anonimo"}", modelo,
                historial = historial?.TakeLast(6).Select(h => new { rol = h.Rol, texto = h.Texto }),
            }, Json);
            await cli.PublishAsync(new MqttApplicationMessageBuilder().WithTopic($"{Topico}/solicitud").WithPayload(cuerpo)
                .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce).Build(), ct);

            if (await Task.WhenAny(respuesta.Task, Task.Delay(TimeSpan.FromSeconds(Espera), ct)) != respuesta.Task)
                return null;
            return Convertir(respuesta.Task.Result);
        }
        catch (Exception ex) when (!ct.IsCancellationRequested)
        {
            log.LogWarning("Sistema multiagente no disponible: {Error}", ex.Message);
            return null;
        }
        finally
        {
            if (cli.IsConnected) await cli.DisconnectAsync();
        }
    }

    private static string S(JsonElement e, string p) => e.TryGetProperty(p, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString()! : "";
    private static long L(JsonElement e, string p) => e.TryGetProperty(p, out var v) && v.TryGetInt64(out var n) ? n : 0;

    /// <summary>Respuesta del orquestador → formato del chat, con la traza completa (intérprete, analistas, herramientas MCP, veredicto).</summary>
    private static AgentReply Convertir(JsonElement r)
    {
        var traza = new List<AgentCall>();
        var plan = r.TryGetProperty("plan", out var p) ? string.Join(", ", p.EnumerateObject().Select(x => x.Name)) : "";
        traza.Add(new AgentCall("interprete", true, 0, $"{S(r, "interprete")} · módulos: {plan}"));
        if (r.TryGetProperty("informes", out var infs))
            foreach (var inf in infs.EnumerateArray())
            {
                var mod = S(inf, "modulo");
                if (inf.TryGetProperty("herramientas", out var hs))
                    foreach (var h in hs.EnumerateArray())
                        traza.Add(new AgentCall($"mcp-{mod}.{S(h, "herramienta")}", h.TryGetProperty("ok", out var ok) && ok.GetBoolean(), L(h, "ms"), ""));
                traza.Add(new AgentCall($"analista-{mod}", S(inf, "modo") != "error", L(inf, "ms"), $"{S(inf, "severidad")} · {S(inf, "modo")}"));
            }
        if (r.TryGetProperty("sin_respuesta", out var sr))
            foreach (var m in sr.EnumerateArray())
                traza.Add(new AgentCall($"analista-{m.GetString()}", false, 0, "no respondió a tiempo"));
        var ver = r.GetProperty("veredicto");
        traza.Add(new AgentCall("veredicto", true, L(ver, "ms"), $"severidad {S(ver, "severidad")} · {S(ver, "modo")}"));
        var modelo = S(ver, "modelo");
        return new AgentReply(S(ver, "respuesta"), "Sistema multiagente MCP · orquestador", DateTimeOffset.Now, traza,
            "multiagente", modelo.Length > 0 ? modelo : null);
    }
}
