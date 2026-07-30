import { View, Text, StyleSheet, Pressable, ActivityIndicator } from 'react-native';
import Animated, { FadeInDown, FadeOut, LinearTransition } from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { ApiDecision } from '@/src/api/client';
import { STATUS_LABELS, formatMinutes, formatDateTime } from '@/src/utils/labels';

type Props = {
  items: ApiDecision[];
  explainEnabled: boolean;
  onWhy: (id: string) => void;
  loadingWhyId: string | null;
};

export function LaterList({ items, explainEnabled, onWhy, loadingWhyId }: Props) {
  if (items.length === 0) return null;
  return (
    <Animated.View layout={LinearTransition.duration(tokens.motion.base)} style={styles.section}>
      <Text style={styles.h2} accessibilityRole="header">Dopo</Text>
      {items.map((d, idx) => (
        <Animated.View
          key={d.id}
          entering={FadeInDown.duration(tokens.motion.base).delay(idx * 40)}
          exiting={FadeOut.duration(tokens.motion.fast)}
          layout={LinearTransition.duration(tokens.motion.base)}
        >
          <LaterCard
            index={idx + 2}
            decision={d}
            explainEnabled={explainEnabled}
            onWhy={() => onWhy(d.id)}
            loadingWhy={loadingWhyId === d.id}
          />
        </Animated.View>
      ))}
    </Animated.View>
  );
}

function LaterCard({ index, decision, explainEnabled, onWhy, loadingWhy }: {
  index: number;
  decision: ApiDecision;
  explainEnabled: boolean;
  onWhy: () => void;
  loadingWhy: boolean;
}) {
  const st = decision.action_state?.status || decision.status;
  return (
    <View
      style={styles.card}
      accessible
      accessibilityLabel={`Prossima ${index}: ${decision.title}`}
    >
      <View style={styles.head}>
        <Text style={styles.indexLabel}>{index}</Text>
        <Text style={styles.title} numberOfLines={2}>{decision.title}</Text>
      </View>
      <View style={styles.meta}>
        <Text style={styles.metaText}>{formatMinutes(decision.time_required_min)}</Text>
        {decision.deadline && <Text style={styles.metaText}>· Scad. {formatDateTime(decision.deadline)}</Text>}
        <Text style={styles.metaText}>· {STATUS_LABELS[st] || 'Da fare'}</Text>
      </View>
      {explainEnabled && (
        <Pressable
          style={({ pressed }) => [styles.whyMini, pressed && styles.pressed]}
          onPress={onWhy}
          disabled={loadingWhy}
          accessibilityRole="button"
          accessibilityLabel="Perché è prioritaria"
          accessibilityState={{ busy: loadingWhy }}
          hitSlop={8}
        >
          {loadingWhy ? (
            <ActivityIndicator size="small" color={tokens.color.onSurfaceMuted} />
          ) : (
            <>
              <Ionicons name="bulb-outline" size={13} color={tokens.color.onSurface} />
              <Text style={styles.whyMiniText}>Perché?</Text>
            </>
          )}
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: tokens.spacing.sm },
  h2: { fontSize: 20, fontWeight: '600', color: tokens.color.onSurface, marginBottom: tokens.spacing.sm },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    gap: 6,
    borderWidth: 1,
    borderColor: tokens.color.border,
    marginBottom: 8,
  },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  indexLabel: { fontSize: 13, color: tokens.color.onSurfaceMuted, fontWeight: '700', minWidth: 18 },
  title: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600', flex: 1, lineHeight: 20 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginLeft: 26 },
  metaText: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  whyMini: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong,
    marginLeft: 26, minHeight: 32, backgroundColor: tokens.color.surfaceTertiary,
  },
  whyMiniText: { fontSize: 11, color: tokens.color.onSurface, fontWeight: '600' },
  pressed: { opacity: 0.7 },
});
