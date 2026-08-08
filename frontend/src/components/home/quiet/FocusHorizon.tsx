import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeV2Response } from '@/src/api/client';
import { buildFocusHorizon } from './buildFocusHorizon';

type Props = {
  home: HomeV2Response | null;
};

/**
 * Near-future perception — vertical temporal sections (Apple Calendar calm).
 * Not a table, not three columns. Hidden when no temporal data.
 */
export function FocusHorizon({ home }: Props) {
  const { colors } = useTheme();
  const buckets = buildFocusHorizon(home);
  if (!buckets.length) return null;

  return (
    <View style={styles.wrap} testID="focus-horizon" accessibilityRole="summary">
      <Text style={[styles.h, { color: colors.textTertiary }]}>Orizzonte</Text>
      <View style={styles.stack}>
        {buckets.map((b, bi) => (
          <View
            key={b.key}
            style={[
              styles.section,
              bi < buckets.length - 1 && {
                marginBottom: tokens.spacing.xl,
              },
            ]}
            testID={`horizon-${b.key}`}
          >
            <Text style={[styles.bucketLabel, { color: colors.textTertiary }]}>{b.label}</Text>
            {b.items.map((it) => (
              <View key={it.id} style={styles.item}>
                <Text style={[styles.itemTitle, { color: colors.textPrimary }]} numberOfLines={2}>
                  {it.title}
                </Text>
                <Text style={[styles.itemWhen, { color: colors.textTertiary }]} numberOfLines={1}>
                  {it.whenLabel}
                </Text>
              </View>
            ))}
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.lg },
  h: {
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.2,
  },
  stack: {},
  section: {
    gap: tokens.spacing.md,
  },
  bucketLabel: {
    fontSize: tokens.typography.caption.fontSize,
    fontWeight: '500',
    letterSpacing: 0.1,
  },
  item: {
    gap: 3,
    paddingLeft: 2,
  },
  itemTitle: {
    fontSize: tokens.typography.bodySmall.fontSize,
    fontWeight: '500',
    lineHeight: 22,
    letterSpacing: -0.15,
  },
  itemWhen: {
    fontSize: tokens.typography.footnote.fontSize,
    fontWeight: '400',
  },
});
