/**
 * Il punto del mattino, aperto dalla notifica: la giornata intera, rifatta
 * adesso (non la fotografia delle 8). La notifica dice due righe; qui c'è il
 * resto: tempo, agenda con l'ora di partenza, promemoria, scadenze, bucato,
 * cosa ORA sta seguendo, domani.
 */
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api, type MorningToday } from '@/src/api/client';
import { OraCard } from '@/src/components/ora-ui';
import { ora, oraType } from '@/src/theme/oraSurface';

export function sezioniVisibili(m: MorningToday | null): MorningToday['sections'] {
  return (m?.sections || []).filter(s => s.lines.some(l => l.trim()));
}

export function PuntoDelMattino({ fallback }: { fallback: string }) {
  const [m, setM] = useState<MorningToday | null>(null);
  const [fallito, setFallito] = useState(false);
  useEffect(() => {
    let vivo = true;
    api.morningToday().then(r => { if (vivo) setM(r); }).catch(() => { if (vivo) setFallito(true); });
    return () => { vivo = false; };
  }, []);

  if (fallito) {
    return <OraCard style={styles.card}><Text style={[oraType.body, { color: ora.ink }]}>{fallback}</Text></OraCard>;
  }
  if (!m) return <ActivityIndicator color={ora.cta} testID="brief-carico" />;
  return (
    <View style={{ gap: 12 }} testID="brief-pagina">
      <View style={{ gap: 2 }}>
        <Text style={[oraType.title, { color: ora.ink, fontSize: 24, lineHeight: 30 }]}>{m.greeting}</Text>
        <Text style={[oraType.body, { color: ora.ink2 }]}>{m.day}</Text>
      </View>
      {sezioniVisibili(m).map(s => (
        <OraCard key={s.key} style={styles.card} testID={`brief-${s.key}`}>
          <View style={styles.testa}>
            <Ionicons name={s.icon as keyof typeof Ionicons.glyphMap} size={20}
              color={s.key === 'drying' ? (s.good ? ora.cta : ora.attention) : ora.deep} />
            <Text style={[oraType.small, { color: ora.ink3, fontWeight: '700', letterSpacing: 0.4 }]}>
              {s.title.toUpperCase()}
            </Text>
          </View>
          {s.lines.map((l, i) => (
            <Text key={i} style={[i === 0 && s.key === 'weather' ? oraType.title : oraType.body,
              { color: i === 0 ? ora.ink : ora.ink2 }]}>{l}</Text>
          ))}
        </OraCard>
      ))}
      <Text style={[oraType.small, { color: ora.ink3 }]}>
        Aggiornato alle {m.at.slice(11, 16)}. Ora e contenuto del punto del mattino si cambiano in Impostazioni.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: 6, padding: 18, alignItems: 'flex-start', alignSelf: 'stretch' },
  testa: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 2 },
});
