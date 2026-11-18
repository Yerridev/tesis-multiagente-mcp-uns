import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import logoAg from '../../assets/logo-ag.svg';
import {
  cerrarLocal,
  fijarAutenticacion,
  iniciarSesion,
  instalarFetchConSesion,
  useUsuario,
} from '../../services/auth';

instalarFetchConSesion();

type Estado = 'cargando' | 'sin-backend' | 'abierto' | 'login' | 'dentro';

/**
 * Puerta de entrada: si el backend exige login (usuarios en TimescaleDB) nada de la
 * plataforma se monta hasta iniciar sesión. `children` recibe el token como key para que
 * SignalR y los contextos se rehagan al cambiar de usuario.
 */
export function AuthGate({ children }: { children: (clave: string) => ReactNode }) {
  const usuario = useUsuario();
  const [estado, setEstado] = useState<Estado>('cargando');
  const [reintento, setReintento] = useState(0);

  useEffect(() => {
    let cancelado = false;
    (async () => {
      try {
        const r = await fetch('/api/auth/estado');
        const d = (await r.json()) as { habilitado: boolean };
        if (cancelado) return;
        fijarAutenticacion(d.habilitado);
        if (!d.habilitado) return setEstado('abierto');
        if (!usuario) return setEstado('login');
        // comprueba que la sesión guardada siga viva (pudo ser revocada o vencer)
        const yo = await fetch('/api/auth/yo');
        if (cancelado) return;
        if (yo.ok) setEstado('dentro');
        else {
          cerrarLocal();
          setEstado('login');
        }
      } catch {
        if (!cancelado) setEstado('sin-backend');
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [usuario?.token, reintento]); // eslint-disable-line react-hooks/exhaustive-deps

  if (estado === 'abierto') return <>{children('dev')}</>;
  if (estado === 'dentro' && usuario) return <>{children(usuario.token)}</>;
  if (estado === 'sin-backend')
    return (
      <Pantalla>
        <p className="login-err">El backend no responde. ¿Está levantado Docker (bat 05 / 13)?</p>
        <button type="button" className="btn login-btn" onClick={() => setReintento((n) => n + 1)}>
          Reintentar
        </button>
      </Pantalla>
    );
  if (estado === 'cargando' || (estado === 'dentro' && !usuario))
    return (
      <Pantalla>
        <p className="login-sub">Comprobando sesión…</p>
      </Pantalla>
    );
  return <FormLogin />;
}

function Pantalla({ children }: { children: ReactNode }) {
  return (
    <div className="login-fondo">
      <div className="login-caja">
        <img src={logoAg} alt="" className="login-logo" />
        <h1>MCP-INDUSTRIAL-USS</h1>
        {children}
      </div>
    </div>
  );
}

function FormLogin() {
  const [usuario, setUsuario] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e: FormEvent) => {
    e.preventDefault();
    setEnviando(true);
    setError(await iniciarSesion(usuario.trim(), password));
    setEnviando(false);
  };

  return (
    <Pantalla>
      <p className="login-sub">Orquestación de datos</p>
      <form onSubmit={enviar} className="login-form">
        <label>
          Usuario
          <input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label>
          Contraseña
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error ? <p className="login-err">{error}</p> : null}
        <button type="submit" className="btn login-btn" disabled={enviando}>
          {enviando ? 'Entrando…' : 'Entrar'}
        </button>
      </form>
      <small className="login-pie">La sesión dura 8 horas. Pide tu usuario al administrador.</small>
    </Pantalla>
  );
}
