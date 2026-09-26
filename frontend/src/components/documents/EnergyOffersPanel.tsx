import { useCallback, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';

import { api, type EnergyOfferMonitoring } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

const day = (value?: string) => value ? new Date(value).toLocaleDateString('it-IT') : '';
const label = (category: string) => ({
  electricity: 'Luce',
  gas: 'Gas',
  insurance_auto: 'Assicurazione auto',
  insurance_home: 'Assicurazione casa',
  insurance: 'Assicurazione',
  telephone: 'Telefonia',
} as Record<string, string>)[category] || 'Contratto';

export function EnergyOffersPanel() {
  const { colors } = useTheme();
  const [data, setData] = useState<EnergyOfferMonitoring | null>(null);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setData(await api.getEnergyOfferMonitoring());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useFocusEffect(useCallback(() => { void refresh(); }, [refresh]));

  const toggle = async () => {
    if (!data || busy) return;
    setBusy(true);
    try {
      setData(await api.setEnergyOfferMonitoring(!data.enabled));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  if (!data?.supplies.length) return null;

  return (
    <View testID="energy-offers-panel" style={{
      padding: tokens.spacing.lg, gap: tokens.spacing.md,
      borderRadius: tokens.radius.lg, backgroundColor: colors.surface,
      borderWidth: 1, borderColor: colors.border,
    }}>
      <Text style={{ color: colors.textPrimary, fontSize: 16, fontWeight: '600' }}>
        Alternative per i tuoi contratti
      </Text>
      <Text style={{ color: colors.textSecondary, fontSize: 13, lineHeight: 19 }}>
        {data.enabled
          ? 'ORA cerca online nuove alternative ogni settimana, anche quando l’app è chiusa.'
          : 'Le ricerche periodiche sono in pausa.'}
      </Text>
      {data.supplies.map((supply) => (
        <View key={`${supply.commodity}:${supply.document_id}`} style={{ gap: 8 }}>
          <Text style={{ color: colors.textPrimary, fontWeight: '600' }}>
            {label(supply.commodity)}
          </Text>
          {supply.last_checked_at ? (
            <Text style={{ color: colors.textTertiary, fontSize: 12 }}>
              Ultimo controllo {day(supply.last_checked_at)}
              {data.enabled && supply.next_check_at ? ` · prossimo ${day(supply.next_check_at)}` : ''}
            </Text>
          ) : (
            <Text style={{ color: colors.textSecondary, fontSize: 12 }}>Primo controllo in programma.</Text>
          )}
          {supply.source_stale && supply.last_checked_at ? (
            <Text style={{ color: colors.textSecondary, fontSize: 13 }}>
              L’ultima ricerca non è abbastanza recente. ORA riproverà automaticamente.
            </Text>
          ) : null}
          {!supply.source_stale && !supply.candidates?.length && supply.last_checked_at ? (
            <Text style={{ color: colors.textSecondary, fontSize: 13 }}>
              Nessuna offerta verificabile emersa nell’ultimo controllo.
            </Text>
          ) : null}
          {supply.source_fetched_at && !supply.source_stale ? (
            <Text style={{ color: colors.textTertiary, fontSize: 12 }}>
              Ricerca online del {day(supply.source_fetched_at)}
            </Text>
          ) : null}
          {supply.advice ? (
            <View style={{ gap: 4, paddingVertical: 6 }}>
              <Text style={{ color: colors.textPrimary, fontSize: 13, fontWeight: '600' }}>
                Consiglio di ORA
              </Text>
              <Text style={{ color: colors.textSecondary, fontSize: 13, lineHeight: 19 }}>
                {supply.advice.text}
              </Text>
            </View>
          ) : null}
          {(supply.candidates || []).slice(0, 3).map((offer) => (
            <Pressable key={offer.code} accessibilityRole="link"
              onPress={() => { void Linking.openURL(offer.url).catch(() => setError(true)); }}
              style={{ paddingVertical: 5 }}>
              <Text style={{ color: colors.textPrimary, fontSize: 13, fontWeight: '600' }}>
                {offer.name} · {offer.seller}
              </Text>
              <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>
                {offer.comparison_basis === 'seller_component_estimate'
                  ? `Stima sulla sola componente di vendita: ${offer.estimated_seller_year?.toFixed(2)} €/anno contro ${offer.current_seller_year?.toFixed(2)} €/anno. Totale bolletta e requisiti da verificare.`
                  : 'Alternativa trovata online. Prezzo, requisiti e convenienza per te da verificare.'}
              </Text>
            </Pressable>
          ))}
          {supply.last_error ? (
            <Text style={{ color: colors.textSecondary, fontSize: 12 }}>
              L'ultimo controllo non è riuscito. ORA riproverà automaticamente.
            </Text>
          ) : null}
        </View>
      ))}
      <Pressable accessibilityRole="button" onPress={() => { void toggle(); }} disabled={busy}>
        <Text style={{ color: colors.textSecondary, fontSize: 13, textDecorationLine: 'underline' }}>
          {busy ? 'Aggiornamento…' : data.enabled ? 'Metti in pausa i controlli' : 'Riattiva i controlli'}
        </Text>
      </Pressable>
      {error ? <Text style={{ color: colors.error, fontSize: 12 }}>
        Non riesco ad aggiornare le offerte. Riprova quando torni su questa schermata.
      </Text> : null}
    </View>
  );
}

