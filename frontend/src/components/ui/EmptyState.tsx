import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AppButton } from './AppButton';

type Props = {
  title: string;
  message?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  actionLabel?: string;
  onAction?: () => void;
};

export function EmptyState({
  title,
  message,
  icon = 'leaf-outline',
  actionLabel,
  onAction,
}: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} accessibilityRole="summary">
      <Ionicons name={icon} size={tokens.icon.size[32]} color={colors.textTertiary} />
      <Text style={[styles.title, { color: colors.textPrimary }]}>{title}</Text>
      {message ? (
        <Text style={[styles.msg, { color: colors.textSecondary }]}>{message}</Text>
      ) : null}
      {actionLabel && onAction ? (
        <AppButton label={actionLabel} onPress={onAction} variant="secondary" />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: tokens.spacing['64'],
    paddingHorizontal: tokens.spacing.xl,
    gap: tokens.spacing.md,
  },
  title: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    textAlign: 'center',
  },
  msg: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    textAlign: 'center',
    maxWidth: 320,
  },
});
