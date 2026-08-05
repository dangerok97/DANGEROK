import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { HomeCurrentSituation } from '@/src/api/client';

type Props = {
  situation: HomeCurrentSituation;
  onOpen: () => void;
};

export function SituazioneCard({ situation, onOpen }: Props) {
  const indicators = (situation.indicators || []).slice(0, 4);
  if (!indicators.length && !situation.free_window && !situation.next_commitment) {
    return null;
  }

  return (
    <View style={styles.card} testID="situazione-card">
      <Text style={styles.h} accessibilityRole="header">La tua situazione</Text>
      <View style={styles.grid}>
        {indicators.map((ind) => (
          <View
            key={ind.id}
            style={[styles.chip, toneBg(ind.tone)]}
            accessible
            accessibilityLabel={`${ind.label}: ${ind.value}`}
          >
            <Text style={styles.chipLabel}>{ind.label}</Text>
            <Text style={styles.chipValue}>{ind.value}</Text>
          </View>
        ))}
      </View>
      {situation.next_commitment ? (
        <Text style={styles.meta}>Prossimo: {situation.next_commitment}</Text>
      ) : null}
      <Pressable
        style={({ pressed }) => [styles.link, pressed && { opacity: 0.7 }]}
        onPress={onOpen}
        accessibilityRole="button"
        accessibilityLabel="Vedi situazione completa"
        testID="btn-situazione-completa"
      >
        <Text style={styles.linkText}>{situation.cta_label || 'Vedi situazione completa'}</Text>
        <Ionicons name="chevron-forward" size={14} color={tokens.color.onSurface} />
      </Pressable>
    </View>
  );
}

function toneBg(tone: string) {
  if (tone === 'warning') return { backgroundColor: tokens.color.warningBg };
  if (tone === 'success') return { backgroundColor: tokens.color.successBg };
  if (tone === 'info') return { backgroundColor: tokens.color.infoBg };
  return { backgroundColor: tokens.color.surfaceTertiary };
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 10,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  h: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    minWidth: '46%',
    flexGrow: 1,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 2,
  },
  chipLabel: { fontSize: 11, color: tokens.color.onSurfaceMuted, fontWeight: '500' },
  chipValue: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '700' },
  meta: { fontSize: 13, color: tokens.color.onSurfaceMuted },
  link: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    alignSelf: 'flex-start', paddingVertical: 8, minHeight: tokens.touch.min,
  },
  linkText: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '600' },
});
