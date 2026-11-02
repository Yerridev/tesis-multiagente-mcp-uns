using System.Text.Json;

namespace MCP.Industrial.Api;

/// <summary>Estado real del MCP-09 recibido desde el UNS; no genera ni simula datos.</summary>
public sealed class PresionState
{
    public const string Base = "uss/campus/lab-automatizacion/sl01la07/presion-mcp09";
    private readonly object _sync = new();
    private readonly Dictionary<string, NivelValor> _valores = new(StringComparer.OrdinalIgnoreCase);

    public bool MqttConectado { get; set; }
    public string? EdgeEstado { get; private set; }
    public string? PlcConexion { get; private set; }
    public DateTimeOffset? UltimoMensaje { get; private set; }
    public DateTimeOffset? UltimoHeartbeat { get; private set; }
    public int Mensajes { get; private set; }

    public void Aplicar(string topic, string payload)
    {
        if (!topic.StartsWith(Base, StringComparison.OrdinalIgnoreCase)) return;
        var relativo = topic[Base.Length..].TrimStart('/');
        lock (_sync)
        {
            Mensajes++;
            UltimoMensaje = DateTimeOffset.Now;
            if (!relativo.StartsWith("funcional/", StringComparison.OrdinalIgnoreCase)) return;
            var sufijo = relativo["funcional/".Length..];
            switch (sufijo.ToLowerInvariant())
            {
                case "edge/estado": EdgeEstado = payload.Trim(); return;
                case "plc/conexion": PlcConexion = payload.Trim(); return;
                case "edge/heartbeat":
                    if (DateTimeOffset.TryParse(payload, out var hb)) UltimoHeartbeat = hb;
                    return;
                default: _valores[sufijo] = Parsear(payload); return;
            }
        }
    }

    private static NivelValor Parsear(string payload)
    {
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var r = doc.RootElement;
            object? valor = null;
            if (r.TryGetProperty("value", out var v))
                valor = v.ValueKind switch
                {
                    JsonValueKind.Number => v.GetDouble(), JsonValueKind.True => true,
                    JsonValueKind.False => false, JsonValueKind.String => v.GetString(), _ => null,
                };
            return new NivelValor(valor,
                r.TryGetProperty("unit", out var u) ? u.GetString() : null,
                r.TryGetProperty("source", out var s) ? s.GetString() : null,
                r.TryGetProperty("tag", out var t) ? t.GetString() : null,
                r.TryGetProperty("timestamp", out var ts) && DateTimeOffset.TryParse(ts.GetString(), out var when) ? when : null);
        }
        catch { return new NivelValor(payload.Trim(), null, null, null, null); }
    }

    public object Snapshot()
    {
        lock (_sync) return new
        {
            mqtt = MqttConectado, edge = EdgeEstado, plc = PlcConexion, mensajes = Mensajes,
            ultimo = UltimoMensaje, heartbeat = UltimoHeartbeat, temaBase = Base,
            valores = new Dictionary<string, NivelValor>(_valores, StringComparer.OrdinalIgnoreCase),
        };
    }

    public double? Numero(string clave)
    {
        lock (_sync)
        {
            if (!_valores.TryGetValue(clave, out var dato) || dato.Valor is null) return null;
            return dato.Valor switch
            {
                double d => d,
                float f => f,
                int i => i,
                long l => l,
                bool b => b ? 1 : 0,
                string s when double.TryParse(s, System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out var n) => n,
                _ => null,
            };
        }
    }

    public bool? Bool(string clave) => Numero(clave) is { } n ? n >= 0.5 : null;

    public string Modo() => Bool("estado/selector_remoto") == true ? "REMOTO" :
        Bool("estado/selector_local") == true ? "LOCAL" : "DESCONOCIDO";

    public bool PlcConectado => string.Equals(PlcConexion, "CONECTADO", StringComparison.OrdinalIgnoreCase);
}
