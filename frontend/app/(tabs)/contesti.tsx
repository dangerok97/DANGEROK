/**
 * Contesti — Quiet Premium placeholder (Application Shell V1).
 * No dashboard; real contexts come later.
 */
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { useAmbientInset } from '@/src/shell';

export default function ContestiScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="contesti-screen"
    >
      <View
        style={[
          styles.inner,
          {
            paddingBottom: ambient.paddingBottom,
            paddingLeft: tokens.spacing.xl + (ambient.isRail ? 0 : 0),
          },
        ]}
      >
        <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>CONTESTI</Text>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
        >
          Contesti
        </Text>
        <Text style={[styles.body, { color: colors.textSecondary }]}>
          Qui vivranno i tuoi contesti di vita — studio, lavoro, casa — con calma e chiarezza.
          Per ora è uno spazio quieto: arriva dopo.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  inner: {
    flex: 1,
    paddingHorizontal: tokens.spacing.xl,
    paddingTop: tokens.spacing.xl,
    gap: tokens.spacing.md,
    maxWidth: 560,
  },
  eyebrow: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 1.2,
  },
  title: {
    fontSize: tokens.typography.hero.fontSize,
    fontWeight: '700',
    letterSpacing: -0.6,
    lineHeight: tokens.typography.hero.lineHeight,
  },
  body: {
    fontSize: tokens.typography.body.fontSize,
    lineHeight: tokens.typography.body.lineHeight,
    letterSpacing: -0.2,
    marginTop: tokens.spacing.sm,
  },
});
