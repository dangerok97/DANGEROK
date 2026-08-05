/**
 * Study plan detail — progress, sessions, docs, flashcards, Interrogami, actions.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';

import { tokens } from '@/src/theme/tokens';
import { api, StudyPlan } from '@/src/api/client';
import { haptic } from '@/src/utils/haptic';
import { humanizeError } from '@/src/utils/errors';

export default function StudyPlanScreen() {
  const { id, session_id, action } = useLocalSearchParams<{
    id: string; session_id?: string; action?: string;
  }>();
  const router = useRouter();
  const [plan, setPlan] = useState<StudyPlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.studyPlanGet(id);
      setPlan(res.plan);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!id || !session_id || !action || !plan?.id) return;
    let cancelled = false;
    (async () => {
      try {
        await api.studyPlanSessionAction(id, session_id, action as any);
        if (!cancelled) {
          await load();
          await api.refreshHome();
        }
      } catch { /* ignore */ }
    })();
    return () => { cancelled = true; };
    // Deep-link session action once when plan loads
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, session_id, action, plan?.id]);

  const runSession = async (sessionId: string, act: 'start' | 'complete' | 'snooze' | 'skip') => {
    if (!id || busy) return;
    setBusy(true);
    try {
      await api.studyPlanSessionAction(id, sessionId, act);
      haptic('success');
      await load();
      await api.refreshHome();
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      haptic('error');
    } finally {
      setBusy(false);
    }
  };

  const pause = async () => {
    if (!id) return;
    setBusy(true);
    try {
      await api.studyPlanUpdate(id, { status: 'paused' });
      await load();
      await api.refreshHome();
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  };

  const regenerate = async () => {
    if (!id) return;
    setBusy(true);
    try {
      await api.studyPlanUpdate(id, { regenerate_future: true });
      await load();
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!id) return;
    setBusy(true);
    try {
      await api.studyPlanDelete(id);
      await api.refreshHome();
      router.replace('/(tabs)' as any);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setBusy(false);
    }
  };

  const retrySync = async () => {
    if (!id) return;
    try {
      await api.studyPlanSync(id);
      await load();
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} testID="study-plan-loading">
        <ActivityIndicator color={tokens.color.onSurface} />
      </SafeAreaView>
    );
  }

  if (!plan) {
    return (
      <SafeAreaView style={styles.safe}>
        <Text style={styles.error}>{error || 'Piano non trovato'}</Text>
        <Pressable onPress={() => router.back()}><Text style={styles.link}>Indietro</Text></Pressable>
      </SafeAreaView>
    );
  }

  const progress = plan.progress || {};
  const next = progress.next_session as Record<string, unknown> | undefined;
  const sessions = plan.sessions || [];
  const fc = plan.flashcard_document_ids || [];
  const iq = plan.interrogami_document_ids || [];
  const banner = (plan.google_sync as any)?.banner?.message;

  return (
    <SafeAreaView style={styles.safe} testID="study-plan-screen">
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} testID="study-plan-back">
          <Ionicons name="chevron-back" size={22} color={tokens.color.onSurface} />
        </Pressable>
        <Text style={styles.status}>{plan.status}</Text>
      </View>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.kicker}>PIANO DI STUDIO</Text>
        <Text style={styles.title} testID="study-plan-title">{String(plan.exam_name)}</Text>
        <Text style={styles.meta}>
          {String(plan.intensity || '')} · {String(plan.daily_minutes ?? '')} min/giorno ·{' '}
          {String(progress.completed_sessions || 0)}/{String(progress.total_sessions || 0)} sessioni
        </Text>
        {banner ? <Text style={styles.banner} testID="study-plan-google-banner">{banner}</Text> : null}
        {error ? <Text style={styles.error}>{error}</Text> : null}

        {next ? (
          <View style={styles.card} testID="study-plan-next">
            <Text style={styles.cardTitle}>Prossima sessione</Text>
            <Text style={styles.cardBody}>{String(next.title || '')}</Text>
            <View style={styles.row}>
              <Pressable style={styles.btn} onPress={() => runSession(String(next.id), 'start')} testID="session-start">
                <Text style={styles.btnText}>Inizia</Text>
              </Pressable>
              <Pressable style={styles.btnGhost} onPress={() => runSession(String(next.id), 'complete')} testID="session-complete">
                <Text style={styles.btnGhostText}>Completa</Text>
              </Pressable>
              <Pressable style={styles.btnGhost} onPress={() => runSession(String(next.id), 'snooze')} testID="session-snooze">
                <Text style={styles.btnGhostText}>Rimanda</Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        <Text style={styles.section}>Sessioni</Text>
        {sessions.map((s: any) => (
          <View key={s.id} style={styles.sessionRow} testID={`session-${s.id}`}>
            <Text style={styles.sessionTitle}>{s.title}</Text>
            <Text style={styles.sessionMeta}>{s.status} · {s.duration_minutes}m</Text>
          </View>
        ))}

        {(plan.document_ids || []).length > 0 ? (
          <>
            <Text style={styles.section}>Materiali</Text>
            {(plan.document_ids || []).map((docId) => (
              <Pressable
                key={docId}
                onPress={() => router.push(`/document/${docId}` as any)}
                style={styles.linkRow}
                testID={`doc-${docId}`}
              >
                <Text style={styles.link}>Documento {docId.slice(0, 8)}…</Text>
              </Pressable>
            ))}
          </>
        ) : null}

        {fc[0] ? (
          <Pressable
            style={styles.btn}
            onPress={() => router.push(`/document/${fc[0]}?mode=flashcards` as any)}
            testID="open-flashcards"
          >
            <Text style={styles.btnText}>Apri flashcard</Text>
          </Pressable>
        ) : null}
        {iq[0] ? (
          <Pressable
            style={styles.btn}
            onPress={() => router.push(`/document/${iq[0]}?mode=quiz` as any)}
            testID="open-interrogami"
          >
            <Text style={styles.btnText}>Apri Interrogami</Text>
          </Pressable>
        ) : null}

        <Text style={styles.section}>Azioni</Text>
        <View style={styles.rowWrap}>
          <Pressable style={styles.btnGhost} onPress={pause} testID="plan-pause" disabled={busy}>
            <Text style={styles.btnGhostText}>Pausa</Text>
          </Pressable>
          <Pressable style={styles.btnGhost} onPress={regenerate} testID="plan-regenerate" disabled={busy}>
            <Text style={styles.btnGhostText}>Rigenera future</Text>
          </Pressable>
          <Pressable style={styles.btnGhost} onPress={retrySync} testID="plan-sync">
            <Text style={styles.btnGhostText}>Retry sync</Text>
          </Pressable>
          <Pressable style={styles.btnDanger} onPress={remove} testID="plan-delete" disabled={busy}>
            <Text style={styles.btnText}>Elimina</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: tokens.color.surface },
  topBar: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md,
  },
  status: { fontSize: 12, color: tokens.color.onSurfaceMuted, textTransform: 'uppercase' },
  content: { padding: tokens.spacing.xl, gap: 12, paddingBottom: 48 },
  kicker: { fontSize: 12, fontWeight: '700', color: tokens.color.onSurfaceMuted, letterSpacing: 1 },
  title: { fontSize: 28, fontWeight: '700', color: tokens.color.onSurface },
  meta: { fontSize: 14, color: tokens.color.onSurfaceMuted },
  section: { marginTop: 16, fontSize: 13, fontWeight: '700', color: tokens.color.onSurfaceMuted },
  card: {
    backgroundColor: tokens.color.surfaceSecondary, borderRadius: tokens.radius.md,
    padding: 14, gap: 8, borderWidth: 1, borderColor: tokens.color.border,
  },
  cardTitle: { fontSize: 13, fontWeight: '700', color: tokens.color.onSurfaceMuted },
  cardBody: { fontSize: 16, fontWeight: '600', color: tokens.color.onSurface },
  row: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  rowWrap: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  btn: {
    backgroundColor: tokens.color.brand, borderRadius: tokens.radius.md,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  btnText: { color: tokens.color.onBrand, fontWeight: '700' },
  btnGhost: {
    borderWidth: 1, borderColor: tokens.color.border, borderRadius: tokens.radius.md,
    paddingHorizontal: 14, paddingVertical: 10, backgroundColor: tokens.color.surfaceSecondary,
  },
  btnGhostText: { color: tokens.color.onSurface, fontWeight: '600' },
  btnDanger: {
    backgroundColor: tokens.color.error, borderRadius: tokens.radius.md,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  sessionRow: { paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: tokens.color.border },
  sessionTitle: { fontSize: 15, color: tokens.color.onSurface, fontWeight: '600' },
  sessionMeta: { fontSize: 12, color: tokens.color.onSurfaceMuted },
  link: { color: tokens.color.onSurface, fontWeight: '600' },
  linkRow: { paddingVertical: 6 },
  error: { color: tokens.color.error },
  banner: {
    fontSize: 13, color: tokens.color.info, backgroundColor: tokens.color.surfaceTertiary,
    padding: 10, borderRadius: tokens.radius.md,
  },
});
