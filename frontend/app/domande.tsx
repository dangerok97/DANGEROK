/**
 * Domande per te — solo quelle che ORA sta aspettando adesso.
 *
 *     «4 DA RISPONDERE» ERA UN'ETICHETTA. ADESSO È UNA PORTA.
 *
 * La lista arriva da `/questions/open`, la stessa sorgente che alimenta il
 * riquadro in Home: la dedupe semantica del V3.21.3a vale qui senza doverla
 * rifare — se una fase è stata superata, non compare né lì né qui.
 *
 * Si risponde da questa pagina. La risposta va dove la domanda stava
 * aspettando (il backend sa quale lavoro riprendere), e appena è risolta la
 * riga sparisce: una domanda risposta che resta in lista è esattamente il
 * difetto che questo sprint sta chiudendo.
 */
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { api, type OpenQuestionItem } from '@/src/api/client';
import { OraButton, OraCard } from '@/src/components/ora-ui';
import { NienteQui, PaginaOra } from '@/src/components/pagine/PaginaOra';
import { ora, oraType } from '@/src/theme/oraSurface';
import { humanizeError } from '@/src/utils/errors';

export default function Domande() {
  const [items, setItems] = useState<OpenQuestionItem[]>([]);
  const [errore, setErrore] = useState<string | null>(null);
  const [carico, setCarico] = useState(true);

  const leggi = useCallback(async (silenzioso = false) => {
    if (!silenzioso) setCarico(true);
    try {
      const res = await api.openQuestions();
      setItems(res.items || []);
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

  return (
    <PaginaOra
      titolo="Domande per te"
      sottotitolo={
        carico
          ? 'Sto guardando che cosa sto aspettando…'
          : items.length === 0
            ? 'Non sto aspettando niente da te.'
            : items.length === 1
              ? 'Una cosa su cui ho bisogno della tua opinione.'
              : `${items.length} cose su cui ho bisogno della tua opinione.`
      }
      attiva="index"
      testID="pagina-domande"
    >
      {carico ? (
        <ActivityIndicator color={ora.cta} testID="domande-carico" />
      ) : errore ? (
        <NienteQui testo={errore} testID="domande-errore" />
      ) : items.length === 0 ? (
        <NienteQui
          testo="Quando mi servirà qualcosa che sai solo tu, la troverai qui."
          testID="domande-vuoto"
        />
      ) : (
        items.map((q) => (
          <Domanda key={q.id} q={q} onRisposta={() => void leggi(true)} />
        ))
      )}
    </PaginaOra>
  );
}

function Domanda({ q, onRisposta }: { q: OpenQuestionItem; onRisposta: () => void }) {
  const router = useRouter();
  const [aperta, setAperta] = useState(false);
  const [testo, setTesto] = useState('');
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState<string | null>(null);

  const rispondi = useCallback(
    async (risposta: string) => {
      const pulita = risposta.trim();
      if (!pulita || inCorso) return;
      setInCorso(true);
      setErrore(null);
      try {
        await api.answerQuestion(q.id, pulita, 'home');
        onRisposta();
      } catch (e) {
        setErrore(humanizeError(e));
      } finally {
        setInCorso(false);
      }
    },
    [inCorso, onRisposta, q.id],
  );

  const dismiss = useCallback(async () => {
    if (inCorso) return;
    setInCorso(true);
    setErrore(null);
    try {
      await api.cancelQuestion(q.id);
      onRisposta();
    } catch (e) {
      setErrore(humanizeError(e));
    } finally {
      setInCorso(false);
    }
  }, [inCorso, onRisposta, q.id]);

  return (
    <OraCard style={styles.card} testID={`domanda-${q.id}`}>
      <Text style={[oraType.section, { color: ora.ink }]} accessibilityRole="header" aria-level={2}>
        {q.question}
      </Text>

      {/* Perché ORA la sta chiedendo, con le parole del suo ragionamento. */}
      {q.why_needed ? (
        <Text style={[oraType.body, { color: ora.ink2 }]}>{q.why_needed}</Text>
      ) : null}

      {/* Di che cosa si sta parlando: il lavoro a cui la domanda appartiene. */}
      {q.context_label ? (
        <View style={styles.contesto}>
          <Ionicons name="albums-outline" size={14} color={ora.ink3} />
          <Text style={[oraType.small, { color: ora.ink3 }]} numberOfLines={2}>
            {q.context_label}
          </Text>
        </View>
      ) : null}

      {/*
        Le risposte brevi che la domanda porta con sé, quando bastano due
        parole. Non sono suggerimenti nostri: le scrive chi ha fatto la domanda.
      */}
      {q.answers?.length ? (
        <View style={styles.scorciatoie}>
          {q.answers.map((a) => (
            <Pressable
              key={a.action}
              onPress={() => void rispondi(a.label)}
              disabled={inCorso}
              accessibilityRole="button"
              style={({ pressed }) => [styles.scorciatoia, pressed && { opacity: 0.7 }]}
              testID={`domanda-${q.id}-veloce-${a.action}`}
            >
              <Text style={[oraType.small, { color: ora.deep, fontWeight: '600' }]}>{a.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {aperta ? (
        <View style={styles.rispostaBox}>
          <TextInput
            value={testo}
            onChangeText={setTesto}
            placeholder="Scrivi la tua risposta…"
            placeholderTextColor={ora.ink3}
            multiline
            style={[styles.input, { color: ora.ink, borderColor: ora.hairline }]}
            testID={`domanda-${q.id}-input`}
          />
          <View style={styles.azioni}>
            <OraButton
              label={inCorso ? 'Invio…' : 'Invia risposta'}
              onPress={() => void rispondi(testo)}
              disabled={inCorso || !testo.trim()}
              compact
              testID={`domanda-${q.id}-invia`}
            />
            {/* Rispondere in chat resta possibile: è la stessa domanda. */}
            {q.session_id ? (
              <Pressable
                onPress={() => router.push(`/ora/${encodeURIComponent(q.session_id!)}` as never)}
                accessibilityRole="button"
                style={({ pressed }) => [styles.inChat, pressed && { opacity: 0.7 }]}
                testID={`domanda-${q.id}-in-chat`}
              >
                <Text style={[oraType.small, { color: ora.cta }]}>Apri la conversazione</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : (
        <OraButton
          label="Rispondi"
          icon="create-outline"
          compact
          onPress={() => setAperta(true)}
          testID={`domanda-${q.id}-rispondi`}
        />
      )}

      <Pressable
        onPress={() => void dismiss()}
        disabled={inCorso}
        accessibilityRole="button"
        accessibilityLabel={`Non voglio rispondere: ${q.question}`}
        style={({ pressed }) => [styles.dismiss, pressed && { opacity: 0.7 }]}
        testID={`domanda-${q.id}-rimuovi`}
      >
        <Text style={[oraType.small, { color: ora.ink3 }]}>Non voglio rispondere</Text>
      </Pressable>

      {errore ? (
        <Text style={[oraType.small, { color: ora.attention }]} testID={`domanda-${q.id}-errore`}>
          {errore}
        </Text>
      ) : null}
    </OraCard>
  );
}

const styles = StyleSheet.create({
  card: { gap: 12, padding: 20, alignItems: 'flex-start' },
  contesto: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  scorciatoie: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  scorciatoia: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: ora.radius.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: ora.hairline,
    backgroundColor: ora.surfaceTint,
  },
  rispostaBox: { width: '100%', gap: 10 },
  input: {
    minHeight: 84,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: ora.radius.inner,
    padding: 14,
    fontSize: 15,
    lineHeight: 21,
    backgroundColor: ora.surface,
  },
  azioni: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  inChat: { paddingVertical: 6 },
  dismiss: { paddingVertical: 6 },
});
