import { Fragment, type ReactNode } from 'react';

/**
 * Markdown básico de las respuestas de la IA, SIN HTML crudo (seguro):
 * **negrita**, *cursiva*, `código`, títulos (#), listas (-, *, 1.) y saltos de línea.
 */
function enLinea(texto: string, clave: string): ReactNode[] {
  const partes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
  let ultimo = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(texto))) {
    if (m.index > ultimo) partes.push(texto.slice(ultimo, m.index));
    const t = m[0];
    const k = `${clave}-${i++}`;
    if (t.startsWith('**')) partes.push(<strong key={k}>{enLinea(t.slice(2, -2), k)}</strong>);
    else if (t.startsWith('`')) partes.push(<code key={k} className="md-code">{t.slice(1, -1)}</code>);
    else partes.push(<em key={k}>{enLinea(t.slice(1, -1), k)}</em>);
    ultimo = m.index + t.length;
  }
  if (ultimo < texto.length) partes.push(texto.slice(ultimo));
  return partes;
}

export function TextoMd({ texto }: { texto: string }) {
  const lineas = (texto ?? '').replace(/\r/g, '').split('\n');
  const bloques: ReactNode[] = [];
  let lista: { ordenada: boolean; items: string[] } | null = null;
  const cerrarLista = (k: number) => {
    if (!lista) return;
    const items = lista.items.map((it, j) => <li key={j}>{enLinea(it, `l${k}-${j}`)}</li>);
    bloques.push(lista.ordenada ? <ol key={`ol${k}`} className="md-lista">{items}</ol> : <ul key={`ul${k}`} className="md-lista">{items}</ul>);
    lista = null;
  };
  lineas.forEach((linea, k) => {
    const vineta = /^\s*[-*•]\s+(.*)$/.exec(linea);
    const numero = /^\s*\d+[.)]\s+(.*)$/.exec(linea);
    const titulo = /^\s*#{1,6}\s+(.*)$/.exec(linea);
    if (vineta || numero) {
      const ordenada = Boolean(numero);
      if (lista && lista.ordenada !== ordenada) cerrarLista(k);
      if (!lista) lista = { ordenada, items: [] };
      lista.items.push((vineta ?? numero)![1]);
      return;
    }
    cerrarLista(k);
    if (titulo) bloques.push(<strong key={`h${k}`} className="md-titulo">{enLinea(titulo[1], `h${k}`)}</strong>);
    else if (linea.trim() === '') bloques.push(<span key={`b${k}`} className="md-espacio" />);
    else bloques.push(<Fragment key={`p${k}`}><span className="md-linea">{enLinea(linea, `p${k}`)}</span></Fragment>);
  });
  cerrarLista(lineas.length);
  return <div className="md">{bloques}</div>;
}
