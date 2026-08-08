/**
 * ORA Quiet Premium — Focus Glow (felt, not seen).
 * Exact visual values from Home Daily Focus polish 2.1 — do not restyle here lightly.
 */
import { Platform, ViewStyle } from 'react-native';
import { ACCENT_DEEP_INDIGO } from './palettes';

export type FocusGlowScheme = 'light' | 'dark';

type FocusGlowNative = Pick<
  ViewStyle,
  'shadowColor' | 'shadowOffset' | 'shadowOpacity' | 'shadowRadius'
>;

type FocusGlowWeb = { boxShadow: string };

export type FocusGlowStyle = FocusGlowNative | FocusGlowWeb;

const WEB: Record<FocusGlowScheme, string> = {
  dark: '0 12px 64px rgba(61, 74, 140, 0.14)',
  light: '0 10px 56px rgba(61, 74, 140, 0.09)',
};

const NATIVE: Record<FocusGlowScheme, FocusGlowNative> = {
  dark: {
    shadowColor: ACCENT_DEEP_INDIGO,
    shadowOpacity: 0.12,
    shadowRadius: 40,
    shadowOffset: { width: 0, height: 10 },
  },
  light: {
    shadowColor: ACCENT_DEEP_INDIGO,
    shadowOpacity: 0.08,
    shadowRadius: 40,
    shadowOffset: { width: 0, height: 10 },
  },
};

/** Platform-aware Focus Glow style — singular signature for Daily Focus. */
export function getFocusGlow(scheme: FocusGlowScheme): FocusGlowStyle {
  if (Platform.OS === 'web') {
    return { boxShadow: WEB[scheme] };
  }
  return NATIVE[scheme];
}

/** Token mirror for docs / ThemeProvider consumers */
export const focusGlowTokens = {
  web: WEB,
  native: NATIVE,
  accent: ACCENT_DEEP_INDIGO,
} as const;
