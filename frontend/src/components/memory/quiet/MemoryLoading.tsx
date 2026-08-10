import { StyleSheet, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

export function MemoryLoading() {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} testID="memory-loading" accessibilityLabel="Caricamento memoria">
      {[0, 1, 2, 3].map((i) => (
        <View
          key={i}
          style={[
            styles.line,
            {
              backgroundColor: colors.surfaceSecondary,
              width: i % 2 === 0 ? '88%' : '64%',
            },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: tokens.spacing.md,
    paddingTop: tokens.spacing.lg,
  },
  line: {
    height: 14,
    borderRadius: 4,
  },
});
