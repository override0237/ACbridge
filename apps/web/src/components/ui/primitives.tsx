import { AlertCircle, CheckCircle2, Info, Inbox, TriangleAlert, type LucideIcon } from 'lucide-react';
import { useId, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react';
import './ui.css';

/** Icon-and-label button. Every action has an icon from lucide-react AND a short label (3 words or fewer). */
export interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  icon: LucideIcon;
  label: string;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  big?: boolean;
  block?: boolean;
}

export function Button({ icon: Icon, label, variant = 'primary', big, block, className = '', type = 'button', ...rest }: ButtonProps) {
  const cls = ['acb-btn', `acb-btn-${variant}`, big && 'acb-btn-big', block && 'acb-btn-block', className].filter(Boolean).join(' ');
  return (
    <button type={type} className={cls} {...rest}>
      <Icon className="acb-icon" size={22} aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
}

export function Card({ title, children, as: Tag = 'section' }: { title?: string; children: ReactNode; as?: 'section' | 'article' | 'div' }) {
  return (
    <Tag className="acb-card">
      {title && <h2>{title}</h2>}
      {children}
    </Tag>
  );
}

export type Tone = 'success' | 'warning' | 'danger' | 'info';
const TONE_ICON: Record<Tone, LucideIcon> = { success: CheckCircle2, warning: TriangleAlert, danger: AlertCircle, info: Info };

/** A status: colour + icon + a word, never colour alone. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  const Icon = TONE_ICON[tone];
  return (
    <span className={`acb-badge acb-badge-${tone}`}>
      <Icon size={18} aria-hidden="true" />
      <span>{children}</span>
    </span>
  );
}

interface FieldBase { label: string; hint?: string; error?: string | null }

/** A labelled input. The label is always visible; the error is announced (aria-live) and linked to the control. */
export function Field({ label, hint, error, multiline, ...rest }: FieldBase & { multiline?: boolean } & InputHTMLAttributes<HTMLInputElement> & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId();
  const describedBy = [hint && `${id}-hint`, error && `${id}-err`].filter(Boolean).join(' ') || undefined;
  const common = { id, 'aria-describedby': describedBy, 'aria-invalid': error ? true : undefined };
  return (
    <div className="acb-field" data-invalid={error ? 'true' : 'false'}>
      <label htmlFor={id}><span className="acb-label">{label}</span></label>
      {multiline ? <textarea rows={3} {...(rest as TextareaHTMLAttributes<HTMLTextAreaElement>)} {...common} /> : <input {...rest} {...common} />}
      {hint && <span id={`${id}-hint`} className="acb-hint">{hint}</span>}
      <div id={`${id}-err`} role="alert" aria-live="assertive" className={error ? 'acb-error' : undefined}>
        {error && (<><AlertCircle size={20} aria-hidden="true" /><span>{error}</span></>)}
      </div>
    </div>
  );
}

/** Placeholder for content that is loading, in the shape of the content (skeleton, not a spinner). */
export function Skeleton({ lines = 3, height = 16 }: { lines?: number; height?: number }) {
  return (
    <div role="status" aria-busy="true" aria-label="Loading" className="acb-stack" style={{ gap: 8 }}>
      {Array.from({ length: lines }, (_, i) => (
        <span key={i} className="acb-skeleton" style={{ height, width: i === lines - 1 ? '60%' : '100%' }} />
      ))}
    </div>
  );
}

/** Designed empty state: says what is empty and what to do next, in plain words. */
export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="acb-state">
      <Inbox className="acb-state-icon" size={40} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}

/** Designed error state with a retry. */
export function ErrorState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="acb-state acb-state-error" role="alert">
      <AlertCircle className="acb-state-icon" size={40} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{body}</p>
      {action}
    </div>
  );
}
