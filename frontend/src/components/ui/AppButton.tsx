import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { triggerHaptic } from '@/src/theme/haptics';

export type AppButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

type Props = {
  label: string;
  onPress?: () => void;
  variant?: AppButtonVariant;
  loading?: boolean;
  disabled?: boolean;
  icon?: keyof typeof Ionicons.glyphMap;
  fullWidth?: boolean;
  testID?: string;
  accessibilityHint?: string;
  haptic?: boolean;
  style?: ViewStyle;
};

export function AppButton({
  label,
  onPress,
  variant = 'primary',
  loading,
  disabled,
  icon,
  fullWidth,
  testID,
  accessibilityHint,
  haptic = true,
  style,
}: Props) {
  const { colors } = useTheme();
  const dim = loading || disabled;

  const bg: Record<AppButtonVariant, string> = {
    primary: colors.accent,
    secondary: colors.surfaceElevated,
    ghost: 'transparent',
    danger: colors.errorBg,
  };
  const fg: Record<AppButtonVariant, string> = {
    primary: colors.onAccent,
    secondary: colors.textPrimary,
    ghost: colors.textPrimary,
    danger: colors.error,
  };
  const border: Record<AppButtonVariant, string> = {
    primary: colors.accent,
    secondary: colors.border,
    ghost: colors.borderStrong,
    danger: colors.error,
  };

  return (
    <Pressable
      onPress={() => {
        if (haptic) void triggerHaptic(variant === 'danger' ? 'warning' : 'selection');
        onPress?.();
      }}
      disabled={dim}
      style={({ pressed }) => [
        styles.btn,
        {
          backgroundColor: bg[variant],
          borderColor: border[variant],
          opacity: dim ? 0.55 : pressed ? 0.88 : 1,
          transform: [{ scale: pressed ? tokens.motion.pressScale : 1 }],
        },
        fullWidth && styles.full,
        style,
      ]}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ busy: !!loading, disabled: dim }}
      testID={testID}
    >
      {loading ? (
        <ActivityIndicator color={fg[variant]} />
      ) : (
        <>
          {icon ? <Ionicons name={icon} size={tokens.icon.size[20]} color={fg[variant]} /> : null}
          <Text style={[styles.label, { color: fg[variant] } as TextStyle]}>{label}</Text>
        </>
      )}
    </Pressable>
  );
}

/** Named convenience exports */
export function PrimaryButton(props: Omit<Props, 'variant'>) {
  return <AppButton {...props} variant="primary" />;
}
export function SecondaryButton(props: Omit<Props, 'variant'>) {
  return <AppButton {...props} variant="secondary" />;
}
export function GhostButton(props: Omit<Props, 'variant'>) {
  return <AppButton {...props} variant="ghost" />;
}
export function DangerButton(props: Omit<Props, 'variant'>) {
  return <AppButton {...props} variant="danger" />;
}

const styles = StyleSheet.create({
  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: tokens.spacing.sm,
    minHeight: tokens.touch.min,
    paddingHorizontal: tokens.spacing.xl,
    paddingVertical: tokens.spacing.md,
    borderRadius: tokens.radius.md,
    borderWidth: 1,
  },
  full: { alignSelf: 'stretch' },
  label: {
    fontSize: tokens.typography.button.fontSize,
    fontWeight: tokens.typography.button.fontWeight,
    letterSpacing: tokens.typography.button.letterSpacing,
  },
});
