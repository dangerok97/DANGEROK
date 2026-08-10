import { StyleSheet, View } from 'react-native';
import { LoadingSkeleton, SkeletonBlock } from '@/src/components/ui/LoadingSkeleton';
import { tokens } from '@/src/theme/tokens';

/** Editorial skeleton — rows, not a card grid. */
export function ContextsLoading() {
  return (
    <View
      style={styles.wrap}
      testID="contesti-loading"
      accessibilityLabel="Caricamento Contesti"
    >
      <LoadingSkeleton height={36} width="40%" radius={tokens.radius.sm} />
      <LoadingSkeleton height={16} width="70%" />
      <View style={styles.section}>
        <LoadingSkeleton height={12} width="28%" />
        <SkeletonBlock lines={2} />
        <LoadingSkeleton height={1} width="100%" />
        <SkeletonBlock lines={2} />
      </View>
      <View style={styles.section}>
        <LoadingSkeleton height={12} width="22%" />
        <SkeletonBlock lines={3} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.lg, paddingTop: tokens.spacing.sm },
  section: { gap: tokens.spacing.md, marginTop: tokens.spacing.md },
});
