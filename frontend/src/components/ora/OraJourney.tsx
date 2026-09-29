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
import { Fragment } from 'react';
import { Linking, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { OraBadge, OraButton, OraCard } from '@/src/components/ora-ui';
import { useTheme } from '@/src/theme/ThemeProvider';
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
  road_choices?: { label: string; duration_seconds: number; delay_minutes?: number | null; delay_reference?: string; recommended: boolean; reason: string; main_steps?: string[]; incidents?: { label: string; road?: string }[] }[];
  route_weather?: { label: string; condition: string; temperature_c: number; rain_chance_pct: number }[];
  route_provider?: string;
  destination_weather?: { condition: string; temperature_c: number } | null;
};

export function OraJourney({
  journey,
  navigation,
}: {
  journey: OraJourneyView;
  navigation?: { id: string; label: string; url: string }[];
}) {
  const { colors } = useTheme();
  if (!journey?.options?.length) {
    // Senza un servizio che conosca i percorsi non si confronta niente: lo si
    // dice, e restano i link alle mappe che funzionano davvero.
    if (!journey?.unavailable && !journey?.destination_weather) return null;
    return (
      <View testID="ora-journey-unavailable" style={styles.notaColumn}>
        {journey?.destination_weather ? <Text style={[oraType.small, { color: colors.textPrimary }]}>
          A destinazione adesso: {journey.destination_weather.condition}, {journey.destination_weather.temperature_c}°.
        </Text> : null}
        {journey?.unavailable ? <View style={styles.nota}>
          <Ionicons name="information-circle-outline" size={16} color={colors.textTertiary} />
          <Text style={[oraType.small, { color: colors.textTertiary, flex: 1 }]}>
            Non posso confrontare i tempi di percorrenza: {journey.unavailable}.
          </Text>
        </View> : null}
      </View>
    );
  }
  const apri = navigation?.[0];

  return (
    <OraCard style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]} testID="ora-journey">
      <View style={styles.head}>
        <Ionicons name="car-outline" size={22} color={colors.accent} />
        <View style={{ flex: 1 }}>
          <Text style={[oraType.section, { color: colors.textPrimary }]}>Le migliori opzioni per te</Text>
          <Text style={[oraType.small, { color: colors.textTertiary }]}>
            Aggiornate con i tempi di percorrenza di adesso.
          </Text>
        </View>
      </View>

      <View style={styles.righe}>
        {journey.options.map((o) => (
          <View
            key={o.mode}
            style={[styles.opzione, { backgroundColor: colors.backgroundSecondary, borderColor: o.recommended ? colors.accent : colors.border, borderWidth: o.recommended ? 1.5 : StyleSheet.hairlineWidth }]}
            testID={`ora-journey-${o.mode}`}
          >
            <View style={styles.opzioneHead}>
              <Ionicons name={(o.icon as any) || 'navigate-outline'} size={20} color={colors.accent} />
              <Text style={[oraType.body, { color: colors.textPrimary, fontWeight: '600', flex: 1 }]}>
                {o.label}
              </Text>
              {o.recommended ? <OraBadge label="Consigliato" tone="info" /> : null}
            </View>
            <Text style={[styles.durata, { color: colors.textPrimary }]}>{o.duration_label}</Text>
            {o.distance_meters ? (
              <Text style={[oraType.small, { color: colors.textTertiary }]}>
                {(o.distance_meters / 1000).toFixed(1).replace('.', ',')} km
              </Text>
            ) : null}
            {o.reflects_current_traffic ? (
              <View style={styles.traffico}>
                <View style={styles.pallino} />
                <Text style={[oraType.small, { color: colors.textSecondary }]}>Tiene conto del traffico</Text>
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
        <View style={[styles.consiglio, { backgroundColor: colors.backgroundSecondary }]} testID="ora-journey-advice">
          <Ionicons name="time-outline" size={18} color={colors.accent} />
          <Text style={[oraType.small, { color: colors.textSecondary, flex: 1 }]}>{journey.advice}</Text>
        </View>
      ) : null}

      {journey.road_choices?.length ? (
        <View style={styles.section} testID="ora-road-choices">
          <Text style={[oraType.body, { color: colors.textPrimary, fontWeight: '600' }]}>Quale strada conviene</Text>
          {journey.road_choices.map((road, i) => (
            <Fragment key={i}>
              <Text style={[oraType.small, { color: colors.textSecondary }]}>
                {road.label}: {Math.round(road.duration_seconds / 60)} min
                {road.delay_minutes != null ? `, ${road.delay_minutes} min di rallentamento stimato rispetto al ${road.delay_reference === 'tempo tipico' ? 'tempo tipico' : 'tempo senza traffico'}` : ''}. {road.reason}
                {road.main_steps?.length ? ` Indicazioni principali: ${road.main_steps.join('; ')}.` : ''}
              </Text>
              {road.incidents?.map((incident, j) => (
                <Text key={j} style={[oraType.small, { color: colors.textSecondary }]}>
                  Segnalazione: {incident.label}{incident.road ? ` su ${incident.road}` : ' sul percorso'}.
                </Text>
              ))}
            </Fragment>
          ))}
          <Text style={[oraType.small, { color: colors.textTertiary }]}>La mappa conferma strade e deviazioni al momento dell&apos;apertura.</Text>
          {journey.route_provider === 'mapbox' ? <Text style={[oraType.small, { color: colors.textTertiary }]}>Dati destinazione, percorso e incidenti © Mapbox.</Text> : null}
        </View>
      ) : null}

      {journey.route_weather?.length ? (
        <View style={styles.section} testID="ora-route-weather">
          <Text style={[oraType.body, { color: colors.textPrimary, fontWeight: '600' }]}>Meteo lungo il tragitto</Text>
          {journey.route_weather.map((point, i) => (
            <Text key={i} style={[oraType.small, { color: colors.textSecondary }]}>
              {point.label}: {point.condition}, {point.temperature_c}°, probabilità di pioggia {point.rain_chance_pct}%.
            </Text>
          ))}
          <Text style={[oraType.small, { color: colors.textTertiary }]}>Previsione nei punti del percorso, all&apos;ora approssimativa di passaggio.</Text>
        </View>
      ) : journey.destination_weather ? (
        <Text style={[oraType.small, { color: colors.textSecondary }]}>
          A destinazione adesso: {journey.destination_weather.condition}, {journey.destination_weather.temperature_c}°.
        </Text>
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
              <Text style={[oraType.small, { color: colors.accent }]}>Apri in {n.label}</Text>
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
  notaColumn: { gap: 8, marginTop: 10 },
  section: { gap: 8, padding: 14, borderRadius: ora.radius.inner },
  appLink: { paddingVertical: 4 },
});
