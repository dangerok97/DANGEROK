import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { LiveSituationRow as LiveSituationModel } from './buildContextsMap';

type Props = {
  situation: LiveSituationModel;
  onPress?: () => void;
};

/** Generic live situation — open kind; navigable only when href exists. */
export function LiveSituationRow({ situation, onPress }: Props) {
  const { colors } = useTheme();
  const a11y = [situation.title, situation.temporal, situation.summary]
    .filter(Boolean)
    .join('. ');
  const navigable = Boolean(situation.href && onPress);

  const body = (
    <>
      <View style={styles.textCol}>
        <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={2}>
          {situation.title}
        </Text>
        {situation.temporal ? (
          <Text style={[styles.temporal, { color: colors.textSecondary }]} numberOfLines={1}>
            {situation.temporal}
          </Text>
        ) : null}
        {situation.summary ? (
          <Text style={[styles.summary, { color: colors.textTertiary }]} numberOfLines={2}>
            {situation.summary}
          </Text>
        ) : null}
      </View>
      {navigable ? (
        <Ionicons
          name="chevron-forward"
          size={18}
          color={colors.textTertiary}
          accessibilityElementsHidden
        />
      ) : null}
    </>
  );

  if (navigable) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [
          styles.row,
          {
            backgroundColor: pressed ? colors.accentMuted : colors.surface,
            borderColor: colors.divider,
          },
        ]}
        accessibilityRole="button"
        accessibilityLabel={a11y}
        testID={`contesti-situation-${situation.kind}-${situation.id.split(':').pop() || situation.id}`}
      >
        {body}
      </Pressable>
    );
  }

  return (
    <View
      style={[styles.row, { backgroundColor: colors.surface, borderColor: colors.divider }]}
      accessibilityRole="text"
      accessibilityLabel={a11y}
      testID={`contesti-situation-${situation.kind}-${situation.id.split(':').pop() || situation.id}`}
    >
      {body}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.lg,
    paddingHorizontal: tokens.spacing.lg,
    borderRadius: tokens.radius.md,
    borderWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
    marginBottom: tokens.spacing.sm,
  },
  textCol: { flex: 1, gap: 4 },
  title: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    letterSpacing: tokens.typography.headline.letterSpacing,
  },
  temporal: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  summary: {
    fontSize: tokens.typography.caption.fontSize,
    lineHeight: tokens.typography.caption.lineHeight,
  },
});
