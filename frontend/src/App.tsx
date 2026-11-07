import { PlantProvider } from './context/PlantContext';
import { AppLayout } from './components/layout/AppLayout';
import { ComingSoon } from './components/common/ComingSoon';
import { IconBranch, IconSettings, IconTopology } from './components/common/Icons';
import { useRoute, type Route } from './router';
import { DashboardPage } from './pages/DashboardPage';
import { ArquitecturaLogicaPage } from './pages/ArquitecturaLogicaPage';
import { AgentPage } from './pages/AgentPage';
import { McpPage } from './pages/McpPage';
import { ModuleCaudalPage } from './pages/ModuleCaudalPage';
import { ModulePresionPage } from './pages/ModulePresionPage';
import { ModuleTempPage } from './pages/ModuleTempPage';
import { LevelScadaPage } from './pages/LevelScadaPage';
import { HistoryPage } from './pages/HistoryPage';
import { ReportsPage } from './pages/ReportsPage';
import { StatusPage } from './pages/StatusPage';
import { LienzoPage } from './pages/lienzo/LienzoPage';
import { PlantaLienzoPage } from './pages/lienzo/PlantaLienzoPage';
import { equipoLienzo } from './pages/lienzo/lienzoData';

function View({ route, onNavigate }: { route: Route; onNavigate: (route: Route) => void }) {
  switch (route) {
    case 'dashboard':
      return <DashboardPage onNavigate={onNavigate} />;
    case 'monitor':
      return <DashboardPage onNavigate={onNavigate} />; // monitoreo ahora vive en el Dashboard
    case 'agents':
      return <AgentPage />;
    case 'mcp':
      return <McpPage />;
    case 'mod-caudal':
      return <ModuleCaudalPage />;
    case 'mod-nivel':
      return <LevelScadaPage />;
    case 'nivel':
      return <LevelScadaPage />;
    case 'lienzo-planta':
      return <PlantaLienzoPage onNavigate={onNavigate} />;
    case 'lienzo-caudal':
      return <LienzoPage equipo={equipoLienzo('caudal-mcc09')!} onNavigate={onNavigate} />;
    case 'lienzo-nivel':
      return <LienzoPage equipo={equipoLienzo('nivel-mcn09')!} onNavigate={onNavigate} />;
    case 'lienzo-presion':
      return <LienzoPage equipo={equipoLienzo('presion-mcp09')!} onNavigate={onNavigate} />;
    case 'lienzo-temp':
      return <LienzoPage equipo={equipoLienzo('temp-mct09')!} onNavigate={onNavigate} />;
    case 'history':
      return <HistoryPage onNavigate={onNavigate} />;
    case 'reports':
      return <ReportsPage />;
    case 'status':
      return <StatusPage />;
    case 'arch-physical':
      return (
        <ComingSoon
          icon={<IconTopology />}
          title="Pendiente de implementar"
          text="Aquí se mostrará el esquema de la topología física: PLCs (S7-200, MicroLogix), HMI Advantech, switch, servidor Debian y sus direcciones IP y puertos. Esta sección todavía no está disponible."
        />
      );
    case 'arch-logical':
      return <ArquitecturaLogicaPage />;
    case 'mod-presion':
      return <ModulePresionPage />;
    case 'mod-temp':
      return <ModuleTempPage />;
    case 'config':
      return (
        <ComingSoon
          icon={<IconSettings />}
          title="Sección pendiente de implementar"
          text="Aquí se podrán configurar los módulos, la conexión MQTT/PostgreSQL y los usuarios. Esta funcionalidad todavía no está disponible."
        />
      );
    default:
      return <DashboardPage onNavigate={onNavigate} />;
  }
}

function Shell() {
  const [route, navigate] = useRoute();

  return (
    <AppLayout route={route} onNavigate={navigate}>
      <View route={route} onNavigate={navigate} />
    </AppLayout>
  );
}

export default function App() {
  return (
    <PlantProvider>
      <Shell />
    </PlantProvider>
  );
}
