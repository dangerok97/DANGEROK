import { Platform, ViewStyle } from 'react-native';

export type ShadowLevel = 'none' | 'soft' | 'medium' | 'floating';

type ShadowToken = Pick<
  ViewStyle,
  'shadowColor' | 'shadowOffset' | 'shadowOpacity' | 'shadowRadius' | 'elevation'
>;

const lightShadows: Record<ShadowLevel, ShadowToken> = {
  none: {
    shadowColor: 'transparent',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0,
    shadowRadius: 0,
    elevation: 0,
  },
  soft: {
    shadowColor: '#1C1C1E',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 1,
  },
  medium: {
    shadowColor: '#1C1C1E',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 3,
  },
  floating: {
    shadowColor: '#1C1C1E',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.14,
    shadowRadius: 24,
    elevation: 6,
  },
};

const darkShadows: Record<ShadowLevel, ShadowToken> = {
  none: lightShadows.none,
  soft: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.35,
    shadowRadius: 4,
    elevation: 1,
  },
  medium: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.45,
    shadowRadius: 12,
    elevation: 3,
  },
  floating: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.55,
    shadowRadius: 28,
    elevation: 8,
  },
};

export function getShadows(scheme: 'light' | 'dark'): Record<ShadowLevel, ShadowToken> {
  return scheme === 'light' ? lightShadows : darkShadows;
}

/** Platform-safe shadow style helper */
export function shadowStyle(level: ShadowLevel, scheme: 'light' | 'dark' = 'dark'): ViewStyle {
  const s = getShadows(scheme)[level];
  if (Platform.OS === 'android') {
    return { elevation: s.elevation ?? 0 };
  }
  return s;
}
