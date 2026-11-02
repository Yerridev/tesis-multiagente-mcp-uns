using System.Text;
using System.Text.Json;

namespace MCP.Industrial.Api.Control;

/// <summary>Registro de auditoría: append-only en JSONL + búfer en memoria para consultas.</summary>
public sealed record EventoAuditoria(
    DateTimeOffset Ts,
    string Accion,
    string? OrdenId,
    string Usuario,
    string Rol,
    string Resultado,
    string? Detalle);

public sealed class ControlAuditoria
{
    private readonly object _sync = new();
    private readonly Queue<EventoAuditoria> _recientes = new();
    private readonly string? _rutaArchivo;
    private readonly ILogger<ControlAuditoria>? _log;
    private const int MaxRecientes = 500;

    public ControlAuditoria(string? carpeta = null, ILogger<ControlAuditoria>? log = null)
    {
        _log = log;
        try
        {
            var carpetaFinal = string.IsNullOrWhiteSpace(carpeta)
                ? Path.Combine(AppContext.BaseDirectory, "auditoria")
                : carpeta;
            Directory.CreateDirectory(carpetaFinal);
            _rutaArchivo = Path.Combine(carpetaFinal, $"control-{DateTimeOffset.Now:yyyyMMdd}.jsonl");
        }
        catch (Exception ex)
        {
            _log?.LogWarning(ex, "Auditoría de control sin archivo (solo memoria)");
            _rutaArchivo = null;
        }
    }

    public void Registrar(string accion, string? ordenId, string usuario, string rol, string resultado, string? detalle)
    {
        var ev = new EventoAuditoria(DateTimeOffset.Now, accion, ordenId, usuario, rol, resultado, detalle);
        lock (_sync)
        {
            _recientes.Enqueue(ev);
            while (_recientes.Count > MaxRecientes) _recientes.Dequeue();
        }

        if (_rutaArchivo is null) return;
        try
        {
            var linea = JsonSerializer.Serialize(ev);
            File.AppendAllText(_rutaArchivo, linea + Environment.NewLine, Encoding.UTF8);
        }
        catch (Exception ex)
        {
            _log?.LogWarning(ex, "No se pudo escribir la auditoría de control");
        }
    }

    public IReadOnlyList<EventoAuditoria> Ultimas(int limit)
    {
        limit = Math.Clamp(limit <= 0 ? 50 : limit, 1, MaxRecientes);
        lock (_sync) return _recientes.Reverse().Take(limit).ToArray();
    }
}
