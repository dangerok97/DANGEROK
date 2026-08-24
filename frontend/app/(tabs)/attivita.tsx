import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';

import { PageContainer } from '@/src/components/ui/PageContainer';
import { useAmbientInset } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

/**
 * Attività — the destination where ORA's own questions, updates and actions
 * will live (PX1.6 builds it).
 *
 * It ships now, empty, because the navigation is what has to be right first:
 * adding a sixth destination later reshuffles every surface built on top of
 * five. The copy says what will be here in the user's own terms — never
 * "coming soon", never a roadmap. An empty room with a name is honest; a
 * feature announcement inside a product is not.
 */
export default function AttivitaScreen() {
  const ambient = useAmbientInset();
  const { colors } = useTheme();

  return (
    <SafeAreaView edges={['top', 'left', 'right']} style={[styles.root, { backgroundColor: colors.backgroundPrimary }]}>
      <PageContainer testID="attivita-screen">
        <View style={[styles.body, { paddingBottom: ambient.paddingBottom }]}>
          <View style={[styles.mark, { backgroundColor: colors.accentMuted }]}>
            <Ionicons name="pulse-outline" size={22} color={colors.accent} />
          </View>
          <Text style={[styles.title, { color: colors.textPrimary }]} accessibilityRole="header">
            Attività
          </Text>
          <Text style={[styles.body_, { color: colors.textSecondary }]}>
            Qui troverai le domande, gli aggiornamenti e le azioni di ORA.
          </Text>
          <Text style={[styles.quiet, { color: colors.textTertiary }]}>
            Per ora non c'è nulla che richieda la tua attenzione.
          </Text>
        </View>
      </PageContainer>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  body: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: tokens.spacing.xl,
    gap: tokens.spacing.md,
  },
  mark: {
    width: 52,
    height: 52,
    borderRadius: tokens.radius.full,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: tokens.spacing.xs,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    letterSpacing: -0.4,
  },
  body_: {
    fontSize: 16,
    lineHeight: 24,
    textAlign: 'center',
    maxWidth: 380,
  },
  quiet: {
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
});
