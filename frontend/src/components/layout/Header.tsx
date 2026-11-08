import { useEffect, useRef, useState } from 'react';
import type { LinkState } from '../../types';
import { timeOnly, dateOnly } from '../../utils/format';
import { IconMenu } from '../common/Icons';
import { usePlantaModo } from '../scada/plantaSimulada';

interface Props {
  title: string;
  subtitle: string;
  link: LinkState;
  now: number;
  onOpenMenu: () => void;
  onAction: (message: string) => void;
}

const LINK_LABEL: Record<LinkState, { text: string; cls: string }> = {
  connecting: { text: 'Conectando…', cls: 'pill-idle' },
  connected: { text: 'SignalR en vivo', cls: 'pill-ok pill-live' },
  reconnecting: { text: 'Reconectando…', cls: 'pill-warn pill-live' },
  disconnected: { text: 'Sin conexión', cls: 'pill-err' },
};

export function Header({ title, subtitle, link, now, onOpenMenu, onAction }: Props) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const pill = LINK_LABEL[link];
  const simulada = usePlantaModo() === 'simulado';   // lo decide el backend (MODO_PLANTA): igual para todas las páginas y usuarios

  return (
    <header className="header">
      <button type="button" className="hamburger" onClick={onOpenMenu} aria-label="Abrir menú">
        <IconMenu />
      </button>

      <div className="header-title">
        <h1>{title}</h1>
        <small>{subtitle}</small>
      </div>

      <div className="header-right">
        {simulada
          ? <span className="pill pill-warn" title="Backend con MODO_PLANTA=simulado: SCADA, lienzos y agentes usan los simuladores Python"><i />PLANTA SIMULADA</span>
          : <span className="header-plant">Planta REAL · Laboratorio USS</span>}

        <span className={`pill ${pill.cls}`}>
          <i />
          {pill.text}
        </span>

        <div className="header-clock">
          {dateOnly(now)} · {timeOnly(now)}
        </div>

        <div className="user-menu" ref={menuRef}>
          <button
            type="button"
            className="user-btn"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-haspopup="menu"
          >
            <span className="user-av">K</span>
            <span className="user-name">
              <b>Keysi B.</b>
              <small>Operadora · supervisión</small>
            </span>
            <span aria-hidden="true">▾</span>
          </button>
          <div className={`user-drop${open ? ' open' : ''}`} role="menu">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onAction('Perfil de operadora: pendiente de implementar.');
              }}
            >
              Mi perfil
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onAction('Configuración: pendiente de implementar.');
              }}
            >
              Configuración
            </button>
            <div className="drop-sep" />
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onAction('La autenticación aún no está implementada.');
              }}
            >
              Cerrar sesión
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
