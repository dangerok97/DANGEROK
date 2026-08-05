import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';

export function EmptyHome() {
  return (
    <View style={styles.card} testID="empty-home">
      <View style={styles.iconWrap}>
        <Ionicons name="checkmark-done-outline" size={32} color={tokens.color.success} />
      </View>
      <Text style={styles.title}>Niente di urgente adesso.</Text>
      <Text style={styles.body}>
        Quando arrivano documenti, impegni o scadenze, ORA li ordina qui.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: tokens.radius.lg,
    padding: tokens.spacing.xl,
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderColor: tokens.color.border,
  },
  iconWrap: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: tokens.color.successBg,
    alignItems: 'center', justifyContent: 'center',
  },
  title: { fontSize: 17, fontWeight: '600', color: tokens.color.onSurface, textAlign: 'center' },
  body: { fontSize: 13, color: tokens.color.onSurfaceMuted, textAlign: 'center', lineHeight: 19 },
});
