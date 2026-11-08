import type { CSSProperties } from 'react';

export type Place = 'top' | 'bottom' | 'left';
/** Orden de prioridad: arriba → abajo → al lado de la palanca. ('left' = lado de la palanca) */
export const PLACE_ORDER: Place[] = ['top', 'bottom', 'left'];
export type TagPlan = { open: Place; closed: Place; unknown: Place };

export const stateKey = (open: boolean | null): keyof TagPlan =>
  open === null ? 'unknown' : open ? 'open' : 'closed';

/* ------------------------------------------------------------------
   Regla: el rótulo VX se centra respecto a la PALANCA AZUL en el lado
   pedido (arriba / abajo / derecha / izquierda). Si en esa posición su
   caja (texto + fondo) tapa algún componente de la propia válvula
   (tubería, brida, cuerpo, palanca), se desplaza lo mínimo necesario
   hasta quedar libre, sin cambiar de lado.
   Coordenadas locales del contenedor .valve (70x40 horizontal, 40x70 vertical).
   ------------------------------------------------------------------ */

type Box = { left: number; right: number; top: number; bottom: number };

const GAP = 5;            // separación mínima rótulo ↔ cualquier pieza
const TAG_H = 20;         // alto de .valve__tag (12px + padding + borde)
const CHAR_W = 7.2;       // ancho aprox. por carácter (12px, 600)
const PAD_W = 14;         // padding horizontal + borde
const INF = 10000;        // la tubería continúa fuera del glifo

const PIVOT = { x: 35, y: 5.5 };
const BACK = 2;
const REACH = 28;
const HALF = 2.5;

export const tagWidth = (label: string) => Math.ceil(label.length * CHAR_W + PAD_W);

/** Caja de la palanca en el glifo horizontal 70x40. */
function leverGlyph(open: boolean | null, leverLeft: boolean): Box {
  const a = ((open === null ? -45 : open ? 0 : -90) * Math.PI) / 180;
  const c = Math.cos(a), s = Math.sin(a);
  const pts = [[-BACK, -HALF], [REACH, -HALF], [REACH, HALF], [-BACK, HALF]]
    .map(([x, y]) => [PIVOT.x + x * c - y * s, PIVOT.y + x * s + y * c]);
  const xs = pts.map(([x]) => x), ys = pts.map(([, y]) => y);
  const b = { left: Math.min(...xs), right: Math.max(...xs), top: Math.min(...ys), bottom: Math.max(...ys) };
  return leverLeft ? { ...b, left: 70 - b.right, right: 70 - b.left } : b;
}

/** Glifo horizontal → contenedor vertical 40x70 (rotate 90° o 270° si palanca izquierda). */
function toVertical(b: Box, leverLeft: boolean): Box {
  if (leverLeft) return { left: b.top, right: b.bottom, top: 70 - b.right, bottom: 70 - b.left };
  return { left: 40 - b.bottom, right: 40 - b.top, top: b.left, bottom: b.right };
}

function geometry(vertical: boolean, open: boolean | null, leverLeft: boolean, leverDown = false) {
  // piezas fijas en el glifo horizontal (simétricas, no dependen de leverLeft)
  const pipe: Box = { left: -INF, right: INF, top: 15, bottom: 25 };
  const flange: Box = { left: 22, right: 48, top: 12, bottom: 28 };
  const body: Box = { left: 25, right: 45, top: 10, bottom: 30 };
  const stem: Box = { left: 33.5, right: 36.5, top: 5, bottom: 10 };
  // en abierta/cerrada, la palanca del glifo con leverLeft ya viene espejada
  // vertical+izquierda se dibuja con rotate(270°) SIN espejo → no espejar aquí
  const lever = leverGlyph(open, leverLeft && !vertical);
  const parts = [pipe, flange, body, stem].map((p) => leverLeft ? { ...p, left: 70 - p.right, right: 70 - p.left } : p);
  if (!vertical) {
    // horizontal con palanca hacia ABAJO: espejo vertical (scaleY(-1)) sobre y = 20
    const fy = (b: Box): Box => leverDown ? { ...b, top: 40 - b.bottom, bottom: 40 - b.top } : b;
    return { lever: fy(lever), obstacles: [...parts, lever].map(fy) };
  }
  const rot = (b: Box) => {
    // la tubería rota a vertical infinita
    if (b.left === -INF || b.right === INF) return { left: 15, right: 25, top: -INF, bottom: INF };
    return toVertical(b, leverLeft);
  };
  const vLever = toVertical(lever, leverLeft);
  return { lever: vLever, obstacles: [...parts.map(rot), vLever] };
}

const hits = (a: Box, b: Box) =>
  a.left < b.right + GAP && a.right + GAP > b.left && a.top < b.bottom + GAP && a.bottom + GAP > b.top;

/** Caja del rótulo en un lado: centrado con la palanca; ok=false si ese lado está ocupado. */
type Slot = Place | 'sideR' | 'sideL';

function slotBox(vertical: boolean, slot: Slot, open: boolean | null, leverLeft: boolean, label: string, extra: Box[], leverDown = false): { box: Box; ok: boolean } {
  const { lever, obstacles } = geometry(vertical, open, leverLeft, leverDown);
  const all = [...obstacles, ...extra];
  const w = tagWidth(label), h = TAG_H;
  const cx = (lever.left + lever.right) / 2, cy = (lever.top + lever.bottom) / 2;
  const at = (x: number, y: number): Box => ({ left: x, right: x + w, top: y, bottom: y + h });
  const free = (b: Box) => !all.some((ob) => hits(b, ob));
  if (slot === 'top' || slot === 'bottom') {
    // centrado horizontal exacto con la palanca; solo se aleja en su eje
    const dir = slot === 'top' ? -1 : 1;
    const y0 = slot === 'top' ? lever.top - GAP - h : lever.bottom + GAP;
    for (let o = 0; o <= 30; o++) { const box = at(cx - w / 2, y0 + dir * o); if (free(box)) return { box, ok: true }; }
    return { box: at(cx - w / 2, y0), ok: false };
  }
  // costado: centrado en Y con la palanca, pegado a ella; se aleja solo en X
  const toRight = slot === 'sideR' || (slot === 'left' && cx >= (vertical ? 20 : 35));
  const dir = toRight ? 1 : -1;
  const x0 = toRight ? lever.right + GAP : lever.left - GAP - w;
  // margen corto: si hay otra pieza pegada (p. ej. la tubería), ese lado está ocupado
  for (let o = 0; o <= 6; o++) { const box = at(x0 + dir * o, cy - h / 2); if (free(box)) return { box, ok: true }; }
  return { box: at(x0, cy - h / 2), ok: false };
}

/* ------------------------------------------------------------------
   REGLA FINAL
   · Palanca HORIZONTAL (acostada)  → del lado de la palanca (arriba, o abajo si está debajo) → el otro → costado
   · Palanca VERTICAL (parada)      → a su derecha → a su izquierda → arriba → abajo
   Siempre centrado respecto a la palanca azul y sin tapar nada.
   ------------------------------------------------------------------ */
export function resolvePlace(vertical: boolean, open: boolean | null, leverLeft = false, label = 'V1', _from: Place = 'top', extra: Box[] = [], leverDown = false): { box: Box } {
  const { lever } = geometry(vertical, open, leverLeft, leverDown);
  const standing = lever.bottom - lever.top > lever.right - lever.left;
  // palanca acostada DEBAJO del cuerpo → el rótulo va abajo primero (del lado de la palanca)
  const below = (lever.top + lever.bottom) / 2 > (vertical ? 35 : 20) + 1;
  const chain: Slot[] = standing ? ['sideR', 'sideL', 'top', 'bottom'] : below ? ['bottom', 'top', 'left'] : ['top', 'bottom', 'left'];
  for (const slot of chain) {
    const r = slotBox(vertical, slot, open, leverLeft, label, extra, leverDown);
    if (r.ok) return { box: r.box };
  }
  return { box: slotBox(vertical, chain[0], open, leverLeft, label, extra, leverDown).box };
}

export function tagStyle(vertical: boolean, place: Place, open: boolean | null, leverLeft = false, label = 'V1', leverDown = false): CSSProperties {
  const { box } = resolvePlace(vertical, open, leverLeft, label, place, [], leverDown);
  return { left: box.left, top: box.top, transform: 'none', transition: 'left .2s, top .2s' };
}
