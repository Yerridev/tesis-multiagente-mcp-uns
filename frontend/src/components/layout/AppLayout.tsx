import { useEffect, useState, type ReactNode } from 'react';
import { usePlant } from '../../context/PlantContext';
import { routeDef, type Route } from '../../router';
import { Header } from './Header';
import { Sidebar } from './Sidebar';

interface Props {
  route: Route;
  onNavigate: (route: Route) => void;
  children: ReactNode;
}

const SIDEBAR_KEY = 'mcp-sidebar';

export function AppLayout({ route, onNavigate, children }: Props) {
  const { link, now } = usePlant();
  const def = routeDef(route);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === 'collapsed';
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!toast) return;
    const id = window.setTimeout(() => setToast(null), 2800);
    return () => window.clearTimeout(id);
  }, [toast]);

  const toggleCollapse = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'open');
      } catch {
        /* almacenamiento no disponible */
      }
      return next;
    });
  };

  return (
    <div className="app" data-collapsed={collapsed ? 'true' : 'false'}>
      <Sidebar
        route={route}
        onNavigate={onNavigate}
        collapsed={collapsed}
        onToggleCollapse={toggleCollapse}
        open={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <div className="main">
        <Header
          title={def.title}
          subtitle={def.subtitle}
          link={link}
          now={now}
          onOpenMenu={() => setMobileOpen(true)}
          onAction={setToast}
          onNavigate={onNavigate}
        />
        <main className="content">
          <div className="page">{children}</div>
        </main>
      </div>

      <div
        className={`overlay${mobileOpen ? ' show' : ''}`}
        onClick={() => setMobileOpen(false)}
        aria-hidden="true"
      />

      {toast ? <div className="toast" role="status">{toast}</div> : null}
    </div>
  );
}
