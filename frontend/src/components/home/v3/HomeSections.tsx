import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type {
  HomeInsight,
  HomeItem,
  HomeOpportunity,
  OpenQuestionItem,
  ProactiveSuggestion,
} from '@/src/api/client';
import { ContextualCardVisual } from './ContextualCardVisual';
import { agoLabel, relativeDayLabel } from './homeItemView';

/* -------------------------------------------------------------------------- */
/* Shared section chrome                                                       */
/* -------------------------------------------------------------------------- */

export function SectionShell({
  title,
  count,
  footerLabel,
  onFooter,
  children,
  testID,
}: {
  title: string;
  count?: number;
  footerLabel?: string;
  onFooter?: () => void;
  children: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      <View style={styles.sectionHead}>
        <Text
          style={[styles.sectionTitle, { color: colors.accent }]}
          accessibilityRole="header"
          aria-level={2}
        >
          {title}
        </Text>
        {typeof count === 'number' && count > 0 ? (
          <View style={[styles.badge, { backgroundColor: colors.accentMuted }]}>
            <Text style={[styles.badgeText, { color: colors.accent }]}>{count}</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.sectionBody}>{children}</View>

      {footerLabel && onFooter ? (
        <Pressable
          onPress={onFooter}
          style={({ pressed }) => [styles.footer, pressed && styles.pressed]}
          accessibilityRole="button"
        >
          <Text style={[styles.footerLabel, { color: colors.accent }]}>{footerLabel}</Text>
          <Ionicons name="arrow-forward" size={13} color={colors.accent} />
        </Pressable>
      ) : null}
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* DOMANDE PER TE — ORA is waiting on an answer                                */
/* -------------------------------------------------------------------------- */

export function QuestionsSection({
  open = [],
  questions,
  busyId,
  onAnswer,
  onAnswerOpen,
  onSeeAll,
}: {
  /**
   * Questions ORA is actually blocked on.
   *
   * These come first because they are a different kind of thing from the rows
   * below them: answering one continues a piece of work that stopped, where a
   * suggestion is something ORA thought worth raising. Both belong under the
   * same heading — from the reader's side they are all "things ORA is waiting
   * to hear from me" — but the blockers are the ones with consequences.
   */
  open?: OpenQuestionItem[];
  questions: ProactiveSuggestion[];
  busyId?: string | null;
  onAnswer: (s: ProactiveSuggestion) => void;
  onAnswerOpen?: (q: OpenQuestionItem) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!questions.length && !open.length) return null;

  return (
    <SectionShell
      title="DOMANDE PER TE"
      count={questions.length + open.length}
      footerLabel={onSeeAll ? 'Vedi tutte le domande' : undefined}
      onFooter={onSeeAll}
      testID="home-questions"
    >
      {open.slice(0, 3).map((q) => (
        <View key={q.id} style={styles.row}>
          <ContextualCardVisual
            item={{ type: 'reply', source_type: 'ora' }}
            size="row"
            style={styles.rowVisual}
          />
          <View style={styles.rowText}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={3}>
              {q.question}
            </Text>
            {q.why_needed || q.context_label ? (
              <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={2}>
                {q.why_needed || q.context_label}
              </Text>
            ) : null}
          </View>
          <Pressable
            onPress={() => onAnswerOpen?.(q)}
            style={({ pressed }) => [
              styles.rowCta,
              { borderColor: colors.accent },
              pressed && styles.pressed,
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Rispondi: ${q.question}`}
            testID={`home-open-question-${q.id}`}
          >
            <Text style={[styles.rowCtaLabel, { color: colors.accent }]}>Rispondi</Text>
          </Pressable>
        </View>
      ))}

      {questions.slice(0, 3).map((q) => (
        <View key={q.id} style={styles.row}>
          <ContextualCardVisual
            item={{ type: 'reply', source_type: q.source }}
            size="row"
            style={styles.rowVisual}
          />
          <View style={styles.rowText}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
              {q.title}
            </Text>
            {/*
              Two lines, because one was not enough at 390px: with the answer
              button beside it this line had 166px to say "Proposta: mercoledì
              3 settembre alle 11:00", and a proposed date cut off before the
              time is worse than no date at all. The row is not pressable, so
              there is nowhere else to go and read it.
            */}
            {q.reason ? (
              <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={2}>
                {q.reason}
              </Text>
            ) : null}
          </View>
          <Pressable
            onPress={() => onAnswer(q)}
            disabled={busyId === q.id}
            style={({ pressed }) => [
              styles.rowCta,
              { borderColor: colors.accent },
              pressed && styles.pressed,
              busyId === q.id && styles.disabled,
            ]}
            accessibilityRole="button"
            accessibilityLabel={`Rispondi: ${q.title}`}
            testID={`home-question-answer-${q.id}`}
          >
            <Text style={[styles.rowCtaLabel, { color: colors.accent }]}>Rispondi</Text>
          </Pressable>
        </View>
      ))}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */
/* OGGI                                                                        */
/* -------------------------------------------------------------------------- */

export function TodaySection({
  items,
  onOpen,
  onSeeAll,
}: {
  items: HomeItem[];
  onOpen: (item: HomeItem) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!items.length) return null;

  return (
    <SectionShell
      title="OGGI"
      footerLabel={onSeeAll ? 'Vedi agenda completa' : undefined}
      onFooter={onSeeAll}
      testID="home-today"
    >
      {items.slice(0, 4).map((item) => {
        const at = item.start_at || item.due_at;
        const time = at
          ? new Date(at).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
          : null;
        return (
          <Pressable
            key={item.id}
            onPress={() => onOpen(item)}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            accessibilityRole="button"
            testID={`home-today-${item.id}`}
          >
            {time ? (
              <Text style={[styles.time, { color: colors.textSecondary }]}>{time}</Text>
            ) : (
              <View style={styles.timeSpacer} />
            )}
            <ContextualCardVisual item={item} size="row" style={styles.rowVisual} />
            <View style={styles.rowText}>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={1}>
                {item.title}
              </Text>
              {item.location || item.subtitle ? (
                <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                  {item.location || item.subtitle}
                </Text>
              ) : null}
            </View>
          </Pressable>
        );
      })}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */
/* AGGIORNAMENTI DI ORA                                                        */
/* -------------------------------------------------------------------------- */

export function UpdatesFeed({
  suggestions,
  insights,
  opportunities,
  busyId,
  onOpen,
  onDismiss,
  onInsight,
  onOpportunityOpen,
  onOpportunityDismiss,
  onOpportunityDefer,
  onSeeAll,
}: {
  suggestions: ProactiveSuggestion[];
  insights: HomeInsight[];
  /** What ORA judged worth saying, and worth saying now. Usually none. */
  opportunities?: HomeOpportunity[];
  busyId?: string | null;
  onOpen: (s: ProactiveSuggestion) => void;
  onDismiss: (id: string) => void;
  onInsight: (i: HomeInsight) => void;
  onOpportunityOpen?: (o: HomeOpportunity) => void;
  onOpportunityDismiss?: (o: HomeOpportunity) => void;
  onOpportunityDefer?: (o: HomeOpportunity) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  /*
    The backend already decided which of these belong here and how many —
    two judgements, both the model's. Slicing again is not a second opinion,
    it is the last line of defence: whatever arrives, this section stays a
    section and never becomes a list.
  */
  const raised = (opportunities || []).slice(0, 2);
  const total = suggestions.length + insights.length + raised.length;
  if (!total) return null;

  return (
    <SectionShell
      title="AGGIORNAMENTI DI ORA"
      footerLabel={onSeeAll ? 'Vedi tutti gli aggiornamenti' : undefined}
      onFooter={onSeeAll}
      testID="home-updates"
    >
      {raised.map((o) => (
        <View key={o.id} style={styles.oppItem} testID={`home-opportunity-${o.id}`}>
          <Text style={[styles.oppTitle, { color: colors.textPrimary }]}>{o.title}</Text>
          <Text style={[styles.oppWhy, { color: colors.textTertiary }]} numberOfLines={3}>
            {o.why_now}
          </Text>
          <View style={styles.oppActions}>
            <Pressable
              onPress={() => onOpportunityOpen?.(o)}
              style={({ pressed }) => [styles.oppCta, pressed && styles.pressed]}
              accessibilityRole="button"
              testID={`opportunity-open-${o.id}`}
            >
              <Text style={[styles.oppCtaText, { color: colors.accent }]}>Vediamo</Text>
            </Pressable>
            <Pressable
              onPress={() => onOpportunityDefer?.(o)}
              style={({ pressed }) => [styles.oppCta, pressed && styles.pressed]}
              accessibilityRole="button"
              testID={`opportunity-later-${o.id}`}
            >
              <Text style={[styles.oppCtaText, { color: colors.textSecondary }]}>Più tardi</Text>
            </Pressable>
            <Pressable
              onPress={() => onOpportunityDismiss?.(o)}
              style={({ pressed }) => [styles.oppCta, pressed && styles.pressed]}
              accessibilityRole="button"
              testID={`opportunity-dismiss-${o.id}`}
            >
              <Text style={[styles.oppCtaText, { color: colors.textSecondary }]}>
                Non mi interessa
              </Text>
            </Pressable>
          </View>
        </View>
      ))}

      {suggestions.slice(0, 3).map((s) => (
        <Pressable
          key={s.id}
          onPress={() => onOpen(s)}
          disabled={busyId === s.id}
          style={({ pressed }) => [styles.row, pressed && styles.pressed]}
          accessibilityRole="button"
          testID={`home-update-${s.id}`}
        >
          <ContextualCardVisual
            item={{ type: 'insight', source_type: s.source }}
            size="row"
            style={styles.rowVisual}
          />
          <View style={styles.rowText}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
              {s.title}
            </Text>
            {s.description || s.reason ? (
              <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                {s.description || s.reason}
              </Text>
            ) : null}
          </View>
          {agoLabel(s.created_at) ? (
            <Text style={[styles.ago, { color: colors.textTertiary }]}>{agoLabel(s.created_at)}</Text>
          ) : null}
          <Pressable
            onPress={() => onDismiss(s.id)}
            hitSlop={10}
            style={styles.dismiss}
            accessibilityRole="button"
            accessibilityLabel={`Ignora: ${s.title}`}
          >
            <Ionicons name="close" size={16} color={colors.textTertiary} />
          </Pressable>
        </Pressable>
      ))}

      {insights.slice(0, 3).map((i) => (
        <Pressable
          key={i.id}
          onPress={() => onInsight(i)}
          style={({ pressed }) => [styles.row, pressed && styles.pressed]}
          accessibilityRole="button"
          testID={`home-insight-${i.id}`}
        >
          <ContextualCardVisual
            item={{ type: 'insight', source_type: i.source }}
            size="row"
            style={styles.rowVisual}
          />
          <View style={styles.rowText}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
              {i.text}
            </Text>
          </View>
          {agoLabel(i.created_at) ? (
            <Text style={[styles.ago, { color: colors.textTertiary }]}>{agoLabel(i.created_at)}</Text>
          ) : null}
        </Pressable>
      ))}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */
/* PIÙ AVANTI                                                                  */
/* -------------------------------------------------------------------------- */

export function HorizonSection({
  items,
  onOpen,
  onSeeAll,
}: {
  items: HomeItem[];
  onOpen: (item: HomeItem) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!items.length) return null;

  return (
    <SectionShell
      title="PIÙ AVANTI"
      footerLabel={onSeeAll ? 'Vedi tutto il calendario' : undefined}
      onFooter={onSeeAll}
      testID="home-horizon"
    >
      {items.slice(0, 4).map((item) => {
        const at = item.start_at || item.due_at || item.goal_target_date;
        const rel = relativeDayLabel(at);
        const d = at ? new Date(at) : null;
        return (
          <Pressable
            key={item.id}
            onPress={() => onOpen(item)}
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            accessibilityRole="button"
            testID={`home-horizon-${item.id}`}
          >
            {d ? (
              <View style={styles.dateChip}>
                <Text style={[styles.dateDay, { color: colors.textPrimary }]}>{d.getDate()}</Text>
                <Text style={[styles.dateMonth, { color: colors.textTertiary }]}>
                  {d.toLocaleDateString('it-IT', { month: 'short' }).replace('.', '').toUpperCase()}
                </Text>
              </View>
            ) : (
              <View style={styles.timeSpacer} />
            )}
            <View style={styles.rowText}>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={1}>
                {item.title}
              </Text>
              {item.subtitle || item.description ? (
                <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                  {item.subtitle || item.description}
                </Text>
              ) : null}
            </View>
            {rel ? (
              <View style={[styles.relChip, { backgroundColor: colors.warningBg }]}>
                <Text style={[styles.relText, { color: colors.warning }]}>{rel}</Text>
              </View>
            ) : null}
          </Pressable>
        );
      })}
    </SectionShell>
  );
}

/* -------------------------------------------------------------------------- */

const styles = StyleSheet.create({
  section: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.lg,
    gap: tokens.spacing.md,
  },
  sectionHead: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.sm },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.3,
    flex: 1,
  },
  badge: {
    minWidth: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { fontSize: 12, fontWeight: '700' },
  sectionBody: { gap: tokens.spacing.sm },
  /*
    On a phone this row kept its horizontal shape and left the words about
    165px to live in, so a two-line clamp cut the question itself in half with
    no pressable row to open and read the rest. Wrapping lets the action drop
    beneath the text once the text needs the width; on a wide screen nothing
    moves, because nothing has to.
  */
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    minHeight: 48,
    flexWrap: 'wrap',
  },
  rowVisual: { width: 34, height: 34 },
  rowText: { flex: 1, gap: 2, minWidth: 190 },
  rowTitle: { fontSize: 14, fontWeight: '500', lineHeight: 20 },
  rowMeta: { fontSize: 12, lineHeight: 17 },
  /*
    Hit area, not weight. These three sat at 34, 24 and 32 pixels tall — under
    the floor on a phone, and the dismiss cross was the smallest control in the
    product. The label, the border and the spacing are untouched; only the box
    a thumb has to find grew.
  */
  rowCta: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.md,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  rowCtaLabel: { fontSize: 13, fontWeight: '600' },
  time: { fontSize: 13, fontWeight: '500', width: 46 },
  timeSpacer: { width: 46 },
  dateChip: { width: 46, alignItems: 'flex-start' },
  dateDay: { fontSize: 17, fontWeight: '700', lineHeight: 20 },
  dateMonth: { fontSize: 10, fontWeight: '600', letterSpacing: 0.5 },
  relChip: {
    borderRadius: tokens.radius.sm,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  relText: { fontSize: 11, fontWeight: '600' },
  ago: { fontSize: 11, marginLeft: 'auto', paddingLeft: 6 },
  dismiss: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginRight: -10,
  },
  footer: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    minHeight: tokens.touch.min, alignSelf: 'flex-start',
  },
  footerLabel: { fontSize: 13, fontWeight: '600' },
  pressed: { opacity: 0.65 },
  disabled: { opacity: 0.5 },

  /*
    An opportunity is a sentence, not a row. The other entries here are things
    that already happened and read fine at a glance; this one is ORA saying
    something and offering to talk about it, so it gets room to be read and
    three plain answers underneath. No badge, no colour coding, no icon
    competing for the eye — quiet is the point.
  */
  oppItem: {
    paddingVertical: tokens.spacing.md,
    gap: 4,
  },
  oppTitle: {
    fontSize: tokens.typography.body.fontSize,
    lineHeight: 21,
    fontWeight: '500',
    letterSpacing: -0.15,
  },
  oppWhy: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  oppActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 14,
    marginTop: 6,
  },
  oppCta: {
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
  oppCtaText: { fontSize: 13, fontWeight: '600' },
});
