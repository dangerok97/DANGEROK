import { useState } from 'react';
import { View, Text, StyleSheet, Pressable, Modal } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { ProactiveSuggestion } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';

type Props = {
  suggestions: ProactiveSuggestion[];
  busyId?: string | null;
  onAccept: (id: string) => void;
  onDismiss: (id: string) => void;
  onSnooze: (id: string, preset: '15m' | '1h' | 'stasera' | 'domani') => void;
  onOpen?: (s: ProactiveSuggestion) => void;
};

const SNOOZE_PRESETS: { id: '15m' | '1h' | 'stasera' | 'domani'; label: string }[] = [
  { id: '15m', label: '15 min' },
  { id: '1h', label: '1 ora' },
  { id: 'stasera', label: 'Stasera' },
  { id: 'domani', label: 'Domani' },
];

/** Home section — max 3 proactive suggestions; hidden when empty. */
export function OraTiConsiglia({
  suggestions, busyId, onAccept, onDismiss, onSnooze, onOpen,
}: Props) {
  const router = useRouter();
  const list = (suggestions || []).slice(0, 3);
  const [snoozeFor, setSnoozeFor] = useState<string | null>(null);

  if (!list.length) return null;

  return (
    <View style={styles.section} testID="ora-ti-consiglia">
      <Text style={styles.h} accessibilityRole="header">ORA TI CONSIGLIA</Text>
      {list.map((s) => (
        <View key={s.id} style={styles.card} testID="proactive-suggestion-card">
          <Text style={styles.title}>{s.title}</Text>
          {s.description ? <Text style={styles.desc}>{s.description}</Text> : null}
          {s.reason ? <Text style={styles.reason}>{s.reason}</Text> : null}
          <View style={styles.actions}>
            <Pressable
              style={[styles.btn, styles.btnPrimary]}
              onPress={() => { haptic('tap'); onAccept(s.id); }}
              disabled={busyId === s.id}
              testID="suggestion-accept"
            >
              <Text style={styles.btnPrimaryText}>Accetta</Text>
            </Pressable>
            <Pressable
              style={styles.btn}
              onPress={() => { haptic('tap'); onDismiss(s.id); }}
              disabled={busyId === s.id}
              testID="suggestion-dismiss"
            >
              <Text style={styles.btnText}>Ignora</Text>
            </Pressable>
            <Pressable
              style={styles.btn}
              onPress={() => { haptic('tap'); setSnoozeFor(s.id); }}
              testID="suggestion-snooze"
            >
              <Text style={styles.btnText}>Ricordamelo dopo</Text>
            </Pressable>
            <Pressable
              style={styles.btn}
              onPress={() => {
                haptic('tap');
                if (onOpen) onOpen(s);
                else if (s.action?.route) router.push(s.action.route as any);
              }}
              testID="suggestion-open"
            >
              <Ionicons name="open-outline" size={12} color={tokens.color.onSurface} />
              <Text style={styles.btnText}>Apri</Text>
            </Pressable>
          </View>
        </View>
      ))}

      <Modal visible={!!snoozeFor} transparent animationType="fade" onRequestClose={() => setSnoozeFor(null)}>
        <Pressable style={styles.modalBg} onPress={() => setSnoozeFor(null)}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Ricordamelo dopo</Text>
            {SNOOZE_PRESETS.map((p) => (
              <Pressable
                key={p.id}
                style={styles.modalRow}
                onPress={() => {
                  if (snoozeFor) onSnooze(snoozeFor, p.id);
                  setSnoozeFor(null);
                }}
                testID={`suggestion-snooze-${p.id}`}
              >
                <Text style={styles.btnText}>{p.label}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 8 },
  h: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    gap: 6,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  title: { fontSize: 15, fontWeight: '600', color: tokens.color.onSurface },
  desc: { fontSize: 13, color: tokens.color.onSurfaceMuted, lineHeight: 18 },
  reason: { fontSize: 11, color: tokens.color.onSurfaceDim },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  btn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong,
  },
  btnPrimary: {
    backgroundColor: tokens.color.brand,
    borderColor: tokens.color.brand,
  },
  btnText: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600' },
  btnPrimaryText: { fontSize: 12, color: tokens.color.onBrand, fontWeight: '700' },
  modalBg: {
    flex: 1, backgroundColor: tokens.color.scrim,
    justifyContent: 'center', padding: 24,
  },
  modalCard: {
    backgroundColor: tokens.color.surfaceElevated,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 8,
  },
  modalTitle: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface, marginBottom: 4 },
  modalRow: {
    paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: tokens.color.border,
  },
});
