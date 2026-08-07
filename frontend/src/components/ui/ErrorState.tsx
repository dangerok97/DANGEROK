import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AppButton } from './AppButton';

type Props = {
  title?: string;
  message?: string;
  onRetry?: () => void;
  retryLabel?: string;
};

export function ErrorState({
  title = 'Qualcosa non ha funzionato',
  message = 'Riprova tra un momento.',
  onRetry,
  retryLabel = 'Riprova',
}: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} accessibilityRole="alert">
      <Ionicons name="alert-circle-outline" size={tokens.icon.size[32]} color={colors.error} />
      <Text style={[styles.title, { color: colors.textPrimary }]}>{title}</Text>
      <Text style={[styles.msg, { color: colors.textSecondary }]}>{message}</Text>
      {onRetry ? <AppButton label={retryLabel} onPress={onRetry} variant="secondary" /> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: tokens.spacing['48'],
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
    textAlign: 'center',
    maxWidth: 320,
  },
});
