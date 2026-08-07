import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Appearance, ColorSchemeName, useColorScheme, View, ViewStyle } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { StatusBar } from 'expo-status-bar';

import { darkColors, lightColors } from './palettes';
import { colorsFromPalette, tokens, type AppColorTokens } from './tokens';
import { getShadows, type ShadowLevel } from './shadows';
import { typography } from './typography';
import { motion } from './motion';

const STORAGE_KEY = 'ora.theme.preference';

export type ThemePreference = 'light' | 'dark' | 'system';
export type ResolvedScheme = 'light' | 'dark';

export type ThemeContextValue = {
  preference: ThemePreference;
  scheme: ResolvedScheme;
  colors: AppColorTokens;
  isDark: boolean;
  setPreference: (p: ThemePreference) => void;
  tokens: typeof tokens;
  typography: typeof typography;
  motion: typeof motion;
  shadows: ReturnType<typeof getShadows>;
  shadow: (level: ShadowLevel) => ViewStyle;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function resolveScheme(preference: ThemePreference, system: ColorSchemeName): ResolvedScheme {
  if (preference === 'system') {
    return system === 'light' ? 'light' : 'dark';
  }
  return preference;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  const [preference, setPreferenceState] = useState<ThemePreference>('system');
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const stored = await AsyncStorage.getItem(STORAGE_KEY);
        if (mounted && (stored === 'light' || stored === 'dark' || stored === 'system')) {
          setPreferenceState(stored);
        }
      } catch {
        // ignore
      } finally {
        if (mounted) setHydrated(true);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const setPreference = useCallback((p: ThemePreference) => {
    setPreferenceState(p);
    AsyncStorage.setItem(STORAGE_KEY, p).catch(() => undefined);
  }, []);

  const scheme = resolveScheme(preference, systemScheme ?? Appearance.getColorScheme());
  const colors = useMemo(
    () => colorsFromPalette(scheme === 'light' ? lightColors : darkColors),
    [scheme],
  );
  const shadows = useMemo(() => getShadows(scheme), [scheme]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      preference,
      scheme,
      colors,
      isDark: scheme === 'dark',
      setPreference,
      tokens,
      typography,
      motion,
      shadows,
      shadow: (level: ShadowLevel) => shadows[level] as ViewStyle,
    }),
    [preference, scheme, colors, setPreference, shadows],
  );

  // Avoid flash: until hydrated, still render with system scheme
  void hydrated;

  return (
    <ThemeContext.Provider value={value}>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <View style={{ flex: 1, backgroundColor: colors.backgroundPrimary }}>{children}</View>
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // Safe fallback for tests / early render outside provider
    const colors = colorsFromPalette(darkColors);
    const shadows = getShadows('dark');
    return {
      preference: 'dark',
      scheme: 'dark',
      colors,
      isDark: true,
      setPreference: () => undefined,
      tokens,
      typography,
      motion,
      shadows,
      shadow: (level) => shadows[level] as ViewStyle,
    };
  }
  return ctx;
}

/** Convenience: semantic colors only */
export function useColors(): AppColorTokens {
  return useTheme().colors;
}
