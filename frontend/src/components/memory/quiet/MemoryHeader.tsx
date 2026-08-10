import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/** Editorial intro — Quiet Premium, not search-first, not Contesti clone. */
export function MemoryHeader() {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} accessibilityRole="header">
      <Text
        style={[styles.title, { color: colors.textPrimary }]}
        accessibilityRole="header"
      >
        Memoria
      </Text>
      <Text style={[styles.sub, { color: colors.textSecondary }]}>
        Quello che ORA ha imparato su di te.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: tokens.spacing.sm,
    marginBottom: tokens.spacing.xl,
    paddingTop: tokens.spacing.sm,
  },
  title: {
    fontSize: tokens.typography.title.fontSize,
    fontWeight: tokens.typography.title.fontWeight,
    letterSpacing: tokens.typography.title.letterSpacing,
    lineHeight: tokens.typography.title.lineHeight,
  },
  sub: {
    fontSize: tokens.typography.body.fontSize,
    lineHeight: tokens.typography.body.lineHeight,
    letterSpacing: -0.2,
    maxWidth: 420,
  },
});
