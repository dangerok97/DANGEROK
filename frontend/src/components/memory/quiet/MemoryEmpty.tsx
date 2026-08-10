import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  onTellOra?: () => void;
};

export function MemoryEmpty({ onTellOra }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} testID="memory-empty">
      <Text style={[styles.title, { color: colors.textPrimary }]}>
        ORA sta ancora imparando a conoscerti.
      </Text>
      <Text style={[styles.body, { color: colors.textSecondary }]}>
        Man mano che racconti qualcosa o completi Life Setup, qui comparirà ciò
        che ORA ricorda in modo duraturo.
      </Text>
      {typeof onTellOra === 'function' ? (
        <Pressable
          onPress={onTellOra}
          style={({ pressed }) => [
            styles.cta,
            pressed && { opacity: 0.7 },
          ]}
          accessibilityRole="button"
          accessibilityLabel="Racconta qualcosa a ORA"
          testID="memory-empty-cta"
        >
          <Text style={[styles.ctaText, { color: colors.textPrimary }]}>
            Racconta qualcosa a ORA
          </Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingTop: tokens.spacing.xl,
    gap: tokens.spacing.md,
    maxWidth: 440,
  },
  title: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    lineHeight: tokens.typography.headline.lineHeight,
    letterSpacing: -0.3,
  },
  body: {
    fontSize: tokens.typography.body.fontSize,
    lineHeight: tokens.typography.body.lineHeight,
  },
  cta: {
    alignSelf: 'flex-start',
    marginTop: tokens.spacing.sm,
    paddingVertical: tokens.spacing.sm,
  },
  ctaText: {
    fontSize: tokens.typography.body.fontSize,
    fontWeight: '600',
    letterSpacing: -0.2,
    textDecorationLine: 'underline',
  },
});
