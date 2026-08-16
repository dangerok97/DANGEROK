/**
 * Production ORA conversation surface — AI Core runtime only.
 * Real attachments via ContextFile upload API.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '@/src/api/client';
import { RichOraText } from '@/src/components/ora-ai/RichOraText';
import {
  OraComposer,
  PendingAttachment,
  pickOraAttachment,
} from '@/src/components/ora/OraComposer';
import { LocationPermissionSheet } from '@/src/components/ora/LocationPermissionSheet';
import { requestForegroundPosition } from '@/src/location/foregroundGeo';
import { FocusScreen, FOCUS_DECISION_MAX_WIDTH } from '@/src/shell';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { humanizeError } from '@/src/utils/errors';
import type { OraEntryPoint } from '@/src/ora/oraNav';

type ClientAction = { type?: string; reason?: string; refresh?: boolean };

type PendingTurn = {
  id?: string | null;
  status?: string;
  capability?: string | null;
  client_actions?: ClientAction[];
};

type AiCoreRes = {
  ok?: boolean;
  session_id?: string;
  ora_text?: string;
  question?: string | null;
  sources?: Array<{ title?: string; url?: string }>;
  working_hint?: string | null;
  client_actions?: ClientAction[];
  pending_turn?: PendingTurn;
  history?: Array<{
    role?: string;
    text?: string;
    kind?: string;
    message_id?: string;
    meta?: { attachments?: Array<{ name?: string }> };
  }>;
  error?: string;
};

async function fulfillLocationClientActions(
  sessionId: string,
  actions: ClientAction[],
  opts?: {
    onNeedPermission?: () => Promise<boolean>;
  },
): Promise<{ resume: boolean; completed: string[]; failure?: string }> {
  const completed: string[] = [];
  const recordOutcome = async (
    reason: 'denied' | 'unavailable' | 'timeout' | 'position_unavailable' | 'native_unsupported',
  ) => {
    const state =
      reason === 'denied'
        ? 'denied'
        : reason === 'timeout'
          ? 'timeout'
          : reason === 'native_unsupported' || reason === 'unavailable'
            ? 'unavailable'
            : 'position_unavailable';
    await api.locationPermissionOutcome(state).catch(() => null);
  };

  const runGeo = async (refresh: boolean) =>
    requestForegroundPosition(
      refresh
        ? { timeoutMs: 12000, maximumAgeMs: 0 }
        : { timeoutMs: 12000, maximumAgeMs: 60000 },
    );

  const postSignal = async (geo: {
    latitude: number;
    longitude: number;
    accuracyMeters?: number;
  }) => {
    try {
      const res = await api.locationPostSignal({
        latitude: geo.latitude,
        longitude: geo.longitude,
        accuracy_meters: geo.accuracyMeters,
        session_id: sessionId,
        reverse_geocode: true,
      });
      return Boolean(res && (res as { ok?: boolean }).ok !== false);
    } catch {
      return false;
    }
  };

  for (const action of actions) {
    const type = action?.type || '';
    const refresh = Boolean(action?.refresh);
    if (type === 'request_location_permission') {
      const allowed = opts?.onNeedPermission ? await opts.onNeedPermission() : false;
      if (!allowed) {
        // User declined ORA consent sheet — not a browser/device-disabled claim
        await api.locationPermissionOutcome('denied').catch(() => null);
        completed.push(type);
        return { resume: true, completed, failure: 'ora_consent_denied' };
      }
      await api.locationSetPreference('while_using');
      completed.push(type);
      const geo = await runGeo(true);
      if (!geo.ok) {
        await recordOutcome(geo.reason);
        completed.push('request_foreground_location');
        return { resume: true, completed, failure: geo.reason };
      }
      const posted = await postSignal(geo);
      completed.push('request_foreground_location');
      if (!posted) {
        await api.locationPermissionOutcome('unavailable').catch(() => null);
        return { resume: true, completed, failure: 'signal_post_failed' };
      }
      return { resume: true, completed };
    }
    if (type === 'request_foreground_location') {
      // ORA preference already while_using — skip consent sheet; call geolocation directly.
      const geo = await runGeo(refresh);
      if (!geo.ok) {
        await recordOutcome(geo.reason);
        completed.push(type);
        return { resume: true, completed, failure: geo.reason };
      }
      const posted = await postSignal(geo);
      completed.push(type);
      if (!posted) {
        await api.locationPermissionOutcome('unavailable').catch(() => null);
        return { resume: true, completed, failure: 'signal_post_failed' };
      }
      return { resume: true, completed };
    }
  }
  return { resume: false, completed, failure: 'client_action_not_executed' };
}

type Turn = {
  role: 'user' | 'ora';
  text: string;
  messageId?: string;
  sources?: Array<{ title?: string; url?: string }>;
  attachments?: Array<{ name?: string }>;
};

function historyToTurns(
  hist: Array<{
    role?: string;
    text?: string;
    message_id?: string;
    meta?: { attachments?: Array<{ name?: string }> };
  }>,
): Turn[] {
  return hist
    .filter((h) => h.text && (h.role === 'user' || h.role === 'ora'))
    .map((h) => ({
      role: h.role as 'user' | 'ora',
      text: h.text as string,
      messageId: h.message_id,
      attachments: h.meta?.attachments,
    }));
}

function newClientMessageId(): string {
  return `cmsg_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 9)}`;
}

/** Cross-remount idempotency for pending client capability (StrictMode-safe). */
const fulfilledPendingTurns = new Set<string>();

type Props = {
  sessionId?: string | null;
  planId?: string | null;
  objectId?: string | null;
  planItemId?: string | null;
  entryPoint?: OraEntryPoint;
  devHarness?: boolean;
  testID?: string;
};

export function OraConversationScreen({
  sessionId: paramId,
  planId,
  objectId,
  planItemId,
  entryPoint = 'ora',
  devHarness,
  testID = 'ora-conversation',
}: Props) {
  const router = useRouter();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const scrollRef = useRef<ScrollView>(null);

  const [sessionId, setSessionId] = useState<string | null>(paramId || null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [boot, setBoot] = useState(Boolean(paramId));
  const [workingHint, setWorkingHint] = useState<string | null>(null);
  const [micHint, setMicHint] = useState<string | null>(null);
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [locPermVisible, setLocPermVisible] = useState(false);
  const locPermResolver = useRef<((v: boolean) => void) | null>(null);
  const sendingRef = useRef(false);

  const askLocationPreference = useCallback(() => {
    setLocPermVisible(true);
    return new Promise<boolean>((resolve) => {
      locPermResolver.current = resolve;
    });
  }, []);

  const resolveLocationPreference = useCallback((allowed: boolean) => {
    setLocPermVisible(false);
    locPermResolver.current?.(allowed);
    locPermResolver.current = null;
  }, []);

  const applyAiCoreResponse = useCallback(
    async (res: AiCoreRes, sid: string): Promise<AiCoreRes> => {
      let current = res;
      let guard = 0;
      while ((current.client_actions || []).length && sid && guard < 2) {
        guard += 1;
        setWorkingHint('Posizione…');
        const { resume, completed } = await fulfillLocationClientActions(
          sid,
          current.client_actions || [],
          { onNeedPermission: askLocationPreference },
        );
        if (!resume) break;
        current = await api.aiCoreClientResume(sid, { completed });
      }
      return current;
    },
    [askLocationPreference],
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!paramId) {
        setBoot(false);
        return;
      }
      try {
        if (objectId || planId) {
          try {
            await api.lifeOsSessionFocus({
              session_id: String(paramId),
              object_id: objectId ? String(objectId) : undefined,
              plan_id: planId ? String(planId) : undefined,
              plan_item_id: planItemId ? String(planItemId) : undefined,
              event_type: 'object_opened',
            });
          } catch {
            /* soft */
          }
        }
        let res = (await api.aiCoreGet(paramId)) as AiCoreRes;
        if (cancelled) return;
        const sid = res.session_id || paramId;
        setSessionId(sid);
        setTurns(historyToTurns(res.history || []));

        // Home /ora handoff: resume pending client capability without re-sending user text
        const pending = res.pending_turn;
        const actions =
          (pending?.status === 'awaiting_client'
            ? pending.client_actions || res.client_actions
            : res.client_actions) || [];
        const pendingKey = pending?.id || (actions.length ? `actions:${sid}` : null);
        const lockKey = pendingKey ? `${sid}:${pendingKey}` : null;
        if (
          actions.length &&
          lockKey &&
          !fulfilledPendingTurns.has(lockKey) &&
          !cancelled
        ) {
          fulfilledPendingTurns.add(lockKey);
          setBusy(true);
          setWorkingHint(res.working_hint || 'Posizione…');
          try {
            res = await applyAiCoreResponse({ ...res, client_actions: actions }, sid);
            if (cancelled) return;
            if (Array.isArray(res.history) && res.history.length) {
              setTurns(historyToTurns(res.history));
            } else {
              const ora = (res.ora_text || res.question || '').trim();
              const sources = Array.isArray(res.sources) ? res.sources.slice(0, 5) : [];
              if (ora) {
                setTurns((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role === 'ora' && last.text === ora) return prev;
                  return [...prev, { role: 'ora', text: ora, sources }];
                });
              }
            }
          } catch (e: any) {
            fulfilledPendingTurns.delete(lockKey);
            if (!cancelled) setError(humanizeError(e, 'default'));
          } finally {
            if (!cancelled) {
              setBusy(false);
              setWorkingHint(null);
            }
          }
        }
      } catch (e: any) {
        if (!cancelled) setError(humanizeError(e, 'default'));
      } finally {
        if (!cancelled) setBoot(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [paramId, objectId, planId, planItemId, applyAiCoreResponse]);

  const onAttach = useCallback(async () => {
    setError(null);
    setMicHint(null);
    try {
      const picked = await pickOraAttachment();
      if (!picked) return;
      const localId = `loc_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      setAttachments((prev) => [
        ...prev,
        {
          localId,
          name: picked.name,
          mimeType: picked.type,
          status: 'uploading',
        },
      ]);
      try {
        const res = await api.aiCoreFileUpload(picked, sessionId);
        if (!res.ok || !res.file_id) {
          throw new Error(res.message || res.error || 'Upload fallito');
        }
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId
              ? {
                  ...a,
                  fileId: res.file_id,
                  documentId: res.document_id,
                  status: 'ready',
                  textAvailable: Boolean(res.text_available),
                }
              : a,
          ),
        );
      } catch (e: any) {
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId
              ? {
                  ...a,
                  status: 'failed',
                  error: humanizeError(e, 'default'),
                }
              : a,
          ),
        );
      }
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    }
  }, [sessionId]);

  const send = useCallback(async () => {
    const msg = text.trim();
    const ready = attachments.filter((a) => a.status === 'ready' && a.fileId);
    if ((!msg && !ready.length) || busy || sendingRef.current) return;
    if (attachments.some((a) => a.status === 'uploading')) return;
    sendingRef.current = true;
    setBusy(true);
    setError(null);
    setWorkingHint(ready.length ? 'Sto leggendo l’allegato…' : 'Sto pensando…');
    setText('');
    const pendingAttach = ready.map((a) => ({
      file_id: a.fileId!,
      document_id: a.documentId,
      display_name: a.name,
      mime_type: a.mimeType,
    }));
    setAttachments([]);
    const userLine = msg || ready.map((a) => a.name).join(', ');
    const clientMessageId = newClientMessageId();
    setTurns((prev) => [
      ...prev,
      {
        role: 'user',
        text: userLine,
        messageId: clientMessageId,
        attachments: ready.map((a) => ({ name: a.name })),
      },
    ]);
    try {
      let res: AiCoreRes;
      if (!sessionId) {
        // Need a session before attaching file-only; start with text or placeholder
        const startText = msg || `[Allegato: ${ready.map((a) => a.name).join(', ')}]`;
        res = await api.aiCoreStart({
          text: startText,
          origin: entryPoint === 'home' ? 'home' : 'text',
          entry_point: entryPoint,
          plan_id: planId || undefined,
          object_id: objectId || undefined,
        });
        const id = res.session_id;
        setSessionId(id || null);
        if (id && pendingAttach.length) {
          res = await api.aiCoreMessage(id, {
            text: msg || '',
            attachments: pendingAttach,
            client_message_id: clientMessageId,
          });
        }
        if (id) {
          res = await applyAiCoreResponse(res, id);
        }
        if (id && !paramId) {
          const q = new URLSearchParams({
            ...(planId ? { planId: String(planId) } : {}),
            ...(objectId ? { objectId: String(objectId) } : {}),
            entry: entryPoint,
          });
          router.replace(`/ora/${id}?${q.toString()}` as any);
        }
      } else {
        if (ready.length) setWorkingHint('Sto verificando…');
        res = await api.aiCoreMessage(sessionId, {
          text: msg || '',
          attachments: pendingAttach,
          client_message_id: clientMessageId,
        });
        res = await applyAiCoreResponse(res, sessionId);
      }
      if (Array.isArray(res.history) && res.history.length) {
        setTurns(historyToTurns(res.history));
      } else {
        const ora = (res.ora_text || res.question || '').trim();
        const sources = Array.isArray(res.sources) ? res.sources.slice(0, 5) : [];
        if (ora) setTurns((prev) => [...prev, { role: 'ora', text: ora, sources }]);
      }
      requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
    } catch (e: any) {
      setError(humanizeError(e, 'default'));
    } finally {
      sendingRef.current = false;
      setBusy(false);
      setWorkingHint(null);
    }
  }, [
    text,
    attachments,
    busy,
    sessionId,
    router,
    entryPoint,
    planId,
    objectId,
    paramId,
    applyAiCoreResponse,
  ]);

  if (boot) {
    return (
      <FocusScreen>
        <ActivityIndicator color={colors.textPrimary} />
      </FocusScreen>
    );
  }

  return (
    <FocusScreen testID={testID}>
      <LocationPermissionSheet
        visible={locPermVisible}
        onAllow={() => resolveLocationPreference(true)}
        onDeny={() => resolveLocationPreference(false)}
      />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={insets.top + 48}
      >
        <View style={[styles.wrap, { maxWidth: FOCUS_DECISION_MAX_WIDTH }]}>
          {devHarness ? (
            <Text style={[styles.devBanner, { color: colors.textTertiary }]} testID="ora-dev-banner">
              DEV / diagnostica — usa /ora in produzione
            </Text>
          ) : null}
          <ScrollView
            ref={scrollRef}
            style={styles.scroll}
            contentContainerStyle={styles.scrollContent}
            keyboardShouldPersistTaps="handled"
            testID={`${testID}-scroll`}
            onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          >
            {turns.length === 0 ? (
              <Text style={[styles.hint, { color: colors.textSecondary }]}>
                Parla con ORA. Puoi anche allegare un file come prova o contesto.
              </Text>
            ) : null}
            {turns.map((t, i) => (
              <View
                key={t.messageId || `${t.role}-${i}-${t.text.slice(0, 24)}`}
                style={[styles.bubble, t.role === 'user' ? styles.userAlign : styles.oraAlign]}
              >
                {t.attachments?.length ? (
                  <Text style={[styles.attachLabel, { color: colors.textTertiary }]}>
                    {t.attachments.map((a) => a.name).filter(Boolean).join(' · ')}
                  </Text>
                ) : null}
                {t.role === 'ora' ? (
                  <RichOraText
                    text={t.text}
                    color={colors.textPrimary}
                    secondaryColor={colors.textSecondary}
                  />
                ) : (
                  <Text style={[styles.bubbleText, { color: colors.textSecondary }]}>{t.text}</Text>
                )}
                {t.role === 'ora' && t.sources && t.sources.length > 0 ? (
                  <View style={styles.sources} testID={`${testID}-sources`}>
                    {t.sources.map((s, si) => (
                      <Text
                        key={`${s.url || s.title}-${si}`}
                        style={[styles.sourceLine, { color: colors.textSecondary }]}
                        numberOfLines={1}
                      >
                        {s.title || s.url}
                      </Text>
                    ))}
                  </View>
                ) : null}
              </View>
            ))}
            {busy ? (
              <View style={styles.working} testID={`${testID}-working`}>
                <ActivityIndicator color={colors.textPrimary} />
                <Text style={[styles.workingText, { color: colors.textSecondary }]}>
                  {workingHint || 'Sto pensando…'}
                </Text>
              </View>
            ) : null}
            {error ? (
              <Text style={{ color: colors.error, marginTop: 8 }}>{error}</Text>
            ) : null}
            {micHint ? (
              <Text style={[styles.hint, { color: colors.textTertiary, marginTop: 8 }]}>{micHint}</Text>
            ) : null}
          </ScrollView>

          <View style={{ paddingBottom: Math.max(insets.bottom, 8) }}>
            <OraComposer
              value={text}
              onChangeText={setText}
              onSend={() => void send()}
              busy={busy}
              showAttach
              attachments={attachments}
              onAttachPress={() => void onAttach()}
              onRemoveAttachment={(id) =>
                setAttachments((prev) => prev.filter((a) => a.localId !== id))
              }
              onMicPress={() =>
                setMicHint('Voce: digita per ora — stesso motore, niente riconoscimento vocale.')
              }
              testID={`${testID}-composer`}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </FocusScreen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  wrap: { flex: 1, width: '100%', alignSelf: 'center' },
  scroll: { flex: 1 },
  scrollContent: { paddingHorizontal: tokens.spacing.md, paddingTop: 12, paddingBottom: 24 },
  hint: { fontSize: 15, lineHeight: 22 },
  attachLabel: { fontSize: 12, marginBottom: 4 },
  devBanner: { fontSize: 12, paddingHorizontal: 16, paddingTop: 4 },
  bubble: { marginBottom: 14, maxWidth: '92%' },
  userAlign: { alignSelf: 'flex-end' },
  oraAlign: { alignSelf: 'flex-start' },
  bubbleText: { fontSize: 16, lineHeight: 24 },
  sources: { marginTop: 6, gap: 2 },
  sourceLine: { fontSize: 12, lineHeight: 16, opacity: 0.85 },
  working: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12 },
  workingText: { fontSize: 14 },
});
