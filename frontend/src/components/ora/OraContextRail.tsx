/**
 * La colonna di contesto della conversazione.
 *
 * Reference 2: accanto alla chat si legge che cosa conta adesso, dove sei e
 * cosa succede dopo. Non è decorazione e non è hardcoded — è la stessa
 * risposta canonica che alimenta la Home, letta una volta e mostrata qui.
 * Quello che non c'è non viene inventato: la card sparisce.
 */
import { useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type HomeItem, type HomeV2Response } from '@/src/api/client';
import { OraCard, OraLink } from '@/src/components/ora-ui';
import { ora, oraType } from '@/src/theme/oraSurface';

export const ORA_RAIL_WIDTH = 340;

type Riga = { icon: any; title: string; body?: string | null };

export function OraContextRail({ activeContext }: { activeContext?: string | null }) {
  const router = useRouter();
  const [home, setHome] = useState<HomeV2Response | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getHome()
      .then((d) => { if (alive) setHome(d); })
      .catch(() => { /* il contesto è un di più: senza, la chat resta intera */ });
    return () => { alive = false; };
  }, []);

  const focus = home?.primary_focus || null;
  const situation = home?.current_situation || null;

  const contesto: Riga[] = useMemo(() => {
    const righe: Riga[] = [];
    const place = (home?.ambient?.text || '').trim();
    if (activeContext) righe.push({ icon: 'navigate-outline', title: activeContext });
    if (situation?.next_commitment) {
      righe.push({
        icon: 'calendar-outline',
        title: 'Prossimo impegno',
        body: String(situation.next_commitment),
      });
    }
    if (place) righe.push({ icon: 'pulse-outline', title: 'Ultima cosa che ho fatto', body: place });
    return righe;
  }, [activeContext, home?.ambient?.text, situation?.next_commitment]);

  const prossimi: HomeItem[] = useMemo(() => {
    const tutti = [
      ...(home?.primary_focus ? [home.primary_focus] : []),
      ...((home?.priorities || []).flatMap((p: any) => p.items || [])),
    ];
    const visti = new Set<string>();
    return tutti.filter((i) => (i && !visti.has(i.id) ? visti.add(i.id) : false)).slice(0, 3);
  }, [home?.primary_focus, home?.priorities]);

  if (!home) return <View style={styles.rail} testID="ora-context-rail" />;

  return (
    <View style={styles.rail} testID="ora-context-rail">
      {focus ? (
        <OraCard style={styles.card}>
          <View style={styles.head}>
            <Ionicons name="checkmark-circle-outline" size={20} color={ora.deep} />
            <Text style={[styles.title, { flex: 1 }]}>Cosa conta ora</Text>
            <OraLink label="Modifica" chevron={false} onPress={() => router.push('/situazione' as any)} />
          </View>
          <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]} numberOfLines={2}>
            {focus.title}
          </Text>
          {focus.subtitle || focus.description ? (
            <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={3}>
              {focus.subtitle || focus.description}
            </Text>
          ) : null}
        </OraCard>
      ) : null}

      {contesto.length ? (
        <OraCard style={styles.card}>
          <View style={styles.head}>
            <Ionicons name="stats-chart-outline" size={20} color={ora.deep} />
            <Text style={[styles.title, { flex: 1 }]}>Contesto attuale</Text>
          </View>
          {contesto.map((r, i) => (
            <View key={`${r.title}-${i}`} style={styles.row}>
              <Ionicons name={r.icon} size={18} color={ora.deep} style={{ marginTop: 2 }} />
              <View style={{ flex: 1 }}>
                <Text style={[oraType.small, { color: ora.ink, fontWeight: '600' }]}>{r.title}</Text>
                {r.body ? (
                  <Text style={[oraType.small, { color: ora.ink2 }]} numberOfLines={2}>
                    {r.body}
                  </Text>
                ) : null}
              </View>
            </View>
          ))}
        </OraCard>
      ) : null}

      {prossimi.length ? (
        <OraCard style={styles.card}>
          <View style={styles.head}>
            <Ionicons name="checkbox-outline" size={20} color={ora.deep} />
            <Text style={[styles.title, { flex: 1 }]}>Prossimi passi</Text>
            <OraLink label="Vedi agenda" chevron={false} onPress={() => router.push('/situazione' as any)} />
          </View>
          {prossimi.map((i) => (
            <Pressable
              key={i.id}
              onPress={() => {
                const route = i.actions?.find((a) => a.route)?.route;
                if (route) router.push(route as any);
              }}
              style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}
              accessibilityRole="button"
            >
              <View style={styles.dot} />
              <View style={{ flex: 1 }}>
                <Text style={[oraType.small, { color: ora.ink }]} numberOfLines={2}>
                  {i.title}
                </Text>
                {i.subtitle ? (
                  <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={1}>
                    {i.subtitle}
                  </Text>
                ) : null}
              </View>
            </Pressable>
          ))}
        </OraCard>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  rail: { width: ORA_RAIL_WIDTH, gap: 16, paddingTop: 8 },
  card: { gap: 10, padding: 20 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { fontSize: 17, fontWeight: '600', color: ora.ink },
  row: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  dot: {
    width: 14, height: 14, borderRadius: 7, borderWidth: 1.5,
    borderColor: ora.ctaSoftBorder, marginTop: 3,
  },
});
