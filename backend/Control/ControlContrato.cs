namespace MCP.Industrial.Api.Control;

/// <summary>Tipos de comando admitidos por el contrato de control del MCN-09.</summary>
public enum TipoComando
{
    Iniciar,
    Detener,
    Reiniciar,
    Setpoint,
    ParametroPid,
    AbrirValvula,
    CerrarValvula,
    AjustarValvula,
}

/// <summary>Ciclo de vida de una orden.
/// Recibido â†’ Validando â†’ Enviado â†’ (ack) Aceptado â†’ Escrito â†’ Confirmado.
/// Terminales: Confirmado | Rechazado | Vencido | Timeout | Error.
/// ACEPTADO = el conector recibiÃ³ la orden. ESCRITO = el conector ejecutÃ³ la escritura
/// (solo modo real). CONFIRMADO = una LECTURA POSTERIOR coincide con el esperado:
/// nunca se marca por la simple entrega MQTT.</summary>
public enum EstadoComando
{
    Recibido,
    Validando,
    Enviado,
    Aceptado,
    Escrito,
    Confirmado,
    Rechazado,
    Vencido,
    Timeout,
    /// <summary>Error interno (MQTT caÃ­do, JSON invÃ¡lido, confirmaciÃ³n no coincidente, etc.).</summary>
    Error,
}

/// <summary>CÃ³digos de error normalizados (motivo de rechazo).</summary>
public static class Motivos
{
    public const string RangoInvalido = "RANGO_INVALIDO";
    public const string TipoDesconocido = "TIPO_DESCONOCIDO";
    public const string PermisoInsuficiente = "PERMISO_INSUFICIENTE";
    public const string SinAutenticacion = "SIN_AUTENTICACION";
    public const string PlcDesconectado = "PLC_DESCONECTADO";
    public const string SelectorNoRemoto = "SELECTOR_NO_REMOTO";
    public const string ControlEnHmi = "CONTROL_EN_HMI";
    public const string FuenteControlSinDato = "FUENTE_CONTROL_SIN_DATO";
    public const string NivelBajoT1 = "NIVEL_BAJO_T1";
    public const string Duplicada = "DUPLICADA";
    public const string Vencida = "VENCIDA";
    public const string SinConfirmacion = "SIN_CONFIRMACION";
    public const string MqttNoDisponible = "MQTT_NO_DISPONIBLE";
    public const string DireccionProhibida = "DIRECCION_PROHIBIDA";
    public const string RealNoArmado = "REAL_NO_ARMADO";
    /// <summary>El campo equipo debe ser exactamente nivel-mcn09.</summary>
    public const string EquipoInvalido = "EQUIPO_INVALIDO";
    /// <summary>Setpoint exige unidad "cm".</summary>
    public const string UnidadInvalida = "UNIDAD_INVALIDA";
    /// <summary>Sin telemetrÃ­a fresca del conector edge no se expide ninguna orden.</summary>
    public const string TelemetriaVencida = "TELEMETRIA_VENCIDA";
    /// <summary>El conector confirmÃ³ con una lectura posterior distinta del valor esperado.</summary>
    public const string ConfirmacionNoCoincide = "CONFIRMACION_NO_COINCIDE";
    /// <summary>La direcciÃ³n no estÃ¡ en la allowlist / es de salida / no estÃ¡ verificada (niveles del conector).</summary>
    public const string DireccionNoPermitida = "DIRECCION_NO_PERMITIDA";
    public const string DireccionNoVerificada = "DIRECCION_NO_VERIFICADA";
}

/// <summary>DirecciÃ³n candidata de la allowlist. Todas NO_VERIFICADAS hasta la campaÃ±a de laboratorio.</summary>
public sealed record DireccionPermitida(string Tag, string Direccion, string Tipo, bool Verificada, string? Uso);

/// <summary>
/// Contrato de comandos de nivel-mcn09: rangos, permisos, estados y errores.
/// Reglas de seguridad del contrato:
///  - Nunca se escriben salidas O:0/* ni O:1/* (guard se aplica aunque la allowlist cambie).
///  - Toda direcciÃ³n candidata sale marcada Verificada=false â†’ NO_VERIFICADAS.
/// </summary>
public static class ControlContrato
{
    /* Rangos de proceso (tanque T2 de 0â€“40 cm segÃºn equipos.json; PID en unidades del PD12:0) */
    public const double SetpointMin = 0;
    public const double SetpointMax = 40;   // cm
    public const double KpMin = 0;
    public const double KpMax = 50;
    public const double TiMin = 0;
    public const double TiMax = 600;        // s (o s/min segÃºn configuraciÃ³n del PD12)
    public const double TdMin = 0;
    public const double TdMax = 60;
    public const double AperturaMin = 0;
    public const double AperturaMax = 100;  // %

    /// <summary>Equipo exacto admitido por el contrato (no se aceptan direcciones ni ids arbitrarios).</summary>
    public const string Equipo = "nivel-mcn09";

    /// <summary>Unidad obligatoria del setpoint.</summary>
    public const string UnidadSetpoint = "cm";

    /// <summary>Segundos mÃ¡ximos de antigÃ¼edad de la telemetrÃ­a del edge para expedir Ã³rdenes.</summary>
    public const int TelemetriaMaxSegundos = 30;

    /// <summary>Solo estas terminales cierran la orden (Aceptado/Escrito esperan la confirmaciÃ³n).</summary>
    public static readonly string[] EstadosFinales =
    [
        nameof(EstadoComando.Confirmado), nameof(EstadoComando.Rechazado),
        nameof(EstadoComando.Vencido), nameof(EstadoComando.Timeout), nameof(EstadoComando.Error),
    ];

    /// <summary>Allowlist de direcciones candidatas (extraÃ­das del RSS y del conector edge). TODAS NO_VERIFICADAS.
    /// Evidencia de rung: MCN\07_PLC_RSLOGIX\ladder_control_nivel_micrologix1100.md (programa vigente).</summary>
    public static readonly DireccionPermitida[] Allowlist =
    [
        new("B3:0/3", "B3:0/3", "bit", true, "PC_HMI: 0=PC 1=HMI (verificada en ladder online; rung 0005/0007/0022)"),
        new("B3:0/4", "B3:0/4", "bit", true, "START_PC: 1=marcha sostenida, 0=parada (verificada en ladder online; rung 0005)"),
        new("B3:0/5", "B3:0/5", "bit", false, "START_HMI (externo): NIVEL; rung 0007/0009"),
        new("B3:0/13", "B3:0/13", "bit", true, "START_VALVU: pulso para movimiento temporizado por N7:1/N7:2"),
        new("N7:5", "N7:5", "entero", true, "Setpoint PC â†’ PD12:0.SPS (rung 0022); raw=16348âˆ’400Â·cm"),
        new("N7:6", "N7:6", "entero", false, "Setpoint HMI â†’ PD12:0.SPS (rung 0022) en cuentas"),
        new("N7:8", "N7:8", "entero", true, "KC PC â†’ PD12:0.KC; valor web Ã—100 con RG=1"),
        new("N7:9", "N7:9", "entero", true, "Ti PC â†’ PD12:0.Ti; valor web Ã—100 con RG=1"),
        new("N7:10", "N7:10", "entero", true, "TD PC â†’ PD12:0.TD; valor web Ã—100 con RG=1"),
        new("N7:11", "N7:11", "entero", false, "KC HMI â†’ PD12:0.KC (rung 0022)"),
        new("N7:12", "N7:12", "entero", false, "Ti HMI â†’ PD12:0.Ti (rung 0022)"),
        new("N7:13", "N7:13", "entero", false, "TD HMI â†’ PD12:0.TD (rung 0022)"),
        new("N7:1", "N7:1", "entero", true, "Tiempo apertura â†’ T4:0.PRE; calibrado 9500=95 s"),
        new("N7:2", "N7:2", "entero", true, "Tiempo cierre â†’ T4:1.PRE; calibrado 9500=95 s"),
    ];

    /// <summary>Guard duro: jamÃ¡s se escribe sobre salidas de proceso.</summary>
    public static bool EsSalidaProhibida(string direccion) =>
        direccion.StartsWith("O:0", StringComparison.OrdinalIgnoreCase) ||
        direccion.StartsWith("O:1", StringComparison.OrdinalIgnoreCase);

    /// <summary>Rol mÃ­nimo por tipo de comando (viewer &lt; operador &lt; supervisor &lt; admin).</summary>
    public static string RolMinimo(TipoComando tipo) => tipo switch
    {
        TipoComando.Iniciar or TipoComando.Detener or TipoComando.Reiniciar => "operador",
        _ => "supervisor",   // setpoint, PID y vÃ¡lvula requieren supervisor
    };

    public static bool RolSuficiente(string? rol, TipoComando tipo)
    {
        if (string.IsNullOrWhiteSpace(rol)) return false;
        var minimo = RolMinimo(tipo);
        return rol.ToLowerInvariant() switch
        {
            "admin" => true,
            "supervisor" => true,
            "operador" => minimo == "operador",
            _ => false, // viewer o desconocido
        };
    }

    public static bool TryParseTipo(string? texto, out TipoComando tipo)
    {
        tipo = default;
        if (string.IsNullOrWhiteSpace(texto)) return false;
        return Enum.TryParse(texto.Trim(), ignoreCase: true, out tipo) && Enum.IsDefined(tipo);
    }

    /// <summary>Valida rangos/valores para el tipo. Devuelve el motivo de error si no cumple.</summary>
    public static string? ValidarValor(TipoComando tipo, double? valor)
    {
        switch (tipo)
        {
            case TipoComando.Iniciar:
            case TipoComando.Detener:
            case TipoComando.Reiniciar:
            case TipoComando.AbrirValvula:
            case TipoComando.CerrarValvula:
            case TipoComando.ParametroPid:
                // Sin valor propio (ParametroPid se valida con ValidarPid).
                return null;

            case TipoComando.Setpoint:
                return Rango(valor, SetpointMin, SetpointMax);

            default:
                return Motivos.TipoDesconocido;
        }
    }

    /// <summary>Valida el rango de un parÃ¡metro PID con nombre (kp/ti/td).</summary>
    public static string? ValidarPid(string? parametro, double? valor)
    {
        if (string.IsNullOrWhiteSpace(parametro)) return Motivos.TipoDesconocido;
        return parametro.Trim().ToLowerInvariant() switch
        {
            "kp" => Rango(valor, KpMin, KpMax),
            "ti" => Rango(valor, TiMin, TiMax),
            "td" => Rango(valor, TdMin, TdMax),
            _ => Motivos.TipoDesconocido,
        };
    }

    private static string? Rango(double? valor, double min, double max)
    {
        if (valor is null || !double.IsFinite(valor.Value)) return Motivos.RangoInvalido;
        return valor.Value < min || valor.Value > max ? Motivos.RangoInvalido : null;
    }
}
