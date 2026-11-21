/** Pregunta al agente en curso, fuera de React: sobrevive a que la página de agentes se desmonte. */
let activo = false;
const oyentes = new Set<() => void>();

export const pendiente = {
  get activo(): boolean { return activo; },
  inicio(): void { activo = true; },
  fin(): void { activo = false; oyentes.forEach((f) => f()); },
  suscribir(f: () => void): () => void { oyentes.add(f); return () => { oyentes.delete(f); }; },
};
