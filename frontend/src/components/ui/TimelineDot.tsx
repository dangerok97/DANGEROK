import React from 'react';
import { StyleSheet, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  active?: boolean;
  tone?: 'accent' | 'success' | 'warning' | 'error' | 'neutral';
  size?: number;
};

export function TimelineDot({ active = true, tone = 'accent', size = 10 }: Props) {
  const { colors } = useTheme();
  const map = {
    accent: colors.accent,
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    neutral: colors.borderStrong,
  };
  return (
    <View
      style={[
        styles.dot,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: active ? map[tone] : colors.divider,
          borderColor: colors.focusGlow,
          borderWidth: active ? 2 : 0,
        },
      ]}
      accessibilityElementsHidden
      importantForAccessibility="no"
    />
  );
}

const styles = StyleSheet.create({
  dot: {
    marginVertical: tokens.spacing.xs,
  },
});
