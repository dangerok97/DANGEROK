import { useState } from 'react';
import { View, Text, StyleSheet, Pressable, Modal } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeInsight, ProactiveSuggestion } from '@/src/api/client';
import { triggerHaptic } from '@/src/theme/haptics';
import { AppDivider } from '@/src/components/ui/AppDivider';

type Props = {
  suggestions?: ProactiveSuggestion[] | null;
  insights?: HomeInsight[] | null;
  busyId?: string | null;
  onAccept: (id: string) => void;
  onDismiss: (id: string) => void;
  onSnooze: (id: string, preset: '15m' | '1h' | 'stasera' | 'domani') => void;
  onOpen?: (s: ProactiveSuggestion) => void;
  onIgnoreInsight: (id: string) => void;
  onInsightAction?: (ins: HomeInsight) => void;
};

const SNOOZE_PRESETS: { id: '15m' | '1h' | 'stasera' | 'domani'; label: string }[] = [
  { id: '15m', label: '15 min' },
  { id: '1h', label: '1 ora' },
  { id: 'stasera', label: 'Stasera' },
  { id: 'domani', label: 'Domani' },
];

/** Unified Aggiornamenti — suggestions + observations, no competing section titles. */
export function UpdatesSection({
  suggestions,
  insights,
  busyId,
  onAccept,
  onDismiss,
  onSnooze,
  onOpen,
  onIgnoreInsight,
  onInsightAction,
}: Props) {
  const { colors } = useTheme();
  const router = useRouter();
  const list = (suggestions || []).slice(0, 3);
  const activeInsights = (insights || []).filter((i) => i.status === 'active').slice(0, 2);
  const [snoozeFor, setSnoozeFor] = useState<string | null>(null);

  if (!list.length && !activeInsights.length) return null;

  return (
    <View style={styles.section} testID="updates-section">
      <Text style={[styles.h, { color: colors.textPrimary }]} accessibilityRole="header">
        Aggiornamenti
      </Text>

      {list.length ? (
        <View testID="ora-ti-consiglia" style={styles.block}>
          {list.map((s, idx) => (
            <View key={s.id}>
              <View style={styles.item} testID="proactive-suggestion-card">
                <Text style={[styles.kind, { color: colors.accent }]}>Suggerimento</Text>
                <Text style={[styles.title, { color: colors.textPrimary }]}>{s.title}</Text>
                {s.description ? (
                  <Text style={[styles.desc, { color: colors.textSecondary }]} numberOfLines={3}>
                    {s.description}
                  </Text>
                ) : null}
                {s.reason ? (
                  <Text style={[styles.reason, { color: colors.textTertiary }]} numberOfLines={2}>
                    {s.reason}
                  </Text>
                ) : null}
                <View style={styles.actions}>
                  <Pressable
                    style={[styles.btnPrimary, { backgroundColor: colors.accent }]}
                    onPress={() => { void triggerHaptic('selection'); onAccept(s.id); }}
                    disabled={busyId === s.id}
                    testID="suggestion-accept"
                    accessibilityRole="button"
                    accessibilityLabel="Accetta"
                  >
                    <Text style={[styles.btnPrimaryText, { color: colors.onAccent }]}>Accetta</Text>
                  </Pressable>
                  <Pressable
                    style={styles.btnGhost}
                    onPress={() => { void triggerHaptic('selection'); onDismiss(s.id); }}
                    disabled={busyId === s.id}
                    testID="suggestion-dismiss"
                    accessibilityRole="button"
                  >
                    <Text style={[styles.btnText, { color: colors.textSecondary }]}>Ignora</Text>
                  </Pressable>
                  <Pressable
                    style={styles.btnGhost}
                    onPress={() => { void triggerHaptic('selection'); setSnoozeFor(s.id); }}
                    testID="suggestion-snooze"
                    accessibilityRole="button"
                  >
                    <Text style={[styles.btnText, { color: colors.textSecondary }]}>Ricordamelo dopo</Text>
                  </Pressable>
                  <Pressable
                    style={styles.btnGhost}
                    onPress={() => {
                      void triggerHaptic('selection');
                      if (onOpen) onOpen(s);
                      else if (s.action?.route) router.push(s.action.route as any);
                    }}
                    testID="suggestion-open"
                    accessibilityRole="button"
                  >
                    <Ionicons name="open-outline" size={14} color={colors.textSecondary} />
                    <Text style={[styles.btnText, { color: colors.textSecondary }]}>Apri</Text>
                  </Pressable>
                </View>
              </View>
              {idx < list.length - 1 || activeInsights.length ? <AppDivider /> : null}
            </View>
          ))}
        </View>
      ) : null}

      {activeInsights.length ? (
        <View testID="ora-osserva" style={styles.block}>
          {activeInsights.map((ins, idx) => (
            <View key={ins.id}>
              <View style={styles.item} testID="insight-card">
                <Text style={[styles.kind, { color: colors.textTertiary }]}>Osservazione</Text>
                <Text style={[styles.desc, { color: colors.textPrimary }]}>{ins.text}</Text>
                <View style={styles.actions}>
                  {ins.action?.label ? (
                    <Pressable
                      style={styles.btnGhost}
                      onPress={() => { void triggerHaptic('selection'); onInsightAction?.(ins); }}
                      testID="insight-action"
                      accessibilityRole="button"
                    >
                      <Text style={[styles.btnText, { color: colors.accent }]}>{ins.action.label}</Text>
                    </Pressable>
                  ) : null}
                  <Pressable
                    style={styles.btnGhost}
                    onPress={() => { void triggerHaptic('selection'); onIgnoreInsight(ins.id); }}
                    testID="insight-ignore"
                    accessibilityRole="button"
                  >
                    <Text style={[styles.btnText, { color: colors.textSecondary }]}>Ignora</Text>
                  </Pressable>
                </View>
              </View>
              {idx < activeInsights.length - 1 ? <AppDivider /> : null}
            </View>
          ))}
        </View>
      ) : null}

      <Modal visible={!!snoozeFor} transparent animationType="fade" onRequestClose={() => setSnoozeFor(null)}>
        <Pressable style={[styles.modalBg, { backgroundColor: colors.scrim }]} onPress={() => setSnoozeFor(null)}>
          <View
            style={[styles.modalCard, { backgroundColor: colors.surfaceElevated, borderColor: colors.border }]}
            onStartShouldSetResponder={() => true}
          >
            <Text style={[styles.modalTitle, { color: colors.textPrimary }]}>Ricordamelo dopo</Text>
            {SNOOZE_PRESETS.map((p) => (
              <Pressable
                key={p.id}
                style={[styles.modalRow, { backgroundColor: colors.backgroundSecondary }]}
                onPress={() => {
                  if (snoozeFor) onSnooze(snoozeFor, p.id);
                  setSnoozeFor(null);
                }}
                testID={`suggestion-snooze-${p.id}`}
              >
                <Text style={[styles.btnText, { color: colors.textPrimary }]}>{p.label}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: tokens.spacing.sm },
  h: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    marginBottom: 4,
  },
  block: { gap: 0 },
  item: {
    paddingVertical: tokens.spacing.md,
    gap: 6,
  },
  kind: {
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.15,
  },
  title: {
    fontSize: tokens.typography.body.fontSize,
    fontWeight: '500',
    letterSpacing: -0.15,
  },
  desc: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  reason: {
    fontSize: tokens.typography.footnote.fontSize,
  },
  actions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 4,
  },
  btnPrimary: {
    minHeight: tokens.touch.min,
    paddingHorizontal: 14,
    borderRadius: tokens.radius.full,
    justifyContent: 'center',
  },
  btnPrimaryText: { fontSize: 13, fontWeight: '600' },
  btnGhost: {
    minHeight: tokens.touch.min,
    paddingHorizontal: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  btnText: { fontSize: 13, fontWeight: '500' },
  modalBg: { flex: 1, justifyContent: 'center', padding: 24 },
  modalCard: {
    borderRadius: tokens.radius.lg,
    padding: 16,
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
  },
  modalTitle: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  modalRow: {
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: tokens.radius.md,
    minHeight: tokens.touch.min,
    justifyContent: 'center',
  },
});
