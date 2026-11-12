import type { ReactNode } from 'react';

export function Card({ children, highlight, as: Tag = 'section', className = '' }: {
  children: ReactNode; highlight?: boolean; as?: 'section' | 'article' | 'div'; className?: string;
}) {
  return <Tag className={`card ${highlight ? 'card-highlight' : ''} ${className}`}>{children}</Tag>;
}

/** Status chip: colour + icon + word, never colour alone. */
export function Badge({ icon, text, tone }: { icon: string; text: string; tone: 'good' | 'warn' | 'bad' | 'info' }) {
  return (
    <span className={`badge badge-${tone}`}>
      <span aria-hidden="true">{icon}</span> {text}
    </span>
  );
}
