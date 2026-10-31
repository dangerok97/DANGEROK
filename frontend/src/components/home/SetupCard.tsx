/**
 * «Prepara ORA»: in Home finché la guida al primo avvio non è finita o chiusa.
 * Senza notifiche, posizione e casa ORA non può fare da sola quello che promette.
 */
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';

import { api } from '@/src/api/client';
import { ora, oraType } from '@/src/theme/oraSurface';

export function setupCardVisible(st: { done: boolean; dismissed: boolean } | null): boolean {
  return !!st && !st.done && !st.dismissed;
}

export function SetupCard() {
  const router = useRouter();
  const [st, setSt] = useState<Awaited<ReturnType<typeof api.setupStatus>> | null>(null);
  useFocusEffect(useCallback(() => {
    let alive = true;
    api.setupStatus().then(r => { if (alive) setSt(r); }).catch(() => undefined);
    return () => { alive = false; };
  }, []));
  if (!setupCardVisible(st)) return null;
  const fatti = 5 - (st?.missing.length ?? 5);
  return (
    <Pressable accessibilityRole="button" onPress={() => router.push('/inizia' as never)} testID="home-setup-card"
      style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}>
      <Ionicons name="sparkles-outline" size={22} color={ora.cta} />
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>Prepara ORA ({fatti} di 5)</Text>
        <Text style={[oraType.small, { color: ora.ink2 }]}>Notifiche, posizione, casa e come ti muovi: così ORA lavora da sola.</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={ora.ink3} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 16,
    borderWidth: 1, borderColor: ora.hairline, backgroundColor: '#fff', marginBottom: 12 },
});
