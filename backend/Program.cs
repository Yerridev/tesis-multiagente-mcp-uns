using System.Net.Sockets;
using MCP.Industrial.Api;
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
builder.Services.AddSingleton<AgentService>();

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
    foreach (var u in builder.Configuration.GetSection("Control:Usuarios").GetChildren())
        ctrl.Usuarios[u.Key] = u.Value ?? "viewer";
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
app.MapGet("/api/agent/status", (AgentService agent) => Results.Ok(agent.Status()));
app.MapPost("/api/agent/ask", async (AgentAskRequest request, AgentService agent, CancellationToken token) =>
{
    var reply = await agent.AskAsync(request.Message, token);
    return Results.Ok(reply);
});

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

app.MapHub<PlantHub>("/hubs/plant");
app.MapFallbackToFile("index.html", new StaticFileOptions { OnPrepareResponse = SinCacheHtml });
app.Run();

public record AgentAskRequest(string? Message);
