import { theme, type ThemeMode } from '@acbridge/tokens/theme';
import { useColorScheme } from 'react-native';

/** Colours for the current system mode (light or dark), from the SAME tokens as the web CSS variables. */
export function useTheme(override?: ThemeMode) {
  const system = useColorScheme();
  const mode: ThemeMode = override ?? (system === 'dark' ? 'dark' : 'light');
  return { mode, colors: theme.colors[mode], space: theme.space, radius: theme.radius, type: theme.type, target: theme.target, motion: theme.motion };
}
