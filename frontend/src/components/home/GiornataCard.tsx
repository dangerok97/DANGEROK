/**
 * «La tua giornata» in Home, scritta dal codice.
 *
 * Dopo la pulizia del 3/11 la Home del proprietario era vuota: le proposte
 * vengono dal modello, e con il modello in quota non ne arrivano. Le cose
 * concrete della giornata però ORA le sa senza ragionare — appuntamenti,
 * promemoria, scadenze, cose che segue, bucato, domani — e qui le mostra.
 * Il meteo no: è già nell'intestazione.
 */
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';

import { api, type MorningToday } from '@/src/api/client';
import { ora, oraType } from '@/src/theme/oraSurface';

const KEYS = ['today', 'reminders', 'deadlines', 'meals', 'watching', 'drying', 'tomorrow', 'done'];
const EMPTY = new Set(['Niente in agenda.']);

/** Only sections that say something: an empty day shows nothing here. */
export function sezioniGiornata(m: MorningToday | null): MorningToday['sections'] {
  return (m?.sections || [])
    .filter(s => KEYS.includes(s.key))
    .map(s => ({ ...s, lines: s.lines.filter(l => l.trim() && !EMPTY.has(l.trim())) }))
    .filter(s => s.lines.length > 0)
    .slice(0, 4);
}

export function GiornataCard() {
  const router = useRouter();
  const [m, setM] = useState<MorningToday | null>(null);
  useFocusEffect(useCallback(() => {
    let vivo = true;
    api.morningToday().then(r => { if (vivo) setM(r); }).catch(() => undefined);
    return () => { vivo = false; };
  }, []));
  const sezioni = sezioniGiornata(m);
  if (!sezioni.length) return null;
  return (
    <Pressable accessibilityRole="button" onPress={() => router.push('/giornata' as never)} testID="home-giornata"
      style={({ pressed }) => [styles.card, pressed && { opacity: 0.9 }]}>
      <View style={styles.head}>
        <Text style={[oraType.small, { color: ora.ink3, fontWeight: '700', letterSpacing: 0.4 }]}>LA TUA GIORNATA</Text>
        <Ionicons name="chevron-forward" size={16} color={ora.ink3} />
      </View>
      {sezioni.map(s => (
        <View key={s.key} style={styles.row}>
          <Ionicons name={s.icon as keyof typeof Ionicons.glyphMap} size={18}
            color={s.key === 'drying' && !s.good ? ora.attention : ora.deep} style={{ marginTop: 2 }} />
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={[oraType.small, { color: ora.ink3, fontWeight: '600' }]}>{s.title}</Text>
            {s.lines.slice(0, 3).map((l, i) => (
              <Text key={i} style={[oraType.body, { color: ora.ink }]} numberOfLines={2}>{l}</Text>
            ))}
          </View>
        </View>
      ))}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { gap: 12, padding: 18, borderRadius: 16, borderWidth: 1, borderColor: ora.hairline, backgroundColor: '#fff',
    marginBottom: 12 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  row: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
});
