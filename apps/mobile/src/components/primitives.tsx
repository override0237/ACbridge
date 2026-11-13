import { AlertCircle, CheckCircle2, Info, TriangleAlert, type LucideIcon } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';
import { useTheme } from '../theme/useTheme';

/** Icon-and-label button (icon from lucide-react-native, label of three words or fewer). Tap target is at least 48. */
export function Button({
  icon: Icon, label, onPress, variant = 'primary', disabled,
}: { icon: LucideIcon; label: string; onPress: () => void; variant?: 'primary' | 'secondary' | 'danger'; disabled?: boolean }) {
  const t = useTheme();
  const fg = variant === 'primary' ? t.colors.onAccent : variant === 'danger' ? t.colors.danger : t.colors.accentText;
  const style: ViewStyle = {
    minHeight: t.target.min, minWidth: t.target.min, paddingHorizontal: t.space[5], borderRadius: t.radius.button,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: t.space[2], opacity: disabled ? 0.55 : 1,
    backgroundColor: variant === 'primary' ? t.colors.accent : 'transparent',
    borderWidth: 2, borderColor: variant === 'primary' ? t.colors.accent : variant === 'danger' ? t.colors.danger : t.colors.accent,
  };
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled: !!disabled }} disabled={disabled} onPress={onPress} style={style}>
      <Icon size={22} color={fg} />
      <Text style={{ color: fg, fontSize: t.type.size.body, fontWeight: '600' }}>{label}</Text>
    </Pressable>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  const t = useTheme();
  return (
    <View style={{ backgroundColor: t.colors.surfaceRaised, borderRadius: t.radius.card, borderWidth: 1, borderColor: t.colors.border, padding: t.space[5], gap: t.space[3] }}>
      {title ? <Text accessibilityRole="header" style={{ color: t.colors.text, fontSize: t.type.size.heading, fontWeight: '700' }}>{title}</Text> : null}
      {children}
    </View>
  );
}

const TONE_ICON = { success: CheckCircle2, warning: TriangleAlert, danger: AlertCircle, info: Info } as const;

/** A status: icon + word + colour, never colour alone. */
export function Badge({ tone, children }: { tone: keyof typeof TONE_ICON; children: string }) {
  const t = useTheme();
  const color = tone === 'info' ? t.colors.accentText : t.colors[tone];
  const Icon = TONE_ICON[tone];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: t.space[1], alignSelf: 'flex-start', borderWidth: 2, borderColor: color, borderRadius: t.radius.pill, paddingHorizontal: t.space[3], paddingVertical: t.space[1] }}>
      <Icon size={18} color={color} />
      <Text style={{ color, fontSize: t.type.size.small, fontWeight: '600' }}>{children}</Text>
    </View>
  );
}

export function Body({ children, muted }: { children: ReactNode; muted?: boolean }) {
  const t = useTheme();
  return <Text style={{ color: muted ? t.colors.textMuted : t.colors.text, fontSize: t.type.size.body, lineHeight: t.type.size.body * t.type.lineHeight }}>{children}</Text>;
}

export const styles = StyleSheet.create({ screen: { flex: 1, padding: 16, gap: 16 } });
