export function PumpTag({ on, known = true }: { on: boolean; known?: boolean }) {
  const lit = on === true && known !== false;
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 8px',
        borderRadius: 6,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.04em',
        lineHeight: 1.15,
        whiteSpace: 'nowrap',
        background: '#05090d',
        border: '1px solid #26384a',
        color: '#fff',
      }}
    >
      <span
        aria-hidden
        style={{
          display: 'inline-block',
          width: 10,
          height: 10,
          borderRadius: '50%',
          background: lit ? '#3ddc97' : 'transparent',
          border: lit ? '1px solid #eafff5' : '2px solid #3a4b5a',
          boxShadow: lit ? '0 0 8px #3ddc97' : undefined,
        }}
      />
      BOMBA
    </div>
  );
}
