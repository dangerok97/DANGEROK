/**
 * Life Experience — conversational first-launch behind the Life Setup Gate.
 * NOT a wizard, questionnaire, or settings form.
 * Home access only via completeLifeSetupGate after a successful lifeSetupComplete.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
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
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { tokens } from '@/src/theme/tokens';
import {
  api,
  API_BASE_URL,
  authToken,
  LifeAreaCompleteness,
  LifeSetupTurn,
  LifeSetupDocumentResult,
  LifeSetupDocumentField,
} from '@/src/api/client';
import { LifeSetupSurface } from '@/src/life-setup/LifeSetupSurface';
import { humanizeError } from '@/src/utils/errors';
import { useAuth } from '@/src/contexts/AuthContext';
import {
  completeLifeSetupGate,
  routeByLifeSetupGate,
  setLocalLifeSetupCompleted,
} from '@/src/life-setup/gate';
import { computeAllowSoftExit, shouldShowSoftExit } from '@/src/life-setup/softExit';
import { requestDevicePosition } from '@/src/life-setup/devicePosition';

type Bubble = { role: 'ora' | 'user'; text: string };

function ThinkingDots() {
  const [n, setN] = useState(1);
  useEffect(() => {
    const id = setInterval(() => setN((v) => (v % 3) + 1), 420);
    return () => clearInterval(id);
  }, []);
  return (
    <Text style={styles.thinkingText} testID="life-setup-thinking">
      ORA sta pensando{'.'.repeat(n)}
    </Text>
  );
}

/** Real Life Experience document flow state — Documents V2 remains the ONLY
 * upload/OCR/storage pipeline; this only tracks attach → poll → consume. */
type DocFlowPhase = 'idle' | 'uploading' | 'attaching' | 'analyzing' | 'result' | 'error';

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_ATTEMPTS = 80; // ~2 minutes of polling before surfacing a soft timeout

function fmtFieldValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

export function LifeSetupConversationScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const params = useLocalSearchParams<{ resume?: string }>();
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [turn, setTurn] = useState<LifeSetupTurn | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState('');
  const [explain, setExplain] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  /**
   * Soft-exit (Esci / Più tardi) only on returning/resume flows.
   * Set from `?resume=` or start.resumed — never from wrap `done` or message count.
   * onExit → force start must NOT flip this to true (still first-run until MLC).
   */
  const [allowSoftExit, setAllowSoftExit] = useState(false);
  /*
    How much of a life ORA understands, refreshed after every turn.

    It is read, never sent: the figure is derived on the server from the
    knowledge it holds, so there is nothing here that could set one. And it is
    an extra — if the read fails the setup carries on without it, because a
    progress bar is not worth a broken first run.
  */
  const [profile, setProfile] = useState<{
    percent: number;
    areas: LifeAreaCompleteness[];
    suggested?: string | null;
  } | null>(null);
  /** Pending city from reverse-geocode — confirm before save. */
  const [pendingLocationCity, setPendingLocationCity] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);

  // --- REAL document upload + AI Document Understanding state ---
  const [docPhase, setDocPhase] = useState<DocFlowPhase>('idle');
  const [docPhaseLabel, setDocPhaseLabel] = useState<string>('');
  const [docId, setDocId] = useState<string | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [documentResult, setDocumentResult] = useState<LifeSetupDocumentResult | null>(null);
  const [resolvedFields, setResolvedFields] = useState<Record<string, 'confirmed' | 'rejected'>>({});
  const [editingFieldKey, setEditingFieldKey] = useState<string | null>(null);
  const [editingFieldValue, setEditingFieldValue] = useState('');
  const pollCancelled = useRef(false);
  const pendingTurnRef = useRef<LifeSetupTurn | null>(null);

  // showEsci / showPostpone — never tie visibility to wrap `done` alone
  const showSoftExit = shouldShowSoftExit({ allowSoftExit, done });

  const refreshProfile = useCallback(async () => {
    try {
      const res = await api.lifeProfileCompleteness();
      if (res?.ok) {
        setProfile({
          percent: res.percent,
          areas: res.areas || [],
          suggested: res.suggested_area_id ?? null,
        });
      }
    } catch {
      // Silent on purpose. Knowing how much ORA knows is not worth
      // interrupting the conversation that is teaching it.
    }
  }, []);

  const applyTurn = useCallback((t: LifeSetupTurn | undefined | null, oraExtra?: string) => {
    if (!t) return;
    // Every turn can have changed what ORA knows — an answer, a subject left
    // for later, a document that just finished processing.
    void refreshProfile();
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
  }, [refreshProfile]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!user?.user_id) {
        if (!cancelled) setLoading(false);
        return;
      }
      try {
        const st = await api.lifeSetupStatus();
        if (cancelled) return;

        // Completed (or disabled) → gate decides Home. Never raw-redirect to tabs.
        const sessStatus =
          st.session && typeof st.session === 'object'
            ? (st.session as { status?: string }).status
            : undefined;
        if (sessStatus === 'completed' || st.enabled === false) {
          await routeByLifeSetupGate(router, user.user_id);
          return;
        }

        // Interrupted/skipped/cancelled: force a new session so user stays in setup.
        // Active/not_started: normal start (resume=true forces when requested).
        const force =
          Boolean(params.resume) ||
          sessStatus === 'interrupted' ||
          sessStatus === 'skipped' ||
          sessStatus === 'cancelled';

        let res = await api.lifeSetupStart(force);
        if (cancelled) return;

        if (res.already_finished) {
          const finishedStatus =
            res.session && typeof res.session === 'object'
              ? (res.session as { status?: string }).status
              : undefined;
          if (finishedStatus === 'completed') {
            await routeByLifeSetupGate(router, user.user_id);
            return;
          }
          // Non-completed terminal — force restart inside Life Setup
          res = await api.lifeSetupStart(true);
          if (cancelled) return;
          if (res.already_finished) {
            await routeByLifeSetupGate(router, user.user_id);
            return;
          }
        }

        // Soft-exit only for resume/returning — not mandatory first incomplete Life Setup.
        setAllowSoftExit(
          computeAllowSoftExit({
            resumeParam: params.resume,
            resumed: Boolean(res.resumed),
          }),
        );
        applyTurn(res.turn);
        const pending = (res as any).pending_document as
          | { document_id: string; doc_type?: string; ready_for_consume?: boolean; message?: string }
          | undefined;
        if (pending?.document_id) {
          setDocId(pending.document_id);
          setBubbles((prev) => [...prev, { role: 'ora', text: pending.message || 'Stavo analizzando un documento…' }]);
          if (pending.ready_for_consume) {
            setDocPhase('analyzing');
            void finishConsumeFlow(pending.document_id);
          } else {
            setDocPhase('analyzing');
            void pollDocumentStatus(pending.document_id);
          }
        }
      } catch (e: any) {
        if (!cancelled) setError(humanizeError(e, 'default'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // finishConsumeFlow/pollDocumentStatus are stable useCallback refs defined
    // below and only invoked here for the one-time pending-document resume.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyTurn, params.resume, router, user?.user_id]);

  const send = async () => {
    const text = draft.trim();
    if (!text || sending || locating) return;
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

  const useCurrentLocation = async () => {
    if (sending || locating || pendingLocationCity) return;
    setLocating(true);
    setError(null);
    setBubbles((prev) => [...prev, { role: 'user', text: 'Usa la mia posizione' }]);
    try {
      const pos = await requestDevicePosition();
      if (!pos) {
        // Permission denied / unavailable — never block; text input continues
        setBubbles((prev) => [
          ...prev,
          {
            role: 'ora',
            text: 'Ok, niente posizione — puoi scrivere pure la città.',
          },
        ]);
        return;
      }
      const res = await api.lifeSetupReverseGeocode(pos.lat, pos.lon);
      if (!res.ok || !res.city) {
        setBubbles((prev) => [
          ...prev,
          {
            role: 'ora',
            text: res.message || 'Non riesco a capire la città da qui — puoi scriverla tu?',
          },
        ]);
        return;
      }
      setPendingLocationCity(res.city);
      setBubbles((prev) => [
        ...prev,
        { role: 'ora', text: res.confirm_prompt || `Sembra che tu sia a ${res.city}. È qui che vivi principalmente?` },
      ]);
    } catch {
      setBubbles((prev) => [
        ...prev,
        { role: 'ora', text: 'Ok, niente posizione — puoi scrivere pure la città.' },
      ]);
      setError(null);
    } finally {
      setLocating(false);
    }
  };

  const confirmPendingLocation = async (confirmed: boolean) => {
    if (!pendingLocationCity || sending) return;
    const city = pendingLocationCity;
    setSending(true);
    setError(null);
    setBubbles((prev) => [...prev, { role: 'user', text: confirmed ? 'Sì' : 'No' }]);
    setPendingLocationCity(null);
    try {
      const res = await api.lifeSetupConfirmLocation(city, confirmed);
      applyTurn(res.turn);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setSending(false);
    }
  };

  // -------------------------------------------------------------------
  // REAL document upload + AI Document Understanding.
  // Documents V2 (`POST /api/documents/upload`) remains the ONLY upload /
  // OCR / storage / base-analysis pipeline. This screen only: opens the
  // real Expo file picker, starts the upload, attaches the resulting
  // document_id to the Life Experience conversation, polls its pipeline
  // status, then asks for the extra "life reasoning" read-out (Gemini
  // document understanding, or an honestly-labeled local fallback).
  // -------------------------------------------------------------------
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

  const pollDocumentStatus = useCallback(async (documentId: string) => {
    pollCancelled.current = false;
    for (let attempt = 0; attempt < POLL_MAX_ATTEMPTS; attempt++) {
      if (pollCancelled.current) return;
      try {
        const st = await api.lifeSetupDocumentStatus(documentId);
        if (pollCancelled.current) return;
        setDocPhaseLabel(st.pipeline_status_label || st.pipeline_status || 'in analisi');
        if (st.ready_for_consume) {
          await finishConsumeFlow(documentId);
          return;
        }
        if (st.failed) {
          setDocPhase('error');
          setDocError('La lettura del documento non è riuscita.');
          return;
        }
      } catch (e: any) {
        if (pollCancelled.current) return;
        setDocPhase('error');
        setDocError(humanizeError(e, 'default'));
        return;
      }
      await sleep(POLL_INTERVAL_MS);
    }
    if (!pollCancelled.current) {
      setDocPhase('error');
      setDocError('Sto ancora leggendo il documento — riprova tra poco (nessun dato perso).');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const finishConsumeFlow = useCallback(async (documentId: string) => {
    try {
      const res = await api.lifeSetupConsumeDocument(documentId);
      if (!res.ok) {
        if (res.error === 'pipeline_not_ready') {
          void pollDocumentStatus(documentId);
          return;
        }
        setDocPhase('error');
        setDocError(
          res.error === 'analysis_failed'
            ? 'La lettura del documento non è riuscita.'
            : humanizeError({ message: res.error } as any, 'default'),
        );
        return;
      }
      setDocumentResult(res.document_result || null);
      setResolvedFields({});
      // Store the replanned turn but apply it only when the user continues,
      // so the Document Result panel is never skipped.
      pendingTurnRef.current = res.turn || null;
      setDocPhase('result');
    } catch (e: any) {
      setDocPhase('error');
      setDocError(humanizeError(e, 'default'));
    }
  }, [pollDocumentStatus]);

  const pickAndUploadDocument = async () => {
    const docType = turn?.recommended_document?.doc_type || 'documento';
    const label = turn?.recommended_document?.label || docType;
    setDocError(null);
    let picked: DocumentPicker.DocumentPickerAsset | undefined;
    try {
      const res = await DocumentPicker.getDocumentAsync({
        multiple: false,
        copyToCacheDirectory: true,
        type: ['application/pdf', 'text/plain', 'image/*'],
      });
      if (res.canceled || !res.assets?.[0]) return;
      picked = res.assets[0];
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
      return;
    }

    setBubbles((prev) => [...prev, { role: 'user', text: `[Carico: ${label} — ${picked!.name}]` }]);
    setDocPhase('uploading');
    setDocPhaseLabel(`Carico ${picked.name}…`);
    try {
      const up = await api.documentUpload({
        uri: picked.uri,
        name: picked.name || `${docType}.pdf`,
        type: picked.mimeType || 'application/octet-stream',
      });
      const uploadedId = up.document?.id;
      if (!uploadedId) throw new Error('Caricamento non riuscito');
      setDocId(uploadedId);

      setDocPhase('attaching');
      setDocPhaseLabel('Collego il documento alla conversazione…');
      const attach = await api.lifeSetupAttachDocument(uploadedId, docType);
      if (!attach.ok) throw new Error(attach.message || 'Impossibile collegare il documento');

      setDocPhase('analyzing');
      setDocPhaseLabel(attach.pipeline_status_label || 'Sto leggendo il documento…');
      if (attach.pipeline_status && ['completed', 'needs_review', 'failed'].includes(attach.pipeline_status)) {
        await finishConsumeFlow(uploadedId);
      } else {
        await pollDocumentStatus(uploadedId);
      }
    } catch (e: any) {
      setDocPhase('error');
      setDocError(humanizeError(e, 'default'));
    }
  };

  const cancelAnalysis = () => {
    pollCancelled.current = true;
    setDocPhase('idle');
    setDocPhaseLabel('');
    // document_id stays attached server-side (pending_document_id) — nothing
    // is lost; reopening the conversation will offer to resume it.
  };

  const retryAnalysis = async () => {
    if (!docId) return;
    setDocError(null);
    setDocPhase('analyzing');
    setDocPhaseLabel('Rimetto in coda il documento…');
    try {
      await api.lifeSetupRetryDocument(docId);
      await pollDocumentStatus(docId);
    } catch (e: any) {
      setDocPhase('error');
      setDocError(humanizeError(e, 'default'));
    }
  };

  const dismissDocumentFlow = async () => {
    if (docId) {
      try {
        await api.lifeSetupDetachDocument(docId);
      } catch {}
    }
    pollCancelled.current = true;
    setDocPhase('idle');
    setDocId(null);
    setDocError(null);
    setDocumentResult(null);
  };

  const continueWithOra = () => {
    setDocPhase('idle');
    setDocumentResult(null);
    setDocId(null);
    setResolvedFields({});
    if (pendingTurnRef.current) {
      applyTurn(pendingTurnRef.current);
      pendingTurnRef.current = null;
    }
  };

  const fieldDomain = () => documentResult?.domain || 'generico';

  const handleConfirmField = async (key: string) => {
    try {
      await api.lifeSetupConfirmField(fieldDomain(), key);
      setResolvedFields((prev) => ({ ...prev, [key]: 'confirmed' }));
    } catch (e: any) {
      setDocError(humanizeError(e, 'default'));
    }
  };

  const handleRejectField = async (key: string) => {
    try {
      await api.lifeSetupRejectField(fieldDomain(), key);
      setResolvedFields((prev) => ({ ...prev, [key]: 'rejected' }));
    } catch (e: any) {
      setDocError(humanizeError(e, 'default'));
    }
  };

  const startEditField = (key: string, currentValue: unknown) => {
    setEditingFieldKey(key);
    setEditingFieldValue(fmtFieldValue(currentValue) === '—' ? '' : fmtFieldValue(currentValue));
  };

  const cancelEditField = () => {
    setEditingFieldKey(null);
    setEditingFieldValue('');
  };

  const saveEditField = async (key: string) => {
    try {
      await api.lifeSetupCorrectField(fieldDomain(), key, editingFieldValue);
      setResolvedFields((prev) => ({ ...prev, [key]: 'confirmed' }));
    } catch (e: any) {
      setDocError(humanizeError(e, 'default'));
    } finally {
      setEditingFieldKey(null);
      setEditingFieldValue('');
    }
  };

  const handleResolveConfirmation = async (key: string, resolution: 'keep_existing' | 'use_new') => {
    try {
      await api.lifeSetupResolveConfirmation(fieldDomain(), key, resolution);
      setResolvedFields((prev) => ({ ...prev, [key]: 'confirmed' }));
    } catch (e: any) {
      setDocError(humanizeError(e, 'default'));
    }
  };

  const confirmAllFields = async () => {
    if (!documentResult) return;
    const toConfirm = (documentResult.dati_da_verificare || []).filter(
      (f) => !f.needs_confirmation && !resolvedFields[f.key],
    );
    for (const f of toConfirm) {
      await handleConfirmField(f.key);
    }
  };

  const openOriginalDocument = async () => {
    const info = documentResult?.documento_originale;
    if (!info?.download_url) return;
    try {
      const token = await authToken.get();
      const res = await fetch(`${API_BASE_URL}${info.download_url}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      if (Platform.OS === 'web') {
        const url = URL.createObjectURL(blob);
        (globalThis as any).window?.open(url, '_blank');
      } else {
        const reader = new FileReader();
        reader.onloadend = () => {
          const dataUri = reader.result as string;
          Linking.openURL(dataUri).catch(() =>
            setDocError('Apertura del documento originale non disponibile su questo dispositivo.'),
          );
        };
        reader.readAsDataURL(blob);
      }
    } catch (e: any) {
      setDocError('Impossibile aprire il documento originale: ' + humanizeError(e, 'default'));
    }
  };

  const confirmDraftEvent = async (eventId?: string) => {
    if (!docId || !eventId) return;
    try {
      await api.documentConfirmEvent(docId, eventId);
      setBubbles((prev) => [...prev, { role: 'ora', text: 'Promemoria salvato su ORA.' }]);
    } catch (e: any) {
      setDocError(humanizeError(e, 'default'));
    }
  };

  const notNowDocument = async () => {
    setSending(true);
    try {
      const res = await api.lifeSetupAnswer('Non ora, magari più tardi');
      applyTurn(res.turn);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setSending(false);
    }
  };

  const preferAnswerInstead = async () => {
    setSending(true);
    try {
      const res = await api.lifeSetupAnswer('Preferisco rispondere a voce invece di caricare un documento');
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
    // Backend interrupt (optional soft-resume signal) — never Home, never gate complete.
    setNotice(null);
    setError(null);
    try {
      await api.lifeSetupCancel();
    } catch {
      // Stay on Life Setup even if cancel fails
    }
    if (user?.user_id) {
      try {
        await setLocalLifeSetupCompleted(user.user_id, false);
      } catch {}
    }
    // Session is terminal after cancel — open a fresh setup turn in-place (still pre-Home).
    // Force start creates a NEW session without resumed=true; do NOT set allowSoftExit
    // from that response (first-run incomplete stays without Esci unless ?resume=1).
    try {
      const res = await api.lifeSetupStart(true);
      if (!res.already_finished) {
        setBubbles([]);
        setDone(false);
        setExplain(null);
        setDocPhase('idle');
        setDocumentResult(null);
        // Keep allowSoftExit only if route still has resume; never promote from force start.
        setAllowSoftExit(
          computeAllowSoftExit({
            resumeParam: params.resume,
            resumed: false,
          }),
        );
        applyTurn(res.turn);
      }
    } catch {
      // Keep screen; user can reopen app — gate still blocks Home
    }
    setNotice(
      'Ok, restiamo qui. ORA ha bisogno di un minimo di contesto prima di iniziare — quando vuoi, riprendiamo.',
    );
  };

  const onPostpone = async () => {
    // postponed !== completed — do not terminal-skip to Home.
    setNotice(
      'Va bene. Quando sei pronto, continuiamo da qui: mi serve ancora un po’ di contesto per aiutarti davvero.',
    );
    setError(null);
    if (user?.user_id) {
      try {
        await setLocalLifeSetupCompleted(user.user_id, false);
      } catch {}
    }
  };

  const onComplete = async () => {
    if (!user?.user_id || completing) return;
    setCompleting(true);
    setError(null);
    setNotice(null);
    try {
      const done = await api.lifeSetupComplete();
      if (!done.ok) {
        setError(humanizeError({ message: 'complete_failed' } as any, 'default'));
        return;
      }
      await completeLifeSetupGate(user.user_id);
      await routeByLifeSetupGate(router, user.user_id);
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      setCompleting(false);
    }
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
            Prima conversazione con ORA
          </Text>
          {/* Esci only on resume/returning (!allowSoftExit hides first-run); backend cancel remains */}
          {showSoftExit ? (
            <Pressable onPress={onExit} testID="life-setup-exit" accessibilityRole="button">
              <Text style={styles.exit}>Esci</Text>
            </Pressable>
          ) : null}
        </View>

        {/* Explicit anti-wizard markers for E2E */}
        <View
          testID="life-setup-not-wizard"
          accessibilityLabel="conversazione-naturale-non-wizard"
          style={{ height: 0 }}
        />
        <View testID="life-experience-root" style={{ height: 0 }} />

        <ScrollView
          style={styles.thread}
          contentContainerStyle={{ paddingBottom: 24, gap: 16, paddingHorizontal: 16 }}
        >
          {/*
            The conversation is the middle of a surface, not the whole screen.
            Everything the shell adds is context — who is asking, what part of
            your life this is, what else exists, that you can leave — and none
            of it can be typed into.
          */}
          <LifeSetupSurface
            percent={profile?.percent ?? 0}
            areas={profile?.areas ?? []}
            currentAreaId={profile?.suggested ?? null}
            atTheStart={!bubbles.some((b) => b.role === 'user')}
            onSkipArea={onSkipDomain}
            onLeave={onPostpone}
          >
          {bubbles.map((b, i) => (
            <View
              key={`${i}-${b.role}`}
              testID={b.role === 'ora' ? 'life-setup-ora-bubble' : 'life-setup-user-bubble'}
              style={[styles.bubble, b.role === 'user' ? styles.userBubble : styles.oraBubble]}
            >
              <Text style={styles.bubbleText}>{b.text}</Text>
            </View>
          ))}
          {(sending || locating) && !pendingLocationCity ? (
            <View style={[styles.bubble, styles.oraBubble, styles.thinkingBubble]} testID="life-setup-thinking-bubble">
              <ThinkingDots />
            </View>
          ) : null}
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
          {notice ? (
            <Text style={styles.notice} accessibilityLiveRegion="polite" testID="life-setup-notice">
              {notice}
            </Text>
          ) : null}
          {error ? <Text style={styles.err}>{error}</Text> : null}

          {/* Upload / analysis progress — real Documents V2 pipeline, never a fake spinner */}
          {docPhase === 'uploading' || docPhase === 'attaching' || docPhase === 'analyzing' ? (
            <View style={styles.docProgress} testID="life-setup-doc-progress">
              <ActivityIndicator color={tokens.color.info} />
              <Text style={styles.docProgressText}>{docPhaseLabel || 'Sto elaborando il documento…'}</Text>
              <Pressable onPress={cancelAnalysis} testID="life-setup-doc-cancel">
                <Text style={styles.link}>Annulla</Text>
              </Pressable>
            </View>
          ) : null}

          {docPhase === 'error' ? (
            <View style={styles.docError} testID="life-setup-doc-error">
              <Text style={styles.err}>{docError}</Text>
              <View style={styles.row}>
                <Pressable onPress={retryAnalysis} testID="life-setup-doc-retry">
                  <Text style={styles.link}>Riprova</Text>
                </Pressable>
                <Pressable onPress={dismissDocumentFlow} testID="life-setup-doc-dismiss">
                  <Text style={styles.link}>Continua senza questo documento</Text>
                </Pressable>
              </View>
            </View>
          ) : null}

          {/* Document Result — "Cosa ho capito / Dati trovati / Dati da verificare /
             Cosa posso fare / Documento originale". Never raw JSON, never empty fields. */}
          {docPhase === 'result' && documentResult ? (
            <View style={styles.docResult} testID="life-setup-doc-result">
              {!documentResult.ai_used ? (
                <Text style={styles.docResultBadge}>
                  Analisi locale — Gemini non disponibile in questo momento
                </Text>
              ) : null}

              <Text style={styles.docResultTitle}>Cosa ho capito</Text>
              <Text style={styles.docResultText}>{documentResult.cosa_ho_capito || 'Documento ricevuto.'}</Text>

              {documentResult.dati_trovati?.length ? (
                <>
                  <Text style={styles.docResultTitle}>Dati trovati</Text>
                  {documentResult.dati_trovati.map((f: LifeSetupDocumentField) => (
                    <View key={f.key} style={styles.fieldRow}>
                      <Text style={styles.fieldLabel}>{f.label}</Text>
                      <Text style={styles.fieldValue}>{fmtFieldValue(f.value)}</Text>
                    </View>
                  ))}
                </>
              ) : null}

              {documentResult.dati_da_verificare?.length ? (
                <>
                  <Text style={styles.docResultTitle}>Dati da verificare</Text>
                  {documentResult.dati_da_verificare.map((f: LifeSetupDocumentField) => {
                    const resolved = resolvedFields[f.key];
                    if (resolved) {
                      return (
                        <Text key={f.key} style={styles.fieldResolved}>
                          {f.label}: {resolved === 'confirmed' ? 'confermato' : 'rifiutato'}
                        </Text>
                      );
                    }
                    if (f.needs_confirmation) {
                      return (
                        <View key={f.key} style={styles.conflictRow}>
                          <Text style={styles.fieldLabel}>{f.label}</Text>
                          <Text style={styles.fieldValue}>
                            Avevi: {fmtFieldValue(f.existing_value)} · Trovato ora: {fmtFieldValue(f.new_value)}
                          </Text>
                          <View style={styles.row}>
                            <Pressable onPress={() => handleResolveConfirmation(f.key, 'use_new')}>
                              <Text style={styles.link}>Usa il nuovo</Text>
                            </Pressable>
                            <Pressable onPress={() => handleResolveConfirmation(f.key, 'keep_existing')}>
                              <Text style={styles.link}>Mantieni quello che avevo</Text>
                            </Pressable>
                          </View>
                        </View>
                      );
                    }
                    if (editingFieldKey === f.key) {
                      return (
                        <View key={f.key} style={styles.fieldRow} testID={`life-setup-field-edit-${f.key}`}>
                          <Text style={styles.fieldLabel}>{f.label}</Text>
                          <TextInput
                            testID={`life-setup-field-edit-input-${f.key}`}
                            style={styles.editInput}
                            value={editingFieldValue}
                            onChangeText={setEditingFieldValue}
                            placeholderTextColor={tokens.color.onSurfaceDim}
                            autoFocus
                          />
                          <View style={styles.row}>
                            <Pressable onPress={() => saveEditField(f.key)} testID={`life-setup-field-save-${f.key}`}>
                              <Text style={styles.link}>Salva</Text>
                            </Pressable>
                            <Pressable onPress={cancelEditField}>
                              <Text style={styles.link}>Annulla</Text>
                            </Pressable>
                          </View>
                        </View>
                      );
                    }
                    return (
                      <View key={f.key} style={styles.fieldRow} testID={`life-setup-field-${f.key}`}>
                        <Text style={styles.fieldLabel}>{f.label}</Text>
                        <Text style={styles.fieldValue}>{fmtFieldValue(f.value)}</Text>
                        <View style={styles.row}>
                          <Pressable onPress={() => handleConfirmField(f.key)} testID={`life-setup-field-confirm-${f.key}`}>
                            <Text style={styles.link}>Conferma</Text>
                          </Pressable>
                          <Pressable onPress={() => startEditField(f.key, f.value)} testID={`life-setup-field-edit-btn-${f.key}`}>
                            <Text style={styles.link}>Modifica</Text>
                          </Pressable>
                          <Pressable onPress={() => handleRejectField(f.key)} testID={`life-setup-field-reject-${f.key}`}>
                            <Text style={styles.link}>Rifiuta</Text>
                          </Pressable>
                        </View>
                      </View>
                    );
                  })}
                  <Pressable onPress={confirmAllFields} testID="life-setup-doc-confirm-all">
                    <Text style={styles.link}>Conferma tutto</Text>
                  </Pressable>
                </>
              ) : null}

              {documentResult.cosa_posso_fare?.length ? (
                <>
                  <Text style={styles.docResultTitle} testID="life-setup-doc-actions">
                    Cosa posso fare
                  </Text>
                  {documentResult.cosa_posso_fare.map((a, i) => (
                    <Text
                      key={`${a.action_type}-${i}`}
                      style={styles.docResultText}
                      testID={`life-setup-doc-action-${i}`}
                    >
                      • {a.title}
                      {a.beneficio ? ` — ${a.beneficio}` : a.description ? ` — ${a.description}` : ''}
                    </Text>
                  ))}
                </>
              ) : null}

              {documentResult.draft_events?.length ? (
                <>
                  <Text style={styles.docResultTitle} testID="life-setup-doc-deadlines">
                    Scadenze trovate
                  </Text>
                  {documentResult.draft_events.map((ev, i) => (
                    <View key={ev.event_id || i} style={styles.fieldRow} testID={`life-setup-draft-event-${i}`}>
                      <Text style={styles.fieldLabel}>{ev.title}</Text>
                      <Text style={styles.fieldValue}>{ev.start_datetime}</Text>
                      <Pressable
                        onPress={() => confirmDraftEvent(ev.event_id)}
                        testID={`life-setup-confirm-draft-event-${i}`}
                      >
                        <Text style={styles.link}>Salva promemoria su ORA</Text>
                      </Pressable>
                    </View>
                  ))}
                </>
              ) : null}

              <View style={styles.actions}>
                <Pressable onPress={openOriginalDocument} testID="life-setup-doc-open-original">
                  <Text style={styles.link}>Apri documento originale</Text>
                </Pressable>
                <Pressable onPress={onExplain} testID="life-setup-doc-explain">
                  <Text style={styles.link}>Chiedi spiegazione</Text>
                </Pressable>
              </View>
              <Pressable style={styles.docBtn} onPress={continueWithOra} testID="life-setup-doc-continue">
                <Text style={styles.docBtnText}>Continua con ORA</Text>
              </Pressable>
            </View>
          ) : null}
          </LifeSetupSurface>
        </ScrollView>

        {!done ? (
          <View style={styles.composer}>
            {pendingLocationCity ? (
              <View style={styles.actions} testID="life-setup-location-confirm">
                <Pressable
                  onPress={() => confirmPendingLocation(true)}
                  disabled={sending}
                  testID="life-setup-location-yes"
                >
                  <Text style={styles.link}>Sì</Text>
                </Pressable>
                <Pressable
                  onPress={() => confirmPendingLocation(false)}
                  disabled={sending}
                  testID="life-setup-location-no"
                >
                  <Text style={styles.link}>No</Text>
                </Pressable>
              </View>
            ) : null}
            {turn?.actions?.some((a) => a.id === 'use_current_location') &&
            !pendingLocationCity &&
            docPhase === 'idle' ? (
              <Pressable
                onPress={useCurrentLocation}
                disabled={sending || locating}
                testID="life-setup-use-location"
              >
                <Text style={styles.link}>
                  {turn.actions.find((a) => a.id === 'use_current_location')?.label ||
                    'Usa la mia posizione'}
                </Text>
              </Pressable>
            ) : null}
            {turn?.recommended_document && docPhase === 'idle' ? (
              <>
                <Pressable
                  style={styles.docBtn}
                  onPress={pickAndUploadDocument}
                  testID="life-setup-upload-doc"
                  disabled={sending || locating}
                >
                  <Text style={styles.docBtnText}>
                    Carica {turn.recommended_document.label}
                  </Text>
                </Pressable>
                <View style={styles.actions}>
                  <Pressable
                    onPress={notNowDocument}
                    disabled={sending || locating}
                    testID="life-setup-doc-not-now"
                  >
                    <Text style={styles.link}>Non ora</Text>
                  </Pressable>
                  <Pressable
                    onPress={preferAnswerInstead}
                    disabled={sending || locating}
                    testID="life-setup-doc-prefer-answer"
                  >
                    <Text style={styles.link}>Preferisco rispondere</Text>
                  </Pressable>
                </View>
              </>
            ) : null}
            <View style={styles.row}>
              <TextInput
                testID="life-setup-input"
                style={styles.input}
                value={draft}
                onChangeText={setDraft}
                placeholder="Racconta a ORA…"
                placeholderTextColor={tokens.color.onSurfaceDim}
                editable={!sending && !locating}
                onSubmitEditing={send}
              />
              <Pressable
                style={[styles.send, (sending || locating || !draft.trim()) && { opacity: 0.55 }]}
                onPress={send}
                testID="life-setup-send"
                disabled={sending || locating || !draft.trim()}
              >
                <Text style={styles.sendText}>Invia</Text>
              </Pressable>
            </View>
            <View style={styles.actions}>
              <Pressable onPress={onExplain} disabled={sending || locating} testID="life-setup-why">
                <Text style={styles.link}>Perché me lo chiedi?</Text>
              </Pressable>
              {/*
                Skipping the subject lives on the area card now, where the
                subject is named. Two links for one action, in two different
                vocabularies, made the person work out whether they were the
                same thing.
              */}
              {/* Più tardi only on resume/returning; backend postpone can remain */}
              {showSoftExit ? (
                <Pressable
                  onPress={onPostpone}
                  disabled={sending || locating}
                  testID="life-setup-postpone"
                >
                  <Text style={styles.link}>Più tardi</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        ) : (
          <View style={styles.doneWrap}>
            {/*
              Not "setup completato". The profile is at whatever it is at, and
              a person who told ORA three things has finished their first
              conversation, not filled in a form. Saying otherwise would either
              flatter them or scold them, and both are lies about a number.
            */}
            <Text style={styles.doneNote} testID="life-setup-done-note">
              {profile
                ? `ORA ha un buon punto di partenza: conosce il ${profile.percent}% di ciò che può aiutarti. Puoi aggiungere il resto quando vuoi.`
                : 'ORA ha un buon punto di partenza. Puoi aggiungere il resto quando vuoi.'}
            </Text>
          <Pressable
            style={[styles.doneBtn, completing && { opacity: 0.55 }]}
            onPress={onComplete}
            disabled={completing}
            accessibilityState={{ busy: completing, disabled: completing }}
            testID="life-setup-done"
          >
            {completing ? (
              <ActivityIndicator color={tokens.color.onBrand} />
            ) : (
              <Text style={styles.doneText}>
                {turn?.actions?.find((a) => a.id === 'done')?.label || 'Entra in ORA'}
              </Text>
            )}
          </Pressable>
          </View>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  doneWrap: { paddingHorizontal: 16, paddingBottom: 12, gap: 10 },
  doneNote: { fontSize: 13, lineHeight: 19, color: tokens.color.onSurfaceMuted },
  progressWrap: { paddingHorizontal: 16, paddingBottom: 12 },
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
  thinkingBubble: { opacity: 0.85 },
  thinkingText: {
    color: tokens.color.onSurfaceMuted,
    fontSize: 14,
    fontStyle: 'italic',
    letterSpacing: 0.2,
  },
  benefit: { color: tokens.color.onSurfaceMuted, fontSize: 13, fontStyle: 'italic' },
  explain: { color: tokens.color.info, fontSize: 13 },
  notice: { color: tokens.color.onSurfaceMuted, fontSize: 13 },
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
  docProgress: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: 12,
    padding: 12,
  },
  docProgressText: { color: tokens.color.onSurfaceMuted, fontSize: 13, flex: 1 },
  docError: {
    backgroundColor: tokens.color.errorBg,
    borderRadius: 12,
    padding: 12,
    gap: 8,
  },
  docResult: {
    backgroundColor: tokens.color.surfaceSecondary,
    borderRadius: 16,
    padding: 16,
    gap: 10,
  },
  docResultBadge: {
    color: tokens.color.warning,
    fontSize: 12,
    fontWeight: '600',
  },
  docResultTitle: { color: tokens.color.onSurface, fontSize: 15, fontWeight: '700', marginTop: 6 },
  docResultText: { color: tokens.color.onSurfaceMuted, fontSize: 14, lineHeight: 20 },
  fieldRow: {
    backgroundColor: tokens.color.surfaceTertiary,
    borderRadius: 10,
    padding: 10,
    gap: 4,
  },
  conflictRow: {
    backgroundColor: tokens.color.warningBg,
    borderRadius: 10,
    padding: 10,
    gap: 4,
    borderWidth: 1,
    borderColor: tokens.color.warning,
  },
  fieldLabel: { color: tokens.color.onSurface, fontSize: 13, fontWeight: '600' },
  editInput: {
    backgroundColor: tokens.color.surfaceQuaternary,
    color: tokens.color.onSurface,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    fontSize: 13,
  },
  fieldValue: { color: tokens.color.onSurfaceMuted, fontSize: 13 },
  fieldResolved: { color: tokens.color.success, fontSize: 13 },
});
