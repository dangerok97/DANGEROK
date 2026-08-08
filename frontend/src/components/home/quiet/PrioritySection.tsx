import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeItem, HomePriorityGroup } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { formatWhen } from '@/src/components/home/v2/homeNav';
import { triggerHaptic } from '@/src/theme/haptics';

function displayType(item: HomeItem): string | null {
  const intent = (item.meta as { intent?: string } | undefined)?.intent;
  const subtype = item.subtype || (item.meta as { intent_subtype?: string } | undefined)?.intent_subtype;
  if (intent === 'study' || subtype === 'exam_preparation') return 'studio';
  if (intent === 'event') return 'evento';
  if (intent === 'travel' || subtype === 'vacation') return 'viaggio';
  if (intent === 'medical') return 'visita';
  if (intent === 'payment' || intent === 'financial') return 'pagamento';
  // Omit raw engine types (e.g. "insight") — Quiet Premium, no jargon
  if (!item.type || item.type === 'insight' || item.type === 'generic' || item.type === 'needs_review') {
    return null;
  }
  const human: Record<string, string> = {
    bill: 'pagamento',
    study: 'studio',
    travel: 'viaggio',
    visit: 'visita',
    event: 'evento',
    payment: 'pagamento',
    verify: 'da verificare',
    reply: 'risposta',
    activity: 'attività',
    resume: 'continua',
  };
  return human[item.type] || null;
}

/** Typography + space + hairline — no card chrome. */
export function PrioritySection({ groups }: { groups: HomePriorityGroup[] }) {
  const { colors } = useTheme();
  const nonEmpty = (groups || []).filter((g) => g.items?.length);
  if (!nonEmpty.length) return null;

  let shown = 0;

  return (
    <View style={styles.section} testID="priorita-list">
      <Text style={[styles.h, { color: colors.textPrimary }]} accessibilityRole="header">
        Priorità
      </Text>
      {nonEmpty.map((g) => (
        <View key={g.key} style={styles.group} testID={`priorita-group-${g.key}`}>
          <Text style={[styles.groupLabel, { color: colors.textTertiary }]}>{g.label}</Text>
          {g.items.map((item, idx) => {
            const rank = shown;
            shown += 1;
            const emphasize = rank < 3;
            return (
              <View key={item.id}>
                <PriorityRow item={item} emphasize={emphasize} />
                {idx < g.items.length - 1 ? (
                  <View style={[styles.hairline, { backgroundColor: colors.divider }]} />
                ) : null}
              </View>
            );
          })}
        </View>
      ))}
    </View>
  );
}

function PriorityRow({ item, emphasize }: { item: HomeItem; emphasize: boolean }) {
  const { colors } = useTheme();
  const router = useRouter();
  const when = formatWhen(item.start_at || item.due_at);
  const label = displayType(item);

  return (
    <Pressable
      style={({ pressed }) => [
        styles.row,
        { opacity: pressed ? 0.7 : 1 },
      ]}
      onPress={async () => {
        void triggerHaptic('impactLight');
        await ActionEngine.open(item, router);
      }}
      accessibilityRole="button"
      accessibilityLabel={item.title}
      testID={`priority-card-${item.type}`}
    >
      <View style={styles.body}>
        <Text
          style={[
            {
              color: colors.textPrimary,
              fontSize: emphasize
                ? tokens.typography.body.fontSize + 1
                : tokens.typography.body.fontSize,
              fontWeight: emphasize ? '600' : '500',
              letterSpacing: -0.2,
              lineHeight: emphasize ? 26 : 24,
            },
          ]}
          numberOfLines={2}
        >
          {item.title}
        </Text>
        {label || when ? (
          <Text style={[styles.meta, { color: colors.textTertiary }]} numberOfLines={1}>
            {[label, when].filter(Boolean).join('  ·  ')}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { gap: tokens.spacing.md },
  h: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: '600',
    letterSpacing: -0.3,
    marginBottom: 2,
  },
  group: { marginBottom: tokens.spacing.sm },
  groupLabel: {
    fontSize: 11,
    fontWeight: '500',
    marginBottom: 2,
    letterSpacing: 0.15,
  },
  row: {
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.md + 2,
  },
  body: { flex: 1, gap: 3 },
  meta: {
    fontSize: 11,
    fontWeight: '400',
    letterSpacing: 0.05,
  },
  hairline: {
    height: StyleSheet.hairlineWidth,
    width: '100%',
    opacity: 0.7,
  },
});
