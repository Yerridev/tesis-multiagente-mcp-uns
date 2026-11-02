using System.Text.Json;

namespace MCP.Industrial.Api;

/// <summary>Valor publicado por el conector edge del MCN-09 (payload con "value").</summary>
public record NivelValor(object? Valor, string? Unidad, string? Source, string? Tag, DateTimeOffset? Ts);

/// <summary>
/// Estado REAL del módulo de nivel MCN-09, alimentado únicamente por MQTT
/// (conector edge ML1100 de la tesis, solo lectura). No se simula nada aquí:
/// si no hay mensaje, el campo queda null y la interfaz muestra SIN DATOS.
/// </summary>
public sealed class NivelState
{
    public const string Base = "uss/campus/lab-automatizacion/sl01la07/nivel-mcn09";
    public const string Prefijo = Base + "/funcional/";

    private readonly object _sync = new();
    private readonly Dictionary<string, NivelValor> _valores = new(StringComparer.OrdinalIgnoreCase);

    public bool MqttConectado { get; set; }
    public string? EdgeEstado { get; private set; }
    public string? PlcConexion { get; private set; }
    public DateTimeOffset? UltimoMensaje { get; private set; }
    public DateTimeOffset? UltimoHeartbeat { get; private set; }
    public double? AlturaTanqueCm { get; private set; }
    public int Mensajes { get; private set; }

    /// <summary>Aplica un mensaje MQTT recibido (topic completo + payload en texto).</summary>
    public void Aplicar(string topic, string payload)
    {
        if (!topic.StartsWith(Base, StringComparison.OrdinalIgnoreCase)) return;
        var relativo = topic[Base.Length..].TrimStart('/');

        /* Metadatos del conector (descriptivo/*): calibración y catálogo */
        if (relativo.StartsWith("descriptivo/", StringComparison.OrdinalIgnoreCase))
        {
            lock (_sync)
            {
                Mensajes++;
                UltimoMensaje = DateTimeOffset.Now;
                if (relativo.EndsWith("equipo", StringComparison.OrdinalIgnoreCase)) LeerAlturaTanque(payload);
            }
            return;
        }

        if (!relativo.StartsWith("funcional/", StringComparison.OrdinalIgnoreCase)) return;
        var sufijo = relativo["funcional/".Length..];
        lock (_sync)
        {
            Mensajes++;
            UltimoMensaje = DateTimeOffset.Now;

            switch (sufijo.ToLowerInvariant())
            {
                case "edge/estado":
                    EdgeEstado = payload.Trim();
                    return;
                case "plc/conexion":
                    PlcConexion = payload.Trim();
                    return;
                case "edge/heartbeat":
                    if (DateTimeOffset.TryParse(payload, out var hb)) UltimoHeartbeat = hb;
                    return;
                case "descriptivo/equipo":
                    LeerAlturaTanque(payload);
                    return;
                case "descriptivo/variables":
                    return; // catálogo: no es un dato de proceso
                default:
                    _valores[sufijo] = Parsear(payload);
                    return;
            }
        }
    }

    private void LeerAlturaTanque(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("calibracion_nivel", out var cal) &&
                cal.TryGetProperty("altura_tanque2_cm", out var alt) &&
                alt.TryGetDouble(out var cm))
            {
                AlturaTanqueCm = cm;
            }
        }
        catch
        {
            /* metadatos ilegibles: no afecta a los datos de proceso */
        }
    }

    private static NivelValor Parsear(string payload)
    {
        var texto = payload.Trim();
        if (texto.StartsWith('{'))
        {
            try
            {
                using var doc = JsonDocument.Parse(texto);
                var root = doc.RootElement;
                object? valor = null;
                if (root.TryGetProperty("value", out var v))
                {
                    valor = v.ValueKind switch
                    {
                        JsonValueKind.Number => v.GetDouble(),
                        JsonValueKind.True => true,
                        JsonValueKind.False => false,
                        JsonValueKind.String => v.GetString(),
                        _ => null,
                    };
                }
                return new NivelValor(
                    valor,
                    root.TryGetProperty("unit", out var u) ? u.GetString() : null,
                    root.TryGetProperty("source", out var s) ? s.GetString() : null,
                    root.TryGetProperty("tag", out var t) ? t.GetString() : null,
                    root.TryGetProperty("timestamp", out var ts) && DateTimeOffset.TryParse(ts.GetString(), out var when) ? when : null);
            }
            catch
            {
                /* payload JSON inválido */
            }
        }
        return new NivelValor(texto, null, null, null, null);
    }

    /* ------------------------------------------------------------ lecturas */

    public NivelValor? Get(string sufijo)
    {
        lock (_sync) return _valores.GetValueOrDefault(sufijo);
    }

    public double? Numero(string sufijo)
    {
        var v = Get(sufijo)?.Valor;
        return v switch
        {
            null => null,
            bool b => b ? 1 : 0,
            double d => d,
            int i => i,
            long l => l,
            string s when double.TryParse(s, out var d) => d,
            _ => null,
        };
    }

    public bool? Bool(string sufijo)
    {
        var v = Get(sufijo)?.Valor;
        return v switch
        {
            null => null,
            bool b => b,
            double d => Math.Abs(d) > 0.5,
            string s when bool.TryParse(s, out var b) => b,
            string s when double.TryParse(s, out var d) => Math.Abs(d) > 0.5,
            _ => null,
        };
    }

    public string? Texto(string sufijo)
    {
        var v = Get(sufijo)?.Valor;
        return v switch { null => null, bool b => b ? "ON" : "OFF", _ => v.ToString() };
    }

    /// <summary>Modo real del selector: REMOTO / LOCAL / EN 0 (null = sin datos).</summary>
    public string? Modo()
    {
        var remoto = Bool("estado/selector_remoto");
        var local = Bool("estado/selector_local");
        if (remoto is null && local is null) return null;
        if (remoto == true) return "REMOTO";
        if (local == true) return "LOCAL";
        return "EN 0";
    }

    /// <summary>Propietario del mando remoto según B3:0/3: PC o HMI.</summary>
    public string? FuenteControl()
    {
        var fuente = Texto("estado/fuente_control")?.Trim().ToUpperInvariant();
        return fuente is "PC" or "HMI" ? fuente : null;
    }

    /// <summary>Frecuencia del variador en % sobre su escala 0–50 Hz (derivado del dato real).</summary>
    public double? VfdPercent()
    {
        var hz = Numero("bomba/frecuencia_estimada_hz");
        return hz is null ? null : Math.Clamp(Math.Round(hz.Value / 50 * 100, 1), 0, 100);
    }

    public bool plcConectado => string.Equals(PlcConexion?.Trim(), "CONECTADO", StringComparison.OrdinalIgnoreCase);

    /// <summary>Copia para SignalR/REST (serializable).</summary>
    public object Snapshot()
    {
        lock (_sync)
        {
            return new
            {
                mqtt = MqttConectado,
                edge = EdgeEstado,
                plc = PlcConexion,
                mensajes = Mensajes,
                ultimo = UltimoMensaje,
                heartbeat = UltimoHeartbeat,
                alturaCm = AlturaTanqueCm,
                temaBase = Base,
                valores = new Dictionary<string, NivelValor>(_valores, StringComparer.OrdinalIgnoreCase),
            };
        }
    }
}
