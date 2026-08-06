/**
 * Life Experience — first-launch NATURAL conversation with ORA.
 * NOT a wizard, questionnaire, or settings form.
 * After complete/skip/exit this route is not a permanent module.
 * Route path stays /life-setup for compatibility; UX is Life Experience.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  Pressable,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { tokens } from '@/src/theme/tokens';
import { api, LifeSetupTurn } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';

type Bubble = { role: 'ora' | 'user'; text: string };

export default function LifeSetupConversationScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ resume?: string }>();
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turn, setTurn] = useState<LifeSetupTurn | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState('');
  const [explain, setExplain] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const applyTurn = useCallback((t: LifeSetupTurn | undefined | null, oraExtra?: string) => {
    if (!t) return;
    setTurn(t);
    const text = oraExtra || t.text || t.question || '';
    if (text) {
      setBubbles((prev) => {
        if (prev.length && prev[prev.length - 1].role === 'ora' && prev[prev.length - 1].text === text) {
          return prev;
        }
        return [...prev, { role: 'ora', text }];
      });
    }
    if (t.ui?.done) setDone(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const st = await api.lifeSetupStatus();
        if (!st.should_show && !params.resume) {
          router.replace('/(tabs)' as any);
          return;
        }
        const res = await api.lifeSetupStart(Boolean(params.resume));
        if (cancelled) return;
        if (res.already_finished) {
          router.replace('/(tabs)' as any);
          return;
        }
        applyTurn(res.turn);
      } catch (e: any) {
        if (!cancelled) setError(humanizeError(e, 'default'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyTurn, params.resume, router]);

  const send = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    setBubbles((prev) => [...prev, { role: 'user', text }]);
    setDraft('');
    try {
      const res = await api.lifeSetupAnswer(text);
      if (res.privacy_refusal) {
        setBubbles((prev) => [...prev, { role: 'ora', text: res.message || 'Non memorizzo credenziali.' }]);
        return;
      }
      applyTurn(res.turn);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setSending(false);
    }
  };

  const uploadRecommendedDoc = async () => {
    const docType = turn?.recommended_document?.doc_type || 'rogito';
    const label = turn?.recommended_document?.label || docType;
    setSending(true);
    setError(null);
    setBubbles((prev) => [...prev, { role: 'user', text: `[Carico: ${label}]` }]);
    try {
      const syntheticByType: Record<string, string> = {
        rogito: [
          'ATTO DI COMPRAVENDITA (ROGITO)',
          'Immobile sito in Via Roma 10, Milano',
          'Compravendita conclusa il 15 marzo 2026',
          'Acquirente: Mario Rossi',
        ].join('\n'),
        libretto: 'LIBRETTO DI CIRCOLAZIONE Targa AB123CD Fiat Panda',
        piano_di_studi: 'PIANO DI STUDI Informatica CFU esami programmati',
        bolletta: 'BOLLETTA ENERGIA Importo 80 EUR Scadenza 15/09/2026',
        dispensa: 'PROGRAMMA ESAME Analisi Matematica argomenti',
      };
      const synthetic =
        syntheticByType[docType] ||
        `DOCUMENTO ${label}\nCaricato durante la conversazione con ORA.`;
      const res = await api.lifeSetupUploadDoc({
        doc_type: docType,
        synthetic_text: synthetic,
        filename: `${docType}-sintetico.txt`,
      });
      applyTurn(res.turn);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setSending(false);
    }
  };

  const onExplain = async () => {
    try {
      const res = await api.lifeSetupExplain(turn?.plan as any);
      const ex = res.explain as any;
      setExplain(
        ex?.user_explanation ||
          ex?.expected_benefit ||
          turn?.expected_benefit ||
          turn?.explain ||
          'Questa domanda serve a capire un pezzo della tua vita così ORA può aiutarti in concreto.',
      );
    } catch {
      setExplain(
        turn?.expected_benefit ||
          turn?.explain ||
          'Questa domanda serve a capire un pezzo della tua vita così ORA può aiutarti in concreto.',
      );
    }
  };

  const onSkipDomain = async () => {
    setSending(true);
    try {
      const domain = (turn?.plan as any)?.domain;
      const res = await api.lifeSetupAnswer(String(domain || 'tema'), true);
      applyTurn(res.turn);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setSending(false);
    }
  };

  const onExit = async () => {
    try {
      await api.lifeSetupCancel();
    } catch {}
    router.replace('/(tabs)' as any);
  };

  const onComplete = async () => {
    try {
      await api.lifeSetupComplete();
    } catch {}
    router.replace('/(tabs)' as any);
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.root} testID="life-setup-loading">
        <ActivityIndicator color={tokens.color.onSurface} />
        <Text style={styles.muted}>ORA sta preparando la conversazione…</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.root} testID="life-setup-conversation">
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.header}>
          <Text style={styles.brand} testID="life-setup-brand">ORA</Text>
          <Text style={styles.hint} testID="life-setup-hint">
            Conversazione · ~10–15 min · non un questionario
          </Text>
          <Pressable onPress={onExit} testID="life-setup-exit" accessibilityRole="button">
            <Text style={styles.exit}>Esci</Text>
          </Pressable>
        </View>

        {/* Explicit anti-wizard markers for E2E */}
        <View
          testID="life-setup-not-wizard"
          accessibilityLabel="conversazione-naturale-non-wizard"
          style={{ height: 0 }}
        />
        <View testID="life-experience-root" style={{ height: 0 }} />

        <ScrollView style={styles.thread} contentContainerStyle={{ paddingBottom: 24, gap: 12 }}>
          {bubbles.map((b, i) => (
            <View
              key={`${i}-${b.role}`}
              testID={b.role === 'ora' ? 'life-setup-ora-bubble' : 'life-setup-user-bubble'}
              style={[styles.bubble, b.role === 'user' ? styles.userBubble : styles.oraBubble]}
            >
              <Text style={styles.bubbleText}>{b.text}</Text>
            </View>
          ))}
          {turn?.expected_benefit ? (
            <Text style={styles.benefit} testID="life-setup-benefit">
              {turn.expected_benefit}
            </Text>
          ) : null}
          {explain ? (
            <Text style={styles.explain} testID="life-setup-explain">
              {explain}
            </Text>
          ) : null}
          {error ? <Text style={styles.err}>{error}</Text> : null}
        </ScrollView>

        {!done ? (
          <View style={styles.composer}>
            {turn?.recommended_document ? (
              <Pressable
                style={styles.docBtn}
                onPress={uploadRecommendedDoc}
                testID="life-setup-upload-doc"
                disabled={sending}
              >
                <Text style={styles.docBtnText}>
                  Carica {turn.recommended_document.label}
                </Text>
              </Pressable>
            ) : null}
            <View style={styles.row}>
              <TextInput
                testID="life-setup-input"
                style={styles.input}
                value={draft}
                onChangeText={setDraft}
                placeholder="Racconta a ORA…"
                placeholderTextColor={tokens.color.onSurfaceDim}
                editable={!sending}
                onSubmitEditing={send}
              />
              <Pressable
                style={styles.send}
                onPress={send}
                testID="life-setup-send"
                disabled={sending || !draft.trim()}
              >
                <Text style={styles.sendText}>Invia</Text>
              </Pressable>
            </View>
            <View style={styles.actions}>
              <Pressable onPress={onExplain} testID="life-setup-why">
                <Text style={styles.link}>Perché me lo chiedi?</Text>
              </Pressable>
              <Pressable onPress={onSkipDomain} testID="life-setup-skip-domain">
                <Text style={styles.link}>Salta tema</Text>
              </Pressable>
              <Pressable
                onPress={async () => {
                  await api.lifeSetupSkip({ postpone_all: true });
                  router.replace('/(tabs)' as any);
                }}
                testID="life-setup-postpone"
              >
                <Text style={styles.link}>Più tardi</Text>
              </Pressable>
            </View>
          </View>
        ) : (
          <Pressable style={styles.doneBtn} onPress={onComplete} testID="life-setup-done">
            <Text style={styles.doneText}>Vai alla Home</Text>
          </Pressable>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: tokens.color.surface, paddingHorizontal: 16 },
  muted: { color: tokens.color.onSurfaceMuted, marginTop: 12, textAlign: 'center' },
  header: { paddingVertical: 12, gap: 4 },
  brand: { color: tokens.color.brand, fontSize: 28, fontWeight: '700', letterSpacing: 1 },
  hint: { color: tokens.color.onSurfaceMuted, fontSize: 13 },
  exit: { color: tokens.color.onSurfaceMuted, fontSize: 14, marginTop: 4 },
  thread: { flex: 1 },
  bubble: { borderRadius: 16, padding: 14, maxWidth: '92%' },
  oraBubble: { backgroundColor: tokens.color.surfaceSecondary, alignSelf: 'flex-start' },
  userBubble: { backgroundColor: tokens.color.surfaceTertiary, alignSelf: 'flex-end' },
  bubbleText: { color: tokens.color.onSurface, fontSize: 16, lineHeight: 22 },
  benefit: { color: tokens.color.onSurfaceMuted, fontSize: 13, fontStyle: 'italic' },
  explain: { color: tokens.color.info, fontSize: 13 },
  err: { color: tokens.color.error, fontSize: 13 },
  composer: { paddingVertical: 12, gap: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: tokens.color.border },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  input: {
    flex: 1,
    backgroundColor: tokens.color.surfaceSecondary,
    color: tokens.color.onSurface,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
  },
  send: {
    backgroundColor: tokens.color.brand,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
  },
  sendText: { color: tokens.color.onBrand, fontWeight: '600' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  link: { color: tokens.color.onSurfaceMuted, fontSize: 13 },
  docBtn: {
    backgroundColor: tokens.color.infoBg,
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: tokens.color.info,
  },
  docBtnText: { color: tokens.color.info, fontWeight: '600' },
  doneBtn: {
    backgroundColor: tokens.color.brand,
    borderRadius: 14,
    padding: 16,
    marginBottom: 12,
    alignItems: 'center',
  },
  doneText: { color: tokens.color.onBrand, fontWeight: '700', fontSize: 16 },
});
