import React from 'react';
import { Pressable, StyleSheet, View, ViewProps, ViewStyle } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = ViewProps & {
  children: React.ReactNode;
  elevated?: boolean;
  onPress?: () => void;
  accessibilityLabel?: string;
};

/** Solid surface card — never glass. Soft elevation in light; lifted surface in dark. */
export function AppCard({ children, elevated, onPress, style, accessibilityLabel, ...rest }: Props) {
  const { colors, shadow } = useTheme();
  const cardStyle: ViewStyle[] = [
    styles.card,
    {
      backgroundColor: elevated ? colors.surfaceElevated : colors.surface,
      borderColor: colors.border,
    },
    elevated ? (shadow('soft') as ViewStyle) : null,
    style as ViewStyle,
  ].filter(Boolean) as ViewStyle[];

  if (onPress) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [...cardStyle, pressed && { opacity: 0.92, transform: [{ scale: tokens.motion.pressScale }] }]}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        {...rest}
      >
        {children}
      </Pressable>
    );
  }

  return (
    <View style={cardStyle} accessibilityLabel={accessibilityLabel} {...rest}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
  },
});
