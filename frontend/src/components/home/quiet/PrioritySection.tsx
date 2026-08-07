import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeItem, HomePriorityGroup } from '@/src/api/client';
import { ActionEngine } from '@/src/action-engine';
import { formatWhen } from '@/src/components/home/v2/homeNav';
import { triggerHaptic } from '@/src/theme/haptics';
import { AppDivider } from '@/src/components/ui/AppDivider';

function displayType(item: HomeItem): string {
  const intent = (item.meta as { intent?: string } | undefined)?.intent;
  const subtype = item.subtype || (item.meta as { intent_subtype?: string } | undefined)?.intent_subtype;
  if (intent === 'study' || subtype === 'exam_preparation') return 'studio';
  if (intent === 'event') return 'evento';
  if (intent === 'travel' || subtype === 'vacation') return 'viaggio';
  if (intent === 'medical') return 'visita';
  if (intent === 'payment' || intent === 'financial') return 'pagamento';
  return item.type;
}

/** Light typography-first priorities — max visual weight on first 3 overall. */
export function PrioritySection({ groups }: { groups: HomePriorityGroup[] }) {
  const { colors } = useTheme();
  const nonEmpty = (groups || []).filter((g) => g.items?.length);
  if (!nonEmpty.length) return null;

  let shown = 0;

  return (
    <View style={styles.section} testID="priorita-list">
      <Text
        style={[styles.h, { color: colors.textPrimary }]}
        accessibilityRole="header"
      >
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
                {idx < g.items.length - 1 ? <AppDivider /> : null}
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
        {
          opacity: pressed ? 0.75 : 1,
          transform: [{ scale: pressed ? tokens.motion.pressScale : 1 }],
        },
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
            styles.title,
            {
              color: colors.textPrimary,
              fontSize: emphasize ? tokens.typography.headline.fontSize : tokens.typography.body.fontSize,
              fontWeight: emphasize ? '600' : '500',
              lineHeight: emphasize
                ? tokens.typography.headline.lineHeight
                : tokens.typography.body.lineHeight,
            },
          ]}
          numberOfLines={2}
        >
          {item.title}
        </Text>
        <Text style={[styles.meta, { color: colors.textTertiary }]} numberOfLines={1}>
          {label}
          {when ? ` · ${when}` : ''}
        </Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: { gap: tokens.spacing.sm },
  h: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    letterSpacing: tokens.typography.headline.letterSpacing,
    marginBottom: 4,
  },
  group: { marginBottom: tokens.spacing.sm },
  groupLabel: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '600',
    marginBottom: 4,
    letterSpacing: 0.2,
  },
  row: {
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
  },
  body: { flex: 1, gap: 2 },
  title: {},
  meta: {
    fontSize: tokens.typography.caption.fontSize,
  },
});
