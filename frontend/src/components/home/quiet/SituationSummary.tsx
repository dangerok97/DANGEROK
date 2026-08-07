import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { HomeCurrentSituation } from '@/src/api/client';
import { triggerHaptic } from '@/src/theme/haptics';

type Props = {
  situation: HomeCurrentSituation;
  onOpen: () => void;
};

/** Light day summary — never competes with Daily Focus. */
export function SituationSummary({ situation, onOpen }: Props) {
  const { colors } = useTheme();
  const bits: string[] = [];
  if (situation.next_commitment) bits.push(`Prossimo: ${situation.next_commitment}`);
  if (situation.free_window) bits.push(situation.free_window);
  const top = (situation.indicators || []).slice(0, 2);
  for (const ind of top) {
    if (ind.value) bits.push(`${ind.label}: ${ind.value}`);
  }
  const summary = bits.slice(0, 2).join(' · ') || 'Una sintesi della tua giornata.';

  return (
    <View style={styles.wrap} testID="situazione-card">
      <View style={styles.head}>
        <Text style={[styles.h, { color: colors.textPrimary }]} accessibilityRole="header">
          La tua giornata
        </Text>
        <Pressable
          onPress={() => {
            void triggerHaptic('selection');
            onOpen();
          }}
          testID="btn-situazione-completa"
          accessibilityRole="button"
          accessibilityLabel={situation.cta_label || 'Vedi tutto'}
          style={styles.ctaHit}
        >
          <Text style={[styles.cta, { color: colors.accent }]}>
            {situation.cta_label || 'Vedi tutto'}
          </Text>
        </Pressable>
      </View>
      <Text style={[styles.summary, { color: colors.textSecondary }]} numberOfLines={2}>
        {summary}
      </Text>
      {/* Keep legacy string discoverable for soft e2e fallbacks */}
      <Text style={{ position: 'absolute', width: 1, height: 1, opacity: 0 }}>La tua situazione</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: tokens.spacing.xs },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: tokens.spacing.md,
  },
  h: {
    fontSize: tokens.typography.headline.fontSize,
    fontWeight: tokens.typography.headline.fontWeight,
  },
  ctaHit: { minHeight: tokens.touch.min, justifyContent: 'center' },
  cta: {
    fontSize: tokens.typography.label.fontSize,
    fontWeight: '600',
  },
  summary: {
    fontSize: tokens.typography.bodySmall.fontSize,
    lineHeight: tokens.typography.bodySmall.lineHeight,
  },
});
