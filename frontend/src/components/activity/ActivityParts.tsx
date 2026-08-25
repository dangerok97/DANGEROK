import * as React from 'react';
import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { ContextualCardVisual } from '@/src/components/home/v3/ContextualCardVisual';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { ActivityResponse } from '@/src/api/client';
import {
  actorLabel,
  dayBadge,
  dueLabel,
  heroAction,
  questionCta,
  questionEyebrow,
  waitingLabel,
  whenLabel,
} from './activityView';

type Activity = ActivityResponse;

/** Hints emitted with the row, never derived from its words. */
const SUMMARY_ICONS: Record<string, React.ComponentProps<typeof Ionicons>['name']> = {
  todo: 'checkmark-circle-outline',
  waiting: 'time-outline',
  done: 'checkmark-done-outline',
};

/* -------------------------------------------------------------------------- */
/* Header                                                                     */
/* -------------------------------------------------------------------------- */

export function ActivityHeader({ onWhy }: { onWhy: () => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.header} testID="activity-header">
      <View style={styles.headerText}>
        <Text
          style={[styles.title, { color: colors.textPrimary }]}
          accessibilityRole="header"
          aria-level={1}
        >
          Attività
        </Text>
        <Text style={[styles.sub, { color: colors.textSecondary }]}>
          Qui trovi le domande, gli aggiornamenti e le azioni di ORA.
        </Text>
      </View>
      <Pressable
        onPress={onWhy}
        style={({ pressed }) => [
          styles.whyBtn,
          { backgroundColor: colors.surface, borderColor: colors.border },
          pressed && styles.pressed,
        ]}
        accessibilityRole="button"
        testID="activity-why"
      >
        <Ionicons name="sparkles-outline" size={14} color={colors.accent} />
        <Text style={[styles.whyLabel, { color: colors.textSecondary }]}>Perché conta?</Text>
      </Pressable>
    </View>
  );
}

/** What this page is for, and the promise it exists to make visible. */
export function WhyActivityDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { colors } = useTheme();
  const lines = [
    'Qui vedi cosa ORA sta aspettando da te, cosa è cambiato e quali azioni sono state completate.',
    'ORA non esegue azioni che richiedono il tuo consenso senza chiedertelo.',
  ];
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        onPress={onClose}
        accessibilityLabel="Chiudi"
      >
        <View
          style={[
            styles.dialog,
            { backgroundColor: colors.surfaceElevated, borderColor: colors.border },
          ]}
          onStartShouldSetResponder={() => true}
          accessibilityViewIsModal
          testID="activity-why-dialog"
        >
          <View style={styles.dialogHead}>
            <Text
              style={[styles.dialogTitle, { color: colors.textPrimary }]}
              accessibilityRole="header"
              aria-level={2}
            >
              Perché Attività
            </Text>
            <Pressable
              onPress={onClose}
              hitSlop={8}
              style={({ pressed }) => [styles.close, pressed && styles.pressed]}
              accessibilityRole="button"
              accessibilityLabel="Chiudi"
              testID="activity-why-close"
            >
              <Ionicons name="close" size={20} color={colors.textTertiary} />
            </Pressable>
          </View>
          {lines.map((l) => (
            <Text key={l} style={[styles.dialogLine, { color: colors.textSecondary }]}>
              {l}
            </Text>
          ))}
        </View>
      </Pressable>
    </Modal>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel shell                                                                */
/* -------------------------------------------------------------------------- */

/** A titled surface. Absent when empty — a box with a heading and nothing in it is noise. */
export function Panel({
  icon,
  title,
  children,
  footer,
  testID,
}: {
  icon?: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  const present = React.Children.toArray(children).filter(Boolean);
  if (!present.length) return null;
  return (
    <View
      style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      <View style={styles.panelHead}>
        {icon ? <Ionicons name={icon} size={16} color={colors.accent} /> : null}
        <Text style={[styles.panelTitle, { color: colors.textPrimary }]}>{title}</Text>
      </View>
      {children}
      {footer}
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* DA FARE ADESSO                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The one thing most worth doing, if there is one.
 *
 * Attività does not rank: this is whatever Home's attention already put first,
 * wearing the picture its entity already owns. The button is one of the actions
 * that item genuinely has — never a label invented to fill the space.
 */
export function AttentionHero({
  attention,
  onAct,
}: {
  attention: NonNullable<Activity['attention']>;
  onAct: (action: { kind: string; route?: string | null }) => void;
}) {
  const { colors } = useTheme();
  const action = heroAction(attention.actions);
  const visual = attention.visual;

  return (
    <View
      style={[styles.hero, { backgroundColor: colors.surfaceWarm, borderColor: colors.divider }]}
      testID="activity-hero"
    >
      <View style={styles.heroBody}>
        <Text style={[styles.heroEyebrow, { color: colors.warning }]}>DA FARE ADESSO</Text>
        <Text style={[styles.heroTitle, { color: colors.textPrimary }]} numberOfLines={2}>
          {attention.title}
        </Text>
        {attention.detail ? (
          <Text style={[styles.heroDetail, { color: colors.textSecondary }]} numberOfLines={3}>
            {attention.detail}
          </Text>
        ) : null}
        {action ? (
          <Pressable
            onPress={() => onAct(action)}
            style={({ pressed }) => [
              styles.heroCta,
              { backgroundColor: colors.accent },
              pressed && styles.pressed,
            ]}
            accessibilityRole="button"
            testID="activity-hero-cta"
          >
            <Text style={[styles.heroCtaLabel, { color: colors.onAccent }]}>
              {action.label || 'Apri'}
            </Text>
            <Ionicons name="arrow-forward" size={16} color={colors.onAccent} />
          </Pressable>
        ) : null}
      </View>
      <ContextualCardVisual
        imageSource={visual?.status === 'ready' ? visual.url : null}
        generating={visual?.status === 'queued' || visual?.status === 'generating'}
        size="hero"
        style={styles.heroVisual}
        testID="activity-hero-visual"
      />
    </View>
  );
}

/* -------------------------------------------------------------------------- */
/* DOMANDE PER TE                                                             */
/* -------------------------------------------------------------------------- */

/** How many rows fit before the panel stops being a summary of what is open. */
const QUESTIONS_COLLAPSED = 3;

export function QuestionsPanel({
  questions,
  onAnswer,
}: {
  questions: Activity['questions'];
  onAnswer: (q: Activity['questions'][number]) => void;
}) {
  const { colors } = useTheme();
  const [expanded, setExpanded] = React.useState(false);
  if (!questions.length) return null;
  // Expanding in place rather than linking away: there is no "all questions"
  // surface, and inventing one would make the link a dead end. The rest are one
  // tap from here and never hidden.
  const shown = expanded ? questions : questions.slice(0, QUESTIONS_COLLAPSED);
  const hidden = questions.length - shown.length;
  return (
    <Panel
      icon="help-circle-outline"
      title="Domande per te"
      testID="activity-questions"
      footer={
        hidden > 0 || expanded ? (
          <Pressable
            onPress={() => setExpanded((v) => !v)}
            style={({ pressed }) => [styles.panelFooter, pressed && styles.pressed]}
            accessibilityRole="button"
            testID="activity-questions-more"
          >
            <Text style={[styles.panelFooterLabel, { color: colors.accent }]}>
              {expanded ? 'Mostra meno' : `Vedi tutte le domande (${questions.length})`}
            </Text>
          </Pressable>
        ) : null
      }
    >
      {shown.map((q, i) => {
        const eyebrow = questionEyebrow(q.needs_consent);
        return (
          <View
            key={q.id}
            style={[
              styles.row,
              i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
            ]}
          >
            <View
              style={[
                styles.rowMark,
                { backgroundColor: q.needs_consent ? colors.warningBg : colors.accentMuted },
              ]}
            >
              <Ionicons
                name={q.needs_consent ? 'shield-checkmark-outline' : 'chatbubble-ellipses-outline'}
                size={16}
                color={q.needs_consent ? colors.warning : colors.accent}
              />
            </View>
            <View style={styles.rowBody}>
              {eyebrow ? (
                <Text style={[styles.rowEyebrow, { color: colors.warning }]}>{eyebrow}</Text>
              ) : null}
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={3}>
                {q.title}
              </Text>
              {q.detail ? (
                <Text style={[styles.rowDetail, { color: colors.textSecondary }]} numberOfLines={2}>
                  {q.detail}
                </Text>
              ) : null}
            </View>
            <Pressable
              onPress={() => onAnswer(q)}
              style={({ pressed }) => [
                styles.rowCta,
                { borderColor: colors.border, backgroundColor: colors.backgroundPrimary },
                pressed && styles.pressed,
              ]}
              accessibilityRole="button"
              accessibilityLabel={`${questionCta(q.needs_consent)}: ${q.title}`}
              testID={`activity-answer-${q.id}`}
            >
              <Text style={[styles.rowCtaLabel, { color: colors.accent }]}>
                {questionCta(q.needs_consent)}
              </Text>
            </Pressable>
          </View>
        );
      })}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* IN ATTESA                                                                  */
/* -------------------------------------------------------------------------- */

/**
 * Things that cannot move yet, and what each is waiting on.
 *
 * Never a list of postponed items: what a person chose to see later is their
 * decision about attention, not a dependency, and the read model keeps the two
 * apart before either reaches here.
 */
export function WaitingPanel({
  waiting,
  onOpen,
}: {
  waiting: Activity['waiting'];
  onOpen: (route?: string | null) => void;
}) {
  const { colors } = useTheme();
  if (!waiting.length) return null;
  return (
    <Panel icon="time-outline" title="In attesa" testID="activity-waiting">
      {waiting.map((w, i) => {
        const due = dueLabel(w.when);
        const body = (
          <>
            <View style={[styles.rowMark, { backgroundColor: colors.backgroundSecondary }]}>
              <Ionicons name="hourglass-outline" size={16} color={colors.textTertiary} />
            </View>
            <View style={styles.rowBody}>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
                {w.title}
              </Text>
              <Text style={[styles.rowDetail, { color: colors.textSecondary }]} numberOfLines={2}>
                {waitingLabel(w.waiting_for, w.when)}
              </Text>
            </View>
            {due && due !== 'Scaduta' ? (
              <View style={[styles.pill, { backgroundColor: colors.backgroundSecondary }]}>
                <Text style={[styles.pillLabel, { color: colors.textSecondary }]} numberOfLines={1}>
                  {due}
                </Text>
              </View>
            ) : null}
          </>
        );
        const style = [
          styles.row,
          i > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.divider },
        ];
        if (!w.route) {
          return (
            <View key={w.id} style={style}>
              {body}
            </View>
          );
        }
        return (
          <Pressable
            key={w.id}
            onPress={() => onOpen(w.route)}
            style={({ pressed }) => [...style, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={w.title}
            testID={`activity-waiting-${w.id}`}
          >
            {body}
          </Pressable>
        );
      })}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* AGGIORNAMENTI RECENTI                                                      */
/* -------------------------------------------------------------------------- */

export function UpdatesPanel({
  updates,
  onOpen,
}: {
  updates: Activity['updates'];
  onOpen: (route?: string | null) => void;
}) {
  const { colors } = useTheme();
  if (!updates.length) return null;
  return (
    <Panel icon="pulse-outline" title="Aggiornamenti recenti" testID="activity-updates">
      {updates.map((u) => {
        const when = whenLabel(u.at);
        const body = (
          <>
            <View style={styles.timelineCol}>
              <View style={[styles.timelineDot, { backgroundColor: colors.accent }]} />
            </View>
            <View style={styles.rowBody}>
              {/* Who moved: ORA authored it, or ORA registered that it changed.
                  Claiming the first when it was the second would be flattering
                  and false. */}
              <Text style={[styles.rowEyebrow, { color: colors.textTertiary }]}>
                {actorLabel(u.actor)}
              </Text>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
                {u.title}
              </Text>
              <Text style={[styles.rowMeta, { color: colors.textTertiary }]} numberOfLines={1}>
                {[u.context, when].filter(Boolean).join(' · ')}
              </Text>
            </View>
          </>
        );
        if (!u.route) {
          return (
            <View key={u.id} style={styles.updateRow}>
              {body}
            </View>
          );
        }
        return (
          <Pressable
            key={u.id}
            onPress={() => onOpen(u.route)}
            style={({ pressed }) => [styles.updateRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={u.title}
            testID={`activity-update-${u.id}`}
          >
            {body}
          </Pressable>
        );
      })}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* Right rail                                                                 */
/* -------------------------------------------------------------------------- */

export function SummaryPanel({ rows }: { rows: Activity['summary'] }) {
  const { colors } = useTheme();
  if (!rows.length) return null;
  return (
    <Panel title="IN SINTESI" testID="activity-summary">
      {rows.map((r) => (
        <View key={r.label} style={styles.summaryRow}>
          <Ionicons name={SUMMARY_ICONS[r.icon || ''] || 'ellipse-outline'} size={16} color={colors.accent} />
          <Text style={[styles.summaryLabel, { color: colors.textSecondary }]} numberOfLines={1}>
            {r.label}
          </Text>
          <Text style={[styles.summaryValue, { color: colors.textPrimary }]}>{r.value}</Text>
        </View>
      ))}
    </Panel>
  );
}

export function DeadlinesPanel({
  deadlines,
  onOpen,
}: {
  deadlines: Activity['deadlines'];
  onOpen: (route?: string | null) => void;
}) {
  const { colors } = useTheme();
  if (!deadlines.length) return null;
  return (
    <Panel title="PROSSIME SCADENZE" testID="activity-deadlines">
      {deadlines.map((d) => {
        const badge = dayBadge(d.at);
        const due = dueLabel(d.at);
        const body = (
          <>
            {badge ? (
              <View style={styles.dateBadge}>
                <Text style={[styles.dateDay, { color: colors.textPrimary }]}>{badge.day}</Text>
                <Text style={[styles.dateMonth, { color: colors.textTertiary }]}>{badge.month}</Text>
              </View>
            ) : null}
            <View style={styles.rowBody}>
              <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
                {d.title}
              </Text>
              {due ? (
                <Text style={[styles.rowMeta, { color: colors.textTertiary }]}>{due}</Text>
              ) : null}
            </View>
            {d.route ? (
              <Ionicons name="chevron-forward" size={15} color={colors.textTertiary} />
            ) : null}
          </>
        );
        if (!d.route) {
          return (
            <View key={d.id} style={styles.railRow}>
              {body}
            </View>
          );
        }
        return (
          <Pressable
            key={d.id}
            onPress={() => onOpen(d.route)}
            style={({ pressed }) => [styles.railRow, pressed && styles.pressed]}
            accessibilityRole="button"
            accessibilityLabel={d.title}
            testID={`activity-deadline-${d.id}`}
          >
            {body}
          </Pressable>
        );
      })}
    </Panel>
  );
}

export function CompletedPanel({ completed }: { completed: Activity['completed'] }) {
  const { colors } = useTheme();
  if (!completed.length) return null;
  return (
    <Panel title="COMPLETATE DI RECENTE" testID="activity-completed">
      {completed.map((c) => (
        <View key={c.id} style={styles.railRow}>
          <Ionicons name="checkmark-circle" size={18} color={colors.success} />
          <View style={styles.rowBody}>
            <Text style={[styles.rowTitle, { color: colors.textPrimary }]} numberOfLines={2}>
              {c.title}
            </Text>
            <Text style={[styles.rowMeta, { color: colors.textTertiary }]}>
              {whenLabel(c.at)}
            </Text>
          </View>
        </View>
      ))}
    </Panel>
  );
}

/* -------------------------------------------------------------------------- */
/* States                                                                     */
/* -------------------------------------------------------------------------- */

export function ActivityEmpty() {
  const { colors } = useTheme();
  return (
    <View style={styles.empty} testID="activity-empty">
      <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
        Non c'è nulla che richieda la tua attenzione.
      </Text>
      <Text style={[styles.emptyBody, { color: colors.textSecondary }]}>
        Quando ORA avrà una domanda, un aggiornamento o qualcosa da mostrarti, lo troverai qui.
      </Text>
    </View>
  );
}

export function ActivitySkeleton({ wide }: { wide: boolean }) {
  const { colors } = useTheme();
  const box = (h: number) => (
    <View
      style={[
        styles.skBox,
        { backgroundColor: colors.surface, borderColor: colors.border, minHeight: h },
      ]}
    />
  );
  const bar = (w: any, h = 12) => (
    <View style={{ width: w, height: h, borderRadius: 6, backgroundColor: colors.skeleton }} />
  );
  return (
    <View style={styles.skeleton} testID="activity-skeleton">
      <View style={styles.skHead}>
        {bar(120, 28)}
        {bar('50%')}
      </View>
      <View style={wide ? styles.skRow : undefined}>
        <View style={[styles.skMain, wide && styles.skFlex]}>
          {box(220)}
          <View style={styles.skPair}>
            {box(200)}
            {box(200)}
          </View>
          {box(240)}
        </View>
        {wide ? (
          <View style={styles.skRail}>
            {box(150)}
            {box(190)}
            {box(190)}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.lg },
  headerText: { flex: 1, gap: 4 },
  title: { fontSize: 30, fontWeight: '700', letterSpacing: -0.8, lineHeight: 37 },
  sub: { fontSize: 15, lineHeight: 21, maxWidth: 520 },
  whyBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 7,
    borderWidth: StyleSheet.hairlineWidth, borderRadius: tokens.radius.md,
    paddingHorizontal: tokens.spacing.lg, minHeight: 40,
  },
  whyLabel: { fontSize: 13, fontWeight: '500' },

  scrim: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: tokens.spacing.xl },
  dialog: {
    width: 460, maxWidth: '100%',
    borderRadius: tokens.radius.xl, borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.xl, gap: tokens.spacing.md,
  },
  dialogHead: { flexDirection: 'row', alignItems: 'flex-start', gap: tokens.spacing.md },
  dialogTitle: { fontSize: 19, fontWeight: '700', flex: 1, letterSpacing: -0.3 },
  close: {
    width: tokens.touch.min, height: tokens.touch.min,
    alignItems: 'center', justifyContent: 'center', marginTop: -10, marginRight: -12,
  },
  dialogLine: { fontSize: 14, lineHeight: 21 },

  hero: {
    flexDirection: 'row',
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
    minHeight: 220,
  },
  /**
   * Held clear of the illustration. Left to take the full width, the title and
   * the supporting line ran across the picture — text over an image with no
   * scrim, unreadable at exactly the size a hero needs to be read at.
   */
  heroBody: { width: '58%', padding: tokens.spacing.xl, gap: 8, zIndex: 1 },
  heroEyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 1.4 },
  heroTitle: { fontSize: 24, fontWeight: '700', lineHeight: 31, letterSpacing: -0.5 },
  heroDetail: { fontSize: 14, lineHeight: 21, maxWidth: 420 },
  heroCta: {
    flexDirection: 'row', alignItems: 'center', gap: 8, alignSelf: 'flex-start',
    minHeight: tokens.touch.min, paddingHorizontal: tokens.spacing.xl,
    borderRadius: tokens.radius.md, marginTop: 'auto',
  },
  heroCtaLabel: { fontSize: 15, fontWeight: '600' },
  heroVisual: { position: 'absolute', right: 0, top: 0, bottom: 0, width: '40%', borderRadius: 0 },

  panel: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: tokens.spacing.lg,
    paddingVertical: tokens.spacing.md,
    gap: 2,
  },
  panelHead: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: tokens.spacing.sm,
  },
  panelTitle: { fontSize: 15, fontWeight: '700', letterSpacing: -0.1 },

  row: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    paddingVertical: tokens.spacing.md, minHeight: 56,
  },
  rowMark: {
    width: 34, height: 34, borderRadius: tokens.radius.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  rowBody: { flex: 1, gap: 1 },
  rowEyebrow: { fontSize: 11, fontWeight: '700', letterSpacing: 0.6 },
  rowTitle: { fontSize: 14, lineHeight: 20, fontWeight: '500' },
  rowDetail: { fontSize: 12, lineHeight: 17 },
  rowMeta: { fontSize: 11, lineHeight: 16 },
  rowCta: {
    minHeight: tokens.touch.min, justifyContent: 'center',
    paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.pill, borderWidth: StyleSheet.hairlineWidth,
  },
  rowCtaLabel: { fontSize: 13, fontWeight: '600' },
  pill: {
    borderRadius: tokens.radius.sm, paddingHorizontal: 8, paddingVertical: 3, maxWidth: 110,
  },
  pillLabel: { fontSize: 11, fontWeight: '600' },

  panelFooter: { minHeight: 38, justifyContent: 'center', paddingTop: 2 },
  panelFooterLabel: { fontSize: 12, fontWeight: '600' },
  updateRow: { flexDirection: 'row', gap: tokens.spacing.md, paddingVertical: tokens.spacing.md },
  timelineCol: { width: 10, alignItems: 'center', paddingTop: 6 },
  timelineDot: { width: 7, height: 7, borderRadius: 4 },

  summaryRow: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 38 },
  summaryLabel: { fontSize: 13, flex: 1 },
  summaryValue: { fontSize: 16, fontWeight: '700' },

  railRow: {
    flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md,
    paddingVertical: tokens.spacing.sm, minHeight: tokens.touch.min,
  },
  dateBadge: { width: 34, alignItems: 'center' },
  dateDay: { fontSize: 16, fontWeight: '700', lineHeight: 20 },
  dateMonth: { fontSize: 10, fontWeight: '700', letterSpacing: 0.6 },

  empty: { gap: 8, paddingVertical: tokens.spacing.xxxl, maxWidth: 520 },
  emptyTitle: { fontSize: 22, fontWeight: '700', letterSpacing: -0.5, lineHeight: 29 },
  emptyBody: { fontSize: 15, lineHeight: 22 },

  skeleton: { gap: tokens.spacing.xl },
  skHead: { gap: tokens.spacing.sm },
  skRow: { flexDirection: 'row', gap: tokens.spacing.xl, alignItems: 'flex-start' },
  skMain: { gap: tokens.spacing.lg },
  skFlex: { flex: 1 },
  skRail: { width: 300, gap: tokens.spacing.lg },
  skPair: { flexDirection: 'row', gap: tokens.spacing.lg },
  skBox: { flex: 1, borderRadius: tokens.radius.lg, borderWidth: StyleSheet.hairlineWidth },
  pressed: { opacity: 0.75 },
});
