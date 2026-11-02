using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.SignalR;

namespace MCP.Industrial.Api;

/// <summary>Estado de supervisión de un equipo. Solo lectura: nunca escribe al PLC.</summary>
public record EquipmentState(string Id, string Name, string Controller, string Ip, string Variable, double Value, string Unit, double Setpoint, DateTimeOffset Timestamp)
{
    public string Status => DateTimeOffset.Now - Timestamp <= TimeSpan.FromSeconds(15) ? "ONLINE" : "OFFLINE";
    public double Deviation => Math.Round(Value - Setpoint, 2);
    // Sin dato fresco no se evalúa alarma: jamás se reporta una alarma sobre telemetría vieja o inexistente.
    public bool Alarm => Setpoint != 0
        && DateTimeOffset.Now - Timestamp <= TimeSpan.FromSeconds(15)
        && Math.Abs(Value - Setpoint) > Math.Max(1e-6, Math.Abs(Setpoint) * PlantState.Tolerance);
}

public record HistorySample(string Id, string Variable, string Unit, double Value, DateTimeOffset Ts);

/// <summary>
/// Detalle del módulo de nivel construido SOLO con datos reales (MQTT/conector edge).
/// Los campos nullable quedan null cuando no hay dato real: la interfaz muestra «Sin datos».
/// </summary>
public record LevelDetail(
    string EquipmentId,
    string Name,
    string Controller,
    string PlcIp,
    string PlcStatus,
    string? Mode,
    double? Level,
    string Unit,
    double? Setpoint,
    double? TankHeight,
    double? Percent,
    bool? PumpOn,
    double? VfdHz,
    double? VfdPercent,
    double? ValveOpen,
    bool? HighAlarm,
    bool? LowAlarm,
    bool? ValvulaAbriendo,
    bool? ValvulaCerrando,
    DateTimeOffset? Timestamp);

public record AgentTool(string Name, string Server, string Description);
public record AgentCall(string Name, bool Ok, long Ms, string Result);
public record AgentReply(string Reply, string Agent, DateTimeOffset Ts, IReadOnlyList<AgentCall> Tools, string Mode = "rules", string? Model = null);

public sealed class PlantState
{
    public const double Tolerance = 0.12;          // ±12 % de la consigna = banda de alarma
    public const string NivelId = "nivel-mcn09";
    public const string CaudalId = "caudal-mcc09";
    public const string PresionId = "presion-mcp09";
    public const string TemperaturaId = "temp-mct09";
    private const int HistoryCapacity = 1800;      // ~30 min de muestras por equipo (1 Hz)

    private readonly NivelState _nivel;
    private DateTimeOffset? _ultimoPushNivel;
    private DateTimeOffset? _ultimoPushCaudal;
    private DateTimeOffset? _ultimoPushPresion;
    private DateTimeOffset? _ultimoPushTemperatura;
    private readonly object _sync = new();
    private readonly Dictionary<string, EquipmentState> _items = new()
    {
        // Todos los equipos arrancan SIN DATOS (OFFLINE) hasta que exista telemetría real.
        ["caudal-mcc09"] = New("caudal-mcc09", "Control de caudal", "Siemens S7-200", "192.168.114.7", "Caudal", 0, "L/min", 75),
        [NivelId] = new EquipmentState(NivelId, "Control de nivel", "MicroLogix 1100", "192.168.114.9", "Nivel", 0, "cm", 0, DateTimeOffset.UnixEpoch),
        ["presion-mcp09"] = New("presion-mcp09", "Control de presión", "NI cFP-2200", "192.168.114.8", "Presión", 0, "psi", 22),
        [TemperaturaId] = New(TemperaturaId, "Control de temperatura", "Schneider Twido", "192.168.114.10", "Temperatura", 0, "°C", 40)
    };

    private readonly Dictionary<string, Queue<HistorySample>> _history = new();

    public PlantState(NivelState nivel)
    {
        _nivel = nivel;
        foreach (var item in _items.Values) _history[item.Id] = new Queue<HistorySample>();
        Seed();
    }

    public IReadOnlyCollection<EquipmentState> GetAll()
    {
        lock (_sync) return _items.Values.ToArray();
    }

    public EquipmentState? Get(string id)
    {
        lock (_sync) return _items.GetValueOrDefault(id);
    }

    /// <summary>Detalle del nivel: exclusivamente con las señales reales del conector edge (MQTT).</summary>
    public LevelDetail GetLevel()
    {
        var n = _nivel;
        EquipmentState? eq;
        lock (_sync) eq = _items.GetValueOrDefault(NivelId);

        return new LevelDetail(
            EquipmentId: NivelId,
            Name: "Tanque MCN-09",
            Controller: eq?.Controller ?? "MicroLogix 1100",
            PlcIp: eq?.Ip ?? "192.168.114.9",
            PlcStatus: n.MqttConectado && n.plcConectado ? "ONLINE" : "OFFLINE",
            Mode: n.Modo(),
            Level: n.Numero("nivel/cm"),
            Unit: "cm",
            Setpoint: null,                       // no hay consigna en cm confirmada en el conector
            TankHeight: n.AlturaTanqueCm,          // 60 cm publicados en descriptivo/equipo
            Percent: n.Numero("nivel/pct"),
            PumpOn: n.Bool("estado/bomba_marcha"),
            VfdHz: n.Numero("bomba/frecuencia_estimada_hz"),
            VfdPercent: n.VfdPercent(),
            ValveOpen: null,                       // no hay % real de apertura
            HighAlarm: null,
            LowAlarm: null,
            ValvulaAbriendo: n.Bool("valvula/abriendo"),
            ValvulaCerrando: n.Bool("valvula/cerrando"),
            Timestamp: n.UltimoMensaje);
    }

    /// <summary>Aplica la lectura REAL del PLC (vía MQTT) al equipo de nivel y a su historial.</summary>
    public void AplicarNivel(NivelState n)
    {
        var ts = n.UltimoMensaje;
        if (ts is null) return;                       // nunca ha llegado un mensaje real
        var cm = n.Numero("nivel/cm");
        lock (_sync)
        {
            if (!_items.TryGetValue(NivelId, out var cur)) return;
            var valor = cm is null ? cur.Value : Math.Round(cm.Value, 2);
            _items[NivelId] = cur with { Value = valor, Timestamp = ts.Value };
            if (cm is not null && _ultimoPushNivel != ts)
            {
                _ultimoPushNivel = ts;
                Push(NivelId, cur.Variable, cur.Unit, valor, ts.Value);
            }
        }
    }

    /// <summary>Aplica la lectura REAL del PLC de caudal (vía MQTT) al equipo y a su historial.</summary>
    public void AplicarCaudal(CaudalState c)
    {
        var ts = c.UltimoMensaje;
        if (ts is null) return;                       // nunca ha llegado un mensaje real
        var pv = c.Numero("caudal/pv_pid");
        var med = c.Numero("caudal/caudalimetro");
        var sp = c.Numero("caudal/setpoint");
        lock (_sync)
        {
            if (!_items.TryGetValue(CaudalId, out var cur)) return;
            var valor = pv ?? med ?? cur.Value;
            var consigna = sp ?? cur.Setpoint;
            _items[CaudalId] = cur with
            {
                Value = Math.Round(valor, 2),
                Setpoint = Math.Round(consigna, 2),
                Timestamp = ts.Value
            };
            if (_ultimoPushCaudal != ts)
            {
                _ultimoPushCaudal = ts;
                Push(CaudalId, cur.Variable, cur.Unit, Math.Round(valor, 2), ts.Value);
            }
        }
    }

    /// <summary>Aplica la lectura REAL del cFP-2200 (vía MQTT) al equipo de presión y a su historial.</summary>
    public void AplicarPresion(PresionState p)
    {
        var ts = p.UltimoMensaje;
        if (ts is null) return;                       // nunca ha llegado un mensaje real
        var psi = p.Numero("presion/psi");
        var sp = p.Numero("pid/setpoint_pc");
        lock (_sync)
        {
            if (!_items.TryGetValue(PresionId, out var cur)) return;
            var valor = psi ?? cur.Value;
            var consigna = sp ?? cur.Setpoint;
            _items[PresionId] = cur with
            {
                Value = Math.Round(valor, 3),
                Setpoint = Math.Round(consigna, 2),
                Timestamp = ts.Value
            };
            if (_ultimoPushPresion != ts)
            {
                _ultimoPushPresion = ts;
                Push(PresionId, cur.Variable, cur.Unit, Math.Round(valor, 3), ts.Value);
            }
        }
    }

    /// <summary>Aplica la lectura REAL del Twido (vía MQTT) al equipo de temperatura y a su historial.</summary>
    public void AplicarTemperatura(TemperaturaState t)
    {
        var ts = t.UltimaTelemetria;
        if (ts is null) return;
        var principal = t.Numero("temperatura/principal_c");
        var setpoint = t.Numero("pid/setpoint_c");
        lock (_sync)
        {
            if (!_items.TryGetValue(TemperaturaId, out var cur)) return;
            var valor = principal ?? cur.Value;
            var consigna = setpoint ?? cur.Setpoint;
            _items[TemperaturaId] = cur with
            {
                Value = Math.Round(valor, 2),
                Setpoint = Math.Round(consigna, 2),
                Timestamp = ts.Value
            };
            if (principal is not null && _ultimoPushTemperatura != ts)
            {
                _ultimoPushTemperatura = ts;
                Push(TemperaturaId, cur.Variable, cur.Unit, Math.Round(valor, 2), ts.Value);
            }
        }
    }

    public IReadOnlyList<HistorySample> GetHistory(string? id, int limit)
    {
        limit = Math.Clamp(limit <= 0 ? 300 : limit, 1, 5000);
        lock (_sync)
        {
            if (!string.IsNullOrWhiteSpace(id))
                return _history.TryGetValue(id, out var q) ? q.Reverse().Take(limit).Reverse().ToArray() : [];
            return _history.Values.SelectMany(q => q).OrderBy(s => s.Ts).TakeLast(limit).ToArray();
        }
    }

    /// <summary>Sin simulación: devuelve el estado actual sin inventar valores ni muestras.</summary>
    public IReadOnlyCollection<EquipmentState> Simulate(Random random)
    {
        lock (_sync) return _items.Values.ToArray();
    }

    public static IReadOnlyList<AgentTool> Tools() =>
    [
        new("estado_planta", "tiempo-real", "Devuelve el estado ONLINE/OFFLINE y el valor actual de los equipos de la planta."),
        new("leer_equipo", "tiempo-real", "Lee valor, consigna, desviación y alarma de un equipo concreto."),
        new("verificar_alarma", "tiempo-real", "Lista las alarmas activas de la planta y del tanque."),
        new("resumen_historico", "histórico", "Calcula mínimo, promedio y máximo de una variable en el búfer de historial."),
        new("estado_plc", "tiempo-real", "Reporta la comunicación con el PLC 192.168.114.9 (MicroLogix 1100).")
    ];

    /// <summary>Agente de supervisión: responde con datos reales del estado y del historial. Solo lectura.</summary>
    public AgentReply Ask(string? message)
    {
        var text = (message ?? string.Empty).Trim();
        var norm = text.ToLowerInvariant();
        var calls = new List<AgentCall>();
        var reply = string.Empty;

        if (norm.Length == 0 || Rx(norm, @"hola|ayuda|qué puedes|que puedes|help"))
        {
            reply = "Soy el agente de supervisión de MCP Industrial. Puedo responder sobre el estado de los equipos, las alarmas, el historial y el PLC 192.168.114.9. Ejemplos: «estado de la planta», «¿hay alarmas?», «promedio de caudal», «estado del PLC». Solo lectura: no envío órdenes al PLC.";
            calls.Add(Call("ayuda", () => "listado de capacidades"));
        }
        else if (Rx(norm, @"histor|promedio|prom |media|mínim|minim|máxim|maxim|tendencia"))
        {
            var target = GetAll().FirstOrDefault(v => Rx(norm, KeyOf(v.Id)));
            target ??= Get("caudal-mcc09")!;
            var key = target.Id;
            calls.Add(Call("resumen_historico", () =>
            {
                var samples = GetHistory(key, HistoryCapacity);
                if (samples.Count == 0) return "sin muestras";
                var values = samples.Select(s => s.Value).ToArray();
                var min = values.Min();
                var avg = Math.Round(values.Average(), 2);
                var max = values.Max();
                reply = $"Historial de {target.Variable.ToLowerInvariant()} ({samples.Count} muestras): mínimo {min} {target.Unit}, promedio {avg} {target.Unit}, máximo {max} {target.Unit}. Consigna {target.Setpoint} {target.Unit}.";
                return $"{samples.Count} muestras · min {min} · avg {avg} · max {max}";
            }));
        }
        else if (Rx(norm, @"alarma|alarm|fuera de rango|exceso"))
        {
            calls.Add(Call("verificar_alarma", () =>
            {
                var alarms = GetAll().Where(e => e.Alarm).Select(e => $"{e.Name} ({e.Value} {e.Unit} vs {e.Setpoint} {e.Unit})").ToArray();
                var level = GetLevel();
                var tags = new List<string>();
                if (level.HighAlarm == true) tags.Add("nivel alto");
                if (level.LowAlarm == true) tags.Add("nivel bajo");
                reply = alarms.Length == 0 && tags.Count == 0
                    ? "Sin alarmas activas. Todos los equipos operan dentro de la banda de ±12 % de su consigna y el tanque no reporta nivel alto ni bajo."
                    : $"Alarmas activas: {(alarms.Length == 0 ? "ninguna en equipo" : string.Join("; ", alarms))}{(tags.Count > 0 ? "; tanque: " + string.Join(", ", tags) : "")}.";
                return $"{alarms.Length} equipos + {tags.Count} de tanque";
            }));
        }
        else if (Rx(norm, @"plc|micrologix|114\.9|comunic"))
        {
            calls.Add(Call("estado_plc", () =>
            {
                var level = GetLevel();
                reply = $"PLC {level.Controller} en {level.PlcIp}: {level.PlcStatus}. Última lectura {level.Timestamp:HH:mm:ss}, nivel {level.Level} {level.Unit} (consigna {level.Setpoint} {level.Unit}, {level.Percent} % del tanque).";
                return $"{level.PlcStatus} · {level.Timestamp:HH:mm:ss}";
            }));
        }
        else if (Rx(norm, @"equipo|caudal|nivel|presi|temp|valor|módulo|modulo"))
        {
            var target = GetAll().FirstOrDefault(v => Rx(norm, KeyOf(v.Id)));
            if (target is null)
            {
                calls.Add(Call("estado_planta", () =>
                {
                    reply = string.Join(" · ", GetAll().Select(e => $"{e.Variable} {e.Value} {e.Unit} (consigna {e.Setpoint}, {e.Status})"));
                    return $"{GetAll().Count} equipos";
                }));
            }
            else
            {
                calls.Add(Call("leer_equipo", () =>
                {
                    var live = Get(target.Id) ?? target;
                    reply = $"{live.Name} · {live.Controller} ({live.Ip}): {live.Variable} {live.Value} {live.Unit}, consigna {live.Setpoint} {live.Unit}, desviación {live.Deviation:+0.##;-0.##} {live.Unit}, alarma {(live.Alarm ? "ACTIVA" : "sin actividad")}, estado {live.Status}.";
                    return $"{live.Value} {live.Unit} · {live.Status}";
                }));
            }
        }
        else
        {
            calls.Add(Call("estado_planta", () =>
            {
                var all = GetAll();
                reply = $"Planta con {all.Count} equipos: {string.Join(" · ", all.Select(e => $"{e.Variable} {e.Value} {e.Unit}"))}. " +
                        "Puedo detallar un equipo, alarmas, historial o el PLC 192.168.114.9.";
                return $"{all.Count} equipos";
            }));
        }

        if (string.IsNullOrWhiteSpace(reply))
            reply = "No dispongo de datos para esa consulta. Prueba con «estado de la planta», «alarmas», «promedio de caudal» o «estado del PLC».";

        return new AgentReply(reply, "Agente de supervisión MCP", DateTimeOffset.Now, calls);

        static string KeyOf(string id) => id.Split('-')[0];
    }

    /// <summary>Comparación sin acentos para interpretar la consulta del operador.</summary>
    private static string Deaccent(string text)
    {
        var stripped = new string(text.Normalize(NormalizationForm.FormD)
            .Where(c => CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark)
            .ToArray());
        return stripped.Normalize(NormalizationForm.FormC);
    }

    private static bool Rx(string input, string pattern) =>
        Regex.IsMatch(Deaccent(input), Deaccent(pattern), RegexOptions.IgnoreCase);

    /// <summary>Prompt de sistema con los datos en vivo para el modelo de OpenRouter.</summary>
    public string BuildSystemContext()
    {
        var sb = new StringBuilder();
        sb.AppendLine("Eres el agente de supervisión de MCP Industrial (Laboratorio USS · UNS). Trabajas en MODO SOLO LECTURA: no propongas órdenes de arranque, parada ni cambios de consigna; la lógica de control y seguridad vive en el PLC.");
        sb.AppendLine("Responde en español, con un máximo de 4 frases y sin inventar: usa SOLO los datos en vivo de abajo. Si algo no aparece, dilo.");
        sb.AppendLine("Datos en vivo:");
        foreach (var e in GetAll())
        {
            sb.AppendLine($"- {e.Name} [{e.Id}] · {e.Controller} ({e.Ip}): {e.Variable} = {e.Value} {e.Unit}, consigna {e.Setpoint} {e.Unit}, desviación {e.Deviation} {e.Unit}, estado {e.Status}, alarma {(e.Alarm ? "ACTIVA" : "sin alarma")}, última lectura {e.Timestamp:HH:mm:ss}.");
        }

        var l = GetLevel();
        sb.AppendLine(
            l.Level is null
                ? $"- Tanque MCN-09: sin lecturas reales del PLC ({l.PlcStatus}). Altura del tanque {l.TankHeight ?? 0} {l.Unit}."
                : $"- Tanque MCN-09: nivel {l.Level} {l.Unit}" +
                  (l.TankHeight is null ? "" : $" sobre {l.TankHeight} {l.Unit}") +
                  (l.Percent is null ? "" : $" ({l.Percent} %)") +
                  $", modo {l.Mode ?? "sin datos"}, bomba {(l.PumpOn is null ? "sin datos" : l.PumpOn.Value ? "encendida" : "apagada")}" +
                  (l.VfdHz is null ? "" : $" a {l.VfdHz} Hz") +
                  $", válvula {(l.ValveOpen is null ? "sin datos" : $"{l.ValveOpen} %")}, PLC {l.PlcIp} {l.PlcStatus}.");
        sb.AppendLine($"- Historial en memoria: {HistorySummary()}");
        sb.AppendLine("Los datos provienen del backend de supervisión: historial en memoria y telemetría en vivo cuando el equipo reporta. Todo es de solo lectura: no se envían órdenes al PLC.");
        return sb.ToString();
    }

    private string HistorySummary()
    {
        lock (_sync)
        {
            var parts = new List<string>();
            foreach (var (id, queue) in _history)
            {
                if (queue.Count == 0) continue;
                var values = queue.Select(s => s.Value).ToArray();
                parts.Add($"{id}: {values.Length} muestras, mín {values.Min():0.##}, prom {values.Average():0.##}, máx {values.Max():0.##}");
            }
            return parts.Count == 0 ? "sin muestras" : string.Join(" · ", parts);
        }
    }

    private AgentCall Call(string name, Func<string> run)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            var result = run();
            sw.Stop();
            return new AgentCall(name, true, sw.ElapsedMilliseconds, result);
        }
        catch (Exception ex)
        {
            sw.Stop();
            return new AgentCall(name, false, sw.ElapsedMilliseconds, ex.Message);
        }
    }

    private void Push(string id, string variable, string unit, double value, DateTimeOffset ts)
    {
        if (!_history.TryGetValue(id, out var queue)) return;
        queue.Enqueue(new HistorySample(id, variable, unit, value, ts));
        while (queue.Count > HistoryCapacity) queue.Dequeue();
    }

    private static bool Fresh(DateTimeOffset ts) => DateTimeOffset.Now - ts <= TimeSpan.FromSeconds(15);

    private void Seed()
    {
        // Sin datos simulados: el historial arranca vacío y solo se llena con telemetría real.
    }

    private static EquipmentState New(string id, string name, string controller, string ip, string variable, double value, string unit, double setpoint) =>
        new(id, name, controller, ip, variable, value, unit, setpoint, DateTimeOffset.UnixEpoch);
}

public sealed class PlantHub : Hub;

public sealed class PlantSimulator(PlantState plant, IHubContext<PlantHub> hub) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken token)
    {
        var random = new Random();
        while (!token.IsCancellationRequested)
        {
            await hub.Clients.All.SendAsync("telemetry", plant.Simulate(random), token);
            await Task.Delay(1000, token);
        }
    }
}
