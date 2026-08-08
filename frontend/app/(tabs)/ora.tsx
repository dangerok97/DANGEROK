/**
 * ORA Ambient entry — same ConversationEngine path as Home Ask Bar.
 * Not Aggiungi, not a chat thread.
 */
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { OraInput } from '@/src/components/home/quiet/OraInput';
import { useAmbientInset } from '@/src/shell';

export default function OraEntryScreen() {
  const { colors } = useTheme();
  const ambient = useAmbientInset();

  return (
    <SafeAreaView
      edges={['top']}
      style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}
      testID="ora-entry-screen"
    >
      <View
        style={[
          styles.inner,
          { paddingBottom: ambient.paddingBottom },
        ]}
      >
        <Text style={[styles.eyebrow, { color: colors.textTertiary }]}>ORA</Text>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
        >
          Cosa vuoi risolvere?
        </Text>
        <Text style={[styles.body, { color: colors.textSecondary }]}>
          Scrivi o parla — ORA apre il prossimo passo, non una chat.
        </Text>
        <View style={styles.ask}>
          <OraInput />
        </View>
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
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
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
    marginBottom: tokens.spacing.sm,
  },
  ask: {
    marginTop: tokens.spacing.md,
  },
});
