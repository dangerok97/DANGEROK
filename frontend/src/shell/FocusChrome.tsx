/**
 * Focus chrome — single back OR close (never both), progress, optional context.
 */
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

type Props = {
  /** Prefer back (push) or close (dismiss) — never both. */
  leading?: 'back' | 'close';
  onLeadingPress?: () => void;
  leadingAccessibilityLabel?: string;
  /** e.g. "2 di 5" — omit when unknown (never fake 0%). */
  progressLabel?: string | null;
  /** Human context: Studio / Viaggio / Casa — omit if none. */
  contextLabel?: string | null;
  /** Optional tertiary (e.g. Salva bozza) — not when primary Avanti is enough. */
  trailingLabel?: string | null;
  onTrailingPress?: () => void;
  testID?: string;
};

export function FocusChrome({
  leading = 'back',
  onLeadingPress,
  leadingAccessibilityLabel,
  progressLabel,
  contextLabel,
  trailingLabel,
  onTrailingPress,
  testID = 'focus-chrome',
}: Props) {
  const { colors } = useTheme();
  const leadLabel =
    leadingAccessibilityLabel || (leading === 'close' ? 'Chiudi' : 'Indietro');

  return (
    <View style={styles.row} testID={testID}>
      <Pressable
        onPress={onLeadingPress}
        hitSlop={12}
        accessibilityRole="button"
        accessibilityLabel={leadLabel}
        testID="focus-chrome-back"
        style={({ pressed }) => [styles.lead, { opacity: pressed ? 0.55 : 1 }]}
      >
        <Ionicons
          name={leading === 'close' ? 'close' : 'chevron-back'}
          size={24}
          color={colors.textPrimary}
        />
      </Pressable>

      <View style={styles.center} pointerEvents="none">
        {contextLabel ? (
          <Text style={[styles.context, { color: colors.textTertiary }]} numberOfLines={1}>
            {contextLabel}
          </Text>
        ) : null}
        {progressLabel ? (
          <Text
            style={[styles.progress, { color: colors.textSecondary }]}
            testID="focus-chrome-progress"
          >
            {progressLabel}
          </Text>
        ) : null}
      </View>

      {trailingLabel && onTrailingPress ? (
        <Pressable
          onPress={onTrailingPress}
          hitSlop={12}
          accessibilityRole="button"
          accessibilityLabel={trailingLabel}
          testID="focus-chrome-trailing"
          style={({ pressed }) => [styles.trail, { opacity: pressed ? 0.55 : 1 }]}
        >
          <Text style={[styles.trailText, { color: colors.textSecondary }]}>{trailingLabel}</Text>
        </Pressable>
      ) : (
        <View style={styles.trailSpacer} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: tokens.touch.min,
    paddingHorizontal: tokens.spacing.md,
    paddingVertical: tokens.spacing.sm,
    gap: 8,
  },
  lead: {
    width: tokens.touch.min,
    height: tokens.touch.min,
    alignItems: 'center',
    justifyContent: 'center',
  },
  center: {
    flex: 1,
    alignItems: 'center',
    gap: 2,
  },
  context: {
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  progress: {
    fontSize: 13,
    fontWeight: '600',
  },
  trail: {
    minWidth: tokens.touch.min,
    minHeight: tokens.touch.min,
    alignItems: 'flex-end',
    justifyContent: 'center',
    paddingHorizontal: 4,
  },
  trailText: {
    fontSize: 13,
    fontWeight: '600',
  },
  trailSpacer: {
    width: tokens.touch.min,
  },
});
