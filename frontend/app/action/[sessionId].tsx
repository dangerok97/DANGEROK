/**
 * One-question conversational screen for Action Engine — Focus shell chrome.
 * Study flow: chips, multi-select, date text, preview, confirm.
 * Questions/content unchanged; chrome uses FocusScreen + useTheme.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { useTheme } from '@/src/theme/ThemeProvider';
import { ActionEngine } from '@/src/action-engine';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';
import { api, ActionEngineSession } from '@/src/api/client';
import {
  FocusScreen,
  FOCUS_DECISION_MAX_WIDTH,
  actionProgressLabel,
  flowContextLabel,
} from '@/src/shell';

/**
 * Kept for workflow/debug — Prompt 3.1 Focus UI does not render this surface.
 * Slot data remains on the session; presentation chips competed with the question
 * (e.g. noise like "Destinazione: Partenza").
 */
function buildUnderstoodSummary(session: ActionEngineSession): Record<string, string> {
  const fromMeta = (session.meta?.understood_summary || {}) as Record<string, string>;
  if (fromMeta && Object.keys(fromMeta).length) return fromMeta;
  const ent = (session.meta?.intent_entities || {}) as Record<string, unknown>;
  const answers = (session.answers || {}) as Record<string, unknown>;
  const known = (session.meta?.known_slots || {}) as Record<string, unknown>;
  const pick = (...keys: string[]) => {
    for (const k of keys) {
      let v: unknown = known[k] ?? ent[k] ?? answers[k];
      if (v && typeof v === 'object' && v !== null) {
        const o = v as Record<string, unknown>;
        v = o.label ?? o.normalized ?? o.departure_date ?? o.start_date ?? o.return_date ?? o.end_date;
      }
      if (v !== undefined && v !== null && String(v).trim()) return String(v);
    }
    return null;
  };
  const out: Record<string, string> = {};
  const dep = pick('departure_date', 'start_date');
  const dest = pick('destination', 'travel', 'place');
  const ret = pick('return_date', 'end_date');
  const transport = pick('transport');
  if (dep) out.Partenza = dep;
  if (dest) out.Destinazione = dest;
  if (ret) out.Ritorno = ret;
  if (transport) {
    const map: Record<string, string> = { car: 'Auto', train: 'Treno', plane: 'Aereo' };
    out.Trasporto = map[transport] || transport;
  }
  const subj = pick('subject');
  const exam = pick('exam_date');
  if (subj) out.Materia = subj;
  if (exam) out['Data esame'] = exam;
  return out;
}

/** Prompt 3.1: hide Focus understood-summary chips (presentation noise). */
const SHOW_UNDERSTOOD_SUMMARY = false;

export default function ActionSessionScreen() {
  const { sessionId } = useLocalSearchParams<{ sessionId: string }>();
  const router = useRouter();
  const { colors, isDark } = useTheme();
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
  const preview = (
    session?.meta?.travel_preview
    || session?.meta?.study_preview
    || turn?.meta?.preview
  ) as Record<string, unknown> | undefined;

  const progressLabel = useMemo(() => actionProgressLabel(session), [session]);
  const contextLabel = useMemo(() => flowContextLabel(session?.flow), [session?.flow]);

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
        return;
      }

      if (res.opened_plan_id) {
        try { await api.refreshHome(); } catch { /* non-blocking */ }
        router.replace(`/study-plan/${res.opened_plan_id}` as any);
        return;
      }

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

  const submitMulti = async () => {
    if (!turn) return;
    const values = multi.map((id) => {
      const o = turn.options.find((x) => x.id === id);
      return o?.value !== undefined ? o.value : id;
    });
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

  const onSaveDraftAndLeave = async () => {
    if (!sessionId) return;
    try {
      await api.actionEngineDraft(sessionId);
      haptic('success');
      router.replace('/(tabs)' as any);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    }
  };

  /** Single Focus back: push within flow, else soft draft exit. */
  const onChromeBack = async () => {
    const answered = Object.keys(session?.answers || {}).length;
    if (answered > 0) {
      await onBack();
      return;
    }
    await onSaveDraftAndLeave();
  };

  const themed = {
    kicker: { color: colors.textTertiary },
    title: { color: colors.textPrimary },
    question: { color: colors.textPrimary },
    explain: { color: colors.textSecondary },
    error: { color: colors.error },
    chip: {
      backgroundColor: colors.backgroundSecondary,
      borderColor: colors.border,
    },
    chipOn: {
      backgroundColor: colors.accent,
      borderColor: colors.accent,
    },
    chipText: { color: colors.textPrimary },
    chipTextOn: { color: colors.onAccent },
    input: {
      backgroundColor: colors.surface,
      color: colors.textPrimary,
      borderColor: colors.border,
    },
    primaryCta: { backgroundColor: colors.accent },
    primaryCtaText: { color: colors.onAccent },
    secondaryCta: {
      backgroundColor: colors.backgroundSecondary,
      borderColor: colors.border,
    },
    secondaryCtaText: { color: colors.textPrimary },
    skip: { color: colors.textSecondary },
    understoodBox: {
      backgroundColor: colors.backgroundSecondary,
      borderColor: colors.border,
    },
    understoodLine: { color: colors.textSecondary },
    previewBox: {
      backgroundColor: colors.backgroundSecondary,
      borderColor: colors.border,
    },
    previewLine: { color: colors.textPrimary },
    previewSession: { color: colors.textSecondary },
    banner: {
      color: colors.info,
      backgroundColor: colors.surface,
    },
    actionLabel: { color: colors.textPrimary },
  };

  if (loading) {
    return (
      <FocusScreen
        testID="action-loading"
        maxWidth={FOCUS_DECISION_MAX_WIDTH}
        contentStyle={styles.centerContent}
      >
        <ActivityIndicator color={colors.textPrimary} />
      </FocusScreen>
    );
  }

  if (!session) {
    return (
      <FocusScreen
        testID="action-missing"
        maxWidth={FOCUS_DECISION_MAX_WIDTH}
        chrome={{
          leading: 'back',
          onLeadingPress: () => router.back(),
        }}
        contentStyle={styles.centerContent}
      >
        <Text style={[styles.error, themed.error]}>{error || 'Sessione non trovata'}</Text>
        <Pressable onPress={() => router.back()} style={styles.backBtn}>
          <Text style={[styles.backText, { color: colors.textPrimary }]}>Torna indietro</Text>
        </Pressable>
      </FocusScreen>
    );
  }

  if (session.done || session.status === 'completed') {
    const actions = session.proposed_actions || [];
    const studyPlanId = session.meta?.study_plan_id as string | undefined;
    const travelProjectId = session.meta?.travel_project_id as string | undefined;
    const planId = studyPlanId || travelProjectId;
    const googleBanner = session.meta?.google_banner as { message?: string } | undefined;
    const isTravel = session.flow === 'travel';
    return (
      <FocusScreen
        testID="action-complete"
        maxWidth={FOCUS_DECISION_MAX_WIDTH}
        chrome={{
          leading: 'back',
          onLeadingPress: () => router.replace('/(tabs)' as any),
          contextLabel,
        }}
      >
        <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
          <Text style={[styles.kicker, themed.kicker]}>FATTO</Text>
          <Text style={[styles.title, themed.title]} accessibilityRole="header">{session.title}</Text>
          <Text style={[styles.explain, themed.explain]}>
            {(session.meta?.next_focus_hint as string)
              || (isTravel
                ? 'Travel Project creato. Home evolve con countdown e fase viaggio.'
                : 'Piano creato. Home si aggiorna con sessioni e countdown esame.')}
          </Text>
          {googleBanner?.message ? (
            <Text style={[styles.banner, themed.banner]} testID="google-banner">{googleBanner.message}</Text>
          ) : null}
          {actions.length > 0 ? (
            <View style={styles.actionsList}>
              {actions.map((a) => (
                <View key={a.id} style={styles.actionRow}>
                  <Ionicons
                    name={a.status === 'done' ? 'checkmark-circle' : a.status === 'blocked' ? 'alert-circle' : 'ellipse-outline'}
                    size={16}
                    color={a.status === 'done' ? colors.success : colors.textSecondary}
                  />
                  <Text style={[styles.actionLabel, themed.actionLabel]}>{a.label}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {planId ? (
            <Pressable
              style={[styles.primaryCta, themed.primaryCta]}
              onPress={() => {
                haptic('tap');
                if (isTravel && travelProjectId) {
                  router.replace(`/travel-project/${travelProjectId}` as any);
                } else if (studyPlanId) {
                  router.replace(`/study-plan/${studyPlanId}` as any);
                }
              }}
              testID="action-open-plan"
            >
              <Text style={[styles.primaryCtaText, themed.primaryCtaText]}>
                {isTravel ? 'Apri progetto viaggio' : 'Apri piano di studio'}
              </Text>
            </Pressable>
          ) : null}
          <Pressable
            style={[
              styles.primaryCta,
              planId ? [styles.secondaryCta, themed.secondaryCta] : themed.primaryCta,
            ]}
            onPress={() => { haptic('tap'); router.replace('/(tabs)' as any); }}
            testID="action-done-home"
          >
            <Text
              style={[
                styles.primaryCtaText,
                planId ? themed.secondaryCtaText : themed.primaryCtaText,
              ]}
            >
              Torna a Home
            </Text>
          </Pressable>
        </ScrollView>
      </FocusScreen>
    );
  }

  if (!turn) {
    return (
      <FocusScreen
        maxWidth={FOCUS_DECISION_MAX_WIDTH}
        chrome={{
          leading: 'back',
          onLeadingPress: () => router.replace('/(tabs)' as any),
        }}
        contentStyle={styles.centerContent}
      >
        <Text style={[styles.error, themed.error]}>Nessuna domanda — chiudo la guida.</Text>
        <Pressable
          onPress={() => router.replace('/(tabs)' as any)}
          style={styles.backBtn}
        >
          <Text style={[styles.backText, { color: colors.textPrimary }]}>Home</Text>
        </Pressable>
      </FocusScreen>
    );
  }

  const showText = turn.input_kind === 'text' || turn.input_kind === 'chips_or_text' || turn.input_kind === 'date';
  const isMulti = turn.input_kind === 'multi_chips';
  const isPreview = turn.input_kind === 'preview' || turn.id === 'preview';
  const showPrimaryCta =
    showText || isMulti || (turn.input_kind !== 'chips' && turn.input_kind !== 'preview');

  return (
    <FocusScreen
      testID="action-session"
      maxWidth={FOCUS_DECISION_MAX_WIDTH}
      chrome={{
        leading: 'back',
        onLeadingPress: () => { void onChromeBack(); },
        progressLabel,
        contextLabel,
        // Salva only as tertiary when no primary Avanti (chip-only turns)
        trailingLabel: showPrimaryCta ? null : 'Salva',
        onTrailingPress: showPrimaryCta ? undefined : () => { void onSaveDraftAndLeave(); },
      }}
    >
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        {contextLabel ? null : (
          <Text style={[styles.kicker, themed.kicker]}>{session.title}</Text>
        )}
        {SHOW_UNDERSTOOD_SUMMARY
          ? (() => {
              const summary = buildUnderstoodSummary(session);
              const entries = Object.entries(summary);
              if (!entries.length) return null;
              return (
                <View style={[styles.understoodBox, themed.understoodBox]} testID="understood-summary">
                  {entries.map(([label, val]) => (
                    <Text
                      key={label}
                      style={[styles.understoodLine, themed.understoodLine]}
                      testID={`understood-${label.toLowerCase()}`}
                    >
                      {label}: {val}
                    </Text>
                  ))}
                </View>
              );
            })()
          : null}
        <Text style={[styles.question, themed.question]} accessibilityRole="header" testID="action-question">
          {turn.question}
        </Text>
        {turn.explanation ? (
          <Text style={[styles.explain, themed.explain]} testID="action-explanation">{turn.explanation}</Text>
        ) : null}

        {isPreview && preview ? (
          <View style={[styles.previewBox, themed.previewBox]} testID="action-preview">
            {session.flow === 'travel' ? (
              <>
                <Text style={[styles.previewLine, themed.previewLine]}>
                  {String(preview.destination || '')} · {String(preview.period_label || '')}
                </Text>
                <Text style={[styles.previewLine, themed.previewLine]}>
                  {String(preview.transport_label || preview.transport || '')}
                  {preview.companions ? ` · ${preview.companions} pers.` : ''}
                  {preview.calendar_proposed
                    ? ` · ${preview.calendar_event_count || 0} eventi calendario`
                    : ''}
                </Text>
                {(preview.maps as any)?.duration_label || (preview.maps as any)?.distance_km ? (
                  <Text style={[styles.previewLine, themed.previewLine]}>
                    Maps: {(preview.maps as any).distance_km
                      ? `${(preview.maps as any).distance_km} km`
                      : ''}
                    {(preview.maps as any).duration_label
                      ? ` · ${(preview.maps as any).duration_label}`
                      : ''}
                  </Text>
                ) : null}
                {(preview.honesty as any)?.maps ? (
                  <Text style={[styles.previewSession, themed.previewSession]}>
                    {String((preview.honesty as any).maps)}
                  </Text>
                ) : null}
                {Array.isArray(preview.calendar_events_summary) ? (
                  (preview.calendar_events_summary as any[]).map((e) => (
                    <Text key={e.kind} style={[styles.previewSession, themed.previewSession]}>
                      · {e.title}
                    </Text>
                  ))
                ) : null}
              </>
            ) : (
              <>
                <Text style={[styles.previewLine, themed.previewLine]}>
                  {(preview.session_count as number) || 0} sessioni · {String(preview.total_hours || 0)}h ·{' '}
                  {String(preview.intensity || '')} · {String(preview.daily_minutes || '')} min/giorno
                </Text>
                <Text style={[styles.previewLine, themed.previewLine]}>
                  Esame: {String(preview.exam_label || preview.exam_date || '')}
                </Text>
                {Array.isArray(preview.sessions_summary) ? (
                  (preview.sessions_summary as any[]).slice(0, 6).map((s) => (
                    <Text key={s.id} style={[styles.previewSession, themed.previewSession]}>
                      · {s.title} ({s.duration_minutes}m)
                    </Text>
                  ))
                ) : null}
              </>
            )}
          </View>
        ) : null}

        {!session.meta?.google_connected && turn.id === 'calendar_sync' ? (
          <Text style={[styles.banner, themed.banner]} testID="google-disconnected-banner">
            Google Calendar non collegato — il piano resta su ORA.
          </Text>
        ) : null}

        <View style={styles.chips} testID="action-chips">
          {turn.options.map((o) => {
            const on = isMulti ? multi.includes(o.id) : selected === o.id;
            return (
              <Pressable
                key={o.id}
                style={[styles.chip, themed.chip, on && themed.chipOn]}
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
                <Text style={[styles.chipText, themed.chipText, on && themed.chipTextOn]}>{o.label}</Text>
              </Pressable>
            );
          })}
        </View>

        {showText ? (
          <TextInput
            style={[styles.input, themed.input]}
            placeholder="Oppure scrivi (es. 15/09/2026)…"
            placeholderTextColor={colors.placeholder}
            value={text}
            onChangeText={setText}
            editable={!busy}
            keyboardAppearance={isDark ? 'dark' : 'light'}
            testID="action-text"
          />
        ) : null}

        {error ? <Text style={[styles.error, themed.error]} testID="action-error">{error}</Text> : null}

        {showPrimaryCta ? (
          <Pressable
            style={[styles.primaryCta, themed.primaryCta, busy && { opacity: 0.5 }]}
            disabled={busy || (isMulti ? multi.length === 0 : (!selected && !text.trim() && !turn.allow_skip))}
            onPress={() => {
              if (isMulti) submitMulti();
              else submit(selected || undefined, undefined);
            }}
            testID="action-next"
            accessibilityLabel="Continua"
          >
            {busy ? (
              <ActivityIndicator color={colors.onAccent} />
            ) : (
              <Text style={[styles.primaryCtaText, themed.primaryCtaText]}>Continua</Text>
            )}
          </Pressable>
        ) : null}

        {turn.allow_skip ? (
          <Pressable onPress={() => submit(undefined, undefined, true)} disabled={busy}>
            <Text style={[styles.skip, themed.skip]}>Salta</Text>
          </Pressable>
        ) : null}
      </ScrollView>
    </FocusScreen>
  );
}

const styles = StyleSheet.create({
  centerContent: {
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
  },
  content: {
    gap: tokens.spacing.md,
    paddingBottom: 48,
    paddingTop: tokens.spacing.sm,
  },
  understoodBox: {
    gap: 4,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: tokens.radius.md,
    borderWidth: 1,
  },
  understoodLine: {
    fontSize: 13,
    fontWeight: '500',
  },
  kicker: {
    fontSize: 12, fontWeight: '700',
    letterSpacing: 1, textTransform: 'uppercase',
  },
  title: { fontSize: 26, fontWeight: '700', letterSpacing: -0.3 },
  question: {
    fontSize: 28, fontWeight: '700',
    lineHeight: 34, letterSpacing: -0.4,
  },
  explain: { fontSize: 15, lineHeight: 22 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 12, borderRadius: tokens.radius.md,
    borderWidth: 1,
  },
  chipText: { fontSize: 15, fontWeight: '600' },
  input: {
    marginTop: 8, borderRadius: tokens.radius.md, padding: 14,
    borderWidth: 1, fontSize: 15,
  },
  primaryCta: {
    marginTop: 16, borderRadius: tokens.radius.md,
    paddingVertical: 14, alignItems: 'center',
  },
  primaryCtaText: { fontWeight: '700', fontSize: 16 },
  secondaryCta: { borderWidth: 1 },
  skip: { textAlign: 'center', marginTop: 12, fontSize: 14 },
  error: { fontSize: 14 },
  backBtn: { marginTop: 16, alignSelf: 'center' },
  backText: { fontWeight: '600' },
  actionsList: { gap: 8, marginTop: 8 },
  actionRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  actionLabel: { fontSize: 14 },
  previewBox: {
    borderRadius: tokens.radius.md,
    padding: 14, gap: 6, borderWidth: 1,
  },
  previewLine: { fontSize: 14, fontWeight: '600' },
  previewSession: { fontSize: 13 },
  banner: {
    fontSize: 13, lineHeight: 18,
    padding: 10, borderRadius: tokens.radius.md,
  },
});
