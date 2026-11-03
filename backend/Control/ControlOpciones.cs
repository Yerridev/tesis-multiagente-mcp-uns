namespace MCP.Industrial.Api.Control;

/// <summary>
/// Opciones de control remoto de nivel-mcn09.
/// El modo REAL exige SIMULTÁNEAMENTE: Modo=Real + HabilitadoEscritura + variable de entorno
/// CONTROL_REAL=1 + selector físico en REMOTO. Si falta algo, el modo efectivo es DRY-RUN.
/// </summary>
public sealed class ControlOpciones
{
    /// <summary>DryRun | Real (lo que pide la configuración; el modo efectivo se calcula con el triple gate).</summary>
    public string Modo { get; set; } = "DryRun";

    /// <summary>Segundo interruptor del triple gate: debe ser true para escritura real.</summary>
    public bool HabilitadoEscritura { get; set; }

    /// <summary>Primer interruptor del triple gate: variable de entorno explícita (CONTROL_REAL=1).</summary>
    public Func<string?> VariableEntornoReal { get; set; } = () => Environment.GetEnvironmentVariable("CONTROL_REAL");

    /// <summary>
    /// Interruptor de operación degradada. Por defecto (false) el preflight RECHAZA toda orden
    /// salvo Detener cuando el sensor de nivel está saturado o su calidad es desconocida, porque
    /// el PV del lazo no sería una medida. Ponerlo en true permite trabajar con instrumentación
    /// degradada (banco de pruebas, setpoint, válvula) aun así: es una decisión explícita del
    /// laboratorio, queda registrada en la auditoría de cada orden y la interfaz lo advierte.
    /// Variable de entorno equivalente: CONTROL_PERMITIR_SENSOR_FUERA_DE_RANGO=1.
    /// </summary>
    public bool PermitirSensorFueraDeRango { get; set; }

    /// <summary>Segundos que la orden espera confirmación antes de pasar a TIMEOUT.</summary>
    public int TimeoutSegundos { get; set; } = 10;

    /// <summary>Vida útil de la orden (si el ack llega después, se marca VENCIDA).</summary>
    public int ExpiracionSegundos { get; set; } = 15;

    /// <summary>Ventana para considerar "pendiente idéntico" = duplicada.</summary>
    public int VentanaDuplicadosSegundos { get; set; } = 30;

    /// <summary>Base de tópicos MQTT de control: {Topico}/cmd, {Topico}/ack, {Topico}/state.</summary>
    public string TopicoBase { get; set; } = NivelState.Base + "/control";

    /// <summary>Archivo JSONL de auditoría (null = carpeta por defecto junto al ejecutable).</summary>
    public string? AuditoriaRuta { get; set; }

    /// <summary>Usuarios de desarrollo: clave Bearer → rol (viewer|operador|supervisor|admin).</summary>
    public Dictionary<string, string> Usuarios { get; set; } = new(StringComparer.Ordinal)
    {
        ["dev-viewer"] = "viewer",
        ["dev-operador"] = "operador",
        ["dev-supervisor"] = "supervisor",
        ["dev-admin"] = "admin",
    };
}
