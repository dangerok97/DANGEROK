/**
 * One-question conversational screen for Action Engine.
 * Study flow: chips, multi-select, date text, preview, confirm.
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
  const [multi, setMulti] = useState<string[]>([]);

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
  const preview = (session?.meta?.study_preview || turn?.meta?.preview) as Record<string, unknown> | undefined;

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
        if (t && (!optionId || turn?.input_kind === 'chips_or_text' || turn?.input_kind === 'date')) {
          payload.text = t;
        }
      }
      const res = await ActionEngine.answer(sessionId, payload);
      if (res.ok === false && res.message) {
        setError(res.message);
        if (res.session) setSession(res.session);
        haptic('error');
        return;
      }
      haptic('success');
      setSession(res.session);
      setText('');
      setSelected(null);
      setMulti([]);

      if (res.upload_required) {
        setError(res.message || 'Carica un documento, poi riprendi da Home.');
        // Keep session active — user can open Documents
        return;
      }

      if (res.opened_plan_id) {
        try { await api.refreshHome(); } catch { /* non-blocking */ }
        router.replace(`/study-plan/${res.opened_plan_id}` as any);
        return;
      }

      if (res.completed || res.session?.done) {
        try { await api.refreshHome(); } catch { /* non-blocking */ }
        const planId = (res.plan as any)?.id || res.session?.meta?.study_plan_id;
        if (planId && res.session?.flow === 'study') {
          // Stay on complete screen; CTA can open plan
        }
      }
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      haptic('error');
    } finally {
      setBusy(false);
    }
  };

  const submitMulti = async () => {
    if (!turn) return;
    const values = multi.map((id) => {
      const o = turn.options.find((x) => x.id === id);
      return o?.value !== undefined ? o.value : id;
    });
    // Flatten doc ids; keep upload sentinel
    const flat: unknown[] = [];
    for (const v of values) {
      if (Array.isArray(v)) flat.push(...v);
      else flat.push(v);
    }
    if (flat.includes('__upload__')) {
      await submit('upload', '__upload__');
      return;
    }
    await submit(multi[0] || 'multi', flat.filter((v) => v !== 'none' && v !== 'skip_docs'));
  };

  const onBack = async () => {
    if (!sessionId || busy) return;
    setBusy(true);
    try {
      const res = await api.actionEngineBack(sessionId);
      if (res.session) setSession(res.session);
      haptic('tap');
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  };

  const onCancel = async () => {
    if (!sessionId) return;
    try {
      await api.actionEngineDraft(sessionId);
    } catch { /* ignore */ }
    try { await ActionEngine.cancel(sessionId); } catch { /* ignore */ }
    router.back();
  };

  const onSaveDraft = async () => {
    if (!sessionId) return;
    try {
      await api.actionEngineDraft(sessionId);
      haptic('success');
      router.replace('/(tabs)' as any);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    }
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
    const planId = session.meta?.study_plan_id as string | undefined;
    const googleBanner = session.meta?.google_banner as { message?: string } | undefined;
    return (
      <SafeAreaView style={styles.safe} testID="action-complete">
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.kicker}>FATTO</Text>
          <Text style={styles.title} accessibilityRole="header">{session.title}</Text>
          <Text style={styles.explain}>
            {(session.meta?.next_focus_hint as string)
              || 'Piano creato. Home si aggiorna con sessioni e countdown esame.'}
          </Text>
          {googleBanner?.message ? (
            <Text style={styles.banner} testID="google-banner">{googleBanner.message}</Text>
          ) : null}
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
          {planId ? (
            <Pressable
              style={styles.primaryCta}
              onPress={() => { haptic('tap'); router.replace(`/study-plan/${planId}` as any); }}
              testID="action-open-plan"
            >
              <Text style={styles.primaryCtaText}>Apri piano di studio</Text>
            </Pressable>
          ) : null}
          <Pressable
            style={[styles.primaryCta, planId ? styles.secondaryCta : null]}
            onPress={() => { haptic('tap'); router.replace('/(tabs)' as any); }}
            testID="action-done-home"
          >
            <Text style={[styles.primaryCtaText, planId ? styles.secondaryCtaText : null]}>Torna a Home</Text>
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

  const showText = turn.input_kind === 'text' || turn.input_kind === 'chips_or_text' || turn.input_kind === 'date';
  const isMulti = turn.input_kind === 'multi_chips';
  const isPreview = turn.input_kind === 'preview' || turn.id === 'preview';

  return (
    <SafeAreaView style={styles.safe} testID="action-session">
      <View style={styles.topBar}>
        <Pressable onPress={onCancel} hitSlop={12} accessibilityLabel="Annulla" testID="action-cancel">
          <Ionicons name="close" size={22} color={tokens.color.onSurfaceMuted} />
        </Pressable>
        <Pressable onPress={onBack} hitSlop={12} testID="action-back">
          <Text style={styles.backLink}>Indietro</Text>
        </Pressable>
        <Text style={styles.progress}>{Math.round((session.progress || 0) * 100)}%</Text>
        <Pressable onPress={onSaveDraft} testID="action-save-draft">
          <Text style={styles.backLink}>Salva</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.kicker}>{session.title}</Text>
        <Text style={styles.question} accessibilityRole="header" testID="action-question">
          {turn.question}
        </Text>
        {turn.explanation ? (
          <Text style={styles.explain} testID="action-explanation">{turn.explanation}</Text>
        ) : null}

        {isPreview && preview ? (
          <View style={styles.previewBox} testID="action-preview">
            <Text style={styles.previewLine}>
              {(preview.session_count as number) || 0} sessioni · {String(preview.total_hours || 0)}h ·{' '}
              {String(preview.intensity || '')} · {String(preview.daily_minutes || '')} min/giorno
            </Text>
            <Text style={styles.previewLine}>Esame: {String(preview.exam_label || preview.exam_date || '')}</Text>
            {Array.isArray(preview.sessions_summary) ? (
              (preview.sessions_summary as any[]).slice(0, 6).map((s) => (
                <Text key={s.id} style={styles.previewSession}>
                  · {s.title} ({s.duration_minutes}m)
                </Text>
              ))
            ) : null}
          </View>
        ) : null}

        {!session.meta?.google_connected && turn.id === 'calendar_sync' ? (
          <Text style={styles.banner} testID="google-disconnected-banner">
            Google Calendar non collegato — il piano resta su ORA.
          </Text>
        ) : null}

        <View style={styles.chips} testID="action-chips">
          {turn.options.map((o) => {
            const on = isMulti ? multi.includes(o.id) : selected === o.id;
            return (
              <Pressable
                key={o.id}
                style={[styles.chip, on && styles.chipOn]}
                onPress={() => {
                  haptic('select');
                  if (isMulti) {
                    setMulti((prev) =>
                      prev.includes(o.id) ? prev.filter((x) => x !== o.id) : [...prev, o.id],
                    );
                  } else {
                    setSelected(o.id);
                    if (turn.input_kind === 'chips' || turn.input_kind === 'preview') {
                      submit(o.id, o.value);
                    }
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
            placeholder="Oppure scrivi (es. 15/09/2026)…"
            placeholderTextColor={tokens.color.onSurfaceDim}
            value={text}
            onChangeText={setText}
            editable={!busy}
            testID="action-text"
          />
        ) : null}

        {error ? <Text style={styles.error} testID="action-error">{error}</Text> : null}

        {(showText || isMulti || (turn.input_kind !== 'chips' && turn.input_kind !== 'preview')) ? (
          <Pressable
            style={[styles.primaryCta, busy && { opacity: 0.5 }]}
            disabled={busy || (isMulti ? multi.length === 0 : (!selected && !text.trim() && !turn.allow_skip))}
            onPress={() => {
              if (isMulti) submitMulti();
              else submit(selected || undefined, undefined);
            }}
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
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md, gap: 8,
  },
  progress: { fontSize: 12, color: tokens.color.onSurfaceMuted, fontWeight: '600' },
  backLink: { fontSize: 13, color: tokens.color.onSurfaceMuted, fontWeight: '600' },
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
  secondaryCta: { backgroundColor: tokens.color.surfaceSecondary, borderWidth: 1, borderColor: tokens.color.border },
  secondaryCtaText: { color: tokens.color.onSurface },
  skip: { textAlign: 'center', color: tokens.color.onSurfaceMuted, marginTop: 12, fontSize: 14 },
  error: { color: tokens.color.error, fontSize: 14 },
  backBtn: { marginTop: 16, alignSelf: 'center' },
  backText: { color: tokens.color.onSurface, fontWeight: '600' },
  actionsList: { gap: 8, marginTop: 8 },
  actionRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  actionLabel: { fontSize: 14, color: tokens.color.onSurface },
  previewBox: {
    backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.md,
    padding: 14, gap: 6, borderWidth: 1, borderColor: tokens.color.border,
  },
  previewLine: { fontSize: 14, color: tokens.color.onSurface, fontWeight: '600' },
  previewSession: { fontSize: 13, color: tokens.color.onSurfaceMuted },
  banner: {
    fontSize: 13, color: tokens.color.info, lineHeight: 18,
    backgroundColor: tokens.color.surfaceTertiary, padding: 10, borderRadius: tokens.radius.md,
  },
});
