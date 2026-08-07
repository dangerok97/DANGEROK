import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** Calm empty — control, not celebration. Ask bar remains available above. */
export function EmptyHome() {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} testID="empty-home" accessibilityRole="summary">
      <Text style={[styles.title, { color: colors.textPrimary }]}>
        {"Per ora non c'è nulla che richieda la tua attenzione."}
      </Text>
      <Text style={[styles.body, { color: colors.textSecondary }]}>
        Quando arrivano scadenze, impegni o documenti, ORA li ordina qui.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingVertical: tokens.spacing['48'],
    paddingHorizontal: tokens.spacing.sm,
    gap: tokens.spacing.md,
    alignItems: 'flex-start',
  },
  title: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    letterSpacing: tokens.typography.headline.letterSpacing,
    lineHeight: tokens.typography.headline.lineHeight,
  },
  body: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    maxWidth: 360,
  },
});
