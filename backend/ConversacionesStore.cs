using System.Text.Json;
using System.Text.RegularExpressions;

namespace MCP.Industrial.Api;

/// <summary>Un mensaje guardado de una conversación con el agente.</summary>
public sealed record MensajeGuardado(string Rol, string Texto, DateTimeOffset Ts, string? Modelo = null, string? Modo = null,
    IReadOnlyList<AgentCall>? Herramientas = null, long? Ms = null);

/// <summary>Conversación completa (un archivo JSON por conversación).</summary>
public sealed class Conversacion
{
    public string Id { get; set; } = "";
    public string Origen { get; set; } = "agentes";
    /// <summary>Usuario que inició el chat (null en chats previos a la autenticación).</summary>
    public string? Usuario { get; set; }
    public string Titulo { get; set; } = "";
    public DateTimeOffset Creada { get; set; }
    public DateTimeOffset Actualizada { get; set; }
    public List<MensajeGuardado> Mensajes { get; set; } = [];
}

/// <summary>
/// Registro de chats con los agentes: cada conversación se guarda como JSON en
/// Agente:ConversacionesRuta (por defecto /data/conversaciones, montado en registros/conversaciones).
/// Sirve de evidencia para la tesis (qué se preguntó, qué respondió, con qué modelo y en cuánto tiempo).
/// </summary>
public sealed class ConversacionesStore
{
    private static readonly Regex IdValido = new("^[A-Za-z0-9-]{8,64}$", RegexOptions.Compiled);
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly string _dir;
    private readonly object _sync = new();

    public ConversacionesStore(IConfiguration cfg)
    {
        _dir = cfg["Agente:ConversacionesRuta"] ?? Path.Combine(AppContext.BaseDirectory, "conversaciones");
        try { Directory.CreateDirectory(_dir); } catch { /* sin disco: se intenta al guardar */ }
    }

    private string Ruta(string id) => Path.Combine(_dir, id + ".json");

    public Conversacion? Leer(string id)
    {
        if (!IdValido.IsMatch(id)) return null;
        lock (_sync)
        {
            try { return File.Exists(Ruta(id)) ? JsonSerializer.Deserialize<Conversacion>(File.ReadAllText(Ruta(id)), Json) : null; }
            catch { return null; }
        }
    }

    /// <summary>Agrega la pregunta y la respuesta; crea la conversación si no existe. Devuelve su id.</summary>
    public string Registrar(string? id, string? origen, string pregunta, AgentReply r, string? usuario = null)
    {
        lock (_sync)
        {
            var conv = (id is not null && IdValido.IsMatch(id) ? Leer(id) : null) ?? new Conversacion
            {
                Id = $"{DateTimeOffset.Now.ToOffset(TimeSpan.FromHours(-5)):yyyyMMdd-HHmmss}-{Guid.NewGuid():N}"[..24],
                Origen = string.IsNullOrWhiteSpace(origen) ? "agentes" : origen.Trim()[..Math.Min(40, origen.Trim().Length)],
                Titulo = pregunta.Length > 70 ? pregunta[..70] + "…" : pregunta,
                Creada = DateTimeOffset.Now,
                Usuario = usuario,
            };
            var llm = r.Tools.FirstOrDefault(t => t.Name == "consulta_openrouter");
            conv.Mensajes.Add(new MensajeGuardado("user", pregunta, DateTimeOffset.Now));
            conv.Mensajes.Add(new MensajeGuardado("agente", r.Reply, r.Ts, r.Model, r.Mode, r.Tools, llm?.Ms));
            conv.Actualizada = DateTimeOffset.Now;
            try
            {
                Directory.CreateDirectory(_dir);
                File.WriteAllText(Ruta(conv.Id), JsonSerializer.Serialize(conv, Json));
            }
            catch { /* el chat sigue funcionando aunque no se pueda guardar */ }
            return conv.Id;
        }
    }

    /// <param name="usuario">null = todas; si no, solo las de ese usuario.</param>
    public IReadOnlyList<object> Listar(string? usuario = null, int max = 200)
    {
        lock (_sync)
        {
            if (!Directory.Exists(_dir)) return [];
            return Directory.GetFiles(_dir, "*.json")
                .OrderByDescending(File.GetLastWriteTimeUtc).Take(max)
                .Select(f => { try { return JsonSerializer.Deserialize<Conversacion>(File.ReadAllText(f), Json); } catch { return null; } })
                .Where(c => c is not null && (usuario is null || c.Usuario == usuario))
                .Select(c => (object)new
                {
                    id = c!.Id, origen = c.Origen, usuario = c.Usuario, titulo = c.Titulo, creada = c.Creada, actualizada = c.Actualizada,
                    mensajes = c.Mensajes.Count,
                    modelos = c.Mensajes.Where(m => m.Modelo is not null).Select(m => m.Modelo!).Distinct().ToArray(),
                })
                .ToList();
        }
    }
}
