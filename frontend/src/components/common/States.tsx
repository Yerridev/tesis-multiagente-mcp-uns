import type { ReactNode } from 'react';

export function LoadingBlock({ label = 'Cargando datos de la planta…' }: { label?: string }) {
  return (
    <div className="state-block" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorBlock({
  title = 'No se pudo cargar la información',
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="state-block state-error" role="alert">
      <div className="state-ico" aria-hidden="true">!</div>
      <h3>{title}</h3>
      {message ? <p>{message}</p> : <p>Verifica que el backend FastAPI (Python) esté ejecutándose.</p>}
      {onRetry ? (
        <button type="button" className="btn btn-ghost" onClick={onRetry}>
          Reintentar
        </button>
      ) : null}
    </div>
  );
}

export function EmptyBlock({
  icon = '—',
  title,
  message,
  action,
}: {
  icon?: ReactNode;
  title: string;
  message?: string;
  action?: ReactNode;
}) {
  return (
    <div className="state-block">
      <div className="state-ico" aria-hidden="true">{icon}</div>
      <h3>{title}</h3>
      {message ? <p>{message}</p> : null}
      {action}
    </div>
  );
}

export function Banner({ tone = 'info', children }: { tone?: 'info' | 'warn' | 'err'; children: ReactNode }) {
  return <div className={`banner banner-${tone}`}>{children}</div>;
}
