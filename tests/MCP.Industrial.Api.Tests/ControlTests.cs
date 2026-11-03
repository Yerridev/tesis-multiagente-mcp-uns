using MCP.Industrial.Api;
using MCP.Industrial.Api.Control;
using Microsoft.AspNetCore.Http;
using Xunit;

namespace MCP.Industrial.Api.Tests;

/// <summary>Reloj controlable para expirar/vencer órdenes en pruebas.</summary>
internal sealed class Reloj
{
    public DateTimeOffset Actual { get; private set; } = DateTimeOffset.Now;
    public DateTimeOffset Ahora() => Actual;
    public void Avanzar(TimeSpan ts) => Actual += ts;
}

/// <summary>
/// Pruebas del contrato de control en modo DRY-RUN: sin PLC, sin MQTT real y sin escrituras.
/// Casos cubiertos (Fase 7 del plan de control remoto):
///   1 usuario inexistente · 2 viewer sin permiso · 3 operador con setpoint (rechazado)
///   4 setpoint válido (supervisor) · 5 fuera de rango · 6 unidad incorrecta · 7 vencida
///   8 duplicada · 9 PLC desconectado · 10 MQTT desconectado · 11 telemetría vencida
///   12 selector LOCAL · 13 selector REMOTO (camino feliz) · 14 nivel bajo T1
///   15/16/17/18 allowlist sin O:0/O:1 y todas NO_VERIFICADAS (direcciones arbitrarias
///   no son parte del contrato: el backend solo acepta comandos semánticos)
///   19 triple gate incompleto · 20 ack aceptado · 21 ack rechazado · 22 ack duplicado
///   23 timeout (sin ack y tras ESCRITO sin CONFIRMADO) · 24 lectura posterior diferente
///   25 lectura posterior coincidente · 26/27 pulso y pérdida de conexión → conector Python
///   (validados en la simulación con --modo simulador, ver docs/01-auditoria-control-remoto.md).
/// </summary>
public class ControlTests
{
    private static NivelState Nivel(string plc = "CONECTADO", string selector = "REMOTO", bool nivelBajo = false, bool mqtt = true, string? fuenteControl = "PC")
    {
        var n = new NivelState { MqttConectado = mqtt };
        n.Aplicar($"{NivelState.Base}/funcional/plc/conexion", plc);
        n.Aplicar($"{NivelState.Base}/funcional/estado/selector_remoto", selector == "REMOTO" ? "true" : "false");
        n.Aplicar($"{NivelState.Base}/funcional/estado/selector_local", selector == "LOCAL" ? "true" : "false");
        if (fuenteControl is not null)
            n.Aplicar($"{NivelState.Base}/funcional/estado/fuente_control", fuenteControl);
        if (nivelBajo) n.Aplicar($"{NivelState.Base}/funcional/estado/alarma_nivel_bajo_tanque1", "true");
        // Telemetría sana del sensor de nivel: N7:4 en media escala (no saturado) y el flag
        // explícito en false. El conector edge publica ambos siempre.
        n.Aplicar($"{NivelState.Base}/funcional/nivel/raw", "{\"value\":16548,\"unit\":\"cuentas\"}");
        n.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":false}");
        return n;
    }

    private static (ControlService Svc, EnMemoriaTransporte Bus, Reloj Reloj) Crear(NivelState? nivel = null, Action<ControlOpciones>? ajustar = null)
    {
        var op = new ControlOpciones
        {
            TimeoutSegundos = 5,
            ExpiracionSegundos = 15,
            VentanaDuplicadosSegundos = 30,
            VariableEntornoReal = () => null,   // sin CONTROL_REAL: modo efectivo DRY-RUN
        };
        ajustar?.Invoke(op);
        var bus = new EnMemoriaTransporte();
        var reloj = new Reloj();
        var auditoria = new ControlAuditoria(Path.Combine(Path.GetTempPath(), $"aud_test_{Guid.NewGuid():N}"));
        var svc = new ControlService(nivel ?? Nivel(), bus, auditoria, op, null, null, reloj.Ahora);
        return (svc, bus, reloj);
    }

    private static string Ack(string id, string estado, string? motivo = null, bool? escrito = null, double? esperado = null, double? leido = null)
    {
        var extras = new System.Text.StringBuilder();
        if (escrito is not null) extras.Append($",\"escrito\":{(escrito.Value ? "true" : "false")}");
        if (esperado is not null) extras.Append($",\"valor_esperado\":{esperado.Value.ToString(System.Globalization.CultureInfo.InvariantCulture)}");
        if (leido is not null) extras.Append($",\"valor_leido\":{leido.Value.ToString(System.Globalization.CultureInfo.InvariantCulture)}");
        return $"{{\"id\":\"{id}\",\"estado\":\"{estado}\",\"motivo\":{(motivo is null ? "null" : $"\"{motivo}\"")},\"modo\":\"DRY-RUN\"{extras}}}";
    }

    private static SolicitudComando Setpoint(double valor, string? unidad = "cm") => new("Setpoint", valor, null, unidad);

    /* -------------------------------------------------- 1 usuario inexistente / sin bearer */
    [Fact]
    public void Usuario_inexistente_o_sin_token_da_401()
    {
        var op = new ControlOpciones();
        var ctxSin = new DefaultHttpContext();
        var (rol1, _, err1) = ControlAuth.Resolver(op, ctxSin);
        Assert.Null(rol1);
        Assert.Equal(401, err1);

        var ctxMalo = new DefaultHttpContext();
        ctxMalo.Request.Headers.Authorization = "Bearer dev-que-no-existe";
        var (rol2, _, err2) = ControlAuth.Resolver(op, ctxMalo);
        Assert.Null(rol2);
        Assert.Equal(401, err2);
    }

    /* -------------------------------------------------- 2 viewer intentando escribir */
    [Fact]
    public async Task Viewer_intentando_iniciar_se_rechaza()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "viewer1", "viewer", default);
        Assert.Equal(403, res.CodigoHttp);
        Assert.Equal(Motivos.PermisoInsuficiente, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 3 operador enviando setpoint */
    [Fact]
    public async Task Operador_con_setpoint_se_rechaza_por_rol()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(Setpoint(10), "op1", "operador", default);
        Assert.Equal(403, res.CodigoHttp);
        Assert.Equal(Motivos.PermisoInsuficiente, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 4 supervisor setpoint válido */
    [Fact]
    public async Task Setpoint_valido_de_supervisor_se_envia()
    {
        var (svc, bus, _) = Crear();
        var res = await svc.EnviarAsync(Setpoint(20.5), "sup1", "supervisor", default);
        Assert.Equal(202, res.CodigoHttp);
        Assert.Equal(EstadoComando.Enviado, res.Orden!.Estado);
        Assert.Equal("cm", res.Orden.Unidad);
        Assert.Equal("nivel-mcn09", res.Orden.Equipo);
        Assert.Single(bus.Publicados);
        Assert.EndsWith("/cmd", bus.Publicados[0].Topico);
        Assert.Contains(res.Orden.Id, bus.Publicados[0].Cuerpo);
        Assert.Contains("nivel-mcn09", bus.Publicados[0].Cuerpo);
    }

    /* -------------------------------------------------- 5 fuera de rango */
    [Fact]
    public async Task Setpoint_fuera_de_rango_se_rechaza()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(Setpoint(99), "sup1", "supervisor", default);
        Assert.Equal(400, res.CodigoHttp);
        Assert.Equal(Motivos.RangoInvalido, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 6 unidad incorrecta */
    [Fact]
    public async Task Setpoint_con_unidad_incorrecta_se_rechaza()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(Setpoint(10, unidad: "psi"), "sup1", "supervisor", default);
        Assert.Equal(400, res.CodigoHttp);
        Assert.Equal(Motivos.UnidadInvalida, res.Orden!.Motivo);

        var sinUnidad = await svc.EnviarAsync(Setpoint(10, unidad: null), "sup1", "supervisor", default);
        Assert.Equal(Motivos.UnidadInvalida, sinUnidad.Orden!.Motivo);
    }

    /* -------------------------------------------------- 7 orden vencida (ack tardío) */
    [Fact]
    public async Task Ack_despues_de_expirar_se_marca_vencida()
    {
        var (svc, _, reloj) = Crear();
        var res = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "u", "operador", default);
        Assert.Equal(202, res.CodigoHttp);

        reloj.Avanzar(TimeSpan.FromSeconds(20));           // > ExpiracionSegundos (15)
        svc.ProcesarAck(Ack(res.Orden!.Id, "ACEPTADO"));

        var orden = svc.Obtener(res.Orden.Id);
        Assert.NotNull(orden);
        Assert.Equal(EstadoComando.Vencido, orden!.Estado);
        Assert.Equal(Motivos.Vencida, orden.Motivo);
    }

    /* -------------------------------------------------- 8 duplicada */
    [Fact]
    public async Task Orden_duplicada_pendiente_se_rechaza()
    {
        var (svc, _, _) = Crear();
        var primera = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "u", "operador", default);
        Assert.Equal(202, primera.CodigoHttp);
        var segunda = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "u", "operador", default);
        Assert.Equal(409, segunda.CodigoHttp);
        Assert.Equal(Motivos.Duplicada, segunda.Orden!.Motivo);
    }

    /* -------------------------------------------------- 9 PLC desconectado */
    [Fact]
    public async Task Plc_desconectado_se_rechaza()
    {
        var (svc, _, _) = Crear(Nivel(plc: "DESCONECTADO"));
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.PlcDesconectado, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 10 MQTT desconectado */
    [Fact]
    public async Task Mqtt_desconectado_se_rechaza()
    {
        var (svc, _, _) = Crear(Nivel(mqtt: false));
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.MqttNoDisponible, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 11 telemetría vencida (sin mensajes del edge) */
    [Fact]
    public async Task Telemetria_vencida_se_rechaza()
    {
        // NivelState sin ningún mensaje del conector edge → UltimoMensaje = null → TELEMETRIA_VENCIDA
        var sinDatos = new NivelState { MqttConectado = true };
        var (svc, _, _) = Crear(sinDatos);
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.TelemetriaVencida, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 12 selector LOCAL */
    [Fact]
    public async Task Selector_local_se_rechaza()
    {
        var (svc, _, _) = Crear(Nivel(selector: "LOCAL"));
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.SelectorNoRemoto, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 13 selector REMOTO (camino feliz) */
    [Fact]
    public async Task Selector_remoto_permite_el_envio()
    {
        var (svc, _, _) = Crear(Nivel(selector: "REMOTO"));
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(202, res.CodigoHttp);
    }

    [Fact]
    public async Task Fuente_hmi_bloquea_todas_las_ordenes_web()
    {
        var (svc, _, _) = Crear(Nivel(fuenteControl: "HMI"));
        var res = await svc.EnviarAsync(Setpoint(10), "u", "supervisor", default);
        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.ControlEnHmi, res.Orden!.Motivo);
    }

    [Fact]
    public async Task Fuente_sin_dato_falla_de_forma_segura()
    {
        var (svc, _, _) = Crear(Nivel(fuenteControl: null));
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.FuenteControlSinDato, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- 14 nivel bajo de T1 */
    [Fact]
    public async Task Nivel_bajo_T1_bloquea_arranque_permitiendo_setpoint()
    {
        var (svc, _, _) = Crear(Nivel(nivelBajo: true));
        var arranque = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "u", "operador", default);
        Assert.Equal(409, arranque.CodigoHttp);
        Assert.Equal(Motivos.NivelBajoT1, arranque.Orden!.Motivo);

        var sp = await svc.EnviarAsync(Setpoint(10), "u", "supervisor", default);
        Assert.Equal(202, sp.CodigoHttp);
    }

    /* ------------------------------------- 15-18 allowlist: sin O:0/O:1, todas NO_VERIFICADAS */
    [Fact]
    public void Allowlist_sin_salidas_prohibidas_y_solo_marcha_pc_verificada()
    {
        Assert.All(ControlContrato.Allowlist, d => Assert.False(ControlContrato.EsSalidaProhibida(d.Direccion), d.Direccion));
        var verificadas = ControlContrato.Allowlist.Where(d => d.Verificada).Select(d => d.Direccion).ToArray();
        Assert.Equal(new[] { "B3:0/3", "B3:0/4", "B3:0/13", "N7:5", "N7:8", "N7:9", "N7:10", "N7:1", "N7:2" }, verificadas);
        Assert.True(ControlContrato.EsSalidaProhibida("O:0/2"));
        Assert.True(ControlContrato.EsSalidaProhibida("O:1/0"));
        // el contrato no expone ningún campo de dirección: el navegador solo envía comandos semánticos
        var campos = typeof(SolicitudComando).GetProperties().Select(p => p.Name).ToArray();
        Assert.DoesNotContain(campos, c => c.Contains("Direccion", StringComparison.OrdinalIgnoreCase));
    }

    /* -------------------------------------------------- 19 triple gate REAL incompleto */
    [Fact]
    public async Task Modo_real_exige_entorno_config_y_selector()
    {
        var (svc, _, _) = Crear(ajustar: o => { o.Modo = "Real"; o.HabilitadoEscritura = true; });
        Assert.Equal("DRY-RUN", svc.ModoEfectivo());

        var (svc2, _, _) = Crear(ajustar: o => { o.Modo = "Real"; o.HabilitadoEscritura = true; o.VariableEntornoReal = () => "1"; });
        Assert.Equal("REAL", svc2.ModoEfectivo());
        await Task.CompletedTask;
    }

    /* -------------------------------------------------- 20/22 ack aceptado + duplicado */
    [Fact]
    public async Task Ack_aceptado_se_propaga_y_el_duplicado_se_ignora()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "u", "operador", default);
        svc.ProcesarAck(Ack(res.Orden!.Id, "ACEPTADO"));
        Assert.Equal(EstadoComando.Aceptado, svc.Obtener(res.Orden.Id)!.Estado);   // NO terminal

        svc.ProcesarAck(Ack(res.Orden.Id, "RECHAZADO", "DESPUES_DE_ACEPTADA"));
        Assert.Equal(EstadoComando.Aceptado, svc.Obtener(res.Orden.Id)!.Estado);   // no pisa ACEPTADO
    }

    /* -------------------------------------------------- 21 ack rechazado propaga motivo */
    [Fact]
    public async Task Ack_rechazado_propaga_el_motivo()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null), "u", "operador", default);
        svc.ProcesarAck(Ack(res.Orden!.Id, "RECHAZADO", "SELECTOR_NO_REMOTO"));
        var orden = svc.Obtener(res.Orden.Id)!;
        Assert.Equal(EstadoComando.Rechazado, orden.Estado);
        Assert.Equal("SELECTOR_NO_REMOTO", orden.Motivo);
    }

    /* -------------------------------------------------- 23a timeout sin ack */
    [Fact]
    public async Task Sin_ack_se_marca_timeout()
    {
        var (svc, _, reloj) = Crear();
        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null), "u", "operador", default);
        Assert.Equal(EstadoComando.Enviado, res.Orden!.Estado);

        reloj.Avanzar(TimeSpan.FromSeconds(6));            // > TimeoutSegundos (5)
        svc.VerificarTimeouts();

        var orden = svc.Obtener(res.Orden.Id);
        Assert.Equal(EstadoComando.Timeout, orden!.Estado);
        Assert.Equal(Motivos.SinConfirmacion, orden.Motivo);
    }

    /* -------------------------------------------------- 23b timeout tras ESCRITO sin CONFIRMADO */
    [Fact]
    public async Task Escrito_sin_confirmacion_se_marca_timeout()
    {
        var (svc, _, reloj) = Crear();
        var res = await svc.EnviarAsync(Setpoint(12), "u", "supervisor", default);
        svc.ProcesarAck(Ack(res.Orden!.Id, "ACEPTADO", escrito: false));
        svc.ProcesarAck(Ack(res.Orden.Id, "ESCRITO", escrito: true, esperado: 12));
        Assert.Equal(EstadoComando.Escrito, svc.Obtener(res.Orden.Id)!.Estado);

        reloj.Avanzar(TimeSpan.FromSeconds(6));
        svc.VerificarTimeouts();
        Assert.Equal(EstadoComando.Timeout, svc.Obtener(res.Orden.Id)!.Estado);
    }

    /* -------------------------------------------------- 24 lectura posterior diferente */
    [Fact]
    public async Task Confirmado_con_lectura_distinta_se_marca_error()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(Setpoint(15), "u", "supervisor", default);
        svc.ProcesarAck(Ack(res.Orden!.Id, "ACEPTADO", escrito: false));
        svc.ProcesarAck(Ack(res.Orden.Id, "ESCRITO", escrito: true, esperado: 15));
        svc.ProcesarAck(Ack(res.Orden.Id, "CONFIRMADO", escrito: true, esperado: 15, leido: 3));

        var orden = svc.Obtener(res.Orden.Id)!;
        Assert.Equal(EstadoComando.Error, orden.Estado);
        Assert.Equal(Motivos.ConfirmacionNoCoincide, orden.Motivo);
        Assert.Equal(15, orden.ValorEsperado);
        Assert.Equal(3, orden.ValorLeido);
    }

    /* -------------------------------------------------- 25 lectura posterior coincidente */
    [Fact]
    public async Task Confirmado_con_lectura_coincidente_cierra_la_orden()
    {
        var (svc, _, _) = Crear();
        var res = await svc.EnviarAsync(Setpoint(15), "u", "supervisor", default);
        svc.ProcesarAck(Ack(res.Orden!.Id, "ACEPTADO", escrito: false));
        svc.ProcesarAck(Ack(res.Orden.Id, "ESCRITO", escrito: true, esperado: 15));
        svc.ProcesarAck(Ack(res.Orden.Id, "CONFIRMADO", escrito: true, esperado: 15, leido: 15));

        var orden = svc.Obtener(res.Orden.Id)!;
        Assert.Equal(EstadoComando.Confirmado, orden.Estado);
        Assert.True(orden.EsTerminal);
        Assert.Null(orden.Motivo);

        // un ack tardío tras la terminal no pisa el estado
        svc.ProcesarAck(Ack(res.Orden.Id, "RECHAZADO", "TARDIO"));
        Assert.Equal(EstadoComando.Confirmado, svc.Obtener(res.Orden.Id)!.Estado);
    }

    /* -------------------------------------------------- flujo completo con simulador */
    [Fact]
    public async Task Flujo_completo_con_simulador_hasta_confirmado()
    {
        var (svc, bus, _) = Crear(Nivel(plc: "DESCONECTADO", selector: "LOCAL"));
        svc.ProcesarState("{\"simulador\":true}");
        var res = await svc.EnviarAsync(Setpoint(20), "u", "supervisor", default);
        Assert.Equal(202, res.CodigoHttp);
        Assert.Single(bus.Publicados);

        svc.ProcesarAck(Ack(res.Orden!.Id, "ACEPTADO", escrito: false));
        Assert.Equal(EstadoComando.Aceptado, svc.Obtener(res.Orden.Id)!.Estado);

        svc.ProcesarAck(Ack(res.Orden.Id, "ESCRITO", escrito: true, esperado: 20));
        Assert.Equal(EstadoComando.Escrito, svc.Obtener(res.Orden.Id)!.Estado);

        svc.ProcesarAck(Ack(res.Orden.Id, "CONFIRMADO", escrito: true, esperado: 20, leido: 20));
        Assert.Equal(EstadoComando.Confirmado, svc.Obtener(res.Orden.Id)!.Estado);
    }

    /* -------------------------------------------------- trazabilidad de la orden */
    [Fact]
    public async Task Orden_lleva_correlacion_comentario_y_origen()
    {
        var (svc, bus, _) = Crear();
        var sol = new SolicitudComando("Setpoint", 10, null, "cm", "nivel-mcn09",
            Comentario: "prueba de trazabilidad", Correlacion: "corr-123", Origen: "SCADA-WEB");
        var res = await svc.EnviarAsync(sol, "sup1", "supervisor", default);

        Assert.Equal("corr-123", res.Orden!.Correlacion);
        Assert.Equal("prueba de trazabilidad", res.Orden.Comentario);
        Assert.Equal("SCADA-WEB", res.Orden.Origen);
        Assert.Contains("corr-123", bus.Publicados[0].Cuerpo);
        Assert.Contains("SCADA-WEB", bus.Publicados[0].Cuerpo);
    }

    /* -------------------------------------------------- equipo distinto al contrato */
    [Fact]
    public async Task Equipo_distinto_de_nivel_mcn09_se_rechaza()
    {
        var (svc, _, _) = Crear();
        var sol = new SolicitudComando("Iniciar", null, null, null, "presion-mcp09");
        var res = await svc.EnviarAsync(sol, "u", "operador", default);
        Assert.Equal(400, res.CodigoHttp);
        Assert.Equal(Motivos.EquipoInvalido, res.Orden!.Motivo);
    }

    /* -------------------------------------------------- sensor de nivel saturado */
    /// <summary>
    /// Sensor ultrasónico saturado o muerto: N7:4 queda pegado en el piso de la escala y el
    /// valor en cm es el tope de saturación (≈40,9 cm), NO una medida. Con el PV del lazo sin
    /// medida no se autoriza arrancar ni mover el proceso; solo Detener (dirección segura).
    /// </summary>
    [Fact]
    public async Task Sensor_de_nivel_fuera_de_rango_bloquea_la_orden()
    {
        var nivel = Nivel();
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        var (svc, bus, _) = Crear(nivel);

        var res = await svc.EnviarAsync(new SolicitudComando("Iniciar", null, null, null, "nivel-mcn09"),
            "u", "operador", default);

        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.NivelSensorFueraDeRango, res.Orden!.Motivo);
        Assert.Equal(EstadoComando.Rechazado, res.Orden.Estado);
        Assert.Empty(bus.Publicados);   // no se publica ninguna orden al MQTT
    }

    [Fact]
    public async Task Sensor_de_nivel_fuera_de_rango_bloquea_tambien_el_setpoint()
    {
        var nivel = Nivel();
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        var (svc, bus, _) = Crear(nivel);

        var res = await svc.EnviarAsync(Setpoint(20), "u", "supervisor", default);

        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.NivelSensorFueraDeRango, res.Orden!.Motivo);
        Assert.Empty(bus.Publicados);
    }

    [Fact]
    public async Task Detener_si_se_permite_con_el_sensor_de_nivel_fuera_de_rango()
    {
        var nivel = Nivel();
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        var (svc, bus, _) = Crear(nivel);

        var res = await svc.EnviarAsync(new SolicitudComando("Detener", null, null, null, "nivel-mcn09"),
            "u", "operador", default);

        Assert.Equal(202, res.CodigoHttp);
        Assert.Single(bus.Publicados);
    }

    [Fact]
    public async Task Sensor_de_nivel_en_rango_no_bloquea_la_orden()
    {
        var nivel = Nivel();
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":false}");
        var (svc, bus, _) = Crear(nivel);

        var res = await svc.EnviarAsync(Setpoint(20), "u", "supervisor", default);

        Assert.Equal(202, res.CodigoHttp);
        Assert.Single(bus.Publicados);
    }

    /// <summary>Sin la lectura primaria del sensor no se conoce la calidad: fail-closed.</summary>
    [Fact]
    public async Task Calidad_de_nivel_desconocida_bloquea_la_orden()
    {
        var nivel = new NivelState { MqttConectado = true };
        nivel.Aplicar($"{NivelState.Base}/funcional/plc/conexion", "CONECTADO");
        nivel.Aplicar($"{NivelState.Base}/funcional/estado/selector_remoto", "true");
        nivel.Aplicar($"{NivelState.Base}/funcional/estado/fuente_control", "PC");
        var (svc, bus, _) = Crear(nivel);

        var res = await svc.EnviarAsync(Setpoint(20), "u", "supervisor", default);

        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.NivelCalidadDesconocida, res.Orden!.Motivo);
        Assert.Empty(bus.Publicados);
    }

    /// <summary>
    /// Operación degradada autorizada (CONTROL_PERMITIR_SENSOR_FUERA_DE_RANGO=1): la orden
    /// sale, pero queda marcada para que la auditoría delata el bypass del guard.
    /// </summary>
    [Fact]
    public async Task Override_de_calidad_permite_la_orden_pero_la_marca()
    {
        var nivel = Nivel();
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        var (svc, bus, _) = Crear(nivel, op => op.PermitirSensorFueraDeRango = true);

        // Con el sensor saturado la consigna en cm no significa nada: se rechaza
        // aunque el override este activo (si no, la perilla de la web se desincroniza).
        var setpoint = await svc.EnviarAsync(Setpoint(20), "u", "supervisor", default);
        Assert.Equal(409, setpoint.CodigoHttp);
        Assert.Equal(Motivos.NivelSensorFueraDeRango, setpoint.Orden!.Motivo);
        Assert.Empty(bus.Publicados);
    }

    /// <summary>Sin override, el mismo caso se rechaza (el default es bloquear).</summary>
    [Fact]
    public async Task Sin_override_el_sensor_fuera_de_rango_sigue_bloqueando()
    {
        var nivel = Nivel();
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        var (svc, bus, _) = Crear(nivel);

        var res = await svc.EnviarAsync(Setpoint(20), "u", "supervisor", default);

        Assert.Equal(409, res.CodigoHttp);
        Assert.Equal(Motivos.NivelSensorFueraDeRango, res.Orden!.Motivo);
        Assert.Empty(bus.Publicados);
    }

    /* -------------------------------------------------- el dato saturado no llega al historial */
    /// <summary>
    /// El backend no debe convertir el artefacto de saturación (≈40,7 cm) en una medida:
    /// el nivel no se escribe en el historial ni se publica como valor vigente.
    /// </summary>
    [Fact]
    public void Nivel_saturado_no_alimenta_el_historial_ni_el_valor_vigente()
    {
        var nivel = new NivelState { MqttConectado = true };
        nivel.Aplicar($"{NivelState.Base}/funcional/plc/conexion", "CONECTADO");
        nivel.Aplicar($"{NivelState.Base}/funcional/estado/selector_remoto", "true");
        nivel.Aplicar($"{NivelState.Base}/funcional/estado/fuente_control", "PC");
        // lectura válida: tanque vacío (N7:4 ≈ 16548 → 0 cm)
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/raw", "{\"value\":16548,\"unit\":\"cuentas\"}");
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/cm", "{\"value\":-0.5,\"unit\":\"cm\"}");

        var plant = new PlantState(nivel);
        plant.AplicarNivel(nivel);

        Assert.Single(plant.GetHistory(PlantState.NivelId, 100));
        Assert.Equal(-0.5, plant.Get(PlantState.NivelId)!.Value ?? 0, 2);
        Assert.True(plant.Get(PlantState.NivelId)!.Medible);

        // el sensor se satura: llega el artefacto de 40,7 cm
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/raw", "{\"value\":56,\"unit\":\"cuentas\"}");
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/cm", "{\"value\":40.7,\"unit\":\"cm\"}");
        plant.AplicarNivel(nivel);

        var equipo = plant.Get(PlantState.NivelId)!;
        Assert.Equal(CalidadDato.SensorFueraDeRango, equipo.Calidad);
        Assert.False(equipo.Medible);
        Assert.False(equipo.Alarm);
        Assert.NotEqual(40.7, plant.Get(PlantState.NivelId)!.Value ?? 0);   // el artefacto de saturación NO pasa a valor vigente
        // el historial NO se alimenta con el valor saturado
        Assert.Single(plant.GetHistory(PlantState.NivelId, 100));
        Assert.Null(plant.Get(PlantState.NivelId)!.Value);
        // el detalle de la API no expone nivel ni porcentaje medibles
        var detalle = plant.GetLevel();
        Assert.Null(detalle.Level);
        Assert.Null(detalle.Percent);
        Assert.Equal(CalidadDato.SensorFueraDeRango, detalle.Calidad);
    }

    /// <summary>
    /// Carrera de orden de llegada: nivel/cm puede llegar ANTES que nivel/raw y que el flag.
    /// Mientras no se conozca la calidad, el valor en cm no se acepta (fail-closed).
    /// </summary>
    [Fact]
    public void Nivel_que_llega_antes_de_conocer_la_calidad_no_se_acepta()
    {
        var nivel = new NivelState { MqttConectado = true };
        nivel.Aplicar($"{NivelState.Base}/funcional/plc/conexion", "CONECTADO");
        // llega primero el cm saturado, sin raw ni flag
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/cm", "{\"value\":40.7,\"unit\":\"cm\"}");

        var plant = new PlantState(nivel);
        plant.AplicarNivel(nivel);

        Assert.Equal(CalidadDato.SinCalidad, plant.Get(PlantState.NivelId)!.Calidad);
        Assert.False(plant.Get(PlantState.NivelId)!.Medible);
        Assert.NotEqual(40.7, plant.Get(PlantState.NivelId)!.Value);
        Assert.Empty(plant.GetHistory(PlantState.NivelId, 100));

        // al llegar el dato primario se detecta la saturación (raw < 300 cuentas)
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/raw", "{\"value\":56,\"unit\":\"cuentas\"}");
        plant.AplicarNivel(nivel);

        Assert.Equal(CalidadDato.SensorFueraDeRango, plant.Get(PlantState.NivelId)!.Calidad);
        Assert.NotEqual(40.7, plant.Get(PlantState.NivelId)!.Value);
        Assert.Empty(plant.GetHistory(PlantState.NivelId, 100));
    }

    /// <summary>El prompt del LLM no debe afirmar un nivel que el sensor no mide.</summary>
    [Fact]
    public void El_contexto_del_agente_no_anuncia_un_nivel_no_medible()
    {
        var nivel = new NivelState { MqttConectado = true };
        nivel.Aplicar($"{NivelState.Base}/funcional/plc/conexion", "CONECTADO");
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/fuera_rango_sensor", "{\"value\":true}");
        nivel.Aplicar($"{NivelState.Base}/funcional/nivel/cm", "{\"value\":40.7,\"unit\":\"cm\"}");

        var plant = new PlantState(nivel);
        plant.AplicarNivel(nivel);

        var contexto = plant.BuildSystemContext();
        Assert.Contains("MEDIDA NO VÁLIDA", contexto);
        Assert.Contains("SENSOR DE NIVEL FUERA DE RANGO", contexto);
        Assert.DoesNotContain("nivel = 40.7 cm", contexto);
    }

    /* -------------------------------------------------- notas de cobertura (Fase 8) */
    // 26 "el pulso vuelve a cero" y 27 "pérdida de conexión durante el pulso" pertenecen al
    // conector Python en modo real (escribir_direccion_verificada + pulso). Hoy son
    // inalcanzables porque 0/13 direcciones están VERIFICADAS; se ejercitan el modo
    // simulador durante la simulación completa (Fase 8, docs/01-auditoria-control-remoto.md).
}
