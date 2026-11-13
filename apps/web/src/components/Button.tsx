import type { ButtonHTMLAttributes } from 'react';

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: string; // every action has an icon AND a short label (max three words)
  label: string;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  big?: boolean;
}

export function Button({ icon, label, variant = 'primary', big, className = '', type = 'button', ...rest }: Props) {
  return (
    <button type={type} className={`btn btn-${variant} ${big ? 'btn-big' : ''} ${className}`} {...rest}>
      <span className="btn-icon" aria-hidden="true">{icon}</span>
      <span>{label}</span>
    </button>
  );
}
