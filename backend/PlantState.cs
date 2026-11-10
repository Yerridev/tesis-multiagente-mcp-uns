using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.SignalR;

namespace MCP.Industrial.Api;

/// <summary>
/// Calidad del dato de proceso. Una medida saturada NO es una medida: el sensor
/// ultrasónico del MCN-09 entrega ~0 cuentas cuando se satura o muere, y la escala
/// lineal lo traduce a ~40,9 cm (el tope del rango calibrado). Sin esta marca, ese
/// artefacto se propagaría como si fuera un nivel real.
/// </summary>
public static class CalidadDato
{
    public const string Buena = "buena";
    /// <summary>Sensor de nivel fuera de rango (saturado): el valor en cm no es medible.</summary>
    public const string SensorFueraDeRango = "sensor_fuera_de_rango";
    /// <summary>Todavía no se conoce la calidad del dato: el valor en cm no se acepta.</summary>
    public const string SinCalidad = "sin_calidad";
}

/// <summary>Estado de supervisión de un equipo. Solo lectura: nunca escribe al PLC.</summary>
public record EquipmentState(string Id, string Name, string Controller, string Ip, string Variable, double? Value, string Unit, double Setpoint, DateTimeOffset Timestamp, string Calidad = CalidadDato.Buena)
{
    public string Status => DateTimeOffset.Now - Timestamp <= TimeSpan.FromSeconds(15) ? "ONLINE" : "OFFLINE";
    /// <summary>El valor solo es utilizable si la calidad del dato es buena.</summary>
    public bool Medible => Calidad == CalidadDato.Buena && Value is not null;
    public double Deviation => Value is double v ? Math.Round(v - Setpoint, 2) : 0;
    // Sin dato fresco no se evalúa alarma: jamás se reporta una alarma sobre telemetría vieja o inexistente.
    public bool Alarm => Medible
        && Value is double valor
        && Setpoint != 0
        && DateTimeOffset.Now - Timestamp <= TimeSpan.FromSeconds(15)
        && Math.Abs(valor - Setpoint) > Math.Max(1e-6, Math.Abs(Setpoint) * PlantState.Tolerance);
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
    DateTimeOffset? Timestamp,
    /// <summary>Calidad del dato de nivel: con sensor saturado el valor en cm no es medible.</summary>
    string Calidad = CalidadDato.Buena);

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

        /* Sensor saturado: el valor en cm es un artefacto de la escala (≈40,9 cm con el
           sensor muerto). Se expone SIN nivel, no como un nivel falso. */
        var saturado = n.SensorSaturado;
        var medible = !saturado && n.CalidadConocida;

        return new LevelDetail(
            EquipmentId: NivelId,
            Name: "Tanque MCN-09",
            Controller: eq?.Controller ?? "MicroLogix 1100",
            PlcIp: eq?.Ip ?? "192.168.114.9",
            PlcStatus: n.MqttConectado && n.plcConectado
                       && n.UltimoHeartbeat is DateTimeOffset hb && DateTimeOffset.Now - hb <= TimeSpan.FromSeconds(25)
                ? "ONLINE" : "OFFLINE",
            Mode: n.Modo(),
            Level: medible ? n.Numero("nivel/cm") : null,
            Unit: "cm",
            Setpoint: n.SetpointCm(),             // N7:5 / N7:6 convertido a cm
            TankHeight: n.AlturaTanqueCm,          // 60 cm publicados en descriptivo/equipo
            Percent: medible ? n.Numero("nivel/pct") : null,
            PumpOn: n.Bool("estado/bomba_marcha"),
            VfdHz: n.Numero("bomba/frecuencia_estimada_hz"),
            VfdPercent: n.VfdPercent(),
            ValveOpen: null,                       // no hay % real de apertura
            HighAlarm: null,
            LowAlarm: null,
            ValvulaAbriendo: n.Bool("valvula/abriendo"),
            ValvulaCerrando: n.Bool("valvula/cerrando"),
            Timestamp: n.UltimoMensaje,
            Calidad: saturado ? CalidadDato.SensorFueraDeRango
                    : (n.CalidadConocida ? CalidadDato.Buena : CalidadDato.SinCalidad));
    }

    /// <summary>
    /// Aplica la lectura REAL del PLC (vía MQTT) al equipo de nivel y a su historial.
    /// Si el sensor ultrasónico está SATURADO (fuera de rango), el valor en cm es un
    /// artefacto de la escala —≈40,9 cm con el sensor muerto— y NO una medida: en ese
    /// caso no se actualiza el valor ni se alimenta el historial; solo se marca la calidad.
    /// </summary>
    public void AplicarNivel(NivelState n)
    {
        // La frescura del equipo se mide con el HEARTBEAT del conector edge (el que lee el
        // PLC), no con el último mensaje MQTT: el conector de control sigue publicando
        // (válvula, fuente de mando) aunque el edge o el PLC ya no respondan, y eso hacía
        // que la interfaz mostrara "PLC conectado" con el laboratorio desconectado.
        var ts = n.UltimoHeartbeat ?? n.UltimoMensaje;
        if (ts is null) return;                       // nunca ha llegado un mensaje real
        var cm = n.Numero("nivel/cm");
        lock (_sync)
        {
            if (!_items.TryGetValue(NivelId, out var cur)) return;

            if (n.SensorSaturado)
            {
                // El valor en cm no es una medida: se anula (null) y no se alimenta el
                // historial. Mostrar el último valor conocido haría creer que es el nivel
                // actual; mostrar 0 sería todavía peor (parece una medida válida).
                _items[NivelId] = cur with { Value = null, Timestamp = ts.Value, Calidad = CalidadDato.SensorFueraDeRango };
                return;                               // el historial NO se alimenta con valores falsos
            }

            if (!n.CalidadConocida)
            {
                // Aún no se conoce la calidad del dato (falta el raw y el flag): no se
                // acepta el valor en cm. Fail-closed: es preferible no mostrar nivel
                // antes que mostrar el artefacto de saturación.
                _items[NivelId] = cur with { Value = null, Timestamp = ts.Value, Calidad = CalidadDato.SinCalidad };
                return;
            }

            var valor = cm is null ? cur.Value : Math.Round(cm.Value, 2);
            var consigna = n.SetpointCm() ?? cur.Setpoint;   // consigna real del PLC en cm
            _items[NivelId] = cur with { Value = valor, Setpoint = consigna, Timestamp = ts.Value, Calidad = CalidadDato.Buena };
            if (cm is not null && _ultimoPushNivel != ts)
            {
                _ultimoPushNivel = ts;
                Push(NivelId, cur.Variable, cur.Unit, valor ?? 0, ts.Value);
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
            double? valor = pv ?? med ?? cur.Value;          // sin lectura: null ("Sin datos"), nunca un 0 inventado
            var consigna = sp ?? cur.Setpoint;
            _items[CaudalId] = cur with
            {
                Value = valor is double vc ? Math.Round(vc, 2) : null,
                Setpoint = Math.Round(consigna, 2),
                Timestamp = ts.Value
            };
            if (valor is double vq && _ultimoPushCaudal != ts)
            {
                _ultimoPushCaudal = ts;
                Push(CaudalId, cur.Variable, cur.Unit, Math.Round(vq, 2), ts.Value);
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
            double? valor = psi ?? cur.Value;                // sin lectura: null ("Sin datos")
            var consigna = sp ?? cur.Setpoint;
            _items[PresionId] = cur with
            {
                Value = valor is double vp ? Math.Round(vp, 3) : null,
                Setpoint = Math.Round(consigna, 2),
                Timestamp = ts.Value
            };
            if (valor is double vq && _ultimoPushPresion != ts)
            {
                _ultimoPushPresion = ts;
                Push(PresionId, cur.Variable, cur.Unit, Math.Round(vq, 3), ts.Value);
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
            double? valor = principal ?? cur.Value;          // sin lectura: null ("Sin datos")
            var consigna = setpoint ?? cur.Setpoint;
            _items[TemperaturaId] = cur with
            {
                Value = valor is double vt ? Math.Round(vt, 2) : null,
                Setpoint = Math.Round(consigna, 2),
                Timestamp = ts.Value
            };
            if (principal is double vq && _ultimoPushTemperatura != ts)
            {
                _ultimoPushTemperatura = ts;
                Push(TemperaturaId, cur.Variable, cur.Unit, Math.Round(vq, 2), ts.Value);
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
                var noMedibles = GetAll().Where(e => !e.Medible)
                    .Select(e => $"{e.Name} (sensor fuera de rango)").ToArray();
                reply = noMedibles.Length > 0
                    ? $"ATENCIÓN: hay {noMedibles.Length} equipo(s) con medida no válida por saturación del sensor: {string.Join("; ", noMedibles)}. " +
                      "El valor mostrado en cm es un artefacto de la escala, NO el nivel real: verifica el sensor y el nivel físico antes de operar. " +
                      (alarms.Length == 0 && tags.Count == 0 ? "Sin alarmas activas." : $"Alarmas activas: {(alarms.Length == 0 ? "ninguna en equipo" : string.Join("; ", alarms))}{(tags.Count > 0 ? "; tanque: " + string.Join(", ", tags) : "")}.")
                    : alarms.Length == 0 && tags.Count == 0
                        ? "Sin alarmas activas. Todos los equipos operan dentro de la banda de ±12 % de su consigna y el tanque no reporta nivel alto ni bajo."
                        : $"Alarmas activas: {(alarms.Length == 0 ? "ninguna en equipo" : string.Join("; ", alarms))}{(tags.Count > 0 ? "; tanque: " + string.Join(", ", tags) : "")}.";
                return $"{alarms.Length} equipos + {tags.Count} de tanque + {noMedibles.Length} no medibles";
            }));
        }
        else if (Rx(norm, @"plc|micrologix|114\.9|comunic"))
        {
            calls.Add(Call("estado_plc", () =>
            {
                var level = GetLevel();
                reply = level.Calidad != CalidadDato.Buena
                    ? $"PLC {level.Controller} en {level.PlcIp}: {level.PlcStatus}. Última lectura {level.Timestamp:HH:mm:ss}. " +
                      "SENSOR DE NIVEL FUERA DE RANGO: el nivel no es medible (el valor en cm es saturación de la escala); revisa el sensor y el nivel físico antes de controlar."
                    : $"PLC {level.Controller} en {level.PlcIp}: {level.PlcStatus}. Última lectura {level.Timestamp:HH:mm:ss}, nivel {level.Level} {level.Unit} (consigna {level.Setpoint} {level.Unit}, {level.Percent} % del tanque).";
                return $"{level.PlcStatus} · {level.Timestamp:HH:mm:ss} · calidad {level.Calidad}";
            }));
        }
        else if (Rx(norm, @"equipo|caudal|nivel|presi|temp|valor|módulo|modulo"))
        {
            var target = GetAll().FirstOrDefault(v => Rx(norm, KeyOf(v.Id)));
            if (target is null)
            {
                calls.Add(Call("estado_planta", () =>
                {
                    reply = string.Join(" · ", GetAll().Select(e => e.Medible
                        ? $"{e.Variable} {e.Value} {e.Unit} (consigna {e.Setpoint}, {e.Status})"
                        : $"{e.Variable} NO MEDIBLE (sensor fuera de rango; el valor en {e.Unit} sería saturación de la escala)"));
                    return $"{GetAll().Count} equipos";
                }));
            }
            else
            {
                calls.Add(Call("leer_equipo", () =>
                {
                    var live = Get(target.Id) ?? target;
                    reply = !live.Medible
                        ? $"{live.Name} · {live.Controller} ({live.Ip}): {live.Variable} NO MEDIBLE (sensor fuera de rango). " +
                          $"El valor publicado ({live.Value} {live.Unit}) es saturación de la escala, no el nivel real; verifica el sensor y el nivel físico. Estado {live.Status}."
                        : $"{live.Name} · {live.Controller} ({live.Ip}): {live.Variable} {live.Value} {live.Unit}, consigna {live.Setpoint} {live.Unit}, desviación {live.Deviation:+0.##;-0.##} {live.Unit}, alarma {(live.Alarm ? "ACTIVA" : "sin actividad")}, estado {live.Status}.";
                    return live.Medible ? $"{live.Value} {live.Unit} · {live.Status}" : $"no medible · {live.Status}";
                }));
            }
        }
        else
        {
            calls.Add(Call("estado_planta", () =>
            {
                var all = GetAll();
                var noMedibles = all.Where(e => !e.Medible).Select(e => e.Name).ToArray();
                reply = $"Planta con {all.Count} equipos: {string.Join(" · ", all.Select(e => e.Medible
                    ? $"{e.Variable} {e.Value} {e.Unit}"
                    : $"{e.Variable} NO MEDIBLE (sensor fuera de rango)"))}. " +
                    (noMedibles.Length > 0
                        ? $"Atención: {string.Join(", ", noMedibles)} con medida no válida: el valor en cm es el tope de saturación de la escala, no el nivel real. "
                        : "") +
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
            if (!e.Medible)
            {
                sb.AppendLine($"- {e.Name} [{e.Id}] · {e.Controller} ({e.Ip}): MEDIDA NO VÁLIDA (sensor fuera de rango). " +
                              $"El valor publicado ({e.Value} {e.Unit}) es el tope de saturación de la escala, NO el nivel real. " +
                              "No lo reportes como un nivel ni lo compares con una consigna: dilo así, sin inventar.");
                continue;
            }
            sb.AppendLine($"- {e.Name} [{e.Id}] · {e.Controller} ({e.Ip}): {e.Variable} = {e.Value} {e.Unit}, consigna {e.Setpoint} {e.Unit}, desviación {e.Deviation} {e.Unit}, estado {e.Status}, alarma {(e.Alarm ? "ACTIVA" : "sin alarma")}, última lectura {e.Timestamp:HH:mm:ss}.");
        }

        var l = GetLevel();
        if (l.Calidad == CalidadDato.SensorFueraDeRango)
        {
            sb.AppendLine($"- Tanque MCN-09: SENSOR DE NIVEL FUERA DE RANGO (saturado). El nivel NO es medible; " +
                          "el valor en cm que aparece en la interfaz es un artefacto de la escala. " +
                          "Informa de la falla del sensor y de que el nivel debe verificarse físicamente; no informes un nivel.");
        }
        else if (l.Calidad == CalidadDato.SinCalidad)
        {
            sb.AppendLine("- Tanque MCN-09: calidad del dato de nivel aún no conocida (falta la lectura primaria del sensor). " +
                          "No hay nivel medible en este momento.");
        }
        else
        {
            sb.AppendLine(
            l.Level is null
                ? $"- Tanque MCN-09: sin lecturas reales del PLC ({l.PlcStatus}). Altura del tanque {l.TankHeight ?? 0} {l.Unit}."
                : $"- Tanque MCN-09: nivel {l.Level} {l.Unit}" +
                  (l.TankHeight is null ? "" : $" sobre {l.TankHeight} {l.Unit}") +
                  (l.Percent is null ? "" : $" ({l.Percent} %)") +
                  $", modo {l.Mode ?? "sin datos"}, bomba {(l.PumpOn is null ? "sin datos" : l.PumpOn.Value ? "encendida" : "apagada")}" +
                  (l.VfdHz is null ? "" : $" a {l.VfdHz} Hz") +
                  $", válvula {(l.ValveOpen is null ? "sin datos" : $"{l.ValveOpen} %")}, PLC {l.PlcIp} {l.PlcStatus}.");
        }
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
