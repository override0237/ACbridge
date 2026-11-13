import { GLYPH, GLYPH_TRANSLATE, LETTERS_AC, LETTERS_BRIDGE, LOGO_HEIGHT, LOGO_VIEWBOX, LOGO_WIDTH, MARK_VIEWBOX } from '@acbridge/brand';
import Svg, { Circle, Defs, G, LinearGradient, Path, Stop } from 'react-native-svg';
import { useTheme } from '../theme/useTheme';

/** The ACbridge logo for React Native (same geometry and colours as the web Logo; NOT yet run on a device). */
export function Logo({ variant = 'wordmark', tone = 'auto', height = 36 }: { variant?: 'wordmark' | 'mark'; tone?: 'auto' | 'on-ink'; height?: number }) {
  const t = useTheme();
  const ink = tone === 'on-ink' ? t.colors.onInk : t.colors.text;
  const g = GLYPH;
  const glyph = (
    <G fill="none" strokeLinecap="round" strokeLinejoin="round">
      <Path d={g.arch.d} stroke="url(#gold)" strokeWidth={g.arch.strokeWidth} />
      <Path d={g.baseline.d} stroke="url(#gold)" strokeWidth={g.baseline.strokeWidth} />
      <Path d={g.post.d} stroke="url(#gold)" strokeWidth={g.post.strokeWidth} />
      {g.dots.map((d, i) => <Circle key={i} cx={d.cx} cy={d.cy} r={d.r} fill="url(#gold)" />)}
    </G>
  );
  const defs = (
    <Defs>
      <LinearGradient id="gold" gradientUnits="userSpaceOnUse" x1={g.gradient.x1} y1={g.gradient.y1} x2={g.gradient.x2} y2={g.gradient.y2}>
        <Stop offset="0" stopColor={t.colors.goldLight} />
        <Stop offset="1" stopColor={t.colors.goldDeep} />
      </LinearGradient>
    </Defs>
  );
  if (variant === 'mark') {
    return <Svg accessibilityRole="image" accessibilityLabel="ACbridge" viewBox={MARK_VIEWBOX} height={height} width={height * (116 / 88)}>{defs}{glyph}</Svg>;
  }
  return (
    <Svg accessibilityRole="image" accessibilityLabel="ACbridge" viewBox={LOGO_VIEWBOX} height={height} width={height * (LOGO_WIDTH / LOGO_HEIGHT)}>
      {defs}
      <Path d={LETTERS_AC} fill={ink} />
      <G transform={`translate(${GLYPH_TRANSLATE.x},${GLYPH_TRANSLATE.y})`}>{glyph}</G>
      <Path d={LETTERS_BRIDGE} fill={ink} />
    </Svg>
  );
}
