import { ArrowRight, Check, RefreshCw, Trash2 } from 'lucide-react';
import { Badge, Button, Card, EmptyState, ErrorState, Field, Skeleton } from '../components/ui';
import { colors } from '@acbridge/tokens';

/** Every design-system primitive, in LIGHT and DARK side by side (the "Storybook equivalent" for phase 1). Dev only: /styleguide.html */
function Showcase() {
  return (
    <div className="acb-stack">
      <Card title="Buttons">
        <div className="acb-stack">
          <Button icon={ArrowRight} label="Continue" big block />
          <Button icon={Check} label="Confirm" variant="secondary" />
          <Button icon={Trash2} label="Delete" variant="danger" />
          <Button icon={RefreshCw} label="Try again" variant="ghost" />
          <Button icon={Check} label="Disabled" disabled />
        </div>
      </Card>
      <Card title="Statuses (icon + word)">
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Badge tone="success">Verified</Badge>
          <Badge tone="warning">Waiting</Badge>
          <Badge tone="danger">Held</Badge>
          <Badge tone="info">Accepted</Badge>
        </div>
      </Card>
      <Card title="Form fields">
        <Field label="Phone number" hint="Example: 670123456" inputMode="numeric" defaultValue="" />
        <Field label="Phone number" error="Enter a valid phone number." defaultValue="12" inputMode="numeric" />
        <Field label="About your work" multiline hint="Say what you fix and for how long" />
      </Card>
      <Card title="Loading, empty and error">
        <Skeleton lines={3} />
        <EmptyState title="No requests yet" body="When a customer asks for you, it will appear here." />
        <ErrorState title="Could not load" body="Check your connection and try again." action={<Button icon={RefreshCw} label="Try again" variant="secondary" />} />
      </Card>
      <Card title="Colour tokens">
        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 4 }}>
          {Object.keys(colors.light).map((k) => (
            <li key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span aria-hidden="true" style={{ width: 24, height: 24, borderRadius: 6, border: '1px solid var(--acb-color-border-strong)', background: `var(--acb-color-${k.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)})` }} />
              <code>{k}</code>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

export function Styleguide() {
  return (
    <main style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))' }}>
      <section className="acb-theme-light acb-page" aria-label="Light mode" data-testid="light">
        <h1>Light</h1>
        <Showcase />
      </section>
      <section className="acb-theme-dark acb-page" aria-label="Dark mode" data-testid="dark">
        <h1>Dark</h1>
        <Showcase />
      </section>
    </main>
  );
}
