/**
 * «Collega un conto» — scegliere la propria banca, e andare ad autenticarsi.
 *
 *     QUI DENTRO NON SI DIGITA NIENTE DELLA BANCA.
 *
 * Questa schermata fa tre cose e nessuna di più: mostra le banche del paese,
 * ne fa scegliere una, e apre il percorso ufficiale dove la persona
 * autentica — sul sito della propria banca, non qui. ORA non vede e non
 * vuole vedere quelle credenziali: un campo «password della banca» dentro
 * un'app di terze parti è phishing con una buona intenzione, e resta
 * phishing.
 *
 * Quando si torna indietro, l'unico modo di sapere com'è andata è chiedere
 * all'aggregatore: la schermata lo fa da sola, e nel frattempo dice
 * «Collegamento in corso» invece di far finta che sia finita.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { api, BankConnection } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { useAmbientInset } from '@/src/shell';

const MAX_WIDTH = 720;

type Bank = { id: string; nome: string; logo: string };

/**
 * Il messaggio del server, quando il server ne ha uno scritto per una persona.
 *
 * «Il servizio è temporaneamente non disponibile» è vero e inutile: qui il
 * motivo si sa — non c'è ancora un aggregatore collegato — e dirlo è l'unica
 * versione che permette a chi legge di capire che non è colpa sua e che non
 * deve riprovare fra un minuto.
 */
function whatTheServerSaid(e: any, fallback: string): string {
  const ours = ['bank_provider_not_configured', 'bank_unavailable'];
  const detail = e?.detail;
  if (detail && ours.includes(String(detail.error)) && detail.message) {
    return String(detail.message);
  }
  return fallback;
}

export default function CollegaContoScreen() {
  const router = useRouter();
  const ambient = useAmbientInset();
  const [banks, setBanks] = useState<Bank[] | null>(null);
  const [sandbox, setSandbox] = useState(false);
  const [state, setState] = useState<BankConnection | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waitingOn, setWaitingOn] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setState(await api.bankState());
      const got = await api.bankInstitutions('IT');
      setBanks(got.banche);
      setSandbox(!!got.di_prova);
      setError(null);
    } catch (e: any) {
      // Senza un aggregatore configurato l'elenco non esiste, e dirlo è
      // meglio che mostrare una lista vuota che sembra un guasto.
      setError(whatTheServerSaid(e, humanizeError(e, 'default')));
      setBanks([]);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /**
   * Al ritorno dal percorso della banca non si sa niente finché non lo si
   * chiede: si chiede, e finché la risposta non dice «collegato» la
   * schermata resta onesta sul fatto che sta ancora aspettando.
   */
  useEffect(() => {
    if (!waitingOn) return undefined;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const seen = await api.bankLinkStatus(waitingOn);
        if (!alive) return;
        setState(seen);
        if (seen.stato === 'collegato') {
          setWaitingOn(null);
          router.replace('/conti-e-denaro');
        }
      } catch { /* si riprova al giro dopo */ }
    }, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [waitingOn, router]);

  const choose = useCallback(async (bank: Bank) => {
    setBusy(bank.id);
    try {
      const started = await api.bankLink(bank.id);
      setWaitingOn(started.instance_id);
      // Il percorso ufficiale. Da qui in poi la persona è a casa sua.
      if (started.vai_qui) await Linking.openURL(started.vai_qui);
      setState({ stato: 'collegamento_in_corso', in_parole: started.in_parole });
    } catch (e: any) {
      setError(whatTheServerSaid(e, humanizeError(e, 'default')));
    } finally {
      setBusy(null);
    }
  }, []);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={styles.back}
          accessibilityRole="button"
          accessibilityLabel="Torna indietro"
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.textPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>COLLEGA UN CONTO</Text>
        <View style={styles.back} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: ambient.paddingBottom }]}
        testID="collega-conto"
      >
        <View style={styles.column}>
          <View style={styles.panel}>
            <Text style={styles.body}>
              Ti porto sul sito della tua banca. Le credenziali le inserisci lì,
              non qui: io ricevo solo il permesso di leggere.
            </Text>
            <Text style={styles.note}>
              Posso leggere i saldi e i movimenti. Non posso spostare denaro,
              pagare, né disdire niente.
            </Text>
            {/*
              Se il conto che si sta per collegare non è un conto vero, si
              dice adesso. Scoprirlo dopo sarebbe peggio che leggerlo prima.
            */}
            {sandbox ? (
              <Text style={styles.note} testID="ambiente-di-prova">
                Ambiente di prova: i conti che vedi qui non sono conti veri.
              </Text>
            ) : null}
          </View>

          {state && state.stato !== 'non_collegato' ? (
            <View style={styles.panel}>
              <Text style={styles.itemTitle}>{state.in_parole}</Text>
              {waitingOn ? (
                <ActivityIndicator style={{ marginTop: 10 }} color={tokens.color.textPrimary} />
              ) : null}
            </View>
          ) : null}

          {error ? (
            <View style={styles.panel}>
              <Text style={styles.body}>{error}</Text>
            </View>
          ) : null}

          {banks === null && !error ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={tokens.color.textPrimary} />
          ) : null}

          {banks?.length ? (
            <View style={styles.block}>
              <Text style={styles.blockTitle}>LA TUA BANCA</Text>
              <View style={styles.panel}>
                {banks.map((bank) => (
                  <Pressable
                    key={bank.id}
                    style={styles.bank}
                    accessibilityRole="button"
                    testID={`bank-${bank.id}`}
                    onPress={() => choose(bank)}
                    disabled={!!busy}
                  >
                    <Text style={styles.itemTitle}>{bank.nome}</Text>
                    {busy === bank.id ? (
                      <ActivityIndicator color={tokens.color.textSecondary} />
                    ) : (
                      <Ionicons
                        name="chevron-forward"
                        size={18}
                        color={tokens.color.textTertiary}
                      />
                    )}
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.backgroundPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 8, paddingVertical: 6,
  },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  headerTitle: {
    fontSize: 13, letterSpacing: 1.2, color: tokens.color.textSecondary,
    fontWeight: '600',
  },
  scroll: { paddingBottom: 48 },
  column: {
    width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center',
    paddingHorizontal: 20, gap: 20,
  },
  block: { gap: 8 },
  blockTitle: {
    fontSize: 11, letterSpacing: 1, color: tokens.color.textTertiary,
    fontWeight: '700',
  },
  panel: {
    backgroundColor: tokens.color.surface,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: tokens.color.border,
    padding: 16, gap: 10,
  },
  bank: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingVertical: 10,
  },
  itemTitle: { fontSize: 16, fontWeight: '600', color: tokens.color.textPrimary },
  body: { fontSize: 15, color: tokens.color.textPrimary },
  note: { fontSize: 12, color: tokens.color.textTertiary },
});
