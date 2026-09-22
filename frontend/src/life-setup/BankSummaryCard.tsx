import { useCallback, useState } from 'react';
import { AppState, Platform, Pressable, Text, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { api, type MoneyOverview } from '@/src/api/client';
import { ora, oraType } from '@/src/theme/oraSurface';
import { tokens } from '@/src/theme/tokens';
import { useTheme } from '@/src/theme/ThemeProvider';

export function BankSummaryCard() {
  const router = useRouter();
  const { colors } = useTheme();
  const [data, setData] = useState<MoneyOverview | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useFocusEffect(useCallback(() => {
    let active = true;
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const result = await api.moneyOverview();
        if (active) { setData(result); setError(false); }
      } catch { if (active) setError(true); }
      finally { pending = false; }
    };
    void refresh();
    const sub = AppState.addEventListener('change', state => { if (state === 'active') void refresh(); });
    const focus = () => { void refresh(); };
    if (Platform.OS === 'web') window.addEventListener('focus', focus);
    return () => {
      active = false;
      sub.remove();
      if (Platform.OS === 'web') window.removeEventListener('focus', focus);
    };
  }, [retry]));
  const state = data?.collegamento?.stato;
  const connected = state === 'collegato' || state === 'temporaneamente_non_disponibile';
  return (
    <View style={{ backgroundColor: ora.surface, borderRadius: tokens.radius.xl, borderWidth: 1, borderColor: colors.border, padding: 20, gap: 10 }} testID="vita-bank-space">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Ionicons name="wallet-outline" size={24} color={ora.cta} />
        <Text style={{ fontSize: 22, fontWeight: '700', color: ora.ink }}>La tua banca</Text>
      </View>
      <Text style={[oraType.small, { color: ora.ink2 }]}>Conto di prova · ORA LOCAL · Dati simulati</Text>
      {error ? (
        <View style={{ gap: 8 }}>
          <Text style={{ color: colors.error }}>Non riesco ad aggiornare il riepilogo bancario.</Text>
          <Pressable accessibilityRole="button" onPress={() => setRetry(n => n + 1)}><Text style={{ color: ora.cta }}>Riprova</Text></Pressable>
        </View>
      ) : !data ? <Text style={{ color: ora.ink2 }}>Caricamento del riepilogo…</Text> : connected ? (
        <View style={{ gap: 12 }}>
          <Text style={{ color: ora.ink, fontWeight: '600' }}>{state === 'collegato' ? 'Collegata' : data?.collegamento?.in_parole}</Text>
          {data.conti.map((account, index) => (
            <View key={`${account.banca}-${account.conto}-${index}`} style={{ gap: 4 }}>
              <Text style={[oraType.body, { color: ora.ink, fontWeight: '600' }]}>{account.banca} · {account.conto}{account.numero ? ` · ${account.numero}` : ''}</Text>
              <Text style={{ color: ora.ink, fontSize: 24, fontWeight: '600' }}>
                {account.non_piu_aggiornato ? 'Ultimo saldo osservato ' : account.saldo_noto && account.saldo_tipo ? (account.saldo_tipo === 'disponibile' ? 'Disponibile ' : 'Contabile ') : ''}{account.saldo}
              </Text>
              <Text style={[oraType.small, { color: ora.ink2 }]}>Aggiornato {account.aggiornato}</Text>
            </View>
          ))}
          {!data.conti.length && <Text style={{ color: ora.ink2 }}>Il conto è collegato. I primi dati non sono ancora disponibili.</Text>}
        </View>
      ) : (
        <>
          <Text style={[oraType.body, { color: ora.ink2 }]}>{data.collegamento?.in_parole || 'Uno spazio per conti, saldi e movimenti.'}</Text>
          <Pressable accessibilityRole="button" onPress={() => router.push('/collega-conto')} style={{ backgroundColor: ora.cta, borderRadius: 12, padding: 14, alignSelf: 'flex-start' }}>
            <Text style={{ color: '#fff', fontWeight: '600' }}>{state === 'serve_autorizzare_di_nuovo' ? 'Ricollega il conto' : state === 'collegamento_in_corso' ? 'Continua il collegamento' : 'Prova il collegamento'}</Text>
          </Pressable>
        </>
      )}
      <Pressable accessibilityRole="link" onPress={() => router.push('/conti-e-denaro')}><Text style={{ color: ora.cta }}>Vedi conti e movimenti →</Text></Pressable>
    </View>
  );
}
