import type { ReactNode } from 'react';

export function ComingSoon({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return (
    <section className="panel">
      <div className="coming-soon">
        <div className="cs-ico" aria-hidden="true">
          {icon}
        </div>
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
    </section>
  );
}
