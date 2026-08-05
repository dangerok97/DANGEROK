import { View, Text, StyleSheet, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { HomeInsight } from '@/src/api/client';

type Props = {
  insights: HomeInsight[];
  onIgnore: (id: string) => void;
  onAction?: (insight: HomeInsight) => void;
};

export function OraOsserva({ insights, onIgnore, onAction }: Props) {
  const list = (insights || []).filter((i) => i.status === 'active').slice(0, 2);
  if (!list.length) return null;

  return (
    <View style={styles.section} testID="ora-osserva">
      <Text style={styles.h} accessibilityRole="header">ORA osserva</Text>
      {list.map((ins) => (
        <View key={ins.id} style={styles.card} testID="insight-card">
          <Text style={styles.text}>{ins.text}</Text>
          <Text style={styles.meta}>Fonte: {ins.source}</Text>
          {ins.created_at ? (
            <Text style={styles.meta}>Creato: {new Date(ins.created_at).toLocaleString('it-IT')}</Text>
          ) : null}
          {ins.valid_until ? (
            <Text style={styles.meta}>Valido fino: {new Date(ins.valid_until).toLocaleString('it-IT')}</Text>
          ) : null}
          <View style={styles.actions}>
            {ins.action && onAction ? (
              <Pressable style={styles.btn} onPress={() => onAction(ins)} testID="insight-action">
                <Text style={styles.btnText}>{ins.action.label || 'Apri'}</Text>
              </Pressable>
            ) : null}
            <Pressable style={styles.btn} onPress={() => onIgnore(ins.id)} testID="insight-ignore">
              <Ionicons name="close" size={12} color={tokens.color.onSurfaceMuted} />
              <Text style={styles.btnText}>Ignora</Text>
            </Pressable>
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: 8 },
  h: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.md,
    padding: tokens.spacing.md,
    gap: 4,
    borderWidth: 1,
    borderColor: tokens.color.border,
    borderLeftWidth: 2,
    borderLeftColor: tokens.color.brand,
  },
  text: { fontSize: 14, color: tokens.color.onSurface, lineHeight: 20 },
  meta: { fontSize: 11, color: tokens.color.onSurfaceMuted },
  actions: { flexDirection: 'row', gap: 8, marginTop: 6 },
  btn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: tokens.radius.pill, borderWidth: 1, borderColor: tokens.color.borderStrong,
  },
  btnText: { fontSize: 12, color: tokens.color.onSurface, fontWeight: '600' },
});
