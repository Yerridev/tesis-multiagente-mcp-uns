namespace MCP.Industrial.Api.Control;

/// <summary>Autenticación por Bearer de desarrollo (clave → rol) definida en Control:Usuarios.</summary>
public static class ControlAuth
{
    private static int Rango(string? rol) => rol?.ToLowerInvariant() switch
    {
        "admin" => 4,
        "supervisor" => 3,
        "operador" => 2,
        "viewer" => 1,
        _ => 0,
    };

    /// <summary>¿Tiene el rol indicado o superior?</summary>
    public static bool AlMenos(string? rol, string rolMinimo) => Rango(rol) >= Rango(rolMinimo);

    /// <summary>Devuelve rol + clave (usuario para auditoría) o un código de error HTTP (401).</summary>
    public static (string? Rol, string? Clave, int? Error) Resolver(ControlOpciones op, HttpContext ctx)
    {
        var cabecera = ctx.Request.Headers.Authorization.ToString();
        if (string.IsNullOrWhiteSpace(cabecera)) return (null, null, 401);
        if (!cabecera.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase)) return (null, null, 401);
        var clave = cabecera["Bearer ".Length..].Trim();
        foreach (var (k, rol) in op.Usuarios)
        {
            if (string.Equals(k, clave, StringComparison.Ordinal)) return (rol, k, null);
        }
        return (null, null, 401);
    }
}
