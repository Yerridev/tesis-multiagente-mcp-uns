import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { ROL_DESCRIPCION, ROL_TEXTO, ROLES, useRol, useUsuario, alMenos, type Rol } from '../services/auth';

interface UsuarioFila {
  id: number;
  usuario: string;
  nombre: string;
  rol: Rol;
  activo: boolean;
  creado: string;
  ultimoAcceso: string | null;
}

interface AccesoFila {
  id: number;
  ts: string;
  usuario: string;
  evento: string;
  ip: string | null;
  detalle: string | null;
}

const EVENTO: Record<string, { texto: string; cls: string }> = {
  login_ok: { texto: 'Entró', cls: 'ok' },
  logout: { texto: 'Salió', cls: 'idle' },
  login_fallido: { texto: 'Intento fallido', cls: 'err' },
  login_bloqueado: { texto: 'Bloqueado', cls: 'err' },
  usuario_creado: { texto: 'Usuario creado', cls: 'info' },
  usuario_modificado: { texto: 'Usuario modificado', cls: 'info' },
};

const fecha = (s: string | null) =>
  s ? new Date(s).toLocaleString('es-PE', { dateStyle: 'short', timeStyle: 'medium' }) : '—';

async function llamar<T>(ruta: string, init?: RequestInit): Promise<{ datos?: T; error?: string }> {
  try {
    const res = await fetch(ruta, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } });
    const d = await res.json().catch(() => ({}));
    if (!res.ok) return { error: (d as { error?: string }).error ?? `HTTP ${res.status}` };
    return { datos: d as T };
  } catch {
    return { error: 'El backend no responde' };
  }
}

interface Formulario {
  id: number | null; // null = nuevo
  usuario: string;
  nombre: string;
  rol: Rol;
  activo: boolean;
  password: string;
}
const VACIO: Formulario = { id: null, usuario: '', nombre: '', rol: 'viewer', activo: true, password: '' };

export function UsuariosPage() {
  const rol = useRol();
  const yo = useUsuario();
  const [usuarios, setUsuarios] = useState<UsuarioFila[]>([]);
  const [accesos, setAccesos] = useState<AccesoFila[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [form, setForm] = useState<Formulario | null>(null);
  const [filtro, setFiltro] = useState('');

  const recargar = useCallback(async () => {
    const [u, a] = await Promise.all([
      llamar<UsuarioFila[]>('/api/auth/usuarios'),
      llamar<AccesoFila[]>('/api/auth/accesos?limit=300'),
    ]);
    setError(u.error ?? a.error ?? null);
    if (u.datos) setUsuarios(u.datos);
    if (a.datos) setAccesos(a.datos);
  }, []);

  useEffect(() => {
    if (alMenos(rol, 'admin')) void recargar();
  }, [rol, recargar]);

  const accesosFiltrados = useMemo(() => {
    const f = filtro.trim().toLowerCase();
    return f ? accesos.filter((a) => `${a.usuario} ${a.evento} ${a.ip ?? ''} ${a.detalle ?? ''}`.toLowerCase().includes(f)) : accesos;
  }, [accesos, filtro]);

  if (!alMenos(rol, 'admin'))
    return (
      <section className="panel">
        <div className="panel-head">
          <h2>Usuarios</h2>
        </div>
        <p className="usr-vacio">Solo el administrador puede ver esta sección.</p>
      </section>
    );

  const guardar = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    const cuerpo = {
      usuario: form.usuario,
      nombre: form.nombre,
      rol: form.rol,
      activo: form.activo,
      password: form.password || null,
    };
    const r = form.id === null
      ? await llamar('/api/auth/usuarios', { method: 'POST', body: JSON.stringify(cuerpo) })
      : await llamar(`/api/auth/usuarios/${form.id}`, { method: 'PUT', body: JSON.stringify(cuerpo) });
    if (r.error) return setAviso(r.error);
    setAviso(form.id === null ? `Usuario ${form.usuario} creado` : 'Cambios guardados');
    setForm(null);
    void recargar();
  };

  return (
    <div className="usr-pagina">
      <section className="panel">
        <div className="panel-head">
          <h2>Usuarios</h2>
          <span className="panel-sub">Guardados en TimescaleDB · contraseñas cifradas (PBKDF2) · sesiones de 8 h</span>
          <div className="panel-actions">
            <button type="button" className="btn" onClick={() => { setAviso(null); setForm({ ...VACIO }); }}>
              + Nuevo usuario
            </button>
          </div>
        </div>
        {error ? <p className="login-err">{error}</p> : null}
        {aviso ? <p className="usr-aviso">{aviso}</p> : null}

        {form ? (
          <form className="usr-form" onSubmit={guardar}>
            <label>
              Usuario
              <input
                value={form.usuario}
                disabled={form.id !== null}
                onChange={(e) => setForm({ ...form, usuario: e.target.value })}
                placeholder="ej. jperez"
                required
              />
            </label>
            <label>
              Nombre
              <input value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} required />
            </label>
            <label>
              Rol
              <select value={form.rol} onChange={(e) => setForm({ ...form, rol: e.target.value as Rol })}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {ROL_TEXTO[r]}
                  </option>
                ))}
              </select>
              <small>{ROL_DESCRIPCION[form.rol]}</small>
            </label>
            <label>
              {form.id === null ? 'Contraseña' : 'Nueva contraseña (vacío = no cambiar)'}
              <input
                type="password"
                value={form.password}
                minLength={8}
                required={form.id === null}
                autoComplete="new-password"
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              <small>Mínimo 8 caracteres</small>
            </label>
            {form.id !== null ? (
              <label className="usr-check">
                <input type="checkbox" checked={form.activo} onChange={(e) => setForm({ ...form, activo: e.target.checked })} />
                Activo (si lo desactivas, se cierra su sesión)
              </label>
            ) : null}
            <div className="usr-botones">
              <button type="submit" className="btn">Guardar</button>
              <button type="button" className="btn btn-ghost" onClick={() => setForm(null)}>Cancelar</button>
            </div>
          </form>
        ) : null}

        <div className="usr-tabla-envoltura">
          <table className="usr-tabla">
            <thead>
              <tr>
                <th>Usuario</th>
                <th>Nombre</th>
                <th>Rol</th>
                <th>Estado</th>
                <th>Último acceso</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {usuarios.map((u) => (
                <tr key={u.id} className={u.activo ? '' : 'inactivo'}>
                  <td>
                    <b>{u.usuario}</b>
                    {u.usuario === yo?.usuario ? <span className="usr-tu">tú</span> : null}
                  </td>
                  <td>{u.nombre}</td>
                  <td><span className={`usr-rol rol-${u.rol}`}>{ROL_TEXTO[u.rol]}</span></td>
                  <td>{u.activo ? <span className="usr-ev ok">Activo</span> : <span className="usr-ev idle">Desactivado</span>}</td>
                  <td>{fecha(u.ultimoAcceso)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-ghost usr-editar"
                      onClick={() => { setAviso(null); setForm({ id: u.id, usuario: u.usuario, nombre: u.nombre, rol: u.rol, activo: u.activo, password: '' }); }}
                    >
                      Editar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Historial de accesos</h2>
          <span className="panel-sub">Últimos 300 eventos · entradas, salidas, intentos fallidos y cambios de usuarios</span>
          <div className="panel-actions">
            <input className="usr-filtro" placeholder="Filtrar…" value={filtro} onChange={(e) => setFiltro(e.target.value)} />
            <button type="button" className="btn btn-ghost" onClick={() => void recargar()}>↻</button>
          </div>
        </div>
        <div className="usr-tabla-envoltura">
          <table className="usr-tabla">
            <thead>
              <tr>
                <th>Fecha y hora</th>
                <th>Usuario</th>
                <th>Evento</th>
                <th>IP</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {accesosFiltrados.map((a) => {
                const ev = EVENTO[a.evento] ?? { texto: a.evento, cls: 'idle' };
                return (
                  <tr key={a.id}>
                    <td>{fecha(a.ts)}</td>
                    <td>{a.usuario}</td>
                    <td><span className={`usr-ev ${ev.cls}`}>{ev.texto}</span></td>
                    <td>{a.ip ?? '—'}</td>
                    <td>{a.detalle ?? ''}</td>
                  </tr>
                );
              })}
              {accesosFiltrados.length === 0 ? (
                <tr><td colSpan={5} className="usr-vacio">Sin eventos</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
