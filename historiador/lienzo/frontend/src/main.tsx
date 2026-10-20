import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import { Component, StrictMode, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { ReactFlowProvider } from '@xyflow/react';
import App from './App';

/** Si algo falla en la interfaz, muestra el error en vez de dejar la pagina en blanco. */
class Guardian extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div style={{ padding: 32, fontFamily: 'IBM Plex Sans, sans-serif', color: '#e3e7eb', background: '#15181c', height: '100%' }}>
        <h2 style={{ marginTop: 0 }}>El lienzo encontró un error</h2>
        <pre style={{ whiteSpace: 'pre-wrap', color: '#ef5a5a' }}>{String(this.state.error?.stack ?? this.state.error)}</pre>
        <button onClick={() => location.reload()}>Recargar</button>
      </div>
    );
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Guardian>
      <ReactFlowProvider>
        <App />
      </ReactFlowProvider>
    </Guardian>
  </StrictMode>,
);
