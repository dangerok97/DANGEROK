/**
 * Skeleton building blocks with a subtle shine animation.
 * Uses reanimated shared value + interpolateColor to avoid layout jank.
 */
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  interpolateColor,
  Easing,
} from 'react-native-reanimated';
import { useEffect } from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { tokens } from '@/src/theme/tokens';

export function Skeleton({ style }: { style?: ViewStyle | ViewStyle[] }) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withRepeat(withTiming(1, { duration: 1100, easing: Easing.inOut(Easing.ease) }), -1, true);
  }, [t]);
  const animated = useAnimatedStyle(() => ({
    backgroundColor: interpolateColor(
      t.value,
      [0, 1],
      [tokens.color.skeleton, tokens.color.skeletonShine],
    ),
  }));
  return <Animated.View accessible={false} style={[styles.base, animated, style as any]} />;
}

export function FocusSkeleton() {
  return (
    <View style={styles.focusCard} accessibilityLabel="Caricamento in corso" accessibilityRole="progressbar">
      <View style={styles.rowBetween}>
        <Skeleton style={{ width: 44, height: 22, borderRadius: 999 }} />
        <Skeleton style={{ width: 84, height: 22, borderRadius: 999 }} />
      </View>
      <Skeleton style={{ width: '90%', height: 26, borderRadius: 8, marginTop: 12 }} />
      <Skeleton style={{ width: '70%', height: 16, borderRadius: 6, marginTop: 10 }} />
      <Skeleton style={{ width: '95%', height: 14, borderRadius: 6, marginTop: 14 }} />
      <View style={styles.metaRow}>
        <Skeleton style={{ width: 92, height: 30, borderRadius: 12 }} />
        <Skeleton style={{ width: 92, height: 30, borderRadius: 12 }} />
        <Skeleton style={{ width: 92, height: 30, borderRadius: 12 }} />
      </View>
      <Skeleton style={{ width: 140, height: 32, borderRadius: 999, marginTop: 8 }} />
      <View style={styles.metaRow}>
        <Skeleton style={{ width: 88, height: 44, borderRadius: 12 }} />
        <Skeleton style={{ width: 88, height: 44, borderRadius: 12 }} />
        <Skeleton style={{ width: 88, height: 44, borderRadius: 12 }} />
      </View>
    </View>
  );
}

export function DailySkeleton() {
  return (
    <View style={styles.card} accessibilityLabel="Caricamento giornata" accessibilityRole="progressbar">
      <View style={styles.rowBetween}>
        <Skeleton style={{ width: 140, height: 20, borderRadius: 6 }} />
        <Skeleton style={{ width: 60, height: 22, borderRadius: 999 }} />
      </View>
      <View style={[styles.metaRow, { marginTop: 12 }]}>
        <Skeleton style={{ width: 90, height: 26, borderRadius: 999 }} />
        <Skeleton style={{ width: 100, height: 26, borderRadius: 999 }} />
        <Skeleton style={{ width: 100, height: 26, borderRadius: 999 }} />
      </View>
      <Skeleton style={{ width: '80%', height: 14, borderRadius: 6, marginTop: 12 }} />
    </View>
  );
}

export function LaterSkeleton() {
  return (
    <View style={styles.laterCard} accessible={false}>
      <Skeleton style={{ width: '80%', height: 16, borderRadius: 6 }} />
      <Skeleton style={{ width: '55%', height: 12, borderRadius: 6, marginTop: 8 }} />
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: tokens.color.skeleton,
    borderRadius: 8,
    overflow: 'hidden',
  },
  focusCard: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    borderWidth: 1,
    borderColor: tokens.color.border,
    gap: 8,
  },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    borderWidth: 1,
    borderColor: tokens.color.border,
    gap: 8,
  },
  laterCard: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    borderWidth: 1,
    borderColor: tokens.color.border,
    marginBottom: 8,
  },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
});
