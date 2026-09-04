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

/**
 * ORA opened on something it raised itself.
 *
 * The difference from every other opening on this screen is who spoke first.
 * Here ORA did — on Home, in a card the person tapped — so the thread starts
 * by saying what it said and why, rather than asking an opening question that
 * would make somebody re-explain the thing they just tapped on.
 *
 * It states and stops. No suggested replies, no "vuoi che me ne occupi?": the
 * card was a conversation opener, not an offer, and turning it into one here
 * would be the surface promising something the reasoning has not agreed to.
 */
export function OraRaisedOpening({
  opportunity,
}: {
  opportunity: { title: string; why_now?: string; question?: string | null };
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.empty} testID="ora-raised-opening">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        {opportunity.title}
      </Text>
      {opportunity.why_now ? (
        <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
          Te l'ho segnalato perché {lowerFirst(opportunity.why_now)}
        </Text>
      ) : null}
      {opportunity.question ? (
        <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
          {opportunity.question}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * ORA opened on something it needs the person for.
 *
 * The shape is the argument. What comes first is what ORA already did, and
 * only then the one thing missing — because «mi serve il tuo via libera» on
 * its own is a demand, and the same sentence after four lines of work is a
 * report with a question at the end. The person should be able to see that
 * they are the last step, not the first.
 *
 * For an approval the two answers are here, on the thread, because making
 * somebody navigate to say yes to something already prepared is the
 * workflow this whole phase exists to remove. There is no third button:
 * "later" is what closing the screen already means.
 */
export function OraNeedOpening({
  need,
  onApprove,
  onDeny,
  onAllowAlways,
  busy,
}: {
  need: {
    says: string;
    already_done: string[];
    missing?: string | null;
    asks_for?: string | null;
    can_allow_always?: string | null;
  };
  onApprove?: () => void;
  onDeny?: () => void;
  onAllowAlways?: () => void;
  busy?: boolean;
}) {
  const { colors } = useTheme();
  const wantsAuthority = need.asks_for === 'authority';
  /*
    The third choice, and deliberately not a third button beside the other
    two.

      ONE-TIME APPROVAL IS NOT A STANDING PERMISSION.

    Two answers to "shall I do this" sit together as equals. Allowing it for
    ever is a different question, so it sits apart and quieter, under the
    sentence saying exactly what it would allow — a permission somebody grants
    without having read it is one they did not grant.

    Absent unless the backend offers it. Most things are never offerable, and
    the client does not get to decide which.
  */
  const canAllowAlways = Boolean(
    wantsAuthority && need.can_allow_always && onAllowAlways,
  );

  return (
    <View style={styles.empty} testID="ora-need-opening">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        {need.says}
      </Text>

      {need.already_done.length ? (
        <View style={styles.needDone} testID="ora-need-done">
          {need.already_done.slice(0, 4).map((line, n) => (
            <Text
              key={`${n}-${line.slice(0, 12)}`}
              style={[styles.emptyBody, { color: colors.textTertiary }]}
            >
              {line}
            </Text>
          ))}
        </View>
      ) : null}

      {need.missing ? (
        <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
          {need.missing}
        </Text>
      ) : null}

      {wantsAuthority && onApprove && onDeny ? (
        <View style={styles.needAnswers}>
          <Pressable
            onPress={onApprove}
            disabled={busy}
            accessibilityRole="button"
            testID="ora-need-approve"
            style={({ pressed }) => [
              styles.needAnswer,
              { borderColor: colors.border, opacity: busy || pressed ? 0.6 : 1 },
            ]}
          >
            <Text style={[styles.needAnswerText, { color: colors.textPrimary }]}>
              Vai pure
            </Text>
          </Pressable>
          <Pressable
            onPress={onDeny}
            disabled={busy}
            accessibilityRole="button"
            testID="ora-need-deny"
            style={({ pressed }) => [
              styles.needAnswer,
              { borderColor: colors.border, opacity: busy || pressed ? 0.6 : 1 },
            ]}
          >
            <Text style={[styles.needAnswerText, { color: colors.textTertiary }]}>
              Lascia stare
            </Text>
          </Pressable>
        </View>
      ) : null}

      {canAllowAlways ? (
        <View style={styles.needAlways} testID="ora-need-always">
          <Pressable
            onPress={onAllowAlways}
            disabled={busy}
            accessibilityRole="button"
            accessibilityHint={need.can_allow_always || undefined}
            testID="ora-need-allow-always"
            style={({ pressed }) => [{ opacity: busy || pressed ? 0.5 : 1 }]}
          >
            <Text style={[styles.needAlwaysAction, { color: colors.textSecondary }]}>
              Puoi farlo da sola anche in futuro
            </Text>
          </Pressable>
          <Text style={[styles.needAlwaysNote, { color: colors.textTertiary }]}>
            {need.can_allow_always}
          </Text>
        </View>
      ) : null}
    </View>
  );
}


/* Una frase incollata a "perché" non deve iniziare con la maiuscola. */
function lowerFirst(text: string): string {
  const t = (text || '').trim();
  if (!t) return t;
  return t.charAt(0).toLocaleLowerCase('it-IT') + t.slice(1);
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

  needDone: {
    gap: 2,
    marginTop: 6,
  },
  needAnswers: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 14,
  },
  needAnswer: {
    paddingHorizontal: 16,
    paddingVertical: 9,
    borderRadius: 999,
    borderWidth: 1,
  },
  needAnswerText: {
    fontSize: 14,
    fontWeight: '500',
  },
  /* Sotto, e più piano: è una domanda diversa, non un'opzione più forte. */
  needAlways: {
    marginTop: 18,
    gap: 4,
  },
  needAlwaysAction: {
    fontSize: 14,
    fontWeight: '500',
    textDecorationLine: 'underline',
  },
  needAlwaysNote: {
    fontSize: 13,
    lineHeight: 19,
  },
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
