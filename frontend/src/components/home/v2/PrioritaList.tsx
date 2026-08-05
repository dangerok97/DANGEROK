import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { HomeItem, HomePriorityGroup } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { formatWhen } from './homeNav';
import { haptic } from '@/src/utils/haptic';

const TYPE_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  event: 'calendar-outline',
  travel: 'airplane-outline',
  bill: 'receipt-outline',
  payment: 'card-outline',
  study: 'book-outline',
  verify: 'alert-circle-outline',
  needs_review: 'eye-outline',
  visit: 'medkit-outline',
  reply: 'chatbubble-outline',
  activity: 'checkbox-outline',
  generic: 'ellipse-outline',
  resume: 'play',
};

export function PrioritaList({ groups }: { groups: HomePriorityGroup[] }) {
  const nonEmpty = (groups || []).filter((g) => g.items?.length);
  if (!nonEmpty.length) return null;
  return (
    <View style={styles.section} testID="priorita-list">
      <Text style={styles.h} accessibilityRole="header">Priorità</Text>
      {nonEmpty.map((g) => (
        <View key={g.key} style={styles.group} testID={`priorita-group-${g.key}`}>
          <Text style={styles.groupLabel}>{g.label}</Text>
          {g.items.map((item) => (
            <PriorityCard key={item.id} item={item} />
          ))}
        </View>
      ))}
    </View>
  );
}

function PriorityCard({ item }: { item: HomeItem }) {
  const router = useRouter();
  const when = formatWhen(item.start_at || item.due_at);
  const icon = TYPE_ICON[item.type] || 'ellipse-outline';
  return (
    <Pressable
      style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
      onPress={async () => {
        haptic('tap');
        // Whole card → Action Engine guided flow (never empty route)
        await ActionEngine.open(item, router);
      }}
      accessibilityRole="button"
      accessibilityLabel={item.title}
      testID={`priority-card-${item.type}`}
    >
      <Ionicons name={icon} size={18} color={tokens.color.onSurfaceMuted} />
      <View style={styles.body}>
        <Text style={styles.title} numberOfLines={2}>{item.title}</Text>
        <View style={styles.meta}>
          <Text style={styles.metaText}>{item.type}</Text>
          {when ? <Text style={styles.metaText}>· {when}</Text> : null}
          {item.amount ? <Text style={styles.metaText}>· {item.amount}</Text> : null}
          {item.location ? <Text style={styles.metaText}>· {item.location}</Text> : null}
        </View>
      </View>
      <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurfaceDim} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { gap: tokens.spacing.sm },
  h: { fontSize: 20, fontWeight: '600', color: tokens.color.onSurface, marginBottom: 4 },
  group: { gap: 8, marginBottom: 8 },
  groupLabel: {
    fontSize: 12, fontWeight: '700', color: tokens.color.onSurfaceMuted,
    textTransform: 'uppercase', letterSpacing: 0.6,
  },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  body: { flex: 1, gap: 2 },
  title: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600', lineHeight: 20 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  metaText: { fontSize: 11, color: tokens.color.onSurfaceMuted },
});
