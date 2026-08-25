import * as React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { OraContextView } from './conversationContext';

/* -------------------------------------------------------------------------- */
/* Header                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * Back, the name of the place, and — when the conversation was opened from
 * somewhere — one quiet line saying what ORA already has in hand.
 *
 * This is deliberately not a hero. Its whole job is to let the user write
 * "questa parte non mi convince" without first explaining what "questa parte"
 * is, and a block that large enough to be read once is large enough for that.
 */
export function OraHeader({
  context,
  onBack,
}: {
  context?: OraContextView | null;
  onBack: () => void;
}) {
  const { colors } = useTheme();

  return (
    <View style={styles.header} testID="ora-header">
      <View style={styles.headerRow}>
        <Pressable
          onPress={onBack}
          hitSlop={8}
          style={({ pressed }) => [styles.back, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel="Indietro"
          testID="ora-back"
        >
          <Ionicons name="chevron-back" size={22} color={colors.textSecondary} />
        </Pressable>
        <Text
          style={[styles.brand, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={1}
        >
          ORA
        </Text>
      </View>

      {context ? (
        <View style={styles.context} testID="ora-context">
          <Text style={[styles.contextEyebrow, { color: colors.textTertiary }]}>
            Stai lavorando su
          </Text>
          <Text style={[styles.contextGoal, { color: colors.textPrimary }]} numberOfLines={2}>
            {context.goal}
          </Text>
          {context.step ? (
            <Text style={[styles.contextStep, { color: colors.textSecondary }]} numberOfLines={1}>
              {context.step}
            </Text>
          ) : null}
          {context.material ? (
            <View style={[styles.material, { borderColor: colors.border }]} testID="ora-context-material">
              <Ionicons name="layers-outline" size={13} color={colors.textTertiary} />
              <Text style={[styles.materialText, { color: colors.textSecondary }]} numberOfLines={1}>
                {context.material}
              </Text>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Opening states                                                             */
/* -------------------------------------------------------------------------- */

/**
 * ORA opened from the navigation bar, with nothing in hand.
 *
 * An invitation, not a menu. Suggested prompts would teach the user that ORA
 * handles a fixed catalogue of things, which is the opposite of what it is.
 */
export function OraEmpty() {
  const { colors } = useTheme();
  return (
    <View style={styles.empty} testID="ora-empty">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        Dimmi cosa hai in mente.
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        Puoi anche aggiungere un documento.
      </Text>
    </View>
  );
}

/**
 * ORA opened on something specific, before the first message of this thread.
 *
 * The header above has already named the goal, the step and the material, so
 * repeating any of them here would be the interface telling the user something
 * they can still see. What is left to say is simply that ORA is ready.
 */
export function OraContextOpening() {
  const { colors } = useTheme();
  return (
    <View style={styles.empty} testID="ora-context-opening">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>Ci sono.</Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        Ho già il contesto di questo lavoro. Scrivimi pure da dove vuoi continuare.
      </Text>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Working                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * What ORA is doing, said honestly and inline.
 *
 * No typing simulation: ORA is not writing letter by letter, it is reading a
 * file or checking something, and pretending otherwise would be a small lie
 * told constantly. The real `working_hint` is used whenever the backend sends
 * one.
 */
export function OraWorking({ hint }: { hint?: string | null }) {
  const { colors } = useTheme();
  return (
    <View
      style={styles.working}
      accessibilityRole="progressbar"
      accessibilityLabel={hint || 'Sto ragionando…'}
      accessibilityLiveRegion="polite"
      testID="ora-working"
    >
      <ActivityIndicator size="small" color={colors.textTertiary} />
      <Text style={[styles.workingText, { color: colors.textSecondary }]}>
        {hint || 'Sto ragionando…'}
      </Text>
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* Error                                                                      */
/* -------------------------------------------------------------------------- */

/** Local to the surface, human, with a way forward. Never a status code. */
export function OraError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.error, { backgroundColor: colors.errorBg, borderColor: colors.border }]}
      accessibilityLiveRegion="polite"
      testID="ora-error"
    >
      <Text style={[styles.errorText, { color: colors.textPrimary }]}>{message}</Text>
      {onRetry ? (
        <Pressable
          onPress={onRetry}
          style={({ pressed }) => [styles.retry, { borderColor: colors.border }, pressed && styles.pressed]}
          accessibilityRole="button"
          testID="ora-retry"
        >
          <Text style={[styles.retryLabel, { color: colors.textPrimary }]}>Riprova</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  header: { gap: tokens.spacing.md, paddingBottom: tokens.spacing.md },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  back: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginLeft: -12,
  },
  brand: { fontSize: 17, fontWeight: '700', letterSpacing: 0.5 },

  context: { gap: 3, paddingLeft: 2 },
  contextEyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 1.2, textTransform: 'uppercase' },
  contextGoal: { fontSize: 17, fontWeight: '600', lineHeight: 23, letterSpacing: -0.2 },
  contextStep: { fontSize: 14, lineHeight: 20 },
  material: {
    flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start',
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.pill,
    paddingHorizontal: tokens.spacing.md, minHeight: 30, marginTop: 4, maxWidth: '100%',
  },
  materialText: { fontSize: 12, flexShrink: 1 },

  empty: { gap: 6, maxWidth: 460 },
  emptyTitle: { fontSize: 24, fontWeight: '700', letterSpacing: -0.5, lineHeight: 31 },
  emptyBody: { fontSize: 15, lineHeight: 22 },

  working: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: tokens.spacing.md },
  workingText: { fontSize: 14 },

  error: {
    borderRadius: tokens.radius.md, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg, gap: tokens.spacing.sm, marginTop: tokens.spacing.md,
  },
  errorText: { fontSize: 14, lineHeight: 20 },
  retry: {
    alignSelf: 'flex-start', minHeight: 40, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.lg, borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  retryLabel: { fontSize: 13, fontWeight: '600' },
  pressed: { opacity: 0.7 },
});
