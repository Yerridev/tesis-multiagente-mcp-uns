using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.AspNetCore.SignalR;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api.Control;

/// <summary>Control del MCP-09 (cFP-2200). El PID corre en el controlador: el SCADA solo
/// escribe consigna, ganancias y la toma/cesión de mando (variables de red del cFP-2200).</summary>
public sealed class PresionControlOpciones
{
    public string Modo { get; set; } = "DryRun";
    public bool HabilitadoEscritura { get; set; }
    public int TimeoutSegundos { get; set; } = 12;
    public int ExpiracionSegundos { get; set; } = 20;
    public string TopicoBase { get; set; } = PresionState.Base + "/control";
    public Func<string?> VariableEntornoReal { get; set; } = () => Environment.GetEnvironmentVariable("CONTROL_PRESION_REAL");
}

public static class PresionControlContrato
{
    public const string Equipo = "presion-mcp09";
    public const string Unidad = "psi";
    public const int TelemetriaMaxSegundos = 15;

    /// <summary>Variables de red del cFP-2200 que el SCADA puede escribir. La consigna PC forma
    /// parte del diseño original del supervisor y se confirma mediante lectura posterior.</summary>
    public static readonly string[] VariablesAutorizadas =
    {
        "DATOS_PAC/INICIO_PC", "DATOS_PAC/SALIR_PC", "pid/setpoint_pc",
        "pid/Kp_PC", "pid/Ti_PC", "pid/Td_PC"
    };

    public const string LazoEnElControlador =
        "LAZO_EN_EL_CONTROLADOR: la consigna y el PID se gobiernen en el cFP-2200 (panel HMI o app RT)";

    public static string? Validar(SolicitudComando s, TipoComando tipo)
    {
        static bool Fuera(double? v, double min, double max) => v is null || !double.IsFinite(v.Value) || v < min || v > max;
        return tipo switch
        {
            TipoComando.Setpoint when !string.Equals(s.Unidad, Unidad, StringComparison.OrdinalIgnoreCase) => Motivos.UnidadInvalida,
            TipoComando.Setpoint when Fuera(s.Valor, 0, 40) => Motivos.RangoInvalido,
            TipoComando.ParametroPid when s.Parametro?.ToLowerInvariant() is not ("kp" or "kc" or "ti" or "td") => Motivos.TipoDesconocido,
            TipoComando.ParametroPid when Fuera(s.Valor, 0, s.Parametro?.ToLowerInvariant() switch
            {
                "kp" or "kc" => 20,
                "ti" => 60,
                _ => 10,
            }) => Motivos.RangoInvalido,
            TipoComando.AjustarValvula => LazoEnElControlador,
            TipoComando.Reiniciar or TipoComando.AbrirValvula or TipoComando.CerrarValvula => Motivos.TipoDesconocido,
            _ => null,
        };
    }
}

public sealed class PresionControlService
{
    private readonly PresionState _state;
    private readonly PresionControlOpciones _op;
    private readonly IHubContext<PlantHub> _hub;
    private readonly IConfiguration _cfg;
    private readonly ConcurrentDictionary<string, OrdenControl> _ordenes = new();

    public PresionControlService(PresionState state, PresionControlOpciones op, IHubContext<PlantHub> hub, IConfiguration cfg)
        => (_state, _op, _hub, _cfg) = (state, op, hub, cfg);

    private async Task<bool> PublicarComando(string cuerpo, CancellationToken ct)
    {
        try
        {
            var host = _cfg["Mqtt:PresionControlHost"] ?? _cfg["Mqtt:Host"] ?? "127.0.0.1";
            var port = int.TryParse(_cfg["Mqtt:PresionControlPort"], out var p) ? p : 1883;
            var factory = new MqttFactory(); using var client = factory.CreateMqttClient();
            await client.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(host, port).WithClientId($"presion-cmd-{Guid.NewGuid():N}").Build(), ct);
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
            proceso = new
            {
                plc = _state.PlcConectado ? "CONECTADO" : "DESCONECTADO",
                selector = _state.Modo(),
                mqtt = _state.MqttConectado,
                mandandoElPc = _state.Bool("estado/pulsador_arranque"),
                variadorV = _state.Numero("bomba/salida_variador"),
                valvulaV = _state.Numero("valvula/salida")
            },
            telemetria = new
            {
                ultimo = _state.UltimoMensaje,
                edadSegundos = double.IsFinite(edad) ? Math.Round(edad, 1) : (double?)null,
                fresca = edad <= PresionControlContrato.TelemetriaMaxSegundos
            },
            pendientes = _ordenes.Values.Count(x => !x.EsTerminal),
        };
    }

    public IEnumerable<object> Ultimas(int n) => _ordenes.Values.OrderByDescending(x => x.Expedida).Take(Math.Clamp(n, 1, 50)).Select(x => x.ParaSenal());

    public async Task<ResultadoEnvio> Enviar(SolicitudComando s, string usuario, string rol, CancellationToken ct)
    {
        if (!string.Equals(s.Equipo, PresionControlContrato.Equipo, StringComparison.OrdinalIgnoreCase)) return new(400, null, Motivos.EquipoInvalido);
        if (!ControlContrato.TryParseTipo(s.Tipo, out var tipo)) return new(400, null, Motivos.TipoDesconocido);
        if (!ControlContrato.RolSuficiente(rol, tipo)) return new(403, null, Motivos.PermisoInsuficiente);
        var invalido = PresionControlContrato.Validar(s, tipo);
        if (invalido is not null) return new(400, null, invalido);
        if (!RealArmado) return new(409, null, Motivos.RealNoArmado);
        if (!_state.PlcConectado) return new(409, null, Motivos.PlcDesconectado);
        // El mando automático (DI Ch0 = SEL_AUTO) es condición física: en LOCAL el
        // control lo hacen los pulsadores del tablero y el SCADA no debe escribir.
        if (_state.Bool("estado/selector_remoto") != true) return new(409, null, Motivos.SelectorNoRemoto);
        if ((tipo is TipoComando.Setpoint or TipoComando.ParametroPid) && _state.Bool("estado/control_pc") != true)
            return new(409, null, "CONTROL_EN_HMI");
        if ((tipo is TipoComando.Setpoint or TipoComando.ParametroPid) && (_state.Bool("estado/sistema_funcionando") == true || _state.Bool("estado/bomba_habilitada") == true))
            return new(409, null, "AJUSTE_SOLO_CON_SISTEMA_DETENIDO");
        if (_state.UltimoMensaje is not { } ultimo || (DateTimeOffset.Now - ultimo).TotalSeconds > PresionControlContrato.TelemetriaMaxSegundos)
            return new(409, null, Motivos.TelemetriaVencida);
        if ((tipo is TipoComando.Setpoint or TipoComando.ParametroPid) && _ordenes.Values.Any(x => (x.Tipo is TipoComando.Setpoint or TipoComando.ParametroPid) && !x.EsTerminal))
            return new(409, null, Motivos.Duplicada);
        if (tipo == TipoComando.Iniciar && _ordenes.Values.Any(x => (x.Tipo is TipoComando.Setpoint or TipoComando.ParametroPid) && !x.EsTerminal))
            return new(409, null, "AJUSTE_PENDIENTE_DE_CONFIRMACION");

        var now = DateTimeOffset.Now;
        var orden = new OrdenControl
        {
            Id = Guid.NewGuid().ToString("N"), Tipo = tipo, Valor = s.Valor, Parametro = s.Parametro?.ToLowerInvariant(),
            Unidad = s.Unidad, Equipo = PresionControlContrato.Equipo, Comentario = s.Comentario,
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
        await _hub.Clients.All.SendAsync("presionControlResultado", orden.ParaSenal(), ct);
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
            _ = _hub.Clients.All.SendAsync("presionControlResultado", o.ParaSenal());
        }
        catch { }
    }

    public void VerificarTimeouts()
    {
        foreach (var o in _ordenes.Values.Where(x => !x.EsTerminal && DateTimeOffset.Now >= x.TimeoutEn))
        { o.Estado = EstadoComando.Timeout; o.Motivo = Motivos.SinConfirmacion; o.Actualizada = DateTimeOffset.Now; }
    }
}

/// <summary>Publica/escucha las órdenes de control de presión en el broker del stack (el mismo
/// que usa el conector de la VM LAB-AUTOMATIZACION a través de 192.168.114.70:1884).</summary>
public sealed class PresionControlMqttService : BackgroundService
{
    private readonly PresionControlService _control; private readonly PresionControlOpciones _op; private readonly IConfiguration _cfg;
    public PresionControlMqttService(PresionControlService c, PresionControlOpciones o, IConfiguration cfg) => (_control, _op, _cfg) = (c, o, cfg);
    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var factory = new MQTTnet.MqttFactory();
        while (!stop.IsCancellationRequested)
        {
            try
            {
                using var c = factory.CreateMqttClient();
                c.ApplicationMessageReceivedAsync += e => { var p = e.ApplicationMessage.PayloadSegment; _control.ProcesarAck(p.Count == 0 ? "" : System.Text.Encoding.UTF8.GetString(p.Array!, p.Offset, p.Count)); return Task.CompletedTask; };
                await c.ConnectAsync(new MQTTnet.Client.MqttClientOptionsBuilder().WithTcpServer(_cfg["Mqtt:Host"] ?? "127.0.0.1", int.TryParse(_cfg["Mqtt:Port"], out var p) ? p : 1883).WithClientId("presion-control-api").Build(), stop);
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
