import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  value: string;
  label: string;
  hint?: string;
};

/** Editorial metric — one number, one label. Not a dashboard tile. */
export function Metric({ value, label, hint }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} accessibilityLabel={`${label}: ${value}`}>
      <Text style={[styles.value, { color: colors.textPrimary }]}>{value}</Text>
      <Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text>
      {hint ? <Text style={[styles.hint, { color: colors.textTertiary }]}>{hint}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 2 },
  value: {
    fontSize: tokens.typography.hero.fontSize,
    fontWeight: tokens.typography.hero.fontWeight,
    letterSpacing: tokens.typography.hero.letterSpacing,
  },
  label: {
    fontSize: tokens.typography.caption.fontSize,
    fontWeight: '500',
  },
  hint: {
    fontSize: tokens.typography.footnote.fontSize,
  },
});
