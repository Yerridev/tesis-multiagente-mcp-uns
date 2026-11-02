using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.AspNetCore.SignalR;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api.Control;

public sealed class CaudalControlOpciones
{
    public string Modo { get; set; } = "DryRun";
    public bool HabilitadoEscritura { get; set; }
    public int TimeoutSegundos { get; set; } = 12;
    public int ExpiracionSegundos { get; set; } = 20;
    public string TopicoBase { get; set; } = CaudalState.Base + "/control";
    public Func<string?> VariableEntornoReal { get; set; } = () => Environment.GetEnvironmentVariable("CONTROL_CAUDAL_REAL");
}

public static class CaudalControlContrato
{
    public const string Equipo = "caudal-mcc09";
    public const string Unidad = "L/min";
    public const int TelemetriaMaxSegundos = 15;
    public static string? Validar(SolicitudComando s, TipoComando tipo)
    {
        static bool Fuera(double? v, double min, double max) => v is null || !double.IsFinite(v.Value) || v < min || v > max;
        return tipo switch
        {
            TipoComando.Setpoint when !string.Equals(s.Unidad, Unidad, StringComparison.OrdinalIgnoreCase) => Motivos.UnidadInvalida,
            TipoComando.Setpoint when Fuera(s.Valor, 0, 140) => Motivos.RangoInvalido,
            TipoComando.AjustarValvula when Fuera(s.Valor, 0, 100) => Motivos.RangoInvalido,
            TipoComando.ParametroPid when s.Parametro?.ToLowerInvariant() is not ("kc" or "ti" or "td") => Motivos.TipoDesconocido,
            TipoComando.ParametroPid when Fuera(s.Valor, 0, s.Parametro?.Equals("kc", StringComparison.OrdinalIgnoreCase) == true ? 100 : 600) => Motivos.RangoInvalido,
            TipoComando.Reiniciar or TipoComando.AbrirValvula or TipoComando.CerrarValvula => Motivos.TipoDesconocido,
            _ => null,
        };
    }
}

public sealed class CaudalControlService
{
    private readonly CaudalState _state;
    private readonly CaudalControlOpciones _op;
    private readonly IHubContext<PlantHub> _hub;
    private readonly IConfiguration _cfg;
    private readonly ConcurrentDictionary<string, OrdenControl> _ordenes = new();

    public CaudalControlService(CaudalState state, CaudalControlOpciones op, IHubContext<PlantHub> hub, IConfiguration cfg)
        => (_state, _op, _hub, _cfg) = (state, op, hub, cfg);

    private async Task<bool> PublicarComando(string cuerpo, CancellationToken ct)
    {
        try
        {
            var host = _cfg["Mqtt:CaudalControlHost"] ?? _cfg["Mqtt:Host"] ?? "127.0.0.1";
            var port = int.TryParse(_cfg["Mqtt:CaudalControlPort"], out var p) ? p : 1883;
            var factory = new MqttFactory(); using var client = factory.CreateMqttClient();
            await client.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(host, port).WithClientId($"caudal-cmd-{Guid.NewGuid():N}").Build(), ct);
            await client.PublishAsync(new MqttApplicationMessageBuilder().WithTopic(_op.TopicoBase + "/cmd").WithPayload(cuerpo)
                .WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce).Build(), ct);
            await client.DisconnectAsync(); return true;
        }
        catch { return false; }
    }

    public bool RealArmado => _op.Modo.Equals("Real", StringComparison.OrdinalIgnoreCase) &&
        _op.HabilitadoEscritura && _op.VariableEntornoReal() == "1";

    public object EstadoPublico()
    {
        var edad = _state.UltimoMensaje is { } u ? (DateTimeOffset.Now - u).TotalSeconds : double.PositiveInfinity;
        return new
        {
            modoEfectivo = RealArmado ? "REAL" : "BLOQUEADO",
            realArmado = RealArmado,
            proceso = new { plc = _state.PlcConectado ? "CONECTADO" : "DESCONECTADO", selector = _state.Modo(), mqtt = _state.MqttConectado },
            telemetria = new { ultimo = _state.UltimoMensaje, edadSegundos = double.IsFinite(edad) ? Math.Round(edad, 1) : (double?)null, fresca = edad <= CaudalControlContrato.TelemetriaMaxSegundos },
            pendientes = _ordenes.Values.Count(x => !x.EsTerminal),
        };
    }

    public IEnumerable<object> Ultimas(int n) => _ordenes.Values.OrderByDescending(x => x.Expedida).Take(Math.Clamp(n, 1, 50)).Select(x => x.ParaSenal());

    public async Task<ResultadoEnvio> Enviar(SolicitudComando s, string usuario, string rol, CancellationToken ct)
    {
        if (!string.Equals(s.Equipo, CaudalControlContrato.Equipo, StringComparison.OrdinalIgnoreCase)) return new(400, null, Motivos.EquipoInvalido);
        if (!ControlContrato.TryParseTipo(s.Tipo, out var tipo)) return new(400, null, Motivos.TipoDesconocido);
        if (!ControlContrato.RolSuficiente(rol, tipo)) return new(403, null, Motivos.PermisoInsuficiente);
        var invalido = CaudalControlContrato.Validar(s, tipo);
        if (invalido is not null) return new(400, null, invalido);
        if (!RealArmado) return new(409, null, Motivos.RealNoArmado);
        if (!_state.PlcConectado) return new(409, null, Motivos.PlcDesconectado);
        if (_state.Modo() != "REMOTO") return new(409, null, Motivos.SelectorNoRemoto);
        if (_state.Bool("estado/nivel_bajo") == true && tipo == TipoComando.Iniciar) return new(409, null, Motivos.NivelBajoT1);
        if (_state.UltimoMensaje is not { } ultimo || (DateTimeOffset.Now - ultimo).TotalSeconds > CaudalControlContrato.TelemetriaMaxSegundos)
            return new(409, null, Motivos.TelemetriaVencida);

        var now = DateTimeOffset.Now;
        var orden = new OrdenControl
        {
            Id = Guid.NewGuid().ToString("N"), Tipo = tipo, Valor = s.Valor, Parametro = s.Parametro?.ToLowerInvariant(),
            Unidad = s.Unidad, Equipo = CaudalControlContrato.Equipo, Comentario = s.Comentario,
            Correlacion = s.Correlacion, Origen = s.Origen, Usuario = usuario, Rol = rol, Modo = "REAL",
            Expedida = now, Expira = now.AddSeconds(_op.ExpiracionSegundos), TimeoutEn = now.AddSeconds(_op.TimeoutSegundos),
            Estado = EstadoComando.Enviado, Actualizada = now,
        };
        _ordenes[orden.Id] = orden;
        var cuerpo = JsonSerializer.Serialize(orden.ParaSenal(), new JsonSerializerOptions(JsonSerializerDefaults.Web));
        if (!await PublicarComando(cuerpo, ct))
        {
            orden.Estado = EstadoComando.Error; orden.Motivo = Motivos.MqttNoDisponible;
            return new(503, orden, orden.Motivo);
        }
        await _hub.Clients.All.SendAsync("caudalControlResultado", orden.ParaSenal(), ct);
        return new(202, orden, null);
    }

    public void ProcesarAck(string json)
    {
        try
        {
            using var d = JsonDocument.Parse(json); var r = d.RootElement;
            var id = r.GetProperty("id").GetString();
            if (id is null || !_ordenes.TryGetValue(id, out var o) || o.EsTerminal) return;
            var estado = r.GetProperty("estado").GetString();
            if (!Enum.TryParse<EstadoComando>(estado, true, out var e)) return;
            o.Estado = e; o.Actualizada = DateTimeOffset.Now;
            o.Motivo = r.TryGetProperty("motivo", out var m) ? m.GetString() : null;
            o.Escrito = r.TryGetProperty("escrito", out var w) && w.ValueKind is JsonValueKind.True or JsonValueKind.False ? w.GetBoolean() : null;
            o.ValorLeido = r.TryGetProperty("valor_leido", out var l) && l.TryGetDouble(out var lv) ? lv : null;
            o.ValorEsperado = r.TryGetProperty("valor_esperado", out var x) && x.TryGetDouble(out var xv) ? xv : null;
            _ = _hub.Clients.All.SendAsync("caudalControlResultado", o.ParaSenal());
        }
        catch { }
    }

    public void VerificarTimeouts()
    {
        foreach (var o in _ordenes.Values.Where(x => !x.EsTerminal && DateTimeOffset.Now >= x.TimeoutEn))
        { o.Estado = EstadoComando.Timeout; o.Motivo = Motivos.SinConfirmacion; o.Actualizada = DateTimeOffset.Now; }
    }
}

public sealed class CaudalControlMqttService : BackgroundService
{
    private readonly CaudalControlService _control; private readonly CaudalControlOpciones _op; private readonly IConfiguration _cfg;
    public CaudalControlMqttService(CaudalControlService c, CaudalControlOpciones o, IConfiguration cfg) => (_control, _op, _cfg) = (c, o, cfg);
    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var factory = new MQTTnet.MqttFactory();
        while (!stop.IsCancellationRequested)
        {
            try
            {
                using var c = factory.CreateMqttClient();
                c.ApplicationMessageReceivedAsync += e => { var p = e.ApplicationMessage.PayloadSegment; _control.ProcesarAck(p.Count == 0 ? "" : System.Text.Encoding.UTF8.GetString(p.Array!, p.Offset, p.Count)); return Task.CompletedTask; };
                await c.ConnectAsync(new MQTTnet.Client.MqttClientOptionsBuilder().WithTcpServer(_cfg["Mqtt:Host"] ?? "127.0.0.1", int.TryParse(_cfg["Mqtt:Port"], out var p) ? p : 1883).WithClientId("caudal-control-api").Build(), stop);
                await c.SubscribeAsync(new MQTTnet.Client.MqttClientSubscribeOptionsBuilder()
                    .WithTopicFilter(f => f.WithTopic(_op.TopicoBase + "/ack"))
                    .Build(), stop);
                while (!stop.IsCancellationRequested && c.IsConnected) { _control.VerificarTimeouts(); await Task.Delay(1000, stop); }
            }
            catch (OperationCanceledException) { break; }
            catch { await Task.Delay(3000, stop); }
        }
    }
}
