import { useEffect, useState, type ComponentType } from 'react';
import { NAV, type Route } from '../../router';
import {
  IconAgent,
  IconBarChart,
  IconBranch,
  IconChart,
  IconClose,
  IconFlow,
  IconGauge,
  IconGrid,
  IconHistory,
  IconLayers,
  IconMenu,
  IconMonitor,
  IconServer,
  IconSettings,
  IconTank,
  IconThermometer,
  IconTopology,
  type IconProps,
} from '../common/Icons';

const ICONS: Record<string, ComponentType<IconProps>> = {
  grid: IconGrid,
  monitor: IconMonitor,
  agent: IconAgent,
  server: IconServer,
  topology: IconTopology,
  branch: IconBranch,
  layers: IconLayers,
  flow: IconFlow,
  tank: IconTank,
  gauge: IconGauge,
  thermometer: IconThermometer,
  clock: IconHistory,
  bars: IconBarChart,
  chart: IconChart,
  settings: IconSettings,
};

const renderIcon = (key: string) => {
  const Glyph = ICONS[key] ?? IconGrid;
  return <Glyph />;
};

const GROUP_KEY = (key: string) => `mcp-grupo-${key}`;

interface Props {
  route: Route;
  onNavigate: (route: Route) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  open: boolean;
  onCloseMobile: () => void;
}

export function Sidebar({ route, onNavigate, collapsed, onToggleCollapse, open, onCloseMobile }: Props) {
  const [groups, setGroups] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const initial: Record<string, boolean> = {};
    for (const section of NAV) {
      for (const entry of section.entries) {
        if (entry.kind === 'group') {
          let stored: string | null = null;
          try {
            stored = localStorage.getItem(GROUP_KEY(entry.key));
          } catch {
            stored = null;
          }
          initial[entry.key] = stored !== 'closed';
        }
      }
    }
    setGroups(initial);
  }, []);

  const toggleGroup = (key: string) => {
    setGroups((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(GROUP_KEY(key), next[key] ? 'open' : 'closed');
      } catch {
        /* almacenamiento no disponible */
      }
      return next;
    });
  };

  return (
    <aside className={`sidebar${open ? ' open' : ''}`} aria-label="Navegación principal">
      <div className="sidebar-brand">
        <button
          type="button"
          className="brand-toggle"
          onClick={onToggleCollapse}
          title="Comprimir / abrir menú"
          aria-label="Comprimir / abrir menú"
        >
          <IconClose className="ico-close" />
          <IconMenu className="ico-menu" />
        </button>
        <div className="brand-text">
          <strong>MCP-INDUSTRIAL</strong>
          <small>Orquestación de datos</small>
        </div>
      </div>

      <nav className="sidebar-nav">
        {NAV.map((section) => (
          <div key={section.header}>
            <span className="nav-label">{section.header}</span>

            {section.entries.map((entry) =>
              entry.kind === 'group' ? (
                <div className="nav-groupwrap" key={entry.key}>
                  <button
                    type="button"
                    className={`nav-group${entry.children.some((c) => c.id === route) ? ' child-active' : ''}`}
                    data-group={entry.key}
                    aria-expanded={groups[entry.key] ? 'true' : 'false'}
                    onClick={() => toggleGroup(entry.key)}
                  >
                    <span className="nav-ico">{renderIcon(entry.icon)}</span>
                    <span className="nav-txt">{entry.label}</span>
                    <span className="nav-caret">▸</span>
                  </button>
                  <div className={`nav-sub${groups[entry.key] ? ' open' : ''}`} data-sub={entry.key}>
                    <div className="nav-sub-inner">
                      {entry.children.map((child) => (
                        <a
                          key={child.id}
                          className={`nav-item${route === child.id ? ' active' : ''}`}
                          href={`#/${child.id}`}
                          onClick={(event) => {
                            event.preventDefault();
                            onNavigate(child.id);
                            onCloseMobile();
                          }}
                          aria-current={route === child.id ? 'page' : undefined}
                        >
                          <span className="nav-ico">{renderIcon(child.icon)}</span>
                          <span className="nav-txt">{child.label}</span>
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <a
                  key={entry.id}
                  className={`nav-item${route === entry.id ? ' active' : ''}`}
                  href={`#/${entry.id}`}
                  onClick={(event) => {
                    event.preventDefault();
                    onNavigate(entry.id);
                    onCloseMobile();
                  }}
                  aria-current={route === entry.id ? 'page' : undefined}
                >
                  <span className="nav-ico">{renderIcon(entry.icon)}</span>
                  <span className="nav-txt">{entry.label}</span>
                </a>
              ),
            )}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">USS · 2026</div>
    </aside>
  );
}
