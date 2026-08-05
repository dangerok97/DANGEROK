/**
 * One-question conversational screen for Action Engine.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { ActionEngine } from '@/src/action-engine';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { api, ActionEngineSession } from '@/src/api/client';

export default function ActionSessionScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const router = useRouter();
  const [session, setSession] = useState<ActionEngineSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await ActionEngine.get(sessionId);
      setSession(res.session);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { load(); }, [load]);

  const turn = session?.current_turn;

  const submit = async (optionId?: string, value?: unknown, skip?: boolean) => {
    if (!sessionId || busy) return;
    setBusy(true);
    setError(null);
    try {
      const payload: { option_id?: string; value?: unknown; text?: string; skip?: boolean } = {};
      if (skip) payload.skip = true;
      else {
        if (optionId) payload.option_id = optionId;
        if (value !== undefined) payload.value = value;
        const t = text.trim();
        if (t && (!optionId || turn?.input_kind === 'chips_or_text')) payload.text = t;
      }
      const res = await ActionEngine.answer(sessionId, payload);
      haptic('success');
      setSession(res.session);
      setText('');
      setSelected(null);
      if (res.completed || res.session?.done) {
        try { await api.refreshHome(); } catch { /* non-blocking */ }
      }
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      haptic('error');
    } finally {
      setBusy(false);
    }
  };

  const onCancel = async () => {
    if (!sessionId) return;
    try { await ActionEngine.cancel(sessionId); } catch { /* ignore */ }
    router.back();
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} testID="action-loading">
        <ActivityIndicator color={tokens.color.onSurface} />
      </SafeAreaView>
    );
  }

  if (!session) {
    return (
      <SafeAreaView style={styles.safe}>
        <Text style={styles.error}>{error || 'Sessione non trovata'}</Text>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backText}>Torna indietro</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  if (session.done || session.status === 'completed') {
    const actions = session.proposed_actions || [];
    return (
      <SafeAreaView style={styles.safe} testID="action-complete">
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.kicker}>FATTO</Text>
          <Text style={styles.title} accessibilityRole="header">{session.title}</Text>
          <Text style={styles.explain}>
            {(session.meta?.next_focus_hint as string)
              || 'Ho aggiornato calendario, promemoria e Brain. Home si aggiorna al prossimo focus.'}
          </Text>
          {actions.length > 0 ? (
            <View style={styles.actionsList}>
              {actions.map((a) => (
                <View key={a.id} style={styles.actionRow}>
                  <Ionicons
                    name={a.status === 'done' ? 'checkmark-circle' : a.status === 'blocked' ? 'alert-circle' : 'ellipse-outline'}
                    size={16}
                    color={a.status === 'done' ? tokens.color.success : tokens.color.onSurfaceMuted}
                  />
                  <Text style={styles.actionLabel}>{a.label}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {session.project?.merge_candidate_id ? (
            <Text style={styles.mergeHint}>
              Esiste già un progetto simile: «{session.project.merge_candidate_title}».
              Puoi unirli più avanti.
            </Text>
          ) : null}
          <Pressable
            style={styles.primaryCta}
            onPress={() => { haptic('tap'); router.replace('/(tabs)' as any); }}
            testID="action-done-home"
          >
            <Text style={styles.primaryCtaText}>Torna a Home</Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    );
  }

  if (!turn) {
    return (
      <SafeAreaView style={styles.safe}>
        <Text style={styles.error}>Nessuna domanda — chiudo la guida.</Text>
        <Pressable
          onPress={() => router.replace('/(tabs)' as any)}
          style={styles.backBtn}
        >
          <Text style={styles.backText}>Home</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const showText = turn.input_kind === 'text' || turn.input_kind === 'chips_or_text';

  return (
    <SafeAreaView style={styles.safe} testID="action-session">
      <View style={styles.topBar}>
        <Pressable onPress={onCancel} hitSlop={12} accessibilityLabel="Annulla" testID="action-cancel">
          <Ionicons name="close" size={22} color={tokens.color.onSurfaceMuted} />
        </Pressable>
        <Text style={styles.progress}>{Math.round((session.progress || 0) * 100)}%</Text>
        <Text style={styles.flow}>{session.flow}</Text>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.kicker}>{session.title}</Text>
        <Text style={styles.question} accessibilityRole="header" testID="action-question">
          {turn.question}
        </Text>
        {turn.explanation ? (
          <Text style={styles.explain}>{turn.explanation}</Text>
        ) : null}
        {session.flow === 'medical' ? (
          <Text style={styles.disclaimer}>
            Solo logistica — ORA non fornisce consigli medici né diagnosi.
          </Text>
        ) : null}

        <View style={styles.chips} testID="action-chips">
          {turn.options.map((o) => {
            const on = selected === o.id;
            return (
              <Pressable
                key={o.id}
                style={[styles.chip, on && styles.chipOn]}
                onPress={() => {
                  haptic('select');
                  setSelected(o.id);
                  if (turn.input_kind === 'chips') {
                    submit(o.id, o.value);
                  }
                }}
                disabled={busy}
                testID={`action-chip-${o.id}`}
              >
                <Text style={[styles.chipText, on && styles.chipTextOn]}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>

        {showText ? (
          <TextInput
            style={styles.input}
            placeholder="Oppure scrivi…"
            placeholderTextColor={tokens.color.onSurfaceDim}
            value={text}
            onChangeText={setText}
            editable={!busy}
            testID="action-text"
          />
        ) : null}

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {(showText || turn.input_kind !== 'chips') ? (
          <Pressable
            style={[styles.primaryCta, busy && { opacity: 0.5 }]}
            disabled={busy || (!selected && !text.trim() && !turn.allow_skip)}
            onPress={() => submit(selected || undefined, undefined)}
            testID="action-next"
          >
            {busy ? (
              <ActivityIndicator color={tokens.color.onBrand} />
            ) : (
              <Text style={styles.primaryCtaText}>Avanti</Text>
            )}
          </Pressable>
        ) : null}

        {turn.allow_skip ? (
          <Pressable onPress={() => submit(undefined, undefined, true)} disabled={busy}>
            <Text style={styles.skip}>Salta</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface, justifyContent: 'center' },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md,
  },
  progress: { fontSize: 12, color: tokens.color.onSurfaceMuted, fontWeight: '600' },
  flow: { fontSize: 11, color: tokens.color.onSurfaceDim, textTransform: 'uppercase' },
  content: {
    padding: tokens.spacing.xl,
    gap: tokens.spacing.md,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
    paddingBottom: 48,
  },
  kicker: {
    fontSize: 12, fontWeight: '700', color: tokens.color.onSurfaceMuted,
    letterSpacing: 1, textTransform: 'uppercase',
  },
  title: { fontSize: 26, fontWeight: '700', color: tokens.color.onSurface, letterSpacing: -0.3 },
  question: {
    fontSize: 28, fontWeight: '700', color: tokens.color.onSurface,
    lineHeight: 34, letterSpacing: -0.4,
  },
  explain: { fontSize: 15, color: tokens.color.onSurfaceMuted, lineHeight: 22 },
  disclaimer: {
    fontSize: 12, color: tokens.color.warning, lineHeight: 18,
    backgroundColor: tokens.color.warningBg, padding: 10, borderRadius: tokens.radius.md,
  },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 12, borderRadius: tokens.radius.md,
    backgroundColor: tokens.color.surfaceSecondary, borderWidth: 1, borderColor: tokens.color.border,
  },
  chipOn: { backgroundColor: tokens.color.brand, borderColor: tokens.color.brand },
  chipText: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600' },
  chipTextOn: { color: tokens.color.onBrand },
  input: {
    marginTop: 8, borderRadius: tokens.radius.md, padding: 14,
    backgroundColor: tokens.color.surfaceTertiary, color: tokens.color.onSurface,
    borderWidth: 1, borderColor: tokens.color.border, fontSize: 15,
  },
  primaryCta: {
    marginTop: 16, backgroundColor: tokens.color.brand, borderRadius: tokens.radius.md,
    paddingVertical: 14, alignItems: 'center',
  },
  primaryCtaText: { color: tokens.color.onBrand, fontWeight: '700', fontSize: 16 },
  skip: { textAlign: 'center', color: tokens.color.onSurfaceMuted, marginTop: 12, fontSize: 14 },
  error: { color: tokens.color.error, fontSize: 14 },
  backBtn: { marginTop: 16, alignSelf: 'center' },
  backText: { color: tokens.color.onSurface, fontWeight: '600' },
  actionsList: { gap: 8, marginTop: 8 },
  actionRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  actionLabel: { fontSize: 14, color: tokens.color.onSurface },
  mergeHint: { fontSize: 13, color: tokens.color.info, lineHeight: 18 },
});
