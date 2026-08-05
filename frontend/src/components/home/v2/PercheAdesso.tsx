import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { HomeExplanation } from '@/src/api/client';

type Props = {
  explanation: HomeExplanation;
  onCorrect?: () => void;
  onIgnore?: () => void;
};

/** Real ranking explanation — no chain-of-thought, no invented reasons. */
export function PercheAdesso({ explanation, onCorrect, onIgnore }: Props) {
  if (!explanation?.summary && !(explanation?.factors?.length)) return null;

  return (
    <View style={styles.card} testID="perche-adesso">
      <View style={styles.head}>
        <Ionicons name="bulb-outline" size={16} color={tokens.color.onSurface} />
        <Text style={styles.h} accessibilityRole="header">Perché adesso?</Text>
      </View>
      <Text style={styles.summary}>{explanation.summary}</Text>
      {explanation.factors?.length ? (
        <View style={styles.factors}>
          {explanation.factors.slice(0, 5).map((f) => (
            <View key={`${f.code}-${f.label}`} style={styles.factor}>
              <Text style={styles.factorLabel}>{f.label}</Text>
              {f.detail ? <Text style={styles.factorDetail}>{f.detail}</Text> : null}
            </View>
          ))}
        </View>
      ) : null}
      {explanation.sources?.length ? (
        <Text style={styles.meta}>
          Fonti: {explanation.sources.map((s) => s.type).join(', ')}
        </Text>
      ) : null}
      {explanation.confidence != null ? (
        <Text style={styles.meta}>Confidenza dati: {Math.round(explanation.confidence * 100)}%</Text>
      ) : null}
      {explanation.missing_data?.length ? (
        <Text style={styles.missing}>Dati mancanti: {explanation.missing_data.join(', ')}</Text>
      ) : null}
      <Text style={styles.version}>ranking {explanation.ranking_version}</Text>
      <View style={styles.actions}>
        {onCorrect ? (
          <Pressable style={styles.btn} onPress={onCorrect} testID="btn-correct-priority" accessibilityRole="button">
            <Text style={styles.btnText}>Correggi priorità</Text>
          </Pressable>
        ) : null}
        {onIgnore ? (
          <Pressable style={styles.btn} onPress={onIgnore} testID="btn-ignore-focus" accessibilityRole="button">
            <Text style={styles.btnText}>Ignora</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.lg,
    gap: 8,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  h: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  summary: { fontSize: 14, color: tokens.color.onSurface, lineHeight: 20 },
  factors: { gap: 6, marginTop: 4 },
  factor: {
    backgroundColor: tokens.color.surfaceTertiary,
    borderRadius: tokens.radius.md,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  factorLabel: { fontSize: 13, color: tokens.color.onSurface, fontWeight: '500' },
  factorDetail: { fontSize: 12, color: tokens.color.onSurfaceMuted, marginTop: 2 },
  meta: { fontSize: 12, color: tokens.color.onSurfaceMuted },
  missing: { fontSize: 12, color: tokens.color.warning },
  version: { fontSize: 11, color: tokens.color.onSurfaceDim },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  btn: {
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong,
    minHeight: tokens.touch.min, justifyContent: 'center',
  },
  btnText: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600' },
});
