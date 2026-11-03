/* ───────────── Etiquetas de instrumento: fondo ajustado al texto ───────────── */
const CHAR_W = 0.68;  // ancho medio de una letra MAYÚSCULA en negrita (en em)
const LINE_H = 1.15;  // interlineado
const PAD_X = 0.55;   // margen lateral (en em)
const PAD_Y = 0.45;   // margen vertical (en em)

/** Parte la etiqueta en 2 líneas por el espacio más cercano a la mitad. */
export function splitLabel(label: string, maxChars = 12): string[] {
  const words = label.split(' ');
  if (label.length <= maxChars || words.length < 2) return [label];
  let best = 1, diff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ').length;
    const b = words.slice(i).join(' ').length;
    if (Math.abs(a - b) < diff) { diff = Math.abs(a - b); best = i; }
  }
  return [words.slice(0, best).join(' '), words.slice(best).join(' ')];
}

/** Un solo tamaño de fondo para TODAS las etiquetas, calculado desde el texto más grande. */
export function tagSize(labels: string[], fontSize = 15, maxChars = 12) {
  const all = labels.map((l) => splitLabel(l, maxChars));
  const chars = Math.max(...all.flatMap((ls) => ls.map((l) => l.length)));
  const lines = Math.max(...all.map((ls) => ls.length));
  return {
    w: Math.ceil(chars * CHAR_W * fontSize + 2 * PAD_X * fontSize),
    h: Math.ceil(lines * LINE_H * fontSize + 2 * PAD_Y * fontSize),
    fontSize,
  };
}

export function InstrumentTag({ label, size, maxChars = 12 }: { label: string; size: { w: number; h: number; fontSize: number }; maxChars?: number }) {
  return (
    <div
      style={{
        width: size.w,
        height: size.h,
        boxSizing: 'border-box',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#05090d',
        border: '1px solid #26384a',
        borderRadius: 4,
        color: '#fff',
        fontWeight: 700,
        fontSize: size.fontSize,
        lineHeight: LINE_H,
        textAlign: 'center',
        whiteSpace: 'nowrap',
      }}
    >
      {splitLabel(label, maxChars).map((l, i) => <span key={i}>{l}</span>)}
    </div>
  );
}
