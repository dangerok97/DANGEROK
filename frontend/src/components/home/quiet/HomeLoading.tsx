import { View, StyleSheet } from 'react-native';
import { tokens } from '@/src/theme/tokens';
import { LoadingSkeleton, SkeletonBlock } from '@/src/components/ui/LoadingSkeleton';

/** Geometry matches Daily Focus + light sections. */
export function HomeLoading() {
  return (
    <View style={styles.wrap} testID="home-loading" accessibilityLabel="Caricamento Home">
      <LoadingSkeleton height={28} width="45%" radius={tokens.radius.sm} />
      <View style={styles.hero}>
        <LoadingSkeleton height={14} width="20%" />
        <LoadingSkeleton height={36} width="90%" />
        <LoadingSkeleton height={36} width="70%" />
        <SkeletonBlock lines={2} />
        <LoadingSkeleton height={44} width="40%" radius={tokens.radius.full} />
      </View>
      <LoadingSkeleton height={12} width="30%" />
      <SkeletonBlock lines={3} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.lg },
  hero: {
    gap: tokens.spacing.sm,
    paddingVertical: tokens.spacing.md,
  },
});
