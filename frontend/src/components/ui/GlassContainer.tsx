import React from 'react';
import { Platform, StyleSheet, View, ViewProps, ViewStyle } from 'react-native';
import { BlurView } from 'expo-blur';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type GlassRole = 'tabBar' | 'sheet' | 'floating';

type Props = Omit<ViewProps, 'role'> & {
  children: React.ReactNode;
  intensity?: number;
  /** Glass is ONLY for tab bar / sheets / floating controls — never cards. */
  glassRole?: GlassRole;
};

/**
 * GlassContainer — frosted surface for chrome only (tab bar, bottom sheet, FAB chrome).
 * Falls back to solid surfaceGlass tint when blur is unavailable.
 */
export function GlassContainer({
  children,
  intensity = 48,
  glassRole = 'floating',
  style,
  ...rest
}: Props) {
  const { colors, isDark } = useTheme();
  const tint = isDark ? 'dark' : 'light';

  if (Platform.OS === 'web') {
    return (
      <View
        style={[
          styles.base,
          { backgroundColor: colors.surfaceGlass, borderColor: colors.border },
          style,
        ]}
        accessibilityLabel={glassRole}
        {...rest}
      >
        {children}
      </View>
    );
  }

  return (
    <View style={[styles.clip, style as ViewStyle]} {...rest}>
      <BlurView intensity={intensity} tint={tint} style={StyleSheet.absoluteFill} />
      <View
        style={[
          styles.base,
          styles.fill,
          { backgroundColor: colors.surfaceGlass, borderColor: colors.border },
        ]}
      >
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  clip: {
    overflow: 'hidden',
    borderRadius: tokens.radius.xl,
  },
  base: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.xl,
    overflow: 'hidden',
  },
  fill: {
    flex: 1,
  },
});
