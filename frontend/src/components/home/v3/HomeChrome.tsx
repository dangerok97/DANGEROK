import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { titleCase } from '@/src/shell';

/** Morning / afternoon / evening — the only thing a greeting needs to know. */
export function greetingFor(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 5) return 'Buonanotte';
  if (h < 13) return 'Buongiorno';
  if (h < 18) return 'Buon pomeriggio';
  return 'Buonasera';
}

/**
 * Header — a greeting, and one line telling the user what this page is for.
 *
 * The name comes from the session that is already loaded; no request is made
 * to say hello. It stays one line high on purpose: a greeting that fills the
 * screen is a greeting that delays the thing the user came for.
 */
export function HomeHeaderV3({
  name,
  onWhyNow,
}: {
  name?: string | null;
  onWhyNow?: () => void;
}) {
  const { colors } = useTheme();
  const first = titleCase(name).split(/\s+/)[0] || null;

  return (
    <View style={styles.header} testID="home-header">
      <View style={styles.headerText}>
        <Text style={[styles.greeting, { color: colors.textPrimary }]} accessibilityRole="header">
          {greetingFor()}{first ? `, ${first}.` : '.'}
        </Text>
        <Text style={[styles.sub, { color: colors.textSecondary }]}>
          Ecco cosa conta davvero ora.
        </Text>
      </View>
      {onWhyNow ? (
        <Pressable
          onPress={onWhyNow}
          style={({ pressed }) => [
            styles.whyBtn,
            { backgroundColor: colors.surface, borderColor: colors.border },
            pressed && styles.pressed,
          ]}
          accessibilityRole="button"
          testID="home-why-now"
        >
          <Ionicons name="sparkles-outline" size={14} color={colors.accent} />
          <Text style={[styles.whyLabel, { color: colors.textSecondary }]}>Perché ora?</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/**
 * Empty Home. Not an error, not a blank page — a calm statement that there is
 * genuinely nothing demanding attention, plus the one affordance that still
 * makes sense.
 */
export function HomeEmptyV3({ onAsk }: { onAsk?: () => void }) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID="home-empty"
    >
      <View style={[styles.emptyMark, { backgroundColor: colors.accentMuted }]}>
        <Ionicons name="checkmark" size={22} color={colors.accent} />
      </View>
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        Per ora non c'è nulla che richieda la tua attenzione.
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        ORA continua a seguire quello che cambia. Se serve qualcosa, lo troverai qui.
      </Text>
      {onAsk ? (
        <Pressable
          onPress={onAsk}
          style={({ pressed }) => [styles.emptyCta, { borderColor: colors.border }, pressed && styles.pressed]}
          accessibilityRole="button"
        >
          <Text style={[styles.emptyCtaLabel, { color: colors.textPrimary }]}>Chiedi a ORA</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/**
 * Loading. Shaped like the page it precedes, so nothing jumps when the real
 * content lands — the hero block stays a hero block, the sections stay
 * sections.
 */
export function HomeSkeletonV3({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const bar = (w: number | string, h = 12) => (
    <View style={{ width: w as number, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  return (
    <View style={styles.skeleton} testID="home-skeleton">
      <View style={[styles.skHero, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <View style={styles.skHeroText}>
          {bar(60, 10)}
          {bar('70%' as unknown as number, 26)}
          {bar('50%' as unknown as number)}
          {bar(140, 40)}
        </View>
        {wide ? <View style={[styles.skHeroVisual, { backgroundColor: colors.skeleton }]} /> : null}
      </View>
      {[0, 1].map((i) => (
        <View key={i} style={[styles.skSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          {bar(110, 10)}
          {bar('90%' as unknown as number)}
          {bar('75%' as unknown as number)}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.lg },
  headerText: { flex: 1, gap: 4 },
  greeting: { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, lineHeight: 37 },
  sub: { fontSize: 15, lineHeight: 21 },
  whyBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg,
    minHeight: 40,
  },
  whyLabel: { fontSize: 13, fontWeight: '500' },
  empty: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xxl,
    alignItems: 'center',
    gap: tokens.spacing.sm,
  },
  emptyMark: {
    width: 46, height: 46, borderRadius: 23,
    alignItems: 'center', justifyContent: 'center',
    marginBottom: 4,
  },
  emptyTitle: { fontSize: 17, fontWeight: '600', textAlign: 'center', lineHeight: 24 },
  emptyBody: { fontSize: 14, textAlign: 'center', lineHeight: 20, maxWidth: 360 },
  emptyCta: {
    marginTop: tokens.spacing.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.xl,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  emptyCtaLabel: { fontSize: 14, fontWeight: '600' },
  skeleton: { gap: tokens.spacing.lg },
  skHero: {
    flexDirection: 'row',
    borderRadius: tokens.radius.xl,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
    minHeight: 210,
  },
  skHeroText: { flex: 1, padding: tokens.spacing.xl, gap: tokens.spacing.md },
  skHeroVisual: { width: 260 },
  skSection: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
  },
  pressed: { opacity: 0.7 },
});
