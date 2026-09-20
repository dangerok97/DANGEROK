/**
 * «Le migliori opzioni per te» — come arrivarci, prima dei link.
 *
 * Reference 2: a «portami a lavoro» ORA non risponde con tre link a tre mappe.
 * Confronta i modi con i tempi veri, dice quale consiglia e perché, e solo
 * dopo offre «Avvia navigazione».
 *
 * Tutto quello che si legge qui arriva dal servizio dei percorsi: se non c'è,
 * questo modulo non compare — nessun tempo inventato, nessun traffico finto.
 */
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { OraBadge, OraButton, OraCard } from '@/src/components/ora-ui';
import { ora, oraType } from '@/src/theme/oraSurface';

export type JourneyOption = {
  mode: string;
  label: string;
  icon?: string;
  duration_label: string;
  duration_seconds: number;
  distance_meters?: number | null;
  reflects_current_traffic?: boolean;
  recommended?: boolean;
};

export type OraJourneyView = {
  destination?: string;
  options: JourneyOption[];
  advice?: string;
  /** Perché non c'è un confronto dei tempi. Mai un numero al posto suo. */
  unavailable?: string;
};

export function OraJourney({
  journey,
  navigation,
}: {
  journey: OraJourneyView;
  navigation?: { id: string; label: string; url: string }[];
}) {
  if (!journey?.options?.length) {
    // Senza un servizio che conosca i percorsi non si confronta niente: lo si
    // dice, e restano i link alle mappe che funzionano davvero.
    if (!journey?.unavailable) return null;
    return (
      <View style={styles.nota} testID="ora-journey-unavailable">
        <Ionicons name="information-circle-outline" size={16} color={ora.ink3} />
        <Text style={[oraType.small, { color: ora.ink3, flex: 1 }]}>
          Non posso confrontare i tempi di percorrenza: {journey.unavailable}.
        </Text>
      </View>
    );
  }
  const apri = navigation?.[0];

  return (
    <OraCard style={styles.card} testID="ora-journey">
      <View style={styles.head}>
        <Ionicons name="car-outline" size={22} color={ora.deep} />
        <View style={{ flex: 1 }}>
          <Text style={[oraType.section, { color: ora.ink }]}>Le migliori opzioni per te</Text>
          <Text style={[oraType.small, { color: ora.ink3 }]}>
            Aggiornate con i tempi di percorrenza di adesso.
          </Text>
        </View>
      </View>

      <View style={styles.righe}>
        {journey.options.map((o) => (
          <View
            key={o.mode}
            style={[styles.opzione, o.recommended && styles.consigliata]}
            testID={`ora-journey-${o.mode}`}
          >
            <View style={styles.opzioneHead}>
              <Ionicons name={(o.icon as any) || 'navigate-outline'} size={20} color={ora.deep} />
              <Text style={[oraType.body, { color: ora.ink, fontWeight: '600', flex: 1 }]}>
                {o.label}
              </Text>
              {o.recommended ? <OraBadge label="Consigliato" tone="info" /> : null}
            </View>
            <Text style={[styles.durata, { color: ora.ink }]}>{o.duration_label}</Text>
            {o.distance_meters ? (
              <Text style={[oraType.small, { color: ora.ink3 }]}>
                {(o.distance_meters / 1000).toFixed(1).replace('.', ',')} km
              </Text>
            ) : null}
            {o.reflects_current_traffic ? (
              <View style={styles.traffico}>
                <View style={styles.pallino} />
                <Text style={[oraType.small, { color: ora.ink2 }]}>Tiene conto del traffico</Text>
              </View>
            ) : null}
            {o.recommended && apri ? (
              <OraButton
                label="Avvia navigazione"
                icon="navigate"
                compact
                onPress={() => void Linking.openURL(apri.url)}
                testID="ora-journey-start"
              />
            ) : null}
          </View>
        ))}
      </View>

      {journey.advice ? (
        <View style={styles.consiglio} testID="ora-journey-advice">
          <Ionicons name="time-outline" size={18} color={ora.deep} />
          <Text style={[oraType.small, { color: ora.ink2, flex: 1 }]}>{journey.advice}</Text>
        </View>
      ) : null}

      {navigation && navigation.length > 1 ? (
        <View style={styles.altreApp}>
          {navigation.slice(1).map((n) => (
            <Pressable
              key={n.id}
              onPress={() => void Linking.openURL(n.url)}
              accessibilityRole="link"
              style={({ pressed }) => [styles.appLink, pressed && { opacity: 0.7 }]}
            >
              <Text style={[oraType.small, { color: ora.cta }]}>Apri in {n.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </OraCard>
  );
}

const styles = StyleSheet.create({
  card: { gap: 16, padding: 20, marginTop: 12 },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  righe: {
    flexDirection: Platform.OS === 'web' ? 'row' : 'column',
    gap: 12,
    flexWrap: 'wrap',
  },
  opzione: {
    flexGrow: 1,
    flexBasis: 180,
    gap: 6,
    padding: 16,
    borderRadius: ora.radius.inner,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ora.hairline,
    backgroundColor: ora.surface,
  },
  consigliata: { borderColor: ora.cta, borderWidth: 1.5, backgroundColor: ora.surfaceTint },
  opzioneHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  durata: { fontSize: 26, fontWeight: '700', letterSpacing: -0.4 },
  traffico: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  pallino: { width: 8, height: 8, borderRadius: 4, backgroundColor: ora.success },
  consiglio: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'center',
    backgroundColor: ora.surfaceTint,
    borderRadius: ora.radius.inner,
    padding: 14,
  },
  altreApp: { flexDirection: 'row', gap: 16, flexWrap: 'wrap' },
  nota: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  appLink: { paddingVertical: 4 },
});
