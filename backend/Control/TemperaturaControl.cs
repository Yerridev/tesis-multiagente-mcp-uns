using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.AspNetCore.SignalR;
using MQTTnet;
using MQTTnet.Client;
using MQTTnet.Protocol;

namespace MCP.Industrial.Api.Control;

/// <summary>Control real protegido del MCT-09: solo %M30 (marcha) y %MW100 (SP).</summary>
public sealed class TemperaturaControlOpciones
{
    public string Modo { get; set; } = "DryRun";
    public bool HabilitadoEscritura { get; set; }
    public int TimeoutSegundos { get; set; } = 15;
    public int ExpiracionSegundos { get; set; } = 20;
    public string TopicoBase { get; set; } = TemperaturaState.Base + "/control";
    public Func<string?> VariableEntornoReal { get; set; } = () => Environment.GetEnvironmentVariable("CONTROL_TEMPERATURA_REAL");
}

public static class TemperaturaControlContrato
{
    public const string Equipo = "temp-mct09";
    public const string Unidad = "C";
    public const int TelemetriaMaxSegundos = 15;
    public static string? Validar(SolicitudComando s, TipoComando tipo) => tipo switch
    {
        TipoComando.Setpoint when !string.Equals(s.Unidad, Unidad, StringComparison.OrdinalIgnoreCase) && !string.Equals(s.Unidad, "°C", StringComparison.OrdinalIgnoreCase) => Motivos.UnidadInvalida,
        TipoComando.Setpoint when s.Valor is null or < 15 or > 50 => Motivos.RangoInvalido,
        TipoComando.ParametroPid when s.Parametro?.ToLowerInvariant() is not ("kp" or "ti" or "td") => Motivos.TipoDesconocido,
        TipoComando.ParametroPid when s.Valor is null or < 0 or > 10000 || s.Valor % 1 != 0 => Motivos.RangoInvalido,
        TipoComando.Reiniciar or TipoComando.AbrirValvula or TipoComando.CerrarValvula or TipoComando.AjustarValvula => Motivos.TipoDesconocido,
        _ => null,
    };
}

public sealed class TemperaturaControlService
{
    private readonly TemperaturaState _state; private readonly TemperaturaControlOpciones _op; private readonly IHubContext<PlantHub> _hub; private readonly IConfiguration _cfg;
    private readonly ConcurrentDictionary<string, OrdenControl> _ordenes = new();
    public TemperaturaControlService(TemperaturaState s, TemperaturaControlOpciones o, IHubContext<PlantHub> h, IConfiguration c) => (_state,_op,_hub,_cfg)=(s,o,h,c);
    public bool RealArmado => _op.Modo.Equals("Real",StringComparison.OrdinalIgnoreCase) && _op.HabilitadoEscritura && _op.VariableEntornoReal()=="1";
    public object EstadoPublico() { var e=_state.UltimoMensaje is { } u?(DateTimeOffset.Now-u).TotalSeconds:double.PositiveInfinity; return new { modoEfectivo=RealArmado?"REAL":"BLOQUEADO",realArmado=RealArmado,proceso=new { plc=_state.PlcConectado?"CONECTADO":"DESCONECTADO",selector=_state.Modo(),fallaPrincipal=_state.Bool("falla/nivel_principal"),fallaEnfriador=_state.Bool("falla/nivel_enfriador")},telemetria=new {ultimo=_state.UltimoMensaje,edadSegundos=double.IsFinite(e)?Math.Round(e,1):(double?)null,fresca=e<=TemperaturaControlContrato.TelemetriaMaxSegundos},pendientes=_ordenes.Values.Count(x=>!x.EsTerminal)}; }
    public IEnumerable<object> Ultimas(int n)=>_ordenes.Values.OrderByDescending(x=>x.Expedida).Take(Math.Clamp(n,1,50)).Select(x=>x.ParaSenal());
    async Task<bool> Publicar(string cuerpo,CancellationToken ct) { try { var f=new MqttFactory(); using var c=f.CreateMqttClient(); await c.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(_cfg["Mqtt:Host"]??"127.0.0.1",int.TryParse(_cfg["Mqtt:Port"],out var p)?p:1883).WithClientId($"temp-cmd-{Guid.NewGuid():N}").Build(),ct); await c.PublishAsync(new MqttApplicationMessageBuilder().WithTopic(_op.TopicoBase+"/cmd").WithPayload(cuerpo).WithQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce).Build(),ct); await c.DisconnectAsync(); return true;}catch{return false;} }
    public async Task<ResultadoEnvio> Enviar(SolicitudComando s,string usuario,string rol,CancellationToken ct)
    {
        if(!string.Equals(s.Equipo,TemperaturaControlContrato.Equipo,StringComparison.OrdinalIgnoreCase)) return new(400,null,Motivos.EquipoInvalido);
        if(!ControlContrato.TryParseTipo(s.Tipo,out var tipo)) return new(400,null,Motivos.TipoDesconocido);
        if(!ControlContrato.RolSuficiente(rol,tipo)) return new(403,null,Motivos.PermisoInsuficiente);
        if(TemperaturaControlContrato.Validar(s,tipo) is { } inv) return new(400,null,inv);
        if(!RealArmado)return new(409,null,Motivos.RealNoArmado); if(!_state.PlcConectado)return new(409,null,Motivos.PlcDesconectado);
        if(_state.Modo()!="PC")return new(409,null,Motivos.SelectorNoRemoto);
        if(tipo==TipoComando.Iniciar&&(_state.Bool("falla/nivel_principal")==true||_state.Bool("falla/nivel_enfriador")==true))return new(409,null,Motivos.NivelBajoT1);
        if(_state.UltimoMensaje is not { } u||(DateTimeOffset.Now-u).TotalSeconds>TemperaturaControlContrato.TelemetriaMaxSegundos)return new(409,null,Motivos.TelemetriaVencida);
        var now=DateTimeOffset.Now; var o=new OrdenControl{Id=Guid.NewGuid().ToString("N"),Tipo=tipo,Valor=s.Valor,Parametro=s.Parametro,Unidad=s.Unidad,Equipo=TemperaturaControlContrato.Equipo,Comentario=s.Comentario,Correlacion=s.Correlacion,Origen=s.Origen,Usuario=usuario,Rol=rol,Modo="REAL",Expedida=now,Expira=now.AddSeconds(_op.ExpiracionSegundos),TimeoutEn=now.AddSeconds(_op.TimeoutSegundos),Estado=EstadoComando.Enviado,Actualizada=now}; _ordenes[o.Id]=o;
        if(!await Publicar(JsonSerializer.Serialize(o.ParaSenal(),new JsonSerializerOptions(JsonSerializerDefaults.Web)),ct)){o.Estado=EstadoComando.Error;o.Motivo=Motivos.MqttNoDisponible;return new(503,o,o.Motivo);} await _hub.Clients.All.SendAsync("temperaturaControlResultado",o.ParaSenal(),ct); return new(202,o,null);
    }
    public void Ack(string json){try{using var d=JsonDocument.Parse(json);var r=d.RootElement;var id=r.GetProperty("id").GetString();if(id is null||!_ordenes.TryGetValue(id,out var o)||o.EsTerminal)return;if(!Enum.TryParse<EstadoComando>(r.GetProperty("estado").GetString(),true,out var e))return;o.Estado=e;o.Actualizada=DateTimeOffset.Now;o.Motivo=r.TryGetProperty("motivo",out var m)?m.GetString():null;o.Escrito=r.TryGetProperty("escrito",out var w)&&w.ValueKind is JsonValueKind.True or JsonValueKind.False?w.GetBoolean():null;o.ValorLeido=r.TryGetProperty("valor_leido",out var l)&&l.TryGetDouble(out var v)?v:null;o.ValorEsperado=r.TryGetProperty("valor_esperado",out var x)&&x.TryGetDouble(out var q)?q:null;_=_hub.Clients.All.SendAsync("temperaturaControlResultado",o.ParaSenal());}catch{}}
    public void Timeouts(){foreach(var o in _ordenes.Values.Where(x=>!x.EsTerminal&&DateTimeOffset.Now>=x.TimeoutEn)){o.Estado=EstadoComando.Timeout;o.Motivo=Motivos.SinConfirmacion;o.Actualizada=DateTimeOffset.Now;}}
}

public sealed class TemperaturaControlMqttService:BackgroundService
{ private readonly TemperaturaControlService _c;private readonly TemperaturaControlOpciones _o;private readonly IConfiguration _cfg;public TemperaturaControlMqttService(TemperaturaControlService c,TemperaturaControlOpciones o,IConfiguration cfg)=>(_c,_o,_cfg)=(c,o,cfg); protected override async Task ExecuteAsync(CancellationToken stop){var f=new MqttFactory();while(!stop.IsCancellationRequested){try{using var c=f.CreateMqttClient();c.ApplicationMessageReceivedAsync+=e=>{var p=e.ApplicationMessage.PayloadSegment;_c.Ack(p.Count==0?"":System.Text.Encoding.UTF8.GetString(p.Array!,p.Offset,p.Count));return Task.CompletedTask;};await c.ConnectAsync(new MqttClientOptionsBuilder().WithTcpServer(_cfg["Mqtt:Host"]??"127.0.0.1",int.TryParse(_cfg["Mqtt:Port"],out var p)?p:1883).WithClientId("temp-control-api").Build(),stop);await c.SubscribeAsync(new MqttClientSubscribeOptionsBuilder().WithTopicFilter(x=>x.WithTopic(_o.TopicoBase+"/ack")).Build(),stop);while(!stop.IsCancellationRequested&&c.IsConnected){_c.Timeouts();await Task.Delay(1000,stop);}}catch(OperationCanceledException){break;}catch{await Task.Delay(3000,stop);}}}}
