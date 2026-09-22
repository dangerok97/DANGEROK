/**
 * Meteo — quello che la riga in alto non può dire in due parole.
 *
 *     UN MODULO CHE NON SI APRE È UN'ETICHETTA.
 *
 * In Home c'è la condizione, la temperatura e il posto. Qui c'è il resto:
 * quanto si sente davvero, l'umidità, il vento, le prossime dodici ore e i
 * prossimi giorni, con l'alba e il tramonto.
 *
 * Il punto da cui si guarda è lo stesso della Home — la posizione che il
 * telefono ha già condiviso — e i numeri vengono dalla stessa fonte: due modi
 * diversi di scegliere il punto darebbero due meteo diversi nella stessa app.
 */
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { api, type WeatherDetail } from '@/src/api/client';
import { OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function Meteo() {
  const [dati, setDati] = useState<WeatherDetail | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [carico, setCarico] = useState(true);
  const [localizzando, setLocalizzando] = useState(false);
  const [errorePosizione, setErrorePosizione] = useState<string | null>(null);

  const localizza = async () => {
    if (localizzando) return;
    setLocalizzando(true);
    setErrorePosizione(null);
    try {
      const { shareForegroundPosition } = await import('@/src/location/shareForeground');
      await shareForegroundPosition();
      await leggi();
    } catch (e) {
      setErrorePosizione(e instanceof Error ? e.message : 'Non riesco a rilevare la posizione.');
    } finally { setLocalizzando(false); }
  };

  const leggi = useCallback(async () => {
    setCarico(true);
    try {
      setDati(await api.weather());
      setErrore(null);
    } catch (e) {
      setErrore(humanizeError(e));
    } finally {
      setCarico(false);
    }
  }, []);

  useEffect(() => {
    void leggi();
  }, [leggi]);

  const c = dati?.available ? dati : null;

  return (
    <PaginaOra
      titolo="Meteo"
      sottotitolo={c?.place ? `Dove sei adesso: ${c.place}.` : undefined}
      attiva="index"
      testID="pagina-meteo"
    >
      <Pressable accessibilityRole="button" testID="meteo-consenti-posizione"
        onPress={() => void localizza()} disabled={localizzando}
        style={{ padding: 16 }}>
        <Text style={{ color: ora.cta }}>{localizzando ? 'Rilevo la posizione…' : 'Usa la mia posizione'}</Text>
      </Pressable>
      {errorePosizione ? <Text accessibilityRole="alert">{errorePosizione}</Text> : null}
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="meteo-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="meteo-errore" />
      ) : !c ? (
        <NienteQui
          testo={
            dati?.why_unavailable
              ? `Meteo non disponibile: ${dati.why_unavailable}.`
              : 'Meteo non disponibile.'
          }
          testID="meteo-non-disponibile"
        />
      ) : (
        <>
          <OraCard style={styles.adesso} testID="meteo-adesso">
            <View style={styles.adessoTesta}>
              <Ionicons name={(c.icon as never) || 'partly-sunny-outline'} size={44} color={ora.cta} />
              <View style={{ flex: 1 }}>
                <Text style={styles.gradi}>{c.temperature_c}°C</Text>
                <Text style={[oraType.body, { color: ora.ink2 }]}>{c.label}</Text>
              </View>
            </View>
            <View style={styles.dettagli}>
              <Dato icona="thermometer-outline" etichetta="Percepiti" valore={numero(c.feels_like_c, '°C')} />
              <Dato icona="water-outline" etichetta="Umidità" valore={numero(c.humidity_pct, '%')} />
              <Dato icona="navigate-outline" etichetta="Vento" valore={numero(c.wind_kmh, ' km/h')} />
              <Dato icona="rainy-outline" etichetta="Pioggia" valore={numero(c.precipitation_mm, ' mm')} />
              <Dato icona="sunny-outline" etichetta="Alba" valore={c.sunrise || ''} />
              <Dato icona="moon-outline" etichetta="Tramonto" valore={c.sunset || ''} />
            </View>
          </OraCard>

          {c.hours?.length ? (
            <OraCard style={styles.blocco} testID="meteo-ore">
              <Text style={[oraType.section, { color: ora.ink }]} accessibilityRole="header" aria-level={2}>
                Le prossime ore
              </Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={styles.ore}>
                  {c.hours.map((o) => (
                    <View key={o.time} style={styles.ora} testID={`meteo-ora-${o.time}`}>
                      <Text style={[oraType.small, { color: ora.ink3 }]}>{o.time}</Text>
                      <Ionicons name={(o.icon as never) || 'partly-sunny-outline'} size={22} color={ora.deep} />
                      <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
                        {numero(o.temperature_c, '°')}
                      </Text>
                      {/* La probabilità di pioggia si mostra solo quando c'è. */}
                      {o.rain_chance_pct ? (
                        <Text style={[oraType.small, { color: ora.cta }]}>{o.rain_chance_pct}%</Text>
                      ) : null}
                    </View>
                  ))}
                </View>
              </ScrollView>
            </OraCard>
          ) : null}

          {c.days?.length ? (
            <OraCard style={styles.blocco} testID="meteo-giorni">
              <Text style={[oraType.section, { color: ora.ink }]} accessibilityRole="header" aria-level={2}>
                I prossimi giorni
              </Text>
              {c.days.map((g) => (
                <View key={g.date} style={styles.giorno} testID={`meteo-giorno-${g.date}`}>
                  <Text style={[oraType.body, { color: ora.ink, width: 110 }]}>{g.label}</Text>
                  <Ionicons name={(g.icon as never) || 'partly-sunny-outline'} size={20} color={ora.deep} />
                  <Text style={[oraType.small, { color: ora.ink2, flex: 1 }]} numberOfLines={1}>
                    {g.condition_label || ''}
                    {g.rain_chance_pct ? ` · pioggia ${g.rain_chance_pct}%` : ''}
                  </Text>
                  <Text style={[oraType.body, { color: ora.ink3 }]}>{numero(g.min_c, '°')}</Text>
                  <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>
                    {numero(g.max_c, '°')}
                  </Text>
                </View>
              ))}
            </OraCard>
          ) : null}
        </>
      )}
    </PaginaOra>
  );
}

/** Un numero con la sua unità, o niente: un trattino non è un dato. */
function numero(valore?: number | null, unita = ''): string {
  return typeof valore === 'number' ? `${valore}${unita}` : '';
}

function Dato({
  icona,
  etichetta,
  valore,
}: {
  icona: keyof typeof Ionicons.glyphMap;
  etichetta: string;
  valore: string;
}) {
  // Quello che il servizio non dà non si mostra vuoto: si toglie.
  if (!valore) return null;
  return (
    <View style={styles.dato}>
      <Ionicons name={icona} size={16} color={ora.ink3} />
      <View>
        <Text style={[oraType.small, { color: ora.ink3 }]}>{etichetta}</Text>
        <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>{valore}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  adesso: { gap: 18, padding: 22 },
  adessoTesta: { flexDirection: 'row', alignItems: 'center', gap: 18 },
  gradi: { fontSize: 40, fontWeight: '700', color: ora.ink, letterSpacing: -1 },
  dettagli: { flexDirection: 'row', flexWrap: 'wrap', gap: 20 },
  dato: { flexDirection: 'row', alignItems: 'center', gap: 8, minWidth: 130 },
  blocco: { gap: 14, padding: 22 },
  ore: { flexDirection: 'row', gap: 22, paddingVertical: 4 },
  ora: { alignItems: 'center', gap: 6, minWidth: 54 },
  giorno: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: ora.divider,
  },
});
