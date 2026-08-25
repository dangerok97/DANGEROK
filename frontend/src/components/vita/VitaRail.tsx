import * as React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { whenLabel, type VitaQuestion, type VitaSummaryRow, type VitaUpdate } from './vitaModel';

/** A rail panel. Absent, never empty — a titled box with nothing in it is noise. */
function Panel({
  icon,
  title,
  children,
  footer,
  testID,
}: {
  icon: React.ComponentProps<typeof Ionicons>['name'];
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <View
      style={[styles.panel, { backgroundColor: colors.surface, borderColor: colors.border }]}
      testID={testID}
    >
      <View style={styles.panelHead}>
        <Ionicons name={icon} size={15} color={colors.textTertiary} />
        <Text style={[styles.panelTitle, { color: colors.textSecondary }]}>{title}</Text>
      </View>
      {children}
      {footer}
    </View>
  );
}

/* -------------------------------------------------------------------------- */

/**
 * Things ORA genuinely needs settled.
 *
 * Every row here is a memory the reasoning core itself marked ambiguous and
 * flagged as clarifiable, so tapping one opens the clarification flow that
 * already exists. Nothing is invented to fill the panel: with no open
 * questions the panel does not appear at all, because a page that always has
 * something to ask teaches the user to stop reading it.
 */
export function QuestionsPanel({
  questions,
  onAsk,
  onSeeAll,
}: {
  questions: VitaQuestion[];
  onAsk: (q: VitaQuestion) => void;
  onSeeAll?: () => void;
}) {
  const { colors } = useTheme();
  if (!questions.length) return null;
  return (
    <Panel
      icon="help-circle-outline"
      title="DA CHIARIRE"
      testID="vita-questions"
      footer={
        onSeeAll ? (
          <Pressable
            onPress={onSeeAll}
            style={({ pressed }) => [styles.footerLink, pressed && styles.pressed]}
            accessibilityRole="button"
          >
            <Text style={[styles.footerLabel, { color: colors.accent }]}>
              Vedi tutte le questioni
            </Text>
          </Pressable>
        ) : null
      }
    >
      {questions.map((q) => (
        <Pressable
          key={q.memoryId}
          onPress={() => onAsk(q)}
          style={({ pressed }) => [styles.qRow, pressed && styles.pressed]}
          accessibilityRole="button"
          accessibilityLabel={q.question}
          testID={`vita-question-${q.memoryId}`}
        >
          <Text style={[styles.qMark, { color: colors.textTertiary }]}>?</Text>
          <Text style={[styles.qText, { color: colors.textPrimary }]} numberOfLines={3}>
            {q.question}
          </Text>
          <Ionicons name="chevron-forward" size={15} color={colors.textTertiary} />
        </Pressable>
      ))}
    </Panel>
  );
}

/**
 * Proof that the map is alive.
 *
 * Real revisions, said the way ORA would say them, with when they happened.
 * No internal event vocabulary reaches this list — a person does not need to
 * know that a node was updated, only that ORA now knows something different.
 */
export function UpdatesPanel({ updates }: { updates: VitaUpdate[] }) {
  const { colors } = useTheme();
  if (!updates.length) return null;
  return (
    <Panel icon="time-outline" title="ULTIMI AGGIORNAMENTI" testID="vita-updates">
      {updates.map((u) => {
        const when = whenLabel(u.at);
        return (
          <View key={u.id} style={styles.uRow}>
            <View style={[styles.uDot, { backgroundColor: colors.accent }]} />
            <View style={styles.uBody}>
              {u.areaTitle ? (
                <Text style={[styles.uArea, { color: colors.textTertiary }]} numberOfLines={1}>
                  {u.areaTitle}
                </Text>
              ) : null}
              <Text style={[styles.uText, { color: colors.textPrimary }]} numberOfLines={2}>
                {u.statement}
              </Text>
              {when ? (
                <Text style={[styles.uWhen, { color: colors.textTertiary }]}>{when}</Text>
              ) : null}
            </View>
          </View>
        );
      })}
    </Panel>
  );
}

/** Counts of things visible on this same page — nothing a user cannot verify. */
export function SummaryPanel({ rows }: { rows: VitaSummaryRow[] }) {
  const { colors } = useTheme();
  if (!rows.length) return null;
  return (
    <Panel icon="albums-outline" title="IN SINTESI" testID="vita-summary">
      {rows.map((r) => (
        <View key={r.label} style={styles.sRow}>
          <Text style={[styles.sLabel, { color: colors.textSecondary }]} numberOfLines={1}>
            {r.label}
          </Text>
          <Text style={[styles.sValue, { color: colors.textPrimary }]}>{r.value}</Text>
        </View>
      ))}
    </Panel>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.sm,
  },
  panelHead: { flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 2 },
  panelTitle: { fontSize: 11, fontWeight: '700', letterSpacing: 1.1 },

  qRow: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 9,
    minHeight: tokens.touch.min, paddingVertical: 7,
  },
  qMark: { fontSize: 14, fontWeight: '700', lineHeight: 19, width: 12 },
  qText: { fontSize: 13, lineHeight: 19, flex: 1 },

  uRow: { flexDirection: 'row', gap: 9, alignItems: 'flex-start', paddingVertical: 6 },
  uDot: { width: 7, height: 7, borderRadius: 4, marginTop: 6 },
  uBody: { flex: 1, gap: 1 },
  uArea: { fontSize: 11, fontWeight: '600' },
  uText: { fontSize: 13, lineHeight: 18 },
  uWhen: { fontSize: 11 },

  sRow: { flexDirection: 'row', alignItems: 'center', gap: tokens.spacing.md, minHeight: 32 },
  sLabel: { fontSize: 13, flex: 1 },
  sValue: { fontSize: 15, fontWeight: '700' },

  footerLink: { minHeight: 34, justifyContent: 'center', marginTop: 2 },
  footerLabel: { fontSize: 12, fontWeight: '600' },
  pressed: { opacity: 0.7 },
});
