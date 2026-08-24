import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/**
 * Editorial intro — Quiet Premium, no hero, no card.
 *
 * The wrapper deliberately carries no header role. React Native Web turns each
 * `accessibilityRole="header"` into an `<h1>`, so having it here *and* on the
 * title below emitted `<h1><h1>`: invalid HTML, a hydration error, and the
 * heading announced twice to a screen reader. The heading is the title, not
 * the block around it. Pre-existing; surfaced by the PX1.1 console pass.
 */
export function ContextsHeader() {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <Text
        style={[styles.title, { color: colors.textPrimary }]}
        accessibilityRole="header"
      >
        La tua vita
      </Text>
      <Text style={[styles.sub, { color: colors.textSecondary }]}>
        Gli ambiti della tua vita che ORA conosce.
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
