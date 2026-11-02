using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.AspNetCore.SignalR;
using Microsoft.Extensions.Logging.Abstractions;

namespace MCP.Industrial.Api.Control;

/// <summary>Solicitud entrante desde la API/SPA. Solo comandos SEMÁNTICOS:
/// el navegador jamás envía una dirección del PLC (eso lo resuelve el conector contra su allowlist).</summary>
public sealed record SolicitudComando(
    string? Tipo,
    double? Valor,
    string? Parametro,
    string? Unidad = null,
    string? Equipo = null,
    string? Comentario = null,
    string? Correlacion = null,
    string? Origen = null);

/// <summary>Resultado de un intento de envío (siempre incluye la orden para auditoría/SignalR).</summary>
public sealed record ResultadoEnvio(int CodigoHttp, OrdenControl? Orden, string? Error);

/// <summary>Orden de control rastreada por su id único. Trazabilidad completa:</summary>
public sealed class OrdenControl
{
    public required string Id { get; init; }
    public required TipoComando Tipo { get; init; }
    public double? Valor { get; init; }
    public string? Parametro { get; init; }
    public string? Unidad { get; init; }
    public string Equipo { get; init; } = ControlContrato.Equipo;
    public string? Comentario { get; init; }
    /// <summary>Identificador de correlación elegido por el cliente (opcional, para encadenar con sistemas externos).</summary>
    public string? Correlacion { get; init; }
    /// <summary>Origen de la orden (SPA, herramienta de laboratorio, etc.).</summary>
    public string? Origen { get; init; }
    public required string Usuario { get; init; }
    public required string Rol { get; init; }
    public required string Modo { get; init; }          // DRY-RUN | REAL
    public required DateTimeOffset Expedida { get; init; }
    public required DateTimeOffset Expira { get; init; }
    public required DateTimeOffset TimeoutEn { get; init; }
    public EstadoComando Estado { get; set; } = EstadoComando.Recibido;
    public string? Motivo { get; set; }
    public DateTimeOffset? Actualizada { get; set; }
    /// <summary>Valor esperado tras la escritura (rellenado por el ack del conector).</summary>
    public double? ValorEsperado { get; set; }
    /// <summary>Valor observado en la lectura posterior (rellenado por el ack CONFIRMADO).</summary>
    public double? ValorLeido { get; set; }
    /// <summary>¿El conector ejecutó la escritura (solo modo real)?</summary>
    public bool? Escrito { get; set; }

    /// <summary>Terminal: solo se cierra con confirmación leída o con un rechazo/timeout.</summary>
    public bool EsTerminal => ControlContrato.EstadosFinales.Contains(Estado.ToString());

    public object ParaSenal() => new
    {
        id = Id,
        tipo = Tipo.ToString(),
        valor = Valor,
        parametro = Parametro,
        unidad = Unidad,
        equipo = Equipo,
        comentario = Comentario,
        correlacion = Correlacion,
        origen = Origen,
        usuario = Usuario,
        rol = Rol,
        modo = Modo,
        estado = Estado.ToString(),
        motivo = Motivo,
        expedida = Expedida,
        expira = Expira,
        timeoutEn = TimeoutEn,
        actualizada = Actualizada,
        escrito = Escrito,
        valorEsperado = ValorEsperado,
        valorLeido = ValorLeido,
    };
}

/// <summary>
/// Orquestador de control remoto para nivel-mcn09. El backend NUNCA escribe al PLC:
/// solo valida, audita y publica la orden en MQTT (cmd); la escritura real (si se
/// habilita algún día) la haría el conector Python tras su propio triple gate.
/// </summary>
public sealed class ControlService
{
    private readonly NivelState _nivel;
    private readonly IComandoTransporte _transporte;
    private readonly ControlAuditoria _auditoria;
    private readonly ControlOpciones _op;
    private readonly ILogger<ControlService> _log;
    private readonly IHubContext<PlantHub>? _hub;
    private readonly Func<DateTimeOffset> _ahora;

    private readonly ConcurrentDictionary<string, OrdenControl> _ordenes = new();
    private volatile bool _conectorSimulador;

    public ControlService(
        NivelState nivel,
        IComandoTransporte transporte,
        ControlAuditoria auditoria,
        ControlOpciones op,
        ILogger<ControlService>? log = null,
        IHubContext<PlantHub>? hub = null,
        Func<DateTimeOffset>? ahora = null)
    {
        _nivel = nivel;
        _transporte = transporte;
        _auditoria = auditoria;
        _op = op;
        _log = log ?? NullLogger<ControlService>.Instance;
        _hub = hub;
        _ahora = ahora ?? (() => DateTimeOffset.Now);
    }

    /* ------------------------------------------------------ triple gate REAL */

    /// <summary>Solo con los tres interruptores (entorno + configuración + selector REMOTO) queda armado el modo REAL.</summary>
    public (bool Armado, string[] Motivos) EvaluarModoReal()
    {
        var motivos = new List<string>();
        if (!string.Equals(_op.Modo, "Real", StringComparison.OrdinalIgnoreCase)) motivos.Add("MODO_CONFIG_NO_REAL");
        if (!_op.HabilitadoEscritura) motivos.Add("ESCRITURA_NO_HABILITADA");
        if (!string.Equals(_op.VariableEntornoReal(), "1", StringComparison.Ordinal)) motivos.Add("CONTROL_REAL_NO_DEFINIDO");
        if (!_conectorSimulador && _nivel.Modo() != "REMOTO") motivos.Add(Motivos.SelectorNoRemoto);
        return (motivos.Count == 0, motivos.ToArray());
    }

    public string ModoEfectivo() => EvaluarModoReal().Armado ? "REAL" : "DRY-RUN";

    /* ---------------------------------------------------------- estado público */

    public object EstadoPublico()
    {
        var (armado, motivos) = EvaluarModoReal();
        DateTimeOffset? ultimo = _conectorSimulador ? null : _nivel.UltimoMensaje;
        double? edad = ultimo is null ? null : Math.Round((DateTimeOffset.Now - ultimo.Value).TotalSeconds, 1);
        var fresca = _conectorSimulador || (ultimo is not null && edad is not null && edad <= ControlContrato.TelemetriaMaxSegundos);
        return new
        {
            modoEfectivo = ModoEfectivo(),
            realArmado = armado,
            motivosReal = motivos,
            configuracion = new
            {
                modo = _op.Modo,
                habilitadoEscritura = _op.HabilitadoEscritura,
                controlReal = _op.VariableEntornoReal(),
                timeoutSegundos = _op.TimeoutSegundos,
                expiracionSegundos = _op.ExpiracionSegundos,
            },
            proceso = new
            {
                simulador = _conectorSimulador,
                plc = _conectorSimulador ? "SIMULADOR" : (_nivel.plcConectado ? "CONECTADO" : "DESCONECTADO"),
                selector = _conectorSimulador ? "SIMULADOR" : _nivel.Modo(),
                nivelBajoT1 = _conectorSimulador ? false : _nivel.Bool("estado/alarma_nivel_bajo_tanque1"),
                mqttNivel = _nivel.MqttConectado,
                // Propietario del mando (B3:0/3 publicado por el puente como estado/fuente_control):
                // "PC" = control del SCADA web · "HMI" = control del HMI físico · null = sin dato
                fuenteControl = _conectorSimulador ? "SIMULADOR" : _nivel.FuenteControl(),
            },
            telemetria = new
            {
                ultimo = ultimo,
                edadSegundos = edad,
                fresca,
                maxSegundos = ControlContrato.TelemetriaMaxSegundos,
            },
            pendientes = _ordenes.Values.Count(o => !o.EsTerminal),
        };
    }

    public object ContratoPublico() => new
    {
        equipo = "nivel-mcn09",
        topicos = new { cmd = $"{_op.TopicoBase}/cmd", ack = $"{_op.TopicoBase}/ack", state = $"{_op.TopicoBase}/state" },
        tipos = new object[]
        {
            new { tipo = "Iniciar", valor = (string?)null, rango = (string?)null, rolMinimo = "operador" },
            new { tipo = "Detener", valor = (string?)null, rango = (string?)null, rolMinimo = "operador" },
            new { tipo = "Reiniciar", valor = (string?)null, rango = (string?)null, rolMinimo = "operador" },
            new { tipo = "Setpoint", valor = "cm", rango = new[] { ControlContrato.SetpointMin, ControlContrato.SetpointMax }, rolMinimo = "supervisor" },
            new { tipo = "ParametroPid", valor = "kp|ti|td", rango = "kp 0-50 · ti 0-600 · td 0-60", rolMinimo = "supervisor" },
            new { tipo = "AbrirValvula", valor = (string?)null, rango = (string?)null, rolMinimo = "supervisor" },
            new { tipo = "CerrarValvula", valor = (string?)null, rango = (string?)null, rolMinimo = "supervisor" },
        },
        estados = new[] { "Recibido", "Validando", "Enviado", "Aceptado", "Escrito", "Confirmado", "Rechazado", "Vencido", "Timeout", "Error" },
        confirmacion = new
        {
            regla = "CONFIRMADO exige una lectura posterior del PLC que coincida con el valor esperado; la entrega MQTT por sí sola nunca confirma.",
            distincion = "ACEPTADO = conector recibió · ESCRITO = conector ejecutó la escritura · CONFIRMADO = lectura posterior coincide",
        },
        motivos = new[]
        {
            Motivos.RangoInvalido, Motivos.TipoDesconocido, Motivos.PermisoInsuficiente, Motivos.SinAutenticacion,
            Motivos.PlcDesconectado, Motivos.SelectorNoRemoto, Motivos.NivelBajoT1, Motivos.Duplicada,
            Motivos.ControlEnHmi, Motivos.FuenteControlSinDato,
            Motivos.Vencida, Motivos.SinConfirmacion, Motivos.MqttNoDisponible, Motivos.DireccionProhibida, Motivos.RealNoArmado,
            Motivos.EquipoInvalido, Motivos.UnidadInvalida, Motivos.TelemetriaVencida, Motivos.ConfirmacionNoCoincide,
            Motivos.DireccionNoPermitida, Motivos.DireccionNoVerificada,
        },
        salidasProhibidas = new[] { "O:0/*", "O:1/*" },
        allowlist = ControlContrato.Allowlist.Select(a => new
        {
            a.Tag, a.Direccion, a.Tipo, a.Uso,
            verificada = a.Verificada,
            estado = a.Verificada ? "VERIFICADA" : "NO_VERIFICADAS",
        }),
        estado = EstadoPublico(),
    };

    /* ------------------------------------------------------------ envío */

    public async Task<ResultadoEnvio> EnviarAsync(SolicitudComando sol, string usuario, string rol, CancellationToken ct)
    {
        var ahora = _ahora();

        /*0* equipo exacto (solo nivel-mcn09; null = nivel-mcn09 por compatibilidad con la SPA) */
        var equipo = string.IsNullOrWhiteSpace(sol.Equipo) ? ControlContrato.Equipo : sol.Equipo.Trim();
        if (!string.Equals(equipo, ControlContrato.Equipo, StringComparison.OrdinalIgnoreCase))
        {
            var ordEquipo = NuevaOrden(sol, TipoComando.Iniciar, ahora, equipo, usuario, rol);
            return Rechazar(ordEquipo, Motivos.EquipoInvalido, 400);
        }

        if (!ControlContrato.TryParseTipo(sol.Tipo, out var tipo))
        {
            var ordTipo = NuevaOrden(sol, TipoComando.Iniciar, ahora, equipo, usuario, rol);
            return Rechazar(ordTipo, Motivos.TipoDesconocido, 400);
        }

        var orden = NuevaOrden(sol, tipo, ahora, equipo, usuario, rol);
        orden.Estado = EstadoComando.Validando;

        /*1* permisos por rol */
        if (!ControlContrato.RolSuficiente(rol, tipo))
            return Rechazar(orden, Motivos.PermisoInsuficiente, 403);

        /*2* unidad obligatoria para Setpoint (cm) */
        if (tipo == TipoComando.Setpoint &&
            !string.Equals(sol.Unidad?.Trim(), ControlContrato.UnidadSetpoint, StringComparison.OrdinalIgnoreCase))
            return Rechazar(orden, Motivos.UnidadInvalida, 400);

        /*3* rango del valor / parámetro PID */
        var errorValor = tipo == TipoComando.ParametroPid
            ? ControlContrato.ValidarPid(sol.Parametro, sol.Valor)
            : ControlContrato.ValidarValor(tipo, sol.Valor);
        if (errorValor is not null)
            return Rechazar(orden, errorValor, 400);

        /*4* duplicados: no dos órdenes idénticas pendientes a la vez */
        var duplicada = _ordenes.Values.Any(o =>
            !o.EsTerminal &&
            o.Tipo == tipo &&
            o.Valor == orden.Valor &&
            string.Equals(o.Parametro, orden.Parametro, StringComparison.OrdinalIgnoreCase) &&
            (ahora - o.Expedida).TotalSeconds <= _op.VentanaDuplicadosSegundos);
        if (duplicada)
            return Rechazar(orden, Motivos.Duplicada, 409);

        /*5* preflight del proceso (mismo criterio en dry-run y real; el conector simulador lo saltea) */
        if (!_conectorSimulador)
        {
            if (!_nivel.MqttConectado)
                return Rechazar(orden, Motivos.MqttNoDisponible, 409);

            /* telemetría fresca: sin dato reciente del edge no se expide ninguna orden */
            double? edad = _nivel.UltimoMensaje is null
                ? null
                : (DateTimeOffset.Now - _nivel.UltimoMensaje.Value).TotalSeconds;
            if (edad is null || edad > ControlContrato.TelemetriaMaxSegundos)
                return Rechazar(orden, Motivos.TelemetriaVencida, 409);

            if (!_nivel.plcConectado)
                return Rechazar(orden, Motivos.PlcDesconectado, 409);

            if (_nivel.Modo() != "REMOTO")
                return Rechazar(orden, Motivos.SelectorNoRemoto, 409);

            /* B3:0/3 arbitra el propietario: 0=PC/web, 1=HMI. Sin dato también
               se bloquea (fail closed). El backend jamás cambia este bit. */
            var fuenteControl = _nivel.FuenteControl();
            if (fuenteControl is null)
                return Rechazar(orden, Motivos.FuenteControlSinDato, 409);
            if (fuenteControl == "HMI")
                return Rechazar(orden, Motivos.ControlEnHmi, 409);

            if (tipo == TipoComando.Iniciar && _nivel.Bool("estado/alarma_nivel_bajo_tanque1") == true)
                return Rechazar(orden, Motivos.NivelBajoT1, 409);
        }

        /*6* publicar la orden (el backend jamás escribe al PLC) */
        _ordenes[orden.Id] = orden;
        var cuerpo = SerializarOrden(orden);
        var publicado = await _transporte.Publicar($"{_op.TopicoBase}/cmd", cuerpo, ct);
        if (!publicado)
        {
            if (orden.Estado is EstadoComando.Recibido or EstadoComando.Validando)
            {
                orden.Estado = EstadoComando.Error;
                orden.Motivo = Motivos.MqttNoDisponible;
                orden.Actualizada = _ahora();
                Finalizar(orden, "PUBLICACION_FALLIDA");
            }
            return new ResultadoEnvio(503, orden, Motivos.MqttNoDisponible);
        }

        /* El conector puede responder mientras se publica (ack más rápido que esta
           continuación): solo marcamos ENVIADO si nadie ya cerró/avanzó la orden. */
        if (orden.Estado is EstadoComando.Recibido or EstadoComando.Validando)
        {
            orden.Estado = EstadoComando.Enviado;
            orden.Actualizada = _ahora();
        }
        _auditoria.Registrar("ENVIO", orden.Id, usuario, rol, orden.Estado.ToString(),
            $"{orden.Tipo} {orden.Valor} {orden.Unidad} {orden.Parametro} modo={orden.Modo} correlacion={orden.Correlacion} comentario={orden.Comentario}");
        await DifundirAsync(orden);
        _log.LogInformation("Orden {Id} {Tipo} publicada ({Modo}) por {Usuario}; estado actual {Estado}",
            orden.Id, orden.Tipo, orden.Modo, usuario, orden.Estado);
        return new ResultadoEnvio(202, orden, null);
    }

    private OrdenControl NuevaOrden(SolicitudComando sol, TipoComando tipo, DateTimeOffset ahora, string equipo, string usuario, string rol) => new()
    {
        Id = Guid.NewGuid().ToString("N")[..16],
        Tipo = tipo,
        Valor = sol.Valor,
        Parametro = sol.Parametro,
        Unidad = sol.Unidad,
        Equipo = equipo,
        Comentario = sol.Comentario,
        Correlacion = sol.Correlacion,
        Origen = sol.Origen,
        Usuario = usuario,
        Rol = rol,
        Modo = ModoEfectivo(),
        Expedida = ahora,
        Expira = ahora.AddSeconds(_op.ExpiracionSegundos),
        TimeoutEn = ahora.AddSeconds(_op.TimeoutSegundos),
    };

    private ResultadoEnvio Rechazar(OrdenControl orden, string motivo, int codigo)
    {
        orden.Estado = EstadoComando.Rechazado;
        orden.Motivo = motivo;
        orden.Actualizada = _ahora();
        _ordenes[orden.Id] = orden;
        Finalizar(orden, "VALIDACION");
        return new ResultadoEnvio(codigo, orden, motivo);
    }

    private void Finalizar(OrdenControl orden, string accion)
    {
        _auditoria.Registrar(accion, orden.Id, orden.Usuario, orden.Rol, orden.Estado.ToString(), orden.Motivo);
        _ = DifundirAsync(orden);
    }

    private static string SerializarOrden(OrdenControl o) => JsonSerializer.Serialize(new
    {
        id = o.Id,
        equipo = o.Equipo,
        tipo = o.Tipo.ToString(),
        parametro = o.Parametro,
        valor = o.Valor,
        unidad = o.Unidad ?? (o.Tipo == TipoComando.Setpoint ? ControlContrato.UnidadSetpoint : null),
        comentario = o.Comentario,
        correlacion = o.Correlacion,
        origen = o.Origen,
        expedida = o.Expedida,
        expira = o.Expira,
        modo = o.Modo,
        origenOrden = new { usuario = o.Usuario, rol = o.Rol },
    });

    private async Task DifundirAsync(OrdenControl orden)
    {
        if (_hub is null) return;
        try
        {
            await _hub.Clients.All.SendAsync("controlResultado", orden.ParaSenal());
        }
        catch (Exception ex)
        {
            _log.LogDebug(ex, "No se pudo difundir la orden {Id}", orden.Id);
        }
    }

    /* --------------------------------------------------- ack / state del conector */

    /// <summary>
    /// Procesa el ack del conector Python ({Topico}/ack).
    /// Estados del conector: ACEPTADO (recibió) · ESCRITO (ejecutó la escritura, solo real)
    /// · CONFIRMADO (lectura posterior coincide) · RECHAZADO.
    /// La entrega MQTT por sí sola NUNCA produce CONFIRMADO.
    /// </summary>
    public void ProcesarAck(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            var id = root.TryGetProperty("id", out var i) ? i.GetString() : null;
            if (string.IsNullOrWhiteSpace(id) || !_ordenes.TryGetValue(id!, out var orden)) return;
            if (orden.EsTerminal) return; // ack duplicado de una terminal: se ignora

            var estadoTxt = (root.TryGetProperty("estado", out var e) ? e.GetString() : null)?.ToUpperInvariant();
            var motivo = root.TryGetProperty("motivo", out var mo) ? mo.GetString() : null;
            var detalle = root.TryGetProperty("detalle", out var de) ? de.GetString() : null;
            var modo = root.TryGetProperty("modo", out var md) ? md.GetString() : null;
            if (string.Equals(modo, "SIMULADOR", StringComparison.OrdinalIgnoreCase)) _conectorSimulador = true;

            /* rastro de escritura / lectura posterior (campos nuevos del conector) */
            if (root.TryGetProperty("escrito", out var esc) &&
                (esc.ValueKind is JsonValueKind.True or JsonValueKind.False ||
                 (esc.ValueKind is JsonValueKind.String && bool.TryParse(esc.GetString(), out _))))
                orden.Escrito = esc.ValueKind is JsonValueKind.True ||
                                (esc.ValueKind is JsonValueKind.String && bool.Parse(esc.GetString()!));
            if (root.TryGetProperty("valor_esperado", out var ve) && ve.ValueKind is JsonValueKind.Number) orden.ValorEsperado = ve.GetDouble();
            if (root.TryGetProperty("valor_leido", out var vl) && vl.ValueKind is JsonValueKind.Number) orden.ValorLeido = vl.GetDouble();

            if (_ahora() > orden.Expira && estadoTxt != "CONFIRMADO")
            {
                orden.Estado = EstadoComando.Vencido;
                orden.Motivo = Motivos.Vencida;
            }
            else
            {
                switch (estadoTxt)
                {
                    case "ACEPTADO":
                        orden.Estado = EstadoComando.Aceptado;
                        orden.Motivo = null;
                        break;

                    case "ESCRITO":
                        orden.Estado = EstadoComando.Escrito;
                        orden.Motivo = null;
                        orden.Escrito = orden.Escrito ?? true;
                        break;

                    case "CONFIRMADO":
                        /* Solo se confirma si la lectura posterior coincide con el esperado. */
                        if (orden.ValorEsperado is double esperado && orden.ValorLeido is double leido &&
                            Math.Abs(esperado - leido) > 1e-6)
                        {
                            orden.Estado = EstadoComando.Error;
                            orden.Motivo = Motivos.ConfirmacionNoCoincide;
                        }
                        else
                        {
                            orden.Estado = EstadoComando.Confirmado;
                            orden.Motivo = null;
                        }
                        break;

                    case "RECHAZADO":
                        /* una orden ya aceptada/escrita no retrocede por un ack tardío */
                        if (orden.Estado is EstadoComando.Aceptado or EstadoComando.Escrito) return;
                        orden.Estado = EstadoComando.Rechazado;
                        orden.Motivo = motivo ?? "RECHAZADO_POR_CONECTOR";
                        break;

                    default:
                        orden.Estado = EstadoComando.Error;
                        orden.Motivo = motivo ?? "ACK_DESCONOCIDO";
                        break;
                }
            }

            orden.Actualizada = _ahora();
            Finalizar(orden, "ACK");
            _log.LogInformation("Ack orden {Id}: {Estado} {Motivo} escrito={Escrito} leido={Leido} {Detalle}",
                orden.Id, orden.Estado, orden.Motivo, orden.Escrito, orden.ValorLeido, detalle);
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "Ack de control ilegible");
        }
    }

    /// <summary>Procesa el estado del conector ({Topico}/state): modo, simulador, etc.</summary>
    public void ProcesarState(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("simulador", out var s))
                _conectorSimulador = s.ValueKind == JsonValueKind.True ||
                                     (s.ValueKind == JsonValueKind.String && string.Equals(s.GetString(), "true", StringComparison.OrdinalIgnoreCase));
        }
        catch (Exception ex)
        {
            _log.LogWarning(ex, "State de control ilegible");
        }
    }

    /* --------------------------------------------------------------- timeouts */

    /// <summary>Marca TIMEOUT a las órdenes enviadas/aceptadas/escritas sin confirmación leída.
    /// Lo llama el servicio en segundo plano cada segundo.</summary>
    public void VerificarTimeouts()
    {
        var ahora = _ahora();
        foreach (var orden in _ordenes.Values)
        {
            if (orden.EsTerminal) continue;
            if (orden.Estado is not (EstadoComando.Enviado or EstadoComando.Aceptado or EstadoComando.Escrito)) continue;
            if (ahora < orden.TimeoutEn) continue;
            var previo = orden.Estado;
            orden.Estado = EstadoComando.Timeout;
            orden.Motivo = Motivos.SinConfirmacion;
            orden.Actualizada = ahora;
            Finalizar(orden, "TIMEOUT");
            _log.LogWarning("Orden {Id} sin confirmación ({Tipo}, estado previo {Previo})", orden.Id, orden.Tipo, previo);
        }
    }

    /* ------------------------------------------------------------- consultas */

    public OrdenControl? Obtener(string id) => _ordenes.TryGetValue(id, out var o) ? o : null;

    public IReadOnlyList<OrdenControl> Ultimas(int limit)
    {
        limit = Math.Clamp(limit <= 0 ? 10 : limit, 1, 200);
        return _ordenes.Values.OrderByDescending(o => o.Expedida).Take(limit).ToArray();
    }
}
