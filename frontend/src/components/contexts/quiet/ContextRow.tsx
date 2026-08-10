import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import type { LifeAreaRow } from './buildContextsMap';

type Props = {
  area: LifeAreaRow;
  showDivider?: boolean;
  /** Persistent areas have no Contesti detail yet — informational only. */
  onPress?: (() => void) | null;
};

export function ContextRow({ area, showDivider, onPress }: Props) {
  const { colors } = useTheme();
  const interactive = typeof onPress === 'function';

  const body = (
    <>
      <View style={styles.textCol}>
        <Text style={[styles.title, { color: colors.textPrimary }]} numberOfLines={1}>
          {area.title}
        </Text>
        {area.identity ? (
          <Text style={[styles.identity, { color: colors.textSecondary }]} numberOfLines={2}>
            {area.identity}
          </Text>
        ) : null}
      </View>
      {interactive ? (
        <Ionicons
          name="chevron-forward"
          size={18}
          color={colors.textTertiary}
          accessibilityElementsHidden
        />
      ) : null}
    </>
  );

  return (
    <View>
      {interactive ? (
        <Pressable
          onPress={onPress}
          style={({ pressed }) => [
            styles.row,
            pressed && { backgroundColor: colors.accentMuted },
          ]}
          accessibilityRole="button"
          accessibilityLabel={
            area.identity ? `${area.title}, ${area.identity}` : area.title
          }
          testID={`contesti-area-${area.domain}`}
        >
          {body}
        </Pressable>
      ) : (
        <View
          style={styles.row}
          accessibilityRole="text"
          accessibilityLabel={
            area.identity ? `${area.title}, ${area.identity}` : area.title
          }
          testID={`contesti-area-${area.domain}`}
        >
          {body}
        </View>
      )}
      {showDivider ? (
        <View style={[styles.divider, { backgroundColor: colors.divider }]} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: tokens.touch.min,
    paddingVertical: tokens.spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: tokens.spacing.md,
  },
  textCol: { flex: 1, gap: 2 },
  title: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
    letterSpacing: tokens.typography.headline.letterSpacing,
  },
  identity: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    width: '100%',
  },
});
