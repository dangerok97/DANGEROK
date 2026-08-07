import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { IconButton } from './IconButton';

type Props = {
  title: string;
  subtitle?: string;
  eyebrow?: string;
  onBack?: () => void;
  right?: React.ReactNode;
};

export function ScreenHeader({ title, subtitle, eyebrow, onBack, right }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <View style={styles.topRow}>
        {onBack ? (
          <IconButton name="chevron-back" accessibilityLabel="Indietro" onPress={onBack} />
        ) : (
          <View style={styles.spacer} />
        )}
        {right ?? <View style={styles.spacer} />}
      </View>
      {eyebrow ? (
        <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>{eyebrow}</Text>
      ) : null}
      <Text
        style={[styles.title, { color: colors.textPrimary }]}
        accessibilityRole="header"
      >
        {title}
      </Text>
      {subtitle ? (
        <Text style={[styles.sub, { color: colors.textSecondary }]}>{subtitle}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginBottom: tokens.spacing.xl, gap: tokens.spacing.xs },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    minHeight: tokens.touch.min,
  },
  spacer: { width: tokens.touch.min, height: tokens.touch.min },
  eyebrow: {
    fontSize: tokens.typography.label.fontSize,
    fontWeight: tokens.typography.label.fontWeight,
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  title: {
    fontSize: tokens.typography.title.fontSize,
    fontWeight: tokens.typography.title.fontWeight,
    letterSpacing: tokens.typography.title.letterSpacing,
    lineHeight: tokens.typography.title.lineHeight,
  },
  sub: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    marginTop: 4,
  },
});
