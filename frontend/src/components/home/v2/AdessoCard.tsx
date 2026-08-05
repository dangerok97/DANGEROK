import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { HomeItem } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { formatWhen } from './homeNav';
import { haptic } from '@/src/utils/haptic';

function progressDisplay(item: HomeItem): string | null {
  const label = item.goal_progress_label?.trim();
  // Travel soft progress / phase: prefer honest label, never invent precise %
  if (item.goal_type === 'travel' && label) return label;
  if (item.goal_progress == null) return label || null;
  const pct = Math.round(Number(item.goal_progress));
  if (label) {
    if (label.includes('%') || label.includes('/')) return label;
    return `${pct}% · ${label}`;
  }
  return `${pct}%`;
}

/** Type-specific primary focus — card press opens Action Engine. */
export function AdessoCard({ item }: { item: HomeItem }) {
  const router = useRouter();
  const when = formatWhen(item.start_at || item.due_at || item.goal_target_date);
  const fields: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }[] = [];

  if (when) fields.push({ icon: 'time-outline', label: item.due_at && !item.start_at ? 'Scadenza' : 'Quando', value: when });
  if (item.location) fields.push({ icon: 'location-outline', label: 'Luogo', value: item.location });
  if (item.amount) fields.push({ icon: 'cash-outline', label: 'Importo', value: item.amount });
  if (item.duration_minutes) fields.push({ icon: 'hourglass-outline', label: 'Durata', value: `${item.duration_minutes} min` });

  // Goal context on existing Adesso card — no Goal tab / section
  if (item.goal_title) {
    fields.push({ icon: 'flag-outline', label: 'Obiettivo', value: item.goal_title });
  }
  const prog = progressDisplay(item);
  if (prog) {
    fields.push({ icon: 'trending-up-outline', label: 'Progresso', value: prog });
  }
  if (item.goal_target_date) {
    const targetWhen = formatWhen(item.goal_target_date);
    if (targetWhen && targetWhen !== when) {
      fields.push({ icon: 'calendar-outline', label: 'Target', value: targetWhen });
    }
  }
  if (item.goal_next_action) {
    fields.push({ icon: 'play-outline', label: 'Prossima', value: item.goal_next_action });
  }
  if (item.goal_status && ['blocked', 'waiting', 'paused'].includes(item.goal_status)) {
    const statusLabel =
      item.goal_status === 'blocked' ? 'Bloccato'
        : item.goal_status === 'waiting' ? 'In attesa'
          : 'In pausa';
    fields.push({ icon: 'alert-circle-outline', label: 'Stato', value: statusLabel });
  }
  if (item.goal_blockers?.length) {
    fields.push({ icon: 'warning-outline', label: 'Blocco', value: item.goal_blockers[0] });
  }
  if (item.goal_project_id && item.source_type !== 'action_project') {
    fields.push({ icon: 'folder-outline', label: 'Progetto', value: 'Collegato' });
  }

  const intentLabel = INTENT_LABELS[(item.meta as any)?.intent as string] || INTENT_LABELS[item.subtype || ''];
  const typeLabel = intentLabel || TYPE_LABELS[item.type] || item.type;

  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && { opacity: 0.92 }]}
      onPress={async () => {
        haptic('tap');
        await ActionEngine.open(item, router);
      }}
      accessibilityRole="button"
      accessibilityLabel={`Apri guida per ${item.title}`}
      testID="adesso-card"
    >
      <View style={styles.header}>
        <View style={styles.pill}>
          <View style={styles.pillDot} />
          <Text style={styles.pillText}>ADESSO</Text>
        </View>
        <Text style={styles.type}>{typeLabel}</Text>
      </View>
      <Text style={styles.title} accessibilityRole="header">{item.title}</Text>
      {item.description ? <Text style={styles.desc}>{item.description}</Text> : null}
      {item.goal_title && !(item.description || '').includes('Obiettivo:') ? (
        <Text style={styles.goalCtx} testID="adesso-goal-context">Obiettivo: {item.goal_title}</Text>
      ) : null}
      {fields.length > 0 ? (
        <View style={styles.metaGrid}>
          {fields.map((f) => (
            <View key={f.label} style={styles.meta} accessible accessibilityLabel={`${f.label}: ${f.value}`}>
              <Ionicons name={f.icon} size={13} color={tokens.color.onSurfaceMuted} />
              <Text style={styles.metaLabel}>{f.label}</Text>
              <Text style={styles.metaValue} numberOfLines={2}>{f.value}</Text>
            </View>
          ))}
        </View>
      ) : null}
      <Text style={styles.hint}>Tocca per iniziare la guida ORA</Text>
    </Pressable>
  );
}

const TYPE_LABELS: Record<string, string> = {
  bill: 'Bolletta',
  payment: 'Pagamento',
  event: 'Evento',
  visit: 'Visita',
  study: 'Studio',
  travel: 'Viaggio',
  needs_review: 'Da verificare',
  verify: 'Verifica',
  reply: 'Risposta',
  activity: 'Attività',
  generic: 'Priorità',
  resume: 'In corso',
};

/** Prefer Intent Classification labels over erroneous source typing. */
const INTENT_LABELS: Record<string, string> = {
  study: 'Studio',
  exam_preparation: 'Studio · esame',
  travel: 'Viaggio',
  vacation: 'Vacanza',
  event: 'Evento',
  medical: 'Visita',
  payment: 'Pagamento',
  financial: 'Finanze',
  administrative: 'Pratica',
  document_review: 'Documento',
  task: 'Attività',
  communication: 'Messaggio',
  shopping: 'Acquisto',
  project: 'Progetto',
  generic: 'Priorità',
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: tokens.spacing.md,
    borderWidth: 1,
    borderColor: tokens.color.borderStrong,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, paddingVertical: 5,
    borderRadius: tokens.radius.pill, backgroundColor: tokens.color.brand,
  },
  pillDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: tokens.color.onBrand },
  pillText: { fontSize: 10, fontWeight: '700', color: tokens.color.onBrand, letterSpacing: 1 },
  type: { fontSize: 12, color: tokens.color.onSurfaceMuted, fontWeight: '600', textTransform: 'uppercase' },
  title: { fontSize: 24, fontWeight: '700', color: tokens.color.onSurface, lineHeight: 30, letterSpacing: -0.3 },
  desc: { fontSize: 14, color: tokens.color.onSurfaceMuted, lineHeight: 20 },
  goalCtx: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600', lineHeight: 18 },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.sm },
  meta: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, paddingVertical: 7, borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceTertiary,
    maxWidth: '100%',
  },
  metaLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  metaValue: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600', flexShrink: 1 },
  hint: { fontSize: 12, color: tokens.color.onSurfaceDim, marginTop: 2 },
});
