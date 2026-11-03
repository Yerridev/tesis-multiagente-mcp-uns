import type { CSSProperties } from 'react';

export type Place = 'top' | 'bottom' | 'right' | 'left';
export type TagPlan = { open: Place; closed: Place; unknown: Place };

export const stateKey = (open: boolean | null): keyof TagPlan =>
  open === null ? 'unknown' : open ? 'open' : 'closed';

const GAP_LEVER = 6;
const GAP_SIDE = 6;
const BODY = 8;
const GAP_BODY = 20;
const PIVOT = { x: 35, y: 5.5 };
const BACK = 2;
const REACH = 28;
const HALF = 2.5;

function leverBox(open: boolean | null, leverLeft = false) {
  const angle = ((open === null ? -45 : open ? 0 : -90) * Math.PI) / 180;
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const points = [[-BACK, -HALF], [REACH, -HALF], [REACH, HALF], [-BACK, HALF]]
    .map(([x, y]) => [PIVOT.x + x * cosine - y * sine, PIVOT.y + x * sine + y * cosine]);
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  const cx = (left + right) / 2;
  const cy = (top + bottom) / 2;
  return leverLeft
    ? { left: 70 - right, right: 70 - left, top, bottom, cx: 70 - cx, cy }
    : { left, right, top, bottom, cx, cy };
}

function leverBoxVertical(open: boolean | null, leverLeft: boolean) {
  const glyph = leverBox(open);
  if (leverLeft) {
    const left = glyph.top;
    const right = glyph.bottom;
    const top = 70 - glyph.right;
    const bottom = 70 - glyph.left;
    return { left, right, top, bottom, cx: (left + right) / 2, cy: (top + bottom) / 2 };
  }
  const left = 40 - glyph.bottom;
  const right = 40 - glyph.top;
  const top = glyph.left;
  const bottom = glyph.right;
  return { left, right, top, bottom, cx: (left + right) / 2, cy: (top + bottom) / 2 };
}

export function tagStyle(vertical: boolean, place: Place, open: boolean | null, leverLeft = false): CSSProperties {
  const lever = vertical ? leverBoxVertical(open, leverLeft) : leverBox(open, leverLeft);
  const move = { transition: 'left .2s, top .2s, transform .2s' };
  switch (place) {
    case 'top':
      return { left: lever.cx, top: lever.top - GAP_LEVER, transform: 'translate(-50%, -100%)', ...move };
    case 'bottom':
      return { left: lever.cx, top: lever.bottom + GAP_LEVER, transform: 'translateX(-50%)', ...move };
    case 'right':
      return { left: lever.right + GAP_SIDE, top: lever.cy, transform: 'translateY(-50%)', ...move };
    default:
      return vertical
        ? { left: 20 - BODY - GAP_BODY, top: 35, transform: 'translate(-100%, -50%)', ...move }
        : { left: lever.left - GAP_SIDE, top: lever.cy, transform: 'translate(-100%, -50%)', ...move };
  }
}
