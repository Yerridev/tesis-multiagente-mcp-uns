using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;
using Npgsql;

namespace MCP.Industrial.Api.Auth;

/// <summary>Opciones de autenticación (sección Auth). Sin conexión a la base, la autenticación queda deshabilitada.</summary>
public sealed class AuthOpciones
{
    public bool Habilitado { get; set; } = true;
    public string? Conexion { get; set; }
    public int HorasSesion { get; set; } = 8;
    public string? AdminUsuario { get; set; }
    public string? AdminPassword { get; set; }
    /// <summary>Token fijo de solo lectura (rol viewer) para el servidor MCP y las pruebas (SERVICIO_TOKEN del .env).</summary>
    public string? TokenServicio { get; set; }
}

public sealed record SesionActiva(int UsuarioId, string Usuario, string Nombre, string Rol, DateTimeOffset Expira);
public sealed record UsuarioVista(int Id, string Usuario, string Nombre, string Rol, bool Activo, DateTimeOffset Creado, DateTimeOffset? UltimoAcceso);
public sealed record AccesoVista(long Id, DateTimeOffset Ts, string Usuario, string Evento, string? Ip, string? Detalle);

public static class Roles
{
    public static readonly string[] Todos = ["viewer", "operador", "supervisor", "admin"];
    public static bool Valido(string? r) => r is not null && Todos.Contains(r);
}

/// <summary>
/// Usuarios, sesiones e historial de accesos en TimescaleDB (esquema "seguridad").
/// Contraseñas: PBKDF2-SHA256 (210 000 iteraciones, sal aleatoria). Sesiones: token aleatorio
/// de 256 bits; en la base solo se guarda su SHA-256. Las tablas se crean solas al arrancar.
/// </summary>
public sealed class SeguridadStore(AuthOpciones op, ILogger<SeguridadStore> log)
{
    private const int Iteraciones = 210_000;
    private static readonly TimeSpan CacheSesion = TimeSpan.FromSeconds(30);
    private readonly ConcurrentDictionary<string, (SesionActiva S, DateTimeOffset Hasta)> _cache = new();
    private readonly ConcurrentDictionary<string, List<DateTimeOffset>> _fallos = new();
    private NpgsqlDataSource? _db;

    public bool Listo { get; private set; }
    public string? ErrorInicio { get; private set; }

    private NpgsqlDataSource Db => _db ?? throw new InvalidOperationException("BASE_DE_DATOS_NO_DISPONIBLE");

    // ------------------------------------------------------------------ inicio
    public async Task InicializarAsync(CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(op.Conexion)) { ErrorInicio = "sin cadena de conexión (Auth:Conexion)"; return; }
        _db = NpgsqlDataSource.Create(op.Conexion);
        for (var intento = 1; intento <= 30 && !ct.IsCancellationRequested; intento++)
        {
            try
            {
                await using (var c = Db.CreateCommand(Esquema)) await c.ExecuteNonQueryAsync(ct);
                await SembrarAdminAsync(ct);
                Listo = true; ErrorInicio = null;
                log.LogInformation("Seguridad lista (usuarios en TimescaleDB, esquema seguridad)");
                return;
            }
            catch (Exception ex) when (!ct.IsCancellationRequested)
            {
                ErrorInicio = ex.Message;
                log.LogWarning("Base de seguridad no disponible ({Error}); reintento {N}/30 en 4 s", ex.Message, intento);
                await Task.Delay(4000, ct);
            }
        }
    }

    private const string Esquema = """
        CREATE SCHEMA IF NOT EXISTS seguridad;
        CREATE TABLE IF NOT EXISTS seguridad.usuarios (
            id            serial PRIMARY KEY,
            usuario       text NOT NULL UNIQUE,
            nombre        text NOT NULL,
            rol           text NOT NULL CHECK (rol IN ('viewer','operador','supervisor','admin')),
            hash          text NOT NULL,
            activo        boolean NOT NULL DEFAULT true,
            creado        timestamptz NOT NULL DEFAULT now(),
            ultimo_acceso timestamptz
        );
        CREATE TABLE IF NOT EXISTS seguridad.sesiones (
            token_hash text PRIMARY KEY,
            usuario_id integer NOT NULL REFERENCES seguridad.usuarios(id),
            creada     timestamptz NOT NULL DEFAULT now(),
            expira     timestamptz NOT NULL,
            ip         text,
            agente     text,
            revocada   boolean NOT NULL DEFAULT false
        );
        CREATE TABLE IF NOT EXISTS seguridad.accesos (
            id      bigserial PRIMARY KEY,
            ts      timestamptz NOT NULL DEFAULT now(),
            usuario text NOT NULL,
            evento  text NOT NULL,
            ip      text,
            detalle text
        );
        CREATE INDEX IF NOT EXISTS accesos_ts_idx ON seguridad.accesos (ts DESC);
        DELETE FROM seguridad.sesiones WHERE expira < now() - interval '7 days';
        """;

    private async Task SembrarAdminAsync(CancellationToken ct)
    {
        await using var cnt = Db.CreateCommand("SELECT count(*) FROM seguridad.usuarios");
        if (Convert.ToInt64(await cnt.ExecuteScalarAsync(ct)) > 0) return;
        var u = (op.AdminUsuario ?? "").Trim().ToLowerInvariant();
        if (u.Length == 0 || string.IsNullOrEmpty(op.AdminPassword))
        {
            log.LogWarning("No hay usuarios y faltan ADMIN_USUARIO / ADMIN_PASSWORD en el .env: nadie podrá entrar");
            return;
        }
        await using var ins = Db.CreateCommand("INSERT INTO seguridad.usuarios (usuario, nombre, rol, hash) VALUES (@u, @n, 'admin', @h)");
        ins.Parameters.AddWithValue("u", u);
        ins.Parameters.AddWithValue("n", "Administrador");
        ins.Parameters.AddWithValue("h", Hash(op.AdminPassword));
        await ins.ExecuteNonQueryAsync(ct);
        await RegistrarAsync(u, "usuario_creado", null, "admin inicial desde .env");
        log.LogInformation("Usuario administrador inicial creado: {Usuario}", u);
    }

    // ------------------------------------------------------------------ contraseñas y tokens
    public static string Hash(string password)
    {
        var sal = RandomNumberGenerator.GetBytes(16);
        var h = Rfc2898DeriveBytes.Pbkdf2(Encoding.UTF8.GetBytes(password), sal, Iteraciones, HashAlgorithmName.SHA256, 32);
        return $"pbkdf2-sha256${Iteraciones}${Convert.ToBase64String(sal)}${Convert.ToBase64String(h)}";
    }

    public static bool Verificar(string password, string guardado)
    {
        var p = guardado.Split('$');
        if (p.Length != 4 || p[0] != "pbkdf2-sha256" || !int.TryParse(p[1], out var it)) return false;
        var sal = Convert.FromBase64String(p[2]);
        var esperado = Convert.FromBase64String(p[3]);
        var h = Rfc2898DeriveBytes.Pbkdf2(Encoding.UTF8.GetBytes(password), sal, it, HashAlgorithmName.SHA256, esperado.Length);
        return CryptographicOperations.FixedTimeEquals(h, esperado);
    }

    private static string Sha(string token) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(token)));

    public static string? ValidarPassword(string? p) =>
        string.IsNullOrEmpty(p) || p.Length < 8 ? "La contraseña debe tener al menos 8 caracteres" : null;

    // ------------------------------------------------------------------ login / sesiones
    /// <summary>Máx. 5 intentos fallidos por usuario+IP cada 10 minutos.</summary>
    private bool Bloqueado(string clave)
    {
        if (!_fallos.TryGetValue(clave, out var l)) return false;
        lock (l) { l.RemoveAll(t => t < DateTimeOffset.UtcNow.AddMinutes(-10)); return l.Count >= 5; }
    }

    private void Fallo(string clave)
    {
        var l = _fallos.GetOrAdd(clave, _ => []);
        lock (l) l.Add(DateTimeOffset.UtcNow);
    }

    public async Task<(SesionActiva? Sesion, string? Token, string? Error)> LoginAsync(string? usuario, string? password, string? ip, string? agente)
    {
        var u = (usuario ?? "").Trim().ToLowerInvariant();
        if (u.Length == 0 || string.IsNullOrEmpty(password)) return (null, null, "CREDENCIALES_INCOMPLETAS");
        var clave = $"{u}|{ip}";
        if (Bloqueado(clave)) { await RegistrarAsync(u, "login_bloqueado", ip, "demasiados intentos"); return (null, null, "DEMASIADOS_INTENTOS"); }

        int id; string nombre, rol, hash; bool activo;
        await using (var c = Db.CreateCommand("SELECT id, nombre, rol, hash, activo FROM seguridad.usuarios WHERE usuario = @u"))
        {
            c.Parameters.AddWithValue("u", u);
            await using var r = await c.ExecuteReaderAsync();
            if (!await r.ReadAsync())
            {
                Fallo(clave); await RegistrarAsync(u, "login_fallido", ip, "usuario inexistente");
                return (null, null, "CREDENCIALES_INVALIDAS");
            }
            (id, nombre, rol, hash, activo) = (r.GetInt32(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetBoolean(4));
        }
        if (!Verificar(password, hash))
        {
            Fallo(clave); await RegistrarAsync(u, "login_fallido", ip, "contraseña incorrecta");
            return (null, null, "CREDENCIALES_INVALIDAS");
        }
        if (!activo) { await RegistrarAsync(u, "login_fallido", ip, "usuario desactivado"); return (null, null, "USUARIO_DESACTIVADO"); }

        var token = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).TrimEnd('=').Replace('+', '-').Replace('/', '_');
        DateTimeOffset expira;
        await using (var c = Db.CreateCommand("""
            INSERT INTO seguridad.sesiones (token_hash, usuario_id, expira, ip, agente)
            VALUES (@t, @id, now() + make_interval(hours => @h), @ip, @ag) RETURNING expira
            """))
        {
            c.Parameters.AddWithValue("t", Sha(token));
            c.Parameters.AddWithValue("id", id);
            c.Parameters.AddWithValue("h", Math.Clamp(op.HorasSesion, 1, 72));
            c.Parameters.AddWithValue("ip", (object?)ip ?? DBNull.Value);
            c.Parameters.AddWithValue("ag", (object?)Recortar(agente, 200) ?? DBNull.Value);
            expira = await c.ExecuteScalarAsync() is DateTime d ? Utc(d) : DateTimeOffset.UtcNow.AddHours(op.HorasSesion);
        }
        await using (var c = Db.CreateCommand("UPDATE seguridad.usuarios SET ultimo_acceso = now() WHERE id = @id"))
        { c.Parameters.AddWithValue("id", id); await c.ExecuteNonQueryAsync(); }
        _fallos.TryRemove(clave, out _);
        await RegistrarAsync(u, "login_ok", ip, null);
        return (new SesionActiva(id, u, nombre, rol, expira), token, null);
    }

    public async Task<SesionActiva?> ValidarAsync(string token)
    {
        if (!string.IsNullOrEmpty(op.TokenServicio) && op.TokenServicio.Length >= 16 &&
            CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(token), Encoding.UTF8.GetBytes(op.TokenServicio)))
            return new SesionActiva(0, "servicio-mcp", "Servicio MCP (solo lectura)", "viewer", DateTimeOffset.UtcNow.AddHours(1));
        if (_db is null) return null;
        var h = Sha(token);
        if (_cache.TryGetValue(h, out var c) && c.Hasta > DateTimeOffset.UtcNow && c.S.Expira > DateTimeOffset.UtcNow) return c.S;
        try
        {
            await using var cmd = Db.CreateCommand("""
                SELECT u.id, u.usuario, u.nombre, u.rol, s.expira
                FROM seguridad.sesiones s JOIN seguridad.usuarios u ON u.id = s.usuario_id
                WHERE s.token_hash = @t AND NOT s.revocada AND s.expira > now() AND u.activo
                """);
            cmd.Parameters.AddWithValue("t", h);
            await using var r = await cmd.ExecuteReaderAsync();
            if (!await r.ReadAsync()) { _cache.TryRemove(h, out _); return null; }
            var s = new SesionActiva(r.GetInt32(0), r.GetString(1), r.GetString(2), r.GetString(3),
                new DateTimeOffset(DateTime.SpecifyKind(r.GetDateTime(4), DateTimeKind.Utc)));
            _cache[h] = (s, DateTimeOffset.UtcNow + CacheSesion);
            return s;
        }
        catch { return null; }
    }

    public async Task LogoutAsync(string token, string usuario, string? ip)
    {
        var h = Sha(token);
        _cache.TryRemove(h, out _);
        await using var c = Db.CreateCommand("UPDATE seguridad.sesiones SET revocada = true WHERE token_hash = @t");
        c.Parameters.AddWithValue("t", h);
        await c.ExecuteNonQueryAsync();
        await RegistrarAsync(usuario, "logout", ip, null);
    }

    private async Task RevocarSesionesAsync(int usuarioId)
    {
        await using var c = Db.CreateCommand("UPDATE seguridad.sesiones SET revocada = true WHERE usuario_id = @id AND NOT revocada");
        c.Parameters.AddWithValue("id", usuarioId);
        await c.ExecuteNonQueryAsync();
        foreach (var (k, v) in _cache) if (v.S.UsuarioId == usuarioId) _cache.TryRemove(k, out _);
    }

    // ------------------------------------------------------------------ historial
    public async Task RegistrarAsync(string usuario, string evento, string? ip, string? detalle)
    {
        try
        {
            await using var c = Db.CreateCommand("INSERT INTO seguridad.accesos (usuario, evento, ip, detalle) VALUES (@u, @e, @ip, @d)");
            c.Parameters.AddWithValue("u", Recortar(usuario, 60) ?? "?");
            c.Parameters.AddWithValue("e", evento);
            c.Parameters.AddWithValue("ip", (object?)ip ?? DBNull.Value);
            c.Parameters.AddWithValue("d", (object?)Recortar(detalle, 300) ?? DBNull.Value);
            await c.ExecuteNonQueryAsync();
        }
        catch (Exception ex) { log.LogWarning("No se pudo registrar el acceso: {Error}", ex.Message); }
    }

    public async Task<List<AccesoVista>> AccesosAsync(int limite)
    {
        var l = new List<AccesoVista>();
        await using var c = Db.CreateCommand("SELECT id, ts, usuario, evento, ip, detalle FROM seguridad.accesos ORDER BY ts DESC LIMIT @n");
        c.Parameters.AddWithValue("n", Math.Clamp(limite, 1, 1000));
        await using var r = await c.ExecuteReaderAsync();
        while (await r.ReadAsync())
            l.Add(new AccesoVista(r.GetInt64(0), Utc(r.GetDateTime(1)), r.GetString(2), r.GetString(3),
                r.IsDBNull(4) ? null : r.GetString(4), r.IsDBNull(5) ? null : r.GetString(5)));
        return l;
    }

    // ------------------------------------------------------------------ administración de usuarios
    public async Task<List<UsuarioVista>> UsuariosAsync()
    {
        var l = new List<UsuarioVista>();
        await using var c = Db.CreateCommand("SELECT id, usuario, nombre, rol, activo, creado, ultimo_acceso FROM seguridad.usuarios ORDER BY usuario");
        await using var r = await c.ExecuteReaderAsync();
        while (await r.ReadAsync())
            l.Add(new UsuarioVista(r.GetInt32(0), r.GetString(1), r.GetString(2), r.GetString(3), r.GetBoolean(4),
                Utc(r.GetDateTime(5)), r.IsDBNull(6) ? null : Utc(r.GetDateTime(6))));
        return l;
    }

    public async Task<string?> CrearAsync(string? usuario, string? nombre, string? rol, string? password, string actor, string? ip)
    {
        var u = (usuario ?? "").Trim().ToLowerInvariant();
        if (!System.Text.RegularExpressions.Regex.IsMatch(u, "^[a-z0-9._-]{3,40}$")) return "Usuario: 3-40 caracteres (letras, números, punto, guion)";
        if (string.IsNullOrWhiteSpace(nombre)) return "Falta el nombre";
        if (!Roles.Valido(rol)) return "Rol inválido";
        if (ValidarPassword(password) is { } e) return e;
        try
        {
            await using var c = Db.CreateCommand("INSERT INTO seguridad.usuarios (usuario, nombre, rol, hash) VALUES (@u, @n, @r, @h)");
            c.Parameters.AddWithValue("u", u);
            c.Parameters.AddWithValue("n", nombre.Trim());
            c.Parameters.AddWithValue("r", rol!);
            c.Parameters.AddWithValue("h", Hash(password!));
            await c.ExecuteNonQueryAsync();
        }
        catch (PostgresException ex) when (ex.SqlState == "23505") { return "Ese usuario ya existe"; }
        await RegistrarAsync(actor, "usuario_creado", ip, $"{u} ({rol})");
        return null;
    }

    public async Task<string?> ActualizarAsync(int id, string? nombre, string? rol, bool? activo, string? password, SesionActiva actor, string? ip)
    {
        if (rol is not null && !Roles.Valido(rol)) return "Rol inválido";
        if (password is not null && ValidarPassword(password) is { } e) return e;
        if (id == actor.UsuarioId && (activo == false || (rol is not null && rol != "admin")))
            return "No puedes quitarte el rol de admin ni desactivarte a ti mismo";

        string usuario, rolActual; bool activoActual;
        await using (var c = Db.CreateCommand("SELECT usuario, rol, activo FROM seguridad.usuarios WHERE id = @id"))
        {
            c.Parameters.AddWithValue("id", id);
            await using var r = await c.ExecuteReaderAsync();
            if (!await r.ReadAsync()) return "Usuario no encontrado";
            (usuario, rolActual, activoActual) = (r.GetString(0), r.GetString(1), r.GetBoolean(2));
        }
        var quitaAdmin = rolActual == "admin" && activoActual && ((rol is not null && rol != "admin") || activo == false);
        if (quitaAdmin)
        {
            await using var c = Db.CreateCommand("SELECT count(*) FROM seguridad.usuarios WHERE rol = 'admin' AND activo");
            if (Convert.ToInt64(await c.ExecuteScalarAsync()) <= 1) return "Debe quedar al menos un admin activo";
        }

        await using (var c = Db.CreateCommand("""
            UPDATE seguridad.usuarios SET
              nombre = COALESCE(@n, nombre), rol = COALESCE(@r, rol),
              activo = COALESCE(@a, activo), hash = COALESCE(@h, hash)
            WHERE id = @id
            """))
        {
            c.Parameters.AddWithValue("n", (object?)nombre?.Trim() ?? DBNull.Value);
            c.Parameters.AddWithValue("r", (object?)rol ?? DBNull.Value);
            c.Parameters.Add(new NpgsqlParameter("a", NpgsqlTypes.NpgsqlDbType.Boolean) { Value = (object?)activo ?? DBNull.Value });
            c.Parameters.AddWithValue("h", password is null ? DBNull.Value : (object)Hash(password));
            c.Parameters.AddWithValue("id", id);
            await c.ExecuteNonQueryAsync();
        }
        // cambio de rol, desactivación o nueva contraseña → se cierran sus sesiones abiertas
        if (rol is not null || activo == false || password is not null) await RevocarSesionesAsync(id);
        var cambios = string.Join(", ", new[]
        {
            nombre is null ? null : "nombre", rol is null ? null : $"rol={rol}", activo is null ? null : $"activo={activo}",
            password is null ? null : "contraseña",
        }.Where(x => x is not null));
        await RegistrarAsync(actor.Usuario, "usuario_modificado", ip, $"{usuario}: {cambios}");
        return null;
    }

    private static DateTimeOffset Utc(DateTime d) => new(DateTime.SpecifyKind(d, DateTimeKind.Utc));
    private static string? Recortar(string? s, int n) => s is null ? null : s.Length > n ? s[..n] : s;
}
