import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { HomeItem } from '@/src/api/client';
import { formatWhen } from './homeNav';

/** Type-specific primary focus — hide empty fields. */
export function AdessoCard({ item }: { item: HomeItem }) {
  const when = formatWhen(item.start_at || item.due_at);
  const fields: { icon: keyof typeof Ionicons.glyphMap; label: string; value: string }[] = [];

  if (when) fields.push({ icon: 'time-outline', label: item.due_at && !item.start_at ? 'Scadenza' : 'Quando', value: when });
  if (item.location) fields.push({ icon: 'location-outline', label: 'Luogo', value: item.location });
  if (item.amount) fields.push({ icon: 'cash-outline', label: 'Importo', value: item.amount });
  if (item.duration_minutes) fields.push({ icon: 'hourglass-outline', label: 'Durata', value: `${item.duration_minutes} min` });

  const typeLabel = TYPE_LABELS[item.type] || item.type;

  return (
    <View style={styles.card} testID="adesso-card">
      <View style={styles.header}>
        <View style={styles.pill}>
          <View style={styles.pillDot} />
          <Text style={styles.pillText}>ADESSO</Text>
        </View>
        <Text style={styles.type}>{typeLabel}</Text>
      </View>
      <Text style={styles.title} accessibilityRole="header">{item.title}</Text>
      {item.description ? <Text style={styles.desc}>{item.description}</Text> : null}
      {fields.length > 0 ? (
        <View style={styles.metaGrid}>
          {fields.map((f) => (
            <View key={f.label} style={styles.meta} accessible accessibilityLabel={`${f.label}: ${f.value}`}>
              <Ionicons name={f.icon} size={13} color={tokens.color.onSurfaceMuted} />
              <Text style={styles.metaLabel}>{f.label}</Text>
              <Text style={styles.metaValue}>{f.value}</Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
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
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: tokens.spacing.sm },
  meta: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, paddingVertical: 7, borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceTertiary,
  },
  metaLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  metaValue: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600' },
});
