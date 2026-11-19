using System.Net.Sockets;
using System.Text.Json;
using MCP.Industrial.Api;
using MCP.Industrial.Api.Auth;
using MCP.Industrial.Api.Control;
using Microsoft.AspNetCore.StaticFiles;

var builder = WebApplication.CreateBuilder(args);

/* Modo agents: instancia separada SOLO de agentes/lectura (contenedor "agents").
   No registra el servicio de control ni sus endpoints: los agentes no pueden
   publicar Ã³rdenes ni tocar MQTT de control. */
var agentsOnly = string.Equals(builder.Configuration["AGENTS_ONLY"] ?? Environment.GetEnvironmentVariable("AGENTS_ONLY"), "1", StringComparison.Ordinal);

builder.Services.AddCors(o => o.AddDefaultPolicy(p => p.WithOrigins("http://localhost:5173").AllowAnyHeader().AllowAnyMethod().AllowCredentials()));
builder.Services.AddSignalR();
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.Converters.Add(new System.Text.Json.Serialization.JsonStringEnumConverter()));
builder.Services.AddSingleton<NivelState>();
builder.Services.AddSingleton<CaudalState>();
builder.Services.AddSingleton<PresionState>();
builder.Services.AddSingleton<TemperaturaState>();
builder.Services.AddSingleton<PlantState>();
builder.Services.AddHostedService<NivelMqttService>();
builder.Services.AddHostedService<CaudalMqttService>();
builder.Services.AddHostedService<PresionMqttService>();
builder.Services.AddHostedService<TemperaturaMqttService>();
builder.Services.AddHostedService<PlantSimulator>();
builder.Services.AddHttpClient("openrouter");
builder.Services.AddSingleton<OpenRouterAgent>();
builder.Services.AddSingleton<ContextoAgente>();
builder.Services.AddSingleton<ConversacionesStore>();
builder.Services.AddSingleton<AgentService>();
builder.Services.AddSingleton<OrquestadorMultiagente>();

/* ------------------------- USUARIOS Y SESIONES (TimescaleDB, esquema seguridad) -------------------------
   Con Auth:Conexion definida, TODO /api y /hubs exige sesión (salvo /api/health y el login).
   El primer admin sale del .env (ADMIN_USUARIO / ADMIN_PASSWORD); nunca del código.
   Sin cadena de conexión (p. ej. `dotnet run` local) la autenticación queda deshabilitada. */
var authOp = new AuthOpciones
{
    Habilitado = !string.Equals(builder.Configuration["Auth:Habilitado"], "false", StringComparison.OrdinalIgnoreCase),
    Conexion = builder.Configuration["Auth:Conexion"],
    HorasSesion = int.TryParse(builder.Configuration["Auth:HorasSesion"], out var hsAuth) ? hsAuth : 8,
    AdminUsuario = builder.Configuration["Auth:AdminUsuario"],
    AdminPassword = builder.Configuration["Auth:AdminPassword"],
    TokenServicio = builder.Configuration["Auth:TokenServicio"],
};
if (string.IsNullOrWhiteSpace(authOp.Conexion)) authOp.Habilitado = false;
builder.Services.AddSingleton(authOp);
builder.Services.AddSingleton<SeguridadStore>();

/* ------------------------- CONTROL (dry-run por defecto, sin escrituras al PLC) ------------------------- */
if (!agentsOnly)
{
    var ctrl = new ControlOpciones
    {
        Modo = builder.Configuration["Control:Modo"] ?? "DryRun",
        HabilitadoEscritura = bool.TryParse(builder.Configuration["Control:HabilitadoEscritura"], out var he) && he,
        TimeoutSegundos = int.TryParse(builder.Configuration["Control:TimeoutSegundos"], out var ts) ? ts : 10,
        ExpiracionSegundos = int.TryParse(builder.Configuration["Control:ExpiracionSegundos"], out var es) ? es : 15,
        VentanaDuplicadosSegundos = int.TryParse(builder.Configuration["Control:VentanaDuplicadosSegundos"], out var vs) ? vs : 30,
        TopicoBase = builder.Configuration["Control:TopicoBase"] ?? (NivelState.Base + "/control"),
AuditoriaRuta = builder.Configuration["Control:AuditoriaRuta"],
    };
    /* Operación degradada: permite expedir órdenes con el sensor de nivel saturado.
       Por defecto está DESHABILITADO. La variable de entorno tiene prioridad porque es la
       decisión operativa del laboratorio; queda registrada en la auditoría de cada orden. */
    if (bool.TryParse(builder.Configuration["Control:PermitirSensorFueraDeRango"], out var psfr)) ctrl.PermitirSensorFueraDeRango = psfr;
    var envSfr = builder.Configuration["CONTROL_PERMITIR_SENSOR_FUERA_DE_RANGO"]
                 ?? Environment.GetEnvironmentVariable("CONTROL_PERMITIR_SENSOR_FUERA_DE_RANGO");
    if (!string.IsNullOrWhiteSpace(envSfr))
        ctrl.PermitirSensorFueraDeRango = envSfr.Trim() == "1" || envSfr.Trim().Equals("true", StringComparison.OrdinalIgnoreCase);
    foreach (var u in builder.Configuration.GetSection("Control:Usuarios").GetChildren())
        ctrl.Usuarios[u.Key] = u.Value ?? "viewer";
    // con usuarios reales, las claves dev-… dejan de funcionar
    if (authOp.Habilitado) ctrl.Usuarios.Clear();
    builder.Services.AddSingleton(ctrl);
    builder.Services.AddSingleton(new ControlAuditoria(ctrl.AuditoriaRuta));
    builder.Services.AddSingleton<IComandoTransporte, MqttComandoTransporte>();
    builder.Services.AddSingleton<Func<DateTimeOffset>>(() => DateTimeOffset.Now);
    builder.Services.AddSingleton<ControlService>();
    builder.Services.AddHostedService<ControlMqttService>();

    var caudalCtrl = new CaudalControlOpciones
    {
        Modo = builder.Configuration["ControlCaudal:Modo"] ?? "DryRun",
        HabilitadoEscritura = bool.TryParse(builder.Configuration["ControlCaudal:HabilitadoEscritura"], out var ce) && ce,
        TimeoutSegundos = int.TryParse(builder.Configuration["ControlCaudal:TimeoutSegundos"], out var cts) ? cts : 12,
        ExpiracionSegundos = int.TryParse(builder.Configuration["ControlCaudal:ExpiracionSegundos"], out var ces) ? ces : 20,
        TopicoBase = builder.Configuration["ControlCaudal:TopicoBase"] ?? CaudalState.Base + "/control",
    };
    builder.Services.AddSingleton(caudalCtrl);
    builder.Services.AddSingleton<CaudalControlService>();
    builder.Services.AddHostedService<CaudalControlMqttService>();

    var presionCtrl = new PresionControlOpciones
    {
        Modo = builder.Configuration["ControlPresion:Modo"] ?? "DryRun",
        HabilitadoEscritura = bool.TryParse(builder.Configuration["ControlPresion:HabilitadoEscritura"], out var pe) && pe,
        TimeoutSegundos = int.TryParse(builder.Configuration["ControlPresion:TimeoutSegundos"], out var pts) ? pts : 12,
        ExpiracionSegundos = int.TryParse(builder.Configuration["ControlPresion:ExpiracionSegundos"], out var pes) ? pes : 20,
        TopicoBase = builder.Configuration["ControlPresion:TopicoBase"] ?? PresionState.Base + "/control",
    };
    builder.Services.AddSingleton(presionCtrl);
    builder.Services.AddSingleton<PresionControlService>();
    builder.Services.AddHostedService<PresionControlMqttService>();

    var tempCtrl = new TemperaturaControlOpciones
    {
        Modo = builder.Configuration["ControlTemperatura:Modo"] ?? "DryRun",
        HabilitadoEscritura = bool.TryParse(builder.Configuration["ControlTemperatura:HabilitadoEscritura"], out var te) && te,
        TimeoutSegundos = int.TryParse(builder.Configuration["ControlTemperatura:TimeoutSegundos"], out var tts) ? tts : 15,
        ExpiracionSegundos = int.TryParse(builder.Configuration["ControlTemperatura:ExpiracionSegundos"], out var tes) ? tes : 20,
        TopicoBase = builder.Configuration["ControlTemperatura:TopicoBase"] ?? TemperaturaState.Base + "/control",
    };
    builder.Services.AddSingleton(tempCtrl);
    builder.Services.AddSingleton<TemperaturaControlService>();
    builder.Services.AddHostedService<TemperaturaControlMqttService>();
}

var app = builder.Build();
app.UseCors();

var seguridad = app.Services.GetRequiredService<SeguridadStore>();
if (authOp.Habilitado) _ = Task.Run(() => seguridad.InicializarAsync(app.Lifetime.ApplicationStopping));
else app.Logger.LogWarning("Autenticación DESHABILITADA (sin Auth:Conexion o Auth:Habilitado=false): se usan las claves dev-…");

static string? IpDe(HttpContext ctx)
{
    var f = ctx.Request.Headers["X-Forwarded-For"].ToString().Split(',')[0].Trim();
    return f.Length > 0 ? f : ctx.Connection.RemoteIpAddress?.ToString();
}
static SesionActiva? SesionDe(HttpContext ctx) => ctx.Items["auth.sesion"] as SesionActiva;

/* Puerta de sesión: /api/* y /hubs/* exigen un token válido (cabecera Bearer; en /hubs también
   ?access_token= porque los WebSockets del navegador no envían cabeceras). */
app.Use(async (ctx, next) =>
{
    var ruta = ctx.Request.Path;
    var esHub = ruta.StartsWithSegments("/hubs");
    var publica = ruta.StartsWithSegments("/api/health") || ruta.StartsWithSegments("/api/auth/login") || ruta.StartsWithSegments("/api/auth/estado");
    if (!authOp.Habilitado || publica || !(esHub || ruta.StartsWithSegments("/api"))) { await next(); return; }
    if (!seguridad.Listo)
    {
        ctx.Response.StatusCode = 503;
        await ctx.Response.WriteAsJsonAsync(new { error = "SEGURIDAD_NO_DISPONIBLE", detalle = seguridad.ErrorInicio });
        return;
    }
    var cab = ctx.Request.Headers.Authorization.ToString();
    var token = cab.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase) ? cab[7..].Trim() : null;
    if (string.IsNullOrEmpty(token) && esHub) token = ctx.Request.Query["access_token"].ToString();
    var sesion = string.IsNullOrEmpty(token) ? null : await seguridad.ValidarAsync(token);
    if (sesion is null)
    {
        ctx.Response.StatusCode = 401;
        await ctx.Response.WriteAsJsonAsync(new { error = "SESION_INVALIDA" });
        return;
    }
    ctx.Items["auth.sesion"] = sesion;
    ctx.Items["auth.token"] = token;
    await next();
});

/* null = permitido; si no, la respuesta 401/403. Sin autenticación habilitada no restringe. */
IResult? Requiere(HttpContext ctx, string rolMinimo)
{
    if (!authOp.Habilitado) return null;
    var s = SesionDe(ctx);
    if (s is null) return Results.Json(new { error = "SESION_INVALIDA" }, statusCode: 401);
    return ControlAuth.AlMenos(s.Rol, rolMinimo) ? null : Results.Json(new { error = "PERMISO_INSUFICIENTE", requiere = rolMinimo }, statusCode: 403);
}
IResult? SoloConAuth() => authOp.Habilitado
    ? (seguridad.Listo ? null : Results.Json(new { error = "SEGURIDAD_NO_DISPONIBLE", detalle = seguridad.ErrorInicio }, statusCode: 503))
    : Results.Json(new { error = "AUTENTICACION_DESHABILITADA" }, statusCode: 409);

/* ---------------------------- salud de contenedores ----------------------------
   /health/live  : el proceso responde (no depende de nada externo).
   /health/ready : API activa + Mosquitto accesible + base de datos SOLO si estÃ¡
                   habilitada (Health:DatabaseEnabled). El PLC NUNCA es requisito de
                   arranque: se reporta como dependencia industrial degradada. */
static async Task<(bool Ok, string Detalle)> ProbarTcpAsync(string host, int puerto, int ms)
{
    try
    {
        using var c = new TcpClient();
        var t = c.ConnectAsync(host, puerto);
        if (await Task.WhenAny(t, Task.Delay(ms)) != t) return (false, "timeout");
        return c.Connected ? (true, "ok") : (false, "sin conexion");
    }
    catch (Exception ex)
    {
        return (false, ex.Message);
    }
}

app.MapGet("/health/live", () => Results.Ok(new { status = "live", ts = DateTimeOffset.Now }));

app.MapGet("/health/ready", async (IConfiguration cfg, NivelState nivel) =>
{
    var mqttHost = cfg["Mqtt:Host"] ?? "127.0.0.1";
    var mqttPort = int.TryParse(cfg["Mqtt:Port"], out var mp) ? mp : 1883;
    var (mqttOk, mqttDet) = await ProbarTcpAsync(mqttHost, mqttPort, 2000);

    bool dbHabilitada = string.Equals(cfg["Health:DatabaseEnabled"] ?? "false", "true", StringComparison.OrdinalIgnoreCase);
    bool dbOk = true;
    string dbDet = "deshabilitada";
    if (dbHabilitada)
    {
        var dbHost = cfg["Health:DatabaseHost"] ?? "timescaledb";
        var dbPort = int.TryParse(cfg["Health:DatabasePort"], out var dp) ? dp : 5432;
        (dbOk, dbDet) = await ProbarTcpAsync(dbHost, dbPort, 2000);
    }

    var plcOk = nivel.plcConectado;
    var listo = mqttOk && dbOk;
    return Results.Json(new
    {
        status = listo ? "ready" : "degraded",
        checks = new { api = true, mqtt = new { ok = mqttOk, detalle = mqttDet }, database = new { habilitada = dbHabilitada, ok = dbOk, detalle = dbDet } },
        // El PLC no bloquea el arranque: es una dependencia industrial que puede estar apagada.
        dependenciaIndustrial = new { plc = plcOk ? "CONECTADO" : "DEGRADADA", detalle = "no es requisito de arranque" },
        modoControl = agentsOnly ? "AGENTES-SOLO-LECTURA" : (cfg["Control:Modo"] ?? "DryRun"),
        ts = DateTimeOffset.Now,
    }, statusCode: listo ? 200 : 503);
});

/* HTML, JS y CSS nunca se cachean: cada compilaciÃ³n del frontend se ve al instante (sin Ctrl+F5). */
void SinCacheHtml(StaticFileResponseContext ctx)
{
    var path = ctx.Context.Request.Path.Value ?? string.Empty;
    if (path.EndsWith(".html", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".js", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".css", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".svg", StringComparison.OrdinalIgnoreCase))
        ctx.Context.Response.Headers.CacheControl = "no-cache";
}

/* AutenticaciÃ³n Bearer de desarrollo para el control (clave â†’ rol en Control:Usuarios). */
(string? Rol, string? Usuario, IResult? Fallo) Autenticar(ControlOpciones op, HttpContext ctx, string? rolMinimo = null)
{
    var (rol, clave, error) = ControlAuth.Resolver(op, ctx);
    if (error is not null)
        return (null, null, Results.Json(new { error = Motivos.SinAutenticacion }, statusCode: error));
    if (rolMinimo is not null && !ControlAuth.AlMenos(rol, rolMinimo))
        return (null, null, Results.Json(new { error = Motivos.PermisoInsuficiente }, statusCode: 403));
    return (rol, clave, null);
}

app.UseDefaultFiles();
app.UseStaticFiles(new StaticFileOptions { OnPrepareResponse = SinCacheHtml });
app.MapGet("/api/health", () => Results.Ok(new { status = "healthy", service = "MCP Industrial API", timestamp = DateTimeOffset.Now }));

/* ------------------------------------------- autenticación ------------------------------------------- */
app.MapGet("/api/auth/estado", () => Results.Ok(new { habilitado = authOp.Habilitado, listo = seguridad.Listo, horasSesion = authOp.HorasSesion }));
app.MapPost("/api/auth/login", async (SolicitudLogin sol, HttpContext ctx) =>
{
    if (SoloConAuth() is { } no) return no;
    var (s, token, error) = await seguridad.LoginAsync(sol.Usuario, sol.Password, IpDe(ctx), ctx.Request.Headers.UserAgent.ToString());
    if (s is null) return Results.Json(new { error }, statusCode: error == "DEMASIADOS_INTENTOS" ? 429 : 401);
    return Results.Ok(new { token, usuario = s.Usuario, nombre = s.Nombre, rol = s.Rol, expira = s.Expira });
});
app.MapPost("/api/auth/logout", async (HttpContext ctx) =>
{
    if (SesionDe(ctx) is { } s && ctx.Items["auth.token"] is string t && s.UsuarioId > 0) await seguridad.LogoutAsync(t, s.Usuario, IpDe(ctx));
    return Results.Ok(new { ok = true });
});
app.MapGet("/api/auth/yo", (HttpContext ctx) => SesionDe(ctx) is { } s
    ? Results.Ok(new { habilitado = true, usuario = s.Usuario, nombre = s.Nombre, rol = s.Rol, expira = s.Expira })
    : Results.Ok(new { habilitado = false, usuario = "local", nombre = "Sin autenticación", rol = "admin" }));
app.MapGet("/api/auth/usuarios", async (HttpContext ctx) =>
    SoloConAuth() ?? Requiere(ctx, "admin") ?? Results.Ok(await seguridad.UsuariosAsync()));
app.MapPost("/api/auth/usuarios", async (SolicitudUsuario sol, HttpContext ctx) =>
{
    if ((SoloConAuth() ?? Requiere(ctx, "admin")) is { } no) return no;
    var error = await seguridad.CrearAsync(sol.Usuario, sol.Nombre, sol.Rol, sol.Password, SesionDe(ctx)!.Usuario, IpDe(ctx));
    return error is null ? Results.Ok(new { ok = true }) : Results.BadRequest(new { error });
});
app.MapPut("/api/auth/usuarios/{id:int}", async (int id, SolicitudUsuario sol, HttpContext ctx) =>
{
    if ((SoloConAuth() ?? Requiere(ctx, "admin")) is { } no) return no;
    var error = await seguridad.ActualizarAsync(id, sol.Nombre, sol.Rol, sol.Activo,
        string.IsNullOrEmpty(sol.Password) ? null : sol.Password, SesionDe(ctx)!, IpDe(ctx));
    return error is null ? Results.Ok(new { ok = true }) : Results.BadRequest(new { error });
});
app.MapGet("/api/auth/accesos", async (HttpContext ctx, int? limit) =>
    SoloConAuth() ?? Requiere(ctx, "admin") ?? Results.Ok(await seguridad.AccesosAsync(limit ?? 200)));

app.MapGet("/api/equipment", (PlantState plant) => Results.Ok(plant.GetAll()));
app.MapGet("/api/equipment/{id}", (string id, PlantState plant) => plant.Get(id) is { } item ? Results.Ok(item) : Results.NotFound());
app.MapGet("/api/equipment/nivel-mcn09/signals", (NivelState nivel) => Results.Ok(nivel.Snapshot()));
app.MapGet("/api/equipment/caudal-mcc09/signals", (CaudalState caudal) => Results.Ok(caudal.Snapshot()));
app.MapGet("/api/equipment/presion-mcp09/signals", (PresionState presion) => Results.Ok(presion.Snapshot()));
app.MapGet("/api/equipment/temp-mct09/signals", (TemperaturaState temperatura) => Results.Ok(temperatura.Snapshot()));
app.MapGet("/api/equipment/{id}/detail", (string id, PlantState plant) =>
    id == "nivel-mcn09" ? Results.Ok(plant.GetLevel()) : Results.NotFound(new { error = "Detalle disponible solo para nivel-mcn09" }));
app.MapGet("/api/history", (PlantState plant, string? equipmentId, int? limit) => Results.Ok(plant.GetHistory(equipmentId, limit ?? 300)));
app.MapGet("/api/agent/tools", () => Results.Ok(PlantState.Tools()));
/* Posiciones de los nodos de cada lienzo (y lados de las flechas), guardadas en el servidor:
   así se ven igual en cualquier navegador/PC y en el panel del sistema multiagente.
   Archivo por módulo en Lienzo:Ruta (registros/lienzos en la PC). */
var lienzoDir = app.Configuration["Lienzo:Ruta"] ?? Path.Combine(AppContext.BaseDirectory, "lienzos");
var lienzoIdOk = new System.Text.RegularExpressions.Regex("^[a-z0-9-]{3,40}$");
app.MapGet("/api/lienzo/{id}/layout", (string id) =>
{
    if (!lienzoIdOk.IsMatch(id)) return Results.BadRequest();
    var f = Path.Combine(lienzoDir, id + ".json");
    return File.Exists(f) ? Results.Text(File.ReadAllText(f), "application/json") : Results.NotFound();
});
app.MapPut("/api/lienzo/{id}/layout", async (string id, HttpContext ctx) =>
{
    if (!lienzoIdOk.IsMatch(id)) return Results.BadRequest();
    using var lector = new StreamReader(ctx.Request.Body);
    var cuerpo = await lector.ReadToEndAsync();
    if (cuerpo.Length > 200_000) return Results.BadRequest(new { error = "DEMASIADO_GRANDE" });
    try { using var _ = JsonDocument.Parse(cuerpo); } catch { return Results.BadRequest(new { error = "JSON_INVALIDO" }); }
    Directory.CreateDirectory(lienzoDir);
    await File.WriteAllTextAsync(Path.Combine(lienzoDir, id + ".json"), cuerpo);
    return Results.Ok(new { ok = true });
});

/* Servidores MCP reales del sistema multiagente (catálogo retenido del orquestador, bat 31) */
app.MapGet("/api/mcp/catalogo", async (OrquestadorMultiagente multi, CancellationToken ct) =>
{
    var enLinea = await multi.EnLineaAsync(ct);
    var cat = await multi.CatalogoAsync(ct);
    return Results.Ok(new { disponible = enLinea && cat is not null, catalogo = cat });
});
app.MapGet("/api/agent/status", async (AgentService agent, OrquestadorMultiagente multi, CancellationToken ct) =>
{
    var st = JsonSerializer.SerializeToElement(agent.Status());
    var d = st.EnumerateObject().ToDictionary(p => p.Name, p => (object?)p.Value);
    d["multiagente"] = await multi.EnLineaAsync(ct);
    return Results.Ok(d);
});
app.MapPost("/api/agent/ask", async (AgentAskRequest request, HttpContext ctx, AgentService agent, OrquestadorMultiagente multi, ConversacionesStore chats, CancellationToken token) =>
{
    /* 1º el SISTEMA MULTIAGENTE MCP (Python, bat 31): intérprete → 4 analistas con su servidor MCP → veredicto.
       Si no está corriendo, responde el agente clásico y se avisa. */
    var pregunta = (request.Message ?? "").Trim();
    var reply = await multi.PreguntarAsync(pregunta.Length > 0 ? pregunta : "¿Cómo está la planta ahora?", request.History, request.Model, SesionDe(ctx)?.Usuario, token);
    if (reply is null)
    {
        reply = await agent.AskAsync(request.Message, token, request.Model, request.History);
        reply = reply with { Reply = "ℹ️ Sistema multiagente no disponible (abre el bat 31); respondió el agente clásico.\n\n" + reply.Reply };
    }
    // cada pregunta/respuesta queda registrada en su conversacion (registros/conversaciones), con su usuario
    var id = chats.Registrar(request.ConversacionId, request.Origen, (request.Message ?? "").Trim(), reply, SesionDe(ctx)?.Usuario);
    return Results.Ok(reply with { ConversacionId = id });
});
/* cada usuario ve sus chats; supervisor y admin ven todos (evidencia de la tesis) */
bool VeTodosLosChats(HttpContext ctx) => !authOp.Habilitado || ControlAuth.AlMenos(SesionDe(ctx)?.Rol, "supervisor");
app.MapGet("/api/agent/conversaciones", (HttpContext ctx, ConversacionesStore chats) =>
    Results.Ok(chats.Listar(VeTodosLosChats(ctx) ? null : SesionDe(ctx)?.Usuario ?? "-")));
app.MapGet("/api/agent/conversaciones/{id}", (string id, HttpContext ctx, ConversacionesStore chats) =>
    chats.Leer(id) is { } c && (VeTodosLosChats(ctx) || c.Usuario == SesionDe(ctx)?.Usuario) ? Results.Ok(c) : Results.NotFound());

/* --------------------------------- API de control (NO en modo agents) --------------------------------- */
if (!agentsOnly)
{
    app.MapGet("/api/control/contrato", (ControlService c) => Results.Ok(c.ContratoPublico()));

    app.MapGet("/api/control/estado", (HttpContext ctx, ControlOpciones op, ControlService c) =>
    {
        var (_, usuario, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        return Results.Ok(new { usuario, datos = c.EstadoPublico() });
    });

    app.MapPost("/api/control/nivel/comandos", async (HttpContext ctx, ControlOpciones op, ControlService c, SolicitudComando sol, CancellationToken ct) =>
    {
        var (rol, usuario, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        var res = await c.EnviarAsync(sol, usuario ?? "desconocido", rol ?? "viewer", ct);
        return Results.Json(res.Orden ?? (object)new { error = res.Error }, statusCode: res.CodigoHttp);
    });

    app.MapGet("/api/control/nivel/comandos", (HttpContext ctx, ControlOpciones op, ControlService c, int? limit) =>
    {
        var (_, _, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        return Results.Ok(c.Ultimas(limit ?? 10).Select(o => o.ParaSenal()));
    });

    app.MapGet("/api/control/nivel/comandos/{id}", (HttpContext ctx, ControlOpciones op, ControlService c, string id) =>
    {
        var (_, _, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        return c.Obtener(id) is { } orden ? Results.Ok(orden.ParaSenal()) : Results.NotFound(new { error = "ORDEN_NO_ENCONTRADA" });
    });

    app.MapGet("/api/control/auditoria", (HttpContext ctx, ControlOpciones op, ControlAuditoria aud, int? limit) =>
    {
        var (_, _, fallo) = Autenticar(op, ctx, "supervisor");
        if (fallo is not null) return fallo;
        return Results.Ok(aud.Ultimas(limit ?? 50));
    });

    app.MapGet("/api/control/caudal/estado", (HttpContext ctx, ControlOpciones op, CaudalControlService c) =>
    {
        var (_, usuario, fallo) = Autenticar(op, ctx);
        return fallo ?? Results.Ok(new { usuario, datos = c.EstadoPublico() });
    });

    app.MapPost("/api/control/caudal/comandos", async (HttpContext ctx, ControlOpciones op, CaudalControlService c, SolicitudComando sol, CancellationToken ct) =>
    {
        var (rol, usuario, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        var res = await c.Enviar(sol, usuario ?? "desconocido", rol ?? "viewer", ct);
        return Results.Json(res.Orden ?? (object)new { error = res.Error }, statusCode: res.CodigoHttp);
    });

    app.MapGet("/api/control/caudal/comandos", (HttpContext ctx, ControlOpciones op, CaudalControlService c, int? limit) =>
    {
        var (_, _, fallo) = Autenticar(op, ctx);
        return fallo ?? Results.Ok(c.Ultimas(limit ?? 10));
    });

    app.MapGet("/api/control/presion/estado", (HttpContext ctx, ControlOpciones op, PresionControlService c) =>
    {
        var (_, usuario, fallo) = Autenticar(op, ctx);
        return fallo ?? Results.Ok(new { usuario, datos = c.EstadoPublico() });
    });

    app.MapPost("/api/control/presion/comandos", async (HttpContext ctx, ControlOpciones op, PresionControlService c, SolicitudComando sol, CancellationToken ct) =>
    {
        var (rol, usuario, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        var res = await c.Enviar(sol, usuario ?? "desconocido", rol ?? "viewer", ct);
        return Results.Json(res.Orden ?? (object)new { error = res.Error }, statusCode: res.CodigoHttp);
    });

    app.MapGet("/api/control/presion/comandos", (HttpContext ctx, ControlOpciones op, PresionControlService c, int? limit) =>
    {
        var (_, _, fallo) = Autenticar(op, ctx);
        return fallo ?? Results.Ok(c.Ultimas(limit ?? 10));
    });

    app.MapGet("/api/control/temperatura/estado", (HttpContext ctx, ControlOpciones op, TemperaturaControlService c) =>
    {
        var (_, usuario, fallo) = Autenticar(op, ctx);
        return fallo ?? Results.Ok(new { usuario, datos = c.EstadoPublico() });
    });
    app.MapPost("/api/control/temperatura/comandos", async (HttpContext ctx, ControlOpciones op, TemperaturaControlService c, SolicitudComando sol, CancellationToken ct) =>
    {
        var (rol, usuario, fallo) = Autenticar(op, ctx);
        if (fallo is not null) return fallo;
        var res = await c.Enviar(sol, usuario ?? "desconocido", rol ?? "viewer", ct);
        return Results.Json(res.Orden ?? (object)new { error = res.Error }, statusCode: res.CodigoHttp);
    });
    app.MapGet("/api/control/temperatura/comandos", (HttpContext ctx, ControlOpciones op, TemperaturaControlService c, int? limit) =>
    {
        var (_, _, fallo) = Autenticar(op, ctx);
        return fallo ?? Results.Ok(c.Ultimas(limit ?? 10));
    });
}

/* ------------------------- PLANTA SIMULADA (MODO_PLANTA=simulado) -------------------------
   Una sola planta simulada (simulador/*.py) para SCADA, lienzos y agentes. En modo simulado las
   llaves manuales del mimico (V1..V7, VF) se mandan al simulador por MQTT (broker Windows, el mismo
   del control de caudal). En modo real este endpoint rechaza: las llaves reales son de mano. */
var modoPlanta = string.Equals((Environment.GetEnvironmentVariable("MODO_PLANTA") ?? app.Configuration["Planta:Modo"] ?? "real").Trim(),
    "simulado", StringComparison.OrdinalIgnoreCase) ? "simulado" : "real";
var basesSim = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
{
    ["nivel-mcn09"] = NivelState.Base, ["caudal-mcc09"] = CaudalState.Base,
    ["presion-mcp09"] = PresionState.Base, ["temp-mct09"] = TemperaturaState.Base, ["temperatura-mct09"] = TemperaturaState.Base,
};
async Task<bool> PublicarSim(IConfiguration cfg, string topico, string cuerpo, CancellationToken ct)
{
    try
    {
        var host = cfg["Mqtt:CaudalControlHost"] ?? cfg["Mqtt:Host"] ?? "127.0.0.1";
        var port = int.TryParse(cfg["Mqtt:CaudalControlPort"], out var p) ? p : 1883;
        var factory = new MQTTnet.MqttFactory(); using var client = factory.CreateMqttClient();
        await client.ConnectAsync(new MQTTnet.Client.MqttClientOptionsBuilder().WithTcpServer(host, port)
            .WithClientId($"sim-llave-{Guid.NewGuid():N}").Build(), ct);
        await client.PublishAsync(new MQTTnet.MqttApplicationMessageBuilder().WithTopic(topico).WithPayload(cuerpo)
            .WithQualityOfServiceLevel(MQTTnet.Protocol.MqttQualityOfServiceLevel.AtLeastOnce).Build(), ct);
        await client.DisconnectAsync(new MQTTnet.Client.MqttClientDisconnectOptions(), ct);
        return true;
    }
    catch { return false; }
}
app.MapGet("/api/planta/modo", () => Results.Ok(new { modo = modoPlanta }));
if (!agentsOnly) app.MapPost("/api/sim/llave", async (SolicitudLlave sol, HttpContext ctx, IConfiguration cfg, CancellationToken ct) =>
{
    if (Requiere(ctx, "operador") is { } no) return no;
    if (modoPlanta != "simulado") return Results.Json(new { error = "PLANTA_REAL: las llaves reales son manuales" }, statusCode: 409);
    if (sol.Modulo is null || !basesSim.TryGetValue(sol.Modulo, out var b)) return Results.BadRequest(new { error = "MODULO_DESCONOCIDO" });
    var id = (sol.Id ?? "").Trim().ToUpperInvariant();
    if (!System.Text.RegularExpressions.Regex.IsMatch(id, "^(V[1-7]|VF)$")) return Results.BadRequest(new { error = "LLAVE_DESCONOCIDA" });
    var cuerpo = System.Text.Json.JsonSerializer.Serialize(new { id, abierta = sol.Abierta, ts = DateTimeOffset.Now });
    return await PublicarSim(cfg, b + "/sim/cmd/llave", cuerpo, ct)
        ? Results.Ok(new { ok = true, modulo = sol.Modulo, id, abierta = sol.Abierta })
        : Results.Json(new { error = "MQTT_NO_DISPONIBLE" }, statusCode: 503);
});
if (!agentsOnly) app.MapPost("/api/sim/reiniciar", async (SolicitudLlave sol, HttpContext ctx, IConfiguration cfg, CancellationToken ct) =>
{
    if (Requiere(ctx, "operador") is { } no) return no;
    if (modoPlanta != "simulado") return Results.Json(new { error = "PLANTA_REAL" }, statusCode: 409);
    if (sol.Modulo is null || !basesSim.TryGetValue(sol.Modulo, out var b)) return Results.BadRequest(new { error = "MODULO_DESCONOCIDO" });
    return await PublicarSim(cfg, b + "/sim/cmd/reiniciar", "{}", ct) ? Results.Ok(new { ok = true }) : Results.Json(new { error = "MQTT_NO_DISPONIBLE" }, statusCode: 503);
});

app.MapHub<PlantHub>("/hubs/plant");
app.MapFallbackToFile("index.html", new StaticFileOptions { OnPrepareResponse = SinCacheHtml });
app.Run();

public record AgentAskRequest(string? Message, string? Model = null, List<TurnoChat>? History = null, string? ConversacionId = null, string? Origen = null);
public record TurnoChat(string? Rol, string? Texto);
public record SolicitudLlave(string? Modulo, string? Id, bool Abierta);
public record SolicitudLogin(string? Usuario, string? Password);
public record SolicitudUsuario(string? Usuario, string? Nombre, string? Rol, string? Password, bool? Activo);
