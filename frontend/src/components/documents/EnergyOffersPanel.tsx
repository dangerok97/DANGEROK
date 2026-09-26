import { useCallback, useState } from 'react';
import { Linking, Pressable, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';

import { api, type EnergyOfferMonitoring } from '@/src/api/client';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';

const euro = (value: number) => `€${Math.round(value).toLocaleString('it-IT')}`;
const day = (value?: string) => value ? new Date(value).toLocaleDateString('it-IT') : '';

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
        Offerte luce e gas
      </Text>
      <Text style={{ color: colors.textSecondary, fontSize: 13, lineHeight: 19 }}>
        {data.enabled
          ? 'ORA controlla le offerte pubbliche ogni settimana, anche dopo il primo caricamento.'
          : 'I controlli delle offerte sono in pausa.'}
      </Text>
      {data.supplies.map((supply) => (
        <View key={`${supply.commodity}:${supply.document_id}`} style={{ gap: 8 }}>
          <Text style={{ color: colors.textPrimary, fontWeight: '600' }}>
            {supply.commodity === 'electricity' ? 'Luce' : 'Gas'}
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
              I dati delle offerte non sono abbastanza recenti. ORA riproverà automaticamente.
            </Text>
          ) : null}
          {!supply.source_stale && !supply.candidates?.length && supply.last_checked_at ? (
            <Text style={{ color: colors.textSecondary, fontSize: 13 }}>
              Nessuna alternativa confrontabile emersa nell'ultimo controllo.
            </Text>
          ) : null}
          {supply.source_fetched_at && !supply.source_stale ? (
            <Text style={{ color: colors.textTertiary, fontSize: 12 }}>
              Dati offerte del {day(supply.source_fetched_at)}
            </Text>
          ) : null}
          {(supply.candidates || []).slice(0, 3).map((offer) => (
            <Pressable key={offer.code} accessibilityRole="link"
              onPress={() => { void Linking.openURL(offer.url).catch(() => setError(true)); }}
              style={{ paddingVertical: 5 }}>
              <Text style={{ color: colors.textPrimary, fontSize: 13, fontWeight: '600' }}>
                {offer.name} · {offer.seller}
              </Text>
              <Text style={{ color: colors.textSecondary, fontSize: 12, lineHeight: 18 }}>
                {offer.potential_saving_year != null
                  ? `Possibile differenza ${euro(offer.potential_saving_year)}/anno sulle componenti di vendita; verifica le condizioni complete.`
                  : 'Alternativa pubblicata: convenienza rispetto alla tua bolletta da verificare.'}
              </Text>
            </Pressable>
          ))}
          {supply.source_url ? (
            <Pressable accessibilityRole="link"
              onPress={() => { void Linking.openURL(supply.source_url!).catch(() => setError(true)); }}>
              <Text style={{ color: colors.textSecondary, fontSize: 12, textDecorationLine: 'underline' }}>
                Dati del Portale Offerte
              </Text>
            </Pressable>
          ) : null}
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

