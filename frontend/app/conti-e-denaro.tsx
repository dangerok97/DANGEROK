/**
 * «Conti e denaro» — cosa ORA vede della banca, e cosa ne ha capito.
 *
 * La domanda a cui questa schermata risponde non è «quanto ho speso»: è
 * un'altra, e più scomoda — *cosa sta guardando ORA, e cosa se ne fa?* Una
 * persona che collega il proprio conto a un sistema che le gestisce la vita
 * ha diritto di vederlo, e di vederlo diviso per gradi di certezza.
 *
 * Quattro blocchi, nell'ordine che conta: i conti collegati con cosa ORA può
 * e non può fare; cosa ha capito; cosa ha collegato alla vita; cosa non ha
 * ancora capito. E in fondo, separati, i movimenti come li ha scritti la
 * banca — perché un elenco che scrive «Affitto» sopra una riga che diceva
 * «BONIFICO A ROSSI MARCO» ha appena trasformato un'ipotesi in un fatto
 * sotto gli occhi di chi legge.
 *
 * Nessun totale, nessun grafico, nessun «ti restano»: chi vuole quello apre
 * la banca. Questa schermata esiste per la fiducia.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, Alert, Platform, Pressable, ScrollView, StyleSheet, Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { api, MoneyOverview } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { useAmbientInset } from '@/src/shell';

const MAX_WIDTH = 720;

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  const present = Array.isArray(children) ? children.filter(Boolean) : children;
  if (!present || (Array.isArray(present) && !present.length)) return null;
  return (
    <View style={styles.block}>
      <Text style={styles.blockTitle}>{title}</Text>
      <View style={styles.panel}>{children}</View>
    </View>
  );
}

export default function ContiEDenaroScreen() {
  const router = useRouter();
  // Come è andato il ritorno dal sito della banca. Ci arriva una parola
  // sola: il codice della banca è stato speso sul server e non passa di qui.
  const { collegamento } = useLocalSearchParams<{ collegamento?: string }>();
  const ambient = useAmbientInset();
  const [data, setData] = useState<MoneyOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.moneyOverview());
      setError(null);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /**
   * Scollegare è irreversibile dal lato della banca: il consenso si chiude, e
   * per riaverlo si rifà tutto il percorso. Quindi si chiede prima — e si
   * dice anche cosa *non* succede, perché è la parte che preoccupa: quello
   * che ORA ha capito resta.
   */
  const unlink = useCallback((instanceId: string) => {
    const go = async () => {
      try {
        await api.bankDisconnect(instanceId);
        await load();
      } catch (e: any) {
        setError(humanizeError(e, 'default'));
      }
    };
    const question = 'Vuoi scollegare il conto?';
    const detail = 'Smetto di leggere i movimenti. Quello che ho capito finora '
      + 'resta, con la data in cui l’ho letto.';
    if (Platform.OS === 'web') {
      if (typeof window !== 'undefined' && window.confirm(question + ' ' + detail)) {
        void go();
      }
      return;
    }
    Alert.alert(question, detail, [
      { text: 'Annulla', style: 'cancel' },
      { text: 'Scollega', style: 'destructive', onPress: () => { void go(); } },
    ]);
  }, [load]);

  const answer = useCallback(async (about: string, yes: boolean) => {
    try {
      await api.homeAction({
        item_id: `ask:${about}`, action: yes ? 'money_yes' : 'money_no',
      });
      await load();
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    }
  }, [load]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Pressable
          onPress={() => router.replace('/(tabs)')}
          style={styles.back}
          accessibilityRole="button"
          accessibilityLabel="Torna alla Home"
        >
          <Ionicons name="chevron-back" size={22} color={tokens.color.textPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>CONTI E DENARO</Text>
        <View style={styles.back} />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scroll, { paddingBottom: ambient.paddingBottom },
        ]}
        testID="conti-e-denaro"
      >
        <View style={styles.column}>
          {loading ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={tokens.color.textPrimary} />
          ) : error ? (
            <Text style={styles.body}>{error}</Text>
          ) : !data?.vale_la_pena_mostrarlo ? (
            <View style={styles.panel}>
              <Text style={styles.body}>
                {data?.collegamento?.in_parole
                  || 'Non ho ancora niente da dirti sui tuoi conti.'}
              </Text>
              <Pressable
                style={styles.cta}
                testID="collega-conto"
                accessibilityRole="button"
                onPress={() => router.push('/collega-conto')}
              >
                <Text style={styles.ctaLabel}>Collega un conto</Text>
              </Pressable>
            </View>
          ) : (
            <>
              {/*
                Lo stato del collegamento sta in cima perché cambia il senso
                di tutto quello che c'è sotto: gli stessi movimenti, con un
                consenso scaduto, sono la fotografia di tre settimane fa.
              */}
              {data.collegamento && data.collegamento.stato !== 'collegato' ? (
                <View style={styles.panel}>
                  <Text style={styles.itemTitle} testID="stato-collegamento">
                    {data.collegamento.in_parole}
                  </Text>
                  {data.collegamento.cosa_posso_fare ? (
                    <Pressable
                      style={styles.cta}
                      testID="ricollega"
                      accessibilityRole="button"
                      onPress={() => router.push('/collega-conto')}
                    >
                      <Text style={styles.ctaLabel}>
                        {data.collegamento.cosa_posso_fare}
                      </Text>
                    </Pressable>
                  ) : null}
                </View>
              ) : null}

              {collegamento === 'annullato' || collegamento === 'non_riuscito' ? (
                <View style={styles.panel}>
                  <Text style={styles.body} testID="esito-collegamento">
                    {collegamento === 'annullato'
                      ? 'Non hai completato il collegamento. Puoi rifarlo quando vuoi.'
                      : 'Il collegamento non è andato a buon fine. Riprova.'}
                  </Text>
                </View>
              ) : null}

              <Block title="CONTI COLLEGATI">
                {data.conti.map((c) => (
                  <View key={`${c.banca}-${c.conto}`} style={styles.item}>
                    <Text style={styles.itemTitle}>{c.banca}</Text>
                    <Text style={styles.itemMeta}>
                      {c.conto}{c.numero ? ' · ' + c.numero : ''}
                    </Text>
                    {/*
                      Un saldo senza un'ora sopra è una cifra che si spaccia
                      per adesso; e «disponibile» e «contabile» non sono la
                      stessa cosa, quindi si dice quale dei due è.
                    */}
                    <Text style={styles.amount}>
                      {c.saldo_noto && c.saldo_tipo
                        ? (c.saldo_tipo === 'disponibile' ? 'Disponibile ' : 'Contabile ') + c.saldo
                        : c.saldo}
                    </Text>
                    <Text style={styles.itemMeta}>Aggiornato {c.aggiornato}</Text>
                    {/*
                      Cosa ORA può e non può fare, a parole. Gli scope tecnici
                      non dicono niente a nessuno, e nascondono proprio la
                      cosa che una persona vuole sapere.
                    */}
                    <Text style={styles.note}>{c.cosa_posso_fare}</Text>
                    <Text style={styles.note}>{c.cosa_non_posso_fare}</Text>
                    {data.collegamento?.instance_id ? (
                      <Pressable
                        style={styles.quiet}
                        testID="scollega"
                        accessibilityRole="button"
                        onPress={() => unlink(data.collegamento?.instance_id || '')}
                      >
                        <Text style={styles.quietLabel}>Scollega</Text>
                      </Pressable>
                    ) : null}
                  </View>
                ))}
              </Block>

              {/*
                Quello che c'era. Sotto un titolo che dice cosa è, con il
                saldo al passato: «ultimo saldo osservato», non «disponibile».
                Un conto che ORA non può più leggere non è un conto collegato,
                e mostrarlo come tale è la bugia più facile del prodotto.
              */}
              <Block title="FONTI NON PIÙ COLLEGATE">
                {(data.fonti_non_piu_collegate || []).map((f) => (
                  <View key={`${f.banca}-${f.conto}`} style={styles.item} testID="fonte-passata">
                    <Text style={styles.pastTitle}>
                      {f.banca}{f.numero ? ' · ' + f.numero : ''}
                    </Text>
                    <Text style={styles.itemMeta}>{f.ultimo_saldo}</Text>
                    <Text style={styles.note}>
                      Letto l’ultima volta {f.letto_l_ultima_volta} · scollegato {f.scollegato}
                    </Text>
                    <Text style={styles.note}>{f.in_parole}</Text>
                  </View>
                ))}
              </Block>

              <Block title="COSA HO CAPITO">
                {data.cosa_ho_capito.map((r, n) => (
                  <View key={`${r.cosa}-${n}`} style={styles.item}>
                    <Text style={styles.itemTitle}>
                      {r.cosa.charAt(0).toUpperCase() + r.cosa.slice(1)}
                    </Text>
                    <Text style={styles.amount}>
                      {r.quanto}{r.ogni_quanto ? ` ${r.ogni_quanto}` : ''}
                    </Text>
                    {/*
                      SO · PENSO · HO VISTO. Non sono tre toni della stessa
                      frase: sono tre cose diverse, e appiattirle sarebbe
                      presentare come certo qualcosa che non lo è — o dare un
                      nome a una cosa che nessuno ha ancora capito.
                    */}
                    <Text style={styles.itemMeta} testID="grado">
                      {r.stato || (r.quanto_ci_conto === 'penso' ? 'PENSO' : 'SO')}
                      {r.perche ? ' — ' + r.perche : ''}
                    </Text>
                    {r.non_so ? (
                      <Text style={styles.itemMeta}>{r.non_so}</Text>
                    ) : null}
                  </View>
                ))}
              </Block>

              <Block title="COLLEGATO ALLA TUA VITA">
                {data.collegato_alla_tua_vita.map((l) => (
                  <View key={l.situazione} style={styles.item}>
                    <Text style={styles.itemTitle}>{l.situazione}</Text>
                    <Text style={styles.itemMeta}>
                      Ci metto dentro: {l.cosa_ci_metto.join(', ')}
                    </Text>
                  </View>
                ))}
              </Block>

              <Block title="DA CAPIRE">
                {data.da_capire.map((q) => (
                  <View key={q.cosa} style={styles.item}>
                    <Text style={styles.itemTitle}>{q.cosa}</Text>
                    <Text style={styles.itemMeta}>{q.perche}</Text>
                    {q.posso_rispondere ? (
                      <View style={styles.answers}>
                        <Pressable
                          style={styles.cta}
                          testID="money-yes"
                          accessibilityRole="button"
                          onPress={() => answer(
                            q.cosa.replace(/^«|».*$/g, ''), true,
                          )}
                        >
                          <Text style={styles.ctaLabel}>Sì</Text>
                        </Pressable>
                        <Pressable
                          style={styles.cta}
                          testID="money-no"
                          accessibilityRole="button"
                          onPress={() => answer(
                            q.cosa.replace(/^«|».*$/g, ''), false,
                          )}
                        >
                          <Text style={styles.ctaLabel}>No</Text>
                        </Pressable>
                      </View>
                    ) : null}
                  </View>
                ))}
              </Block>

              <Block title="MOVIMENTI RECENTI">
                {data.movimenti_recenti.map((m, n) => (
                  <View key={`${m.descrizione}-${n}`} style={styles.movement}>
                    <Text style={styles.movementDay}>{m.quando}</Text>
                    <Text style={styles.movementWhat} numberOfLines={1}>
                      {m.descrizione}
                      {m.in_sospeso ? ' · in sospeso' : ''}
                    </Text>
                    <Text style={styles.movementAmount}>{m.quanto}</Text>
                  </View>
                ))}
              </Block>
            </>
          )}
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
    padding: 16, gap: 14,
  },
  item: { gap: 2 },
  itemTitle: { fontSize: 16, fontWeight: '600', color: tokens.color.textPrimary },
  itemMeta: { fontSize: 13, color: tokens.color.textSecondary },
  amount: { fontSize: 15, color: tokens.color.textPrimary },
  note: { fontSize: 12, color: tokens.color.textTertiary, marginTop: 4 },
  answers: { flexDirection: 'row', gap: 8, marginTop: 8 },
  cta: {
    paddingHorizontal: 18, paddingVertical: 8,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.accent,
  },
  ctaLabel: { color: tokens.color.accent, fontSize: 14, fontWeight: '600' },
  pastTitle: { fontSize: 15, fontWeight: '600', color: tokens.color.textSecondary },
  quiet: { marginTop: 10, alignSelf: 'flex-start' },
  quietLabel: { color: tokens.color.textTertiary, fontSize: 13 },
  movement: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  movementDay: { fontSize: 12, color: tokens.color.textTertiary, width: 44 },
  movementWhat: { flex: 1, fontSize: 13, color: tokens.color.textPrimary },
  movementAmount: { fontSize: 13, color: tokens.color.textSecondary },
  body: { fontSize: 15, color: tokens.color.textPrimary },
});
