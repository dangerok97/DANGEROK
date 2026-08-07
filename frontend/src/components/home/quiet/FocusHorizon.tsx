import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeV2Response } from '@/src/api/client';
import { buildFocusHorizon } from './buildFocusHorizon';

type Props = {
  home: HomeV2Response | null;
};

/** Synthetic near-future perception — not a calendar. Hidden when no temporal data. */
export function FocusHorizon({ home }: Props) {
  const { colors } = useTheme();
  const buckets = buildFocusHorizon(home);
  if (!buckets.length) return null;

  return (
    <View style={styles.wrap} testID="focus-horizon" accessibilityRole="summary">
      <Text style={[styles.h, { color: colors.textTertiary }]}>Orizzonte</Text>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.row}
      >
        {buckets.map((b) => (
          <View
            key={b.key}
            style={[styles.bucket, { borderColor: colors.divider }]}
            testID={`horizon-${b.key}`}
          >
            <Text style={[styles.bucketLabel, { color: colors.textTertiary }]}>{b.label}</Text>
            {b.items.map((it) => (
              <View key={it.id} style={styles.item}>
                <Text style={[styles.itemTitle, { color: colors.textPrimary }]} numberOfLines={2}>
                  {it.title}
                </Text>
                <Text style={[styles.itemWhen, { color: colors.textSecondary }]} numberOfLines={1}>
                  {it.whenLabel}
                </Text>
              </View>
            ))}
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.sm },
  h: {
    fontSize: tokens.typography.label.fontSize,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  row: {
    gap: tokens.spacing.lg,
    paddingRight: tokens.spacing.md,
  },
  bucket: {
    minWidth: 140,
    maxWidth: 180,
    paddingRight: tokens.spacing.md,
    borderRightWidth: StyleSheet.hairlineWidth,
    gap: tokens.spacing.sm,
  },
  bucketLabel: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '600',
  },
  item: { gap: 2 },
  itemTitle: {
    fontSize: tokens.typography.caption.fontSize,
    fontWeight: '500',
    lineHeight: 18,
  },
  itemWhen: {
    fontSize: tokens.typography.footnote.fontSize,
  },
});
