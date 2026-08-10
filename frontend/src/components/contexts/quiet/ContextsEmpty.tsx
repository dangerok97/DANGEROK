import { StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { AppButton } from '@/src/components/ui/AppButton';

type Props = {
  /** Optional path to Conversation Engine Ask (ORA). */
  allowOraCta?: boolean;
};

/**
 * Empty Contesti — ORA is still learning; never "create a context".
 */
export function ContextsEmpty({ allowOraCta = true }: Props) {
  const { colors } = useTheme();
  const router = useRouter();

  return (
    <View style={styles.wrap} testID="contesti-empty" accessibilityRole="summary">
      <Text style={[styles.title, { color: colors.textPrimary }]}>
        ORA sta ancora conoscendo la tua vita.
      </Text>
      <Text style={[styles.msg, { color: colors.textSecondary }]}>
        Quando emergeranno ambiti e situazioni utili, li troverai qui.
      </Text>
      {allowOraCta ? (
        <AppButton
          label="Parla con ORA"
          variant="secondary"
          onPress={() => router.push('/(tabs)/ora' as any)}
          testID="contesti-empty-ora"
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingVertical: tokens.spacing['48'],
    gap: tokens.spacing.md,
    alignItems: 'flex-start',
  },
  title: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    letterSpacing: tokens.typography.headline.letterSpacing,
    lineHeight: tokens.typography.headline.lineHeight,
    maxWidth: 360,
  },
  msg: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
    maxWidth: 360,
    marginBottom: tokens.spacing.sm,
  },
});
