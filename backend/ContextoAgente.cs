using System.Globalization;
using System.Text;

namespace MCP.Industrial.Api;

/// <summary>
/// Contexto ENRIQUECIDO para el agente: además del resumen de PlantState, entrega TODAS las
/// señales en vivo de los 4 PLC con su significado (catálogo de los conectores) y el
/// conocimiento operativo del laboratorio. Así el modelo puede responder modo, bomba,
/// válvulas, enclavamientos, PID, etc., sin inventar.
/// </summary>
public sealed class ContextoAgente(NivelState nivel, CaudalState caudal, PresionState presion, TemperaturaState temperatura)
{
    private static readonly TimeSpan HoraLima = TimeSpan.FromHours(-5);
    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    private const string Conocimiento = """
Conocimiento del laboratorio (USS, sala SL01LA07). Cuatro módulos didácticos INDUCONTROL, cada uno con su PLC:
- Nivel MCN-09: MicroLogix 1100 (192.168.114.9). Bomba de T1 (reserva, abajo) a T2 (acrílico, 60 cm); sensor ultrasónico mide T2; válvula Belimo de salida de T2. Selector LOCAL/REMOTO: REMOTO = manda la PC/SCADA (PID del PLC); LOCAL = manda el tablero (potenciómetro + pulsadores). T1: switch de nivel bajo I:0/2 (1 = hay agua) y switch alto I:0/3 (hipótesis).
- Caudal MCC-09: Siemens S7-200 CPU226 (192.168.114.7). Bomba con variador Altivar 11; caudalímetro Kobold 0-140 L/min; PID en el PLC (VD159 PV, VD163 SP). Selector LOCAL/REMOTO igual que nivel; M0.3 = 1 manda la HMI, 0 manda la PC. Q0.2 = sistema en marcha; Q1.1 = orden RUN al variador; Q0.0/Q0.1 = nivel alto/bajo de T1. Guardamotor GV2ME10 SIN señal al PLC: su disparo se infiere si el PLC indica marcha pero el caudal es 0 y la salida del PID está saturada (~100 %); se dispara en LOCAL con el potenciómetro al máximo.
- Presión MCP-09: NI Compact FieldPoint cFP-2200 (192.168.114.8). Bomba presuriza T2 (tanque cerrado con aire); transmisor 4-20 mA → psi; válvula proporcional de salida = perturbación. Selector MANUAL/AUTOMÁTICO.
- Temperatura MCT-09: Schneider Twido (192.168.114.10). Resistencia (PWM por relé SSR) calienta T2 principal; bomba recircula a T1 de enfriamiento (serpentín + enfriador). Switches alto/bajo en ambos tanques; un fallo de nivel detiene el lazo. Selector HMI-0-PC.
- Arquitectura: conectores edge leen los PLC → MQTT (UNS) → backend → SCADA web, lienzos y agentes MCP. Las órdenes pasan SOLO por el servicio de control con confirmación humana; tú NO ejecutas órdenes.
- Las HMI TPC-2106T originales dependían de variables compartidas NI en la PC del SCADA antiguo; hoy no forman parte del flujo.
""";

    public string Construir()
    {
        var sb = new StringBuilder();
        sb.AppendLine(Conocimiento);
        sb.AppendLine(ConocimientoModulos.Texto);
        sb.AppendLine("Señales en vivo de cada PLC (clave = valor · significado). [H] = significado aún en hipótesis. Booleanos: 1/ON = activo.");
        Modulo(sb, "Nivel", "nivel-mcn09", nivel.UltimoMensaje, nivel.Numero);
        Modulo(sb, "Caudal", "caudal-mcc09", caudal.UltimoMensaje, caudal.Numero);
        Modulo(sb, "Presion", "presion-mcp09", presion.UltimoMensaje, presion.Numero);
        Modulo(sb, "Temperatura", "temp-mct09", temperatura.UltimoMensaje, temperatura.Numero);
        return sb.ToString();
    }

    private static void Modulo(StringBuilder sb, string nombre, string id, DateTimeOffset? ultimo, Func<string, double?> numero)
    {
        var edad = ultimo is { } u ? (DateTimeOffset.Now - u).TotalSeconds : double.PositiveInfinity;
        var estado = double.IsInfinity(edad) ? "SIN DATOS"
            : edad <= 15 ? "EN LÍNEA" : $"SIN COMUNICACIÓN desde {ultimo!.Value.ToOffset(HoraLima):HH:mm:ss} (los valores son viejos)";
        sb.AppendLine($"## {nombre} [{id}] · {estado}");
        if (!CatalogoSenales.PorModulo.TryGetValue(nombre, out var senales)) return;
        foreach (var s in senales)
        {
            var v = numero(s.Clave);
            if (v is null) continue;
            var valor = EsBool(s) ? (v >= 0.5 ? "1" : "0") : Math.Round(v.Value, 3).ToString(Inv) + (s.Unidad.Length > 0 ? " " + s.Unidad : "");
            var desc = s.Desc.Length > 110 ? s.Desc[..110] + "…" : s.Desc;
            sb.AppendLine($"- {s.Clave} = {valor} · {desc}{(s.Hipotesis ? " [H]" : "")}");
        }
    }

    private static bool EsBool(CatalogoSenales.Senal s) =>
        s.Clave.StartsWith("estado/", StringComparison.OrdinalIgnoreCase) || s.Clave.StartsWith("io/", StringComparison.OrdinalIgnoreCase)
        || s.Clave.StartsWith("falla/", StringComparison.OrdinalIgnoreCase) || s.Clave.StartsWith("alarma/", StringComparison.OrdinalIgnoreCase)
        || s.Clave.StartsWith("mando/", StringComparison.OrdinalIgnoreCase) || s.Clave.Contains("/abriendo") || s.Clave.Contains("/cerrando")
        || (s.Unidad.Length == 0 && (s.Clave.Contains("_on") || s.Clave.Contains("bajo_ok") || s.Clave.EndsWith("_alto")));
}
