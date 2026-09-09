/**
 * Cercare dentro la propria vita.
 *
 *     NON È UN TROVA-FILE.
 *
 * Chi scrive «casa» non vuole i file che contengono la parola «casa»: vuole
 * sapere cosa c'entra con la sua casa — l'acquisto in corso, i soldi che ci
 * girano intorno, l'appuntamento, la mail. Sono cose diverse, e la schermata
 * le tiene divise per quello che sono invece di metterle in fila per
 * punteggio: una fila per punteggio le rende tutte uguali e nessuna utile.
 *
 * Prima che qualcuno scriva, la schermata propone i nomi delle sue cose — non
 * esempi inventati: un campo vuoto non deve chiedere fantasia a chi cerca.
 *
 * Quello che non compare mai: id, punteggi, «trovato per corrispondenza
 * lessicale». Il modo in cui una cosa è stata trovata serve a chi verifica,
 * ed è una scusa travestita da spiegazione per chiunque altro.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { tokens } from '@/src/theme/tokens';
import { api, LifeSearch } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { useAmbientInset } from '@/src/shell';

const MAX_WIDTH = 720;

export default function CercaScreen() {
  const router = useRouter();
  const ambient = useAmbientInset();
  const field = useRef<TextInput>(null);

  const [text, setText] = useState('');
  const [found, setFound] = useState<LifeSearch | null>(null);
  const [tryThese, setTryThese] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.searchSuggestions()
      .then((got) => setTryThese(got.prova_con || []))
      .catch(() => setTryThese([]));
    const timer = setTimeout(() => field.current?.focus(), 350);
    return () => clearTimeout(timer);
  }, []);

  const run = useCallback(async (query: string) => {
    const asked = query.trim();
    if (!asked) return;
    setText(asked);
    setBusy(true);
    setError(null);
    try {
      setFound(await api.searchLife(asked));
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  }, []);

  /** Ogni risultato porta alla superficie umana giusta, quando ne ha una. */
  const open = useCallback((href?: string) => {
    if (href) router.push(href as any);
  }, [router]);

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
        <View style={styles.fieldWrap}>
          <Ionicons name="search" size={16} color={tokens.color.textTertiary} />
          <TextInput
            ref={field}
            value={text}
            onChangeText={setText}
            onSubmitEditing={() => run(text)}
            placeholder="Cerca nella tua vita"
            placeholderTextColor={tokens.color.textTertiary}
            style={styles.field}
            returnKeyType="search"
            autoCorrect={false}
            testID="search-field"
            accessibilityLabel="Cerca nella tua vita"
          />
          {text ? (
            <Pressable
              onPress={() => { setText(''); setFound(null); }}
              accessibilityRole="button"
              accessibilityLabel="Cancella"
            >
              <Ionicons name="close-circle" size={16} color={tokens.color.textTertiary} />
            </Pressable>
          ) : null}
        </View>
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: ambient.paddingBottom }]}
        keyboardShouldPersistTaps="handled"
        testID="cerca"
      >
        <View style={styles.column}>
          {busy ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={tokens.color.textPrimary} />
          ) : error ? (
            <Text style={styles.body}>{error}</Text>
          ) : !found ? (
            /*
              Prima che qualcuno scriva: i nomi delle sue cose. Non
              suggerimenti generici — quelli chiedono di indovinare cosa
              l'app sappia fare, che è il contrario del punto.
            */
            tryThese.length ? (
              <View style={styles.block}>
                <Text style={styles.blockTitle}>PROVA CON</Text>
                <View style={styles.chips}>
                  {tryThese.map((word) => (
                    <Pressable
                      key={word}
                      onPress={() => run(word)}
                      style={styles.chip}
                      accessibilityRole="button"
                      testID={`suggerimento-${word}`}
                    >
                      <Text style={styles.chipLabel}>{word}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
            ) : null
          ) : found.niente_trovato ? (
            <View style={styles.panel}>
              <Text style={styles.body}>{found.in_parole}</Text>
            </View>
          ) : (
            <>
              {/*
                Due verità diverse restano due: il codice non sceglie quale
                fonte dica il vero, e non lo nasconde nemmeno.
              */}
              {found.in_conflitto?.map((c) => (
                <View key={c.su_cosa} style={styles.conflict} testID="conflitto">
                  <Text style={styles.body}>{c.in_parole}</Text>
                </View>
              ))}

              {/*
                La sintesi, quando la domanda chiedeva di sapere. «Documenti
                della casa» vuole i documenti: lì sopra non c'è niente, ed è
                giusto così — un paragrafo davanti a chi sta navigando è una
                cosa in mezzo.
              */}
              {found.in_sintesi ? (
                <View style={styles.panel} testID="sintesi">
                  <Text style={styles.body}>{found.in_sintesi}</Text>
                </View>
              ) : null}

              {found.risultati.map((section) => (
                <View key={section.gruppo} style={styles.block}>
                  <Text style={styles.blockTitle}>{section.gruppo}</Text>
                  <View style={styles.panel}>
                    {section.cosa_c_e.map((row, n) => (
                      <Pressable
                        key={`${row.cosa}-${n}`}
                        onPress={() => open(row.apri)}
                        disabled={!row.apri}
                        style={styles.item}
                        accessibilityRole={row.apri ? 'button' : undefined}
                      >
                        <Text style={styles.itemTitle}>{row.cosa}</Text>
                        {row.quanto ? (
                          <Text style={styles.amount}>
                            {row.quanto}{row.ogni_quanto ? ` ${row.ogni_quanto}` : ''}
                          </Text>
                        ) : null}
                        {row.quando || row.dove ? (
                          <Text style={styles.itemMeta}>
                            {[row.quando, row.dove].filter(Boolean).join(' · ')}
                          </Text>
                        ) : null}
                        {/*
                          SO · PENSO, e da dove lo so. La differenza fra
                          affermare e riferire non si appiattisce nemmeno
                          dentro un risultato di ricerca.
                        */}
                        {row.stato ? (
                          <Text style={styles.itemMeta}>
                            {row.stato}
                            {row.come_lo_so ? ` — ${row.come_lo_so}` : ''}
                          </Text>
                        ) : null}
                        {row.in_una_riga ? (
                          <Text style={styles.itemMeta}>{row.in_una_riga}</Text>
                        ) : null}
                        {row.da_chiarire ? (
                          <Text style={styles.note}>{row.da_chiarire}</Text>
                        ) : null}
                        {/*
                          Perché questa cosa è qui. Una frase che spiega la
                          relazione — non un badge, non un punteggio.
                        */}
                        {row.perche_e_qui ? (
                          <Text style={styles.note}>{row.perche_e_qui}</Text>
                        ) : null}
                        {row.anche_altrove ? (
                          <Text style={styles.note}>{row.anche_altrove}</Text>
                        ) : null}
                      </Pressable>
                    ))}
                  </View>
                </View>
              ))}
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
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 8, paddingVertical: 6,
  },
  back: { width: 36, height: 40, alignItems: 'center', justifyContent: 'center' },
  fieldWrap: {
    flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 12, height: 40,
    borderRadius: tokens.radius.lg,
    backgroundColor: tokens.color.surface,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border,
    marginRight: 12,
  },
  field: { flex: 1, fontSize: 15, color: tokens.color.textPrimary },
  scroll: { paddingBottom: 48 },
  column: {
    width: '100%', maxWidth: MAX_WIDTH, alignSelf: 'center',
    paddingHorizontal: 20, gap: 20, paddingTop: 8,
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
  conflict: {
    backgroundColor: tokens.color.surface,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.accent,
    padding: 16,
  },
  item: { gap: 2 },
  itemTitle: { fontSize: 16, fontWeight: '600', color: tokens.color.textPrimary },
  itemMeta: { fontSize: 13, color: tokens.color.textSecondary },
  amount: { fontSize: 15, color: tokens.color.textPrimary },
  note: { fontSize: 12, color: tokens.color.textTertiary, marginTop: 4 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: tokens.radius.lg,
    borderWidth: StyleSheet.hairlineWidth, borderColor: tokens.color.border,
    backgroundColor: tokens.color.surface,
  },
  chipLabel: { fontSize: 14, color: tokens.color.textPrimary },
  body: { fontSize: 15, color: tokens.color.textPrimary },
});
