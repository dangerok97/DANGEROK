/**
 * ORA — where the user reasons, clarifies and decides with ORA.
 *
 * Home is what needs attention, the Workspace is where a goal gets advanced,
 * and this is where the two get talked through. So the surface is built around
 * one promise: a conversation opened from somewhere already knows where it came
 * from, and the user never has to re-explain it.
 *
 * The runtime is untouched — AI Core start/message/get, client capability
 * resume, attachment upload and binding, session focus, idempotent message ids.
 * What changed is the surface: the user speaks in a small aside, ORA answers as
 * open editorial text rather than a chat balloon, and the context that opened
 * the thread is stated once at the top instead of being lost in a URL.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api, type AgentNeed, type HomeOpportunity } from '@/src/api/client';
import {
  OraComposer,
  PendingAttachment,
  pickOraAttachment,
} from '@/src/components/ora/OraComposer';
import { LocationPermissionSheet } from '@/src/components/ora/LocationPermissionSheet';
import { requestForegroundPosition } from '@/src/location/foregroundGeo';
import { FocusScreen } from '@/src/shell';
import type { OraNavigationOption } from '@/src/components/ora/OraTurns';
import { useTheme } from '@/src/theme/ThemeProvider';
import { tokens } from '@/src/theme/tokens';
import { buildGoalWorkspaceHref, type OraEntryPoint } from '@/src/ora/oraNav';
import { oraErrorMessage, useOraContext } from './conversationContext';
import {
  OraContextOpening,
  OraEmpty,
  OraError,
  OraHeader,
  OraNeedOpening,
  OraRaisedOpening,
  OraWorking,
} from './OraChrome';
import { OraTurns, type Turn } from './OraTurns';

/** Conversation reading width — long reasoning stays legible, never full-bleed. */
const READING_MAX_WIDTH = 720;

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

/**
 * Evidence for the newest answer, kept across the remount that follows session
 * creation.
 *
 * The runtime reports sources next to the answer it has just produced; it does
 * not store them per turn, and `aiCoreGet` cannot return them. Creating a
 * session replaces the URL, which remounts this screen and reloads history —
 * so without somewhere to keep them, the FONTI block appeared for a few
 * milliseconds and was then overwritten by a history that has no idea they
 * existed. Matched back on the answer text, so evidence can never end up
 * attached to a different reply.
 */
const lastSources = new Map<string, { text: string; sources: OraSourceRef[] }>();
/**
 * The same for the map apps, and for the same reason.
 *
 * History is the authority on what was said and carries neither sources nor
 * navigation options, so a turn rebuilt from it loses both. Losing buttons is
 * worse than losing citations: the sentence still ends "con quale app vuoi
 * navigare?" and there is now nothing to answer it with.
 */
const lastNavigation = new Map<string, { text: string; navigation: OraNavigationOption[] }>();

type OraSourceRef = { title?: string; url?: string };

function rememberSources(sessionId: string | null, turns: Turn[]): void {
  if (!sessionId) return;
  const last = [...turns].reverse().find((t) => t.role === 'ora');
  if (last?.sources?.length) {
    lastSources.set(sessionId, { text: last.text, sources: last.sources });
  }
  if (last?.navigation?.length) {
    lastNavigation.set(sessionId, { text: last.text, navigation: last.navigation });
  }
}

/** Hold what the last live answer carried, keyed on its own text. */
function rememberExtras(
  sessionId: string | null,
  text: string,
  sources: OraSourceRef[],
  navigation: OraNavigationOption[],
): void {
  if (!sessionId || !text.trim()) return;
  if (sources.length) lastSources.set(sessionId, { text, sources });
  if (navigation.length) lastNavigation.set(sessionId, { text, navigation });
}

function withRememberedSources(sessionId: string | null, turns: Turn[]): Turn[] {
  if (!sessionId) return turns;
  const idx = turns.map((t) => t.role).lastIndexOf('ora');
  if (idx < 0) return turns;
  let out = turns;

  const heldSources = lastSources.get(sessionId);
  // Matched on the answer text, so evidence can never end up attached to a
  // different reply.
  if (
    heldSources &&
    !turns[idx].sources?.length &&
    turns[idx].text.trim() === heldSources.text.trim()
  ) {
    out = [...out];
    out[idx] = { ...out[idx], sources: heldSources.sources };
  }

  const heldNav = lastNavigation.get(sessionId);
  if (
    heldNav &&
    !out[idx].navigation?.length &&
    out[idx].text.trim() === heldNav.text.trim()
  ) {
    out = out === turns ? [...turns] : out;
    out[idx] = { ...out[idx], navigation: heldNav.navigation };
  }
  return out;
}

/**
 * Focus already told to the backend, keyed by the exact tuple.
 *
 * Creating a session records focus, and the URL replace that follows remounts
 * the screen on the new id — which would record the identical focus again, and
 * twice more under StrictMode. The write is idempotent, but sending it four
 * times for one hand-off is noise on the wire.
 */
const announcedFocus = new Set<string>();

async function announceFocus(args: {
  sessionId: string;
  planId?: string | null;
  objectId?: string | null;
  planItemId?: string | null;
}): Promise<void> {
  const key = [args.sessionId, args.planId || '', args.objectId || '', args.planItemId || ''].join('|');
  if (announcedFocus.has(key)) return;
  announcedFocus.add(key);
  try {
    await api.lifeOsSessionFocus({
      session_id: args.sessionId,
      object_id: args.objectId ? String(args.objectId) : undefined,
      plan_id: args.planId ? String(args.planId) : undefined,
      plan_item_id: args.planItemId ? String(args.planItemId) : undefined,
      event_type: 'object_opened',
    });
  } catch {
    // Soft: the conversation is still usable, focus is an enrichment.
    announcedFocus.delete(key);
  }
}

/** What a failed send needs in order to be retried under the same identity. */
type Outbox = {
  text: string;
  attachments: Array<{
    file_id: string;
    document_id?: string;
    display_name?: string;
    mime_type?: string;
  }>;
};

type Props = {
  sessionId?: string | null;
  planId?: string | null;
  objectId?: string | null;
  planItemId?: string | null;
  /**
   * A document the conversation should open already holding.
   *
   * It travels as an attachment on the first turn, through the same binding
   * path an uploaded file uses — the runtime promotes a stored document into a
   * context file by id — so ORA reads it before answering rather than being
   * told about it. Only on the first turn: once the session exists the file is
   * bound to it and re-sending would attach the same document twice.
   */
  documentId?: string | null;
  /**
   * An open question this conversation was opened to answer.
   *
   * When present, the next thing the person sends is that answer: it goes
   * through the flow that continues the work the question was blocking,
   * instead of arriving as an unrelated message the reasoning has to
   * re-interpret. Cleared once it has been used.
   */
  questionId?: string | null;
  /**
   * Something ORA raised, that this thread was opened to talk about.
   *
   * "Vediamo" is a conversation, not an acceptance. The concern arrives as the
   * thread's subject so ORA can open with why it said something instead of
   * making the person explain their own week back to it, and the handle goes
   * with the first message so the reasoning reads the same concern the card
   * came from. Nothing is created and nothing is executed by opening this.
   */
  opportunityId?: string | null;
  /** A need ORA raised, and the goal it belongs to. Both, or neither. */
  needId?: string | null;
  goalId?: string | null;
  entryPoint?: OraEntryPoint;
  devHarness?: boolean;
  testID?: string;
};

export function OraConversationScreen({
  sessionId: paramId,
  planId,
  objectId,
  planItemId,
  documentId,
  questionId,
  opportunityId,
  needId,
  goalId,
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
  const outbox = useRef<Map<string, Outbox>>(new Map());
  /*
    The blocker this thread was opened to answer, if any. A ref rather than
    state because it must be read inside a send that is already in flight, and
    it is cleared only once the answer has actually been accepted — a failed
    attempt must still be an answer when it is retried, not a stray remark.
  */
  const pendingQuestion = useRef<string | null>(questionId || null);
  useEffect(() => {
    if (questionId) pendingQuestion.current = questionId;
  }, [questionId]);

  /*
    The concern this thread is about, fetched rather than carried through the
    URL: the card's words are the backend's and a query string is not a place
    to put a sentence about somebody's life. Failing is silent — a thread that
    cannot show its subject is still a thread.
  */
  const [raised, setRaised] = useState<HomeOpportunity | null>(null);
  useEffect(() => {
    let alive = true;
    if (!opportunityId) {
      setRaised(null);
      return;
    }
    void api
      .getOpportunity(String(opportunityId))
      .then((o) => {
        if (alive) setRaised(o);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [opportunityId]);

  /*
    The need this thread was opened for, fetched the same way and for the same
    reason: the words belong to the backend, and a query string is not a place
    to put a sentence about somebody's life. What travels in the URL is two
    opaque handles.
  */
  const [need, setNeed] = useState<AgentNeed | null>(null);
  const [answeringNeed, setAnsweringNeed] = useState(false);
  useEffect(() => {
    let alive = true;
    if (!needId) {
      setNeed(null);
      return;
    }
    void api
      .getAgentNeed(String(needId))
      .then((n) => {
        if (alive) setNeed(n);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [needId]);

  /*
    Approving happens through the same endpoint everything else uses. A second,
    quieter path to authority — one that only exists because somebody arrived
    from a notification — is exactly the kind of shortcut this phase spent two
    sprints refusing to build.

    Opening a notification is not consent, and neither is landing here: only
    pressing one of these two is.
  */
  const answerNeed = useCallback(
    async (approve: boolean, forever = false) => {
      const target = need?.goal_id || (goalId ? String(goalId) : '');
      if (!target || answeringNeed) return;
      setAnsweringNeed(true);
      try {
        // `forever` travels only from the control that says so. Nothing here
        // infers it, and the plain approve path passes the default — which is
        // the whole difference between a yes and a standing permission.
        if (approve) await api.authoriseAgentGoal(target, '', forever);
        else await api.denyAgentGoal(target);
        setNeed((current) => (current ? { ...current, still_open: false } : current));
      } catch {
        /* Failing is silent here: the thread is still a thread. */
      } finally {
        setAnsweringNeed(false);
      }
    },
    [need?.goal_id, goalId, answeringNeed],
  );

  /*
    Answering, in the thread ORA asked in.

    The debt this pays is small to describe and large to experience: ORA asks
    «qual è il tuo comune?», the person writes «Padova», and the words go into
    an ordinary conversation turn while the agent stays blocked on a question
    that was — from its side — never answered. Two things were true at once
    and only one of them was visible.

    Only for a need that actually asks for information. An authority need is
    answered by the two buttons above, and «Vai pure» typed as a sentence is
    not consent: opening is not answering, and answering is not consenting.
  */
  const needsInformation = Boolean(
    need && need.still_open && need.asks_for === 'information',
  );
  const answerInThread = useCallback(
    async (text: string) => {
      const target = need?.goal_id || (goalId ? String(goalId) : '');
      if (!target) return false;
      const res = await api.answerAgentGoal(target, text);
      setNeed((current) => (current ? { ...current, still_open: false } : current));
      // What ORA says back is the server's sentence, not one composed here:
      // the thread must not be able to claim progress the goal has not made.
      const says = String((res as any)?.says || '').trim();
      if (says) {
        setTurns((prev) => [
          ...prev,
          { role: 'ora', text: says, messageId: `agent_${Date.now()}` },
        ]);
      }
      return true;
    },
    [need?.goal_id, goalId],
  );

  const { context, resolving: contextResolving } = useOraContext({
    planId,
    objectId,
    planItemId,
    documentId,
  });

  /**
   * Leaving goes back where the user came from. A conversation opened from a
   * Workspace that dead-ends on the tab bar would make "Continua con ORA" a
   * one-way door.
   */
  const goBack = useCallback(() => {
    if (entryPoint === 'goal_workspace' || entryPoint === 'object') {
      if (planId) {
        router.replace(buildGoalWorkspaceHref(String(planId)) as any);
        return;
      }
    }
    if (router.canGoBack?.()) router.back();
    else router.replace('/' as any);
  }, [entryPoint, planId, router]);

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
        setWorkingHint('Sto usando la tua posizione…');
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
          await announceFocus({
            sessionId: String(paramId),
            planId,
            objectId,
            planItemId,
          });
        }
        let res = (await api.aiCoreGet(paramId)) as AiCoreRes;
        if (cancelled) return;
        const sid = res.session_id || paramId;
        setSessionId(sid);
        setTurns(withRememberedSources(sid, historyToTurns(res.history || [])));

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
          setWorkingHint(res.working_hint || 'Sto usando la tua posizione…');
          try {
            res = await applyAiCoreResponse({ ...res, client_actions: actions }, sid);
            if (cancelled) return;
            {
              // Whatever the live answer carried is held before history —
              // which knows the words and nothing else — is allowed to win.
              const liveText = (res.ora_text || res.question || '').trim();
              rememberExtras(
                sid,
                liveText,
                Array.isArray(res.sources) ? res.sources.slice(0, 5) : [],
                Array.isArray((res as any).navigation)
                  ? ((res as any).navigation as OraNavigationOption[]).slice(0, 3)
                  : [],
              );
            }
            if (Array.isArray(res.history) && res.history.length) {
              setTurns(withRememberedSources(sid, historyToTurns(res.history)));
            } else {
              const ora = (res.ora_text || res.question || '').trim();
              const sources = Array.isArray(res.sources) ? res.sources.slice(0, 5) : [];
              const navigation = Array.isArray((res as any).navigation)
                ? ((res as any).navigation as OraNavigationOption[]).slice(0, 3)
                : [];
              if (ora) {
                setTurns((prev) => {
                  const last = prev[prev.length - 1];
                  if (last?.role === 'ora' && last.text === ora) return prev;
                  return [...prev, { role: 'ora', text: ora, sources, navigation }];
                });
              }
            }
          } catch (e: any) {
            fulfilledPendingTurns.delete(lockKey);
            if (!cancelled) setError(oraErrorMessage(e));
          } finally {
            if (!cancelled) {
              setBusy(false);
              setWorkingHint(null);
            }
          }
        }
      } catch (e: any) {
        if (!cancelled) setError(oraErrorMessage(e));
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
                  error: oraErrorMessage(e),
                }
              : a,
          ),
        );
      }
    } catch (e: any) {
      setError(oraErrorMessage(e));
    }
  }, [sessionId]);

  /** Apply whatever the runtime returned to the visible conversation. */
  const applyTurns = useCallback((res: AiCoreRes, clientMessageId: string, sid: string | null) => {
    if (Array.isArray(res.history) && res.history.length) {
      // History is the authority on what was said, but it carries no sources:
      // the runtime reports them alongside the answer it has just produced, not
      // per stored turn. Rebuilding from history alone silently threw them away
      // every time — so the evidence for the newest answer is put back on it.
      const rebuilt = historyToTurns(res.history);
      const sources = Array.isArray(res.sources) ? res.sources.slice(0, 5) : [];
      const navigation = Array.isArray((res as any).navigation)
        ? ((res as any).navigation as OraNavigationOption[]).slice(0, 3)
        : [];
      const lastOra = rebuilt.map((t) => t.role).lastIndexOf('ora');
      if (lastOra >= 0) {
        // The response carries the answer in full; the stored history entry is
        // bounded. When they are the same answer, show the complete one rather
        // than the copy that stops at the storage limit.
        const full = (res.ora_text || '').trim();
        const stored = rebuilt[lastOra].text;
        const text = full.length > stored.length && full.startsWith(stored.slice(0, 80))
          ? full
          : stored;
        rebuilt[lastOra] = {
          ...rebuilt[lastOra],
          text,
          ...(sources.length ? { sources } : {}),
          ...(navigation.length ? { navigation } : {}),
        };
      }
      rememberSources(sid, rebuilt);
      setTurns(rebuilt);
    } else {
      const ora = (res.ora_text || res.question || '').trim();
      const sources = Array.isArray(res.sources) ? res.sources.slice(0, 5) : [];
      const navigation = Array.isArray((res as any).navigation)
        ? ((res as any).navigation as OraNavigationOption[]).slice(0, 3)
        : [];
      setTurns((prev) => {
        const cleared = prev.map((t) =>
          t.messageId === clientMessageId ? { ...t, failed: false } : t,
        );
        const next = ora
          ? [...cleared, { role: 'ora' as const, text: ora, sources, navigation }]
          : cleared;
        rememberSources(sid, next);
        return next;
      });
    }
    outbox.current.delete(clientMessageId);
  }, []);

  /**
   * Send one turn under a stable client message id.
   *
   * The id is what makes a retry a retry rather than a duplicate: the runtime
   * already treats a repeated `client_message_id` as the same turn, so a failed
   * send can be re-attempted without the user ending up having said the same
   * thing twice.
   */
  const dispatch = useCallback(
    async (clientMessageId: string, payload: Outbox) => {
      const { text: msg, attachments: pendingAttach } = payload;
      setBusy(true);
      setError(null);
      setWorkingHint(
        pendingAttach.length ? 'Sto leggendo l’allegato…' : 'Sto ragionando…',
      );
      try {
        /*
          Answering a blocker is not the same as saying something.

          The words go to the question they belong to, which is what lets the
          server put the reasoning back on the exact plan item and object it
          stopped on. The thread is then re-read from the server rather than
          patched locally: what a person sees afterwards is the transcript as
          it actually is, including whatever the continuation produced.
        */
        // A blocked goal that asked for something gets the answer, before the
        // conversation gets a turn. The order matters: the same words cannot
        // be both an answer to ORA's question and a new thing to talk about.
        if (needsInformation && msg) {
          const handled = await answerInThread(msg);
          if (handled) {
            requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
            return;
          }
        }

        const qid = pendingQuestion.current;
        if (qid && sessionId && msg) {
          await api.answerQuestion(qid, msg, 'ora');
          pendingQuestion.current = null;
          const fresh = (await api.aiCoreGet(sessionId)) as AiCoreRes;
          setTurns(withRememberedSources(sessionId, historyToTurns(fresh.history || [])));
          requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
          return;
        }

        let res: AiCoreRes;
        if (!sessionId) {
          // Need a session before attaching file-only; start with text or placeholder
          const startText =
            msg ||
            `[Allegato: ${pendingAttach.map((a) => a.display_name).filter(Boolean).join(', ')}]`;
          // Attachments travel with the very first turn. Starting the session
          // and then sending the files as a second message produced two user
          // turns for one thing the person said — and the first answer was ORA
          // explaining it could not read a file that had not been bound yet.
          res = await api.aiCoreStart({
            text: startText,
            origin: entryPoint === 'home' ? 'home' : 'text',
            entry_point: entryPoint,
            plan_id: planId || undefined,
            object_id: objectId || undefined,
            opportunity_id: opportunityId || undefined,
            attachments: documentId
              ? [...pendingAttach, { document_id: String(documentId) }]
              : pendingAttach,
          });
          const id = res.session_id;
          setSessionId(id || null);
          // The new session learns which plan item we are on through the focus
          // API that already exists — start() carries plan and object, and this
          // completes the picture rather than adding a second context path.
          if (id && (planId || objectId)) {
            await announceFocus({ sessionId: String(id), planId, objectId, planItemId });
          }
          if (id) {
            res = await applyAiCoreResponse(res, id);
          }
          if (id && !paramId) {
            const q = new URLSearchParams({
              ...(planId ? { planId: String(planId) } : {}),
              ...(objectId ? { objectId: String(objectId) } : {}),
              ...(planItemId ? { planItemId: String(planItemId) } : {}),
              ...(documentId ? { documentId: String(documentId) } : {}),
              ...(opportunityId ? { opportunityId: String(opportunityId) } : {}),
              entry: entryPoint,
            });
            router.replace(`/ora/${id}?${q.toString()}` as any);
          }
        } else {
          if (pendingAttach.length) setWorkingHint('Sto verificando…');
          res = await api.aiCoreMessage(sessionId, {
            text: msg || '',
            attachments: pendingAttach,
            client_message_id: clientMessageId,
          });
          res = await applyAiCoreResponse(res, sessionId);
        }
        applyTurns(res, clientMessageId, sessionId || res.session_id || null);
        requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
      } catch (e: any) {
        // The turn is already on screen. Say plainly that it did not arrive
        // rather than leaving it looking answered.
        setTurns((prev) =>
          prev.map((t) => (t.messageId === clientMessageId ? { ...t, failed: true } : t)),
        );
        setError(oraErrorMessage(e));
      } finally {
        sendingRef.current = false;
        setBusy(false);
        setWorkingHint(null);
      }
    },
    [
      sessionId,
      entryPoint,
      planId,
      objectId,
      planItemId,
      documentId,
      paramId,
      router,
      needsInformation,
      answerInThread,
      applyAiCoreResponse,
      applyTurns,
    ],
  );

  const send = useCallback(async () => {
    const msg = text.trim();
    const ready = attachments.filter((a) => a.status === 'ready' && a.fileId);
    if ((!msg && !ready.length) || busy || sendingRef.current) return;
    if (attachments.some((a) => a.status === 'uploading')) return;
    sendingRef.current = true;
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
    outbox.current.set(clientMessageId, { text: msg, attachments: pendingAttach });
    await dispatch(clientMessageId, { text: msg, attachments: pendingAttach });
  }, [text, attachments, busy, dispatch]);

  const retry = useCallback(
    async (turn: Turn) => {
      const id = turn.messageId;
      if (!id || busy || sendingRef.current) return;
      const payload = outbox.current.get(id);
      if (!payload) return;
      sendingRef.current = true;
      setTurns((prev) => prev.map((t) => (t.messageId === id ? { ...t, failed: false } : t)));
      await dispatch(id, payload);
    },
    [busy, dispatch],
  );

  const opening = useMemo(() => {
    if (turns.length) return null;
    // Say nothing rather than the wrong thing while the context is on its way.
    if (contextResolving) return null;
    /*
      Opened from something ORA raised, the thread already has a subject, and
      a generic "di cosa parliamo?" would throw away the one thing this
      conversation is certain about. So it says what it said and why, and
      leaves the next move to the person.
    */
    if (need && need.still_open)
      return (
        <OraNeedOpening
          need={need}
          busy={answeringNeed}
          onApprove={() => void answerNeed(true)}
          onDeny={() => void answerNeed(false)}
          onAllowAlways={() => void answerNeed(true, true)}
        />
      );
    if (raised) return <OraRaisedOpening opportunity={raised} />;
    return context ? <OraContextOpening /> : <OraEmpty />;
  }, [turns.length, context, contextResolving, raised, need, answeringNeed, answerNeed]);

  /**
   * Before the first turn there is no conversation to scroll, so anchoring the
   * composer to the bottom of the screen left the opening line stranded at the
   * top with a page of nothing between them — a surface that reads as
   * unfinished rather than as waiting. With nothing said yet, the invitation
   * and the place to answer it are one block, held together in the middle.
   */
  const emptyStart = !boot && turns.length === 0 && !busy;

  const composer = (
    <OraComposer
      divider={!emptyStart}
      value={text}
      onChangeText={setText}
      onSend={() => void send()}
      busy={busy}
      placeholder="Scrivi a ORA…"
      showAttach
      attachments={attachments}
      onAttachPress={() => void onAttach()}
      onRemoveAttachment={(id) =>
        setAttachments((prev) => prev.filter((a) => a.localId !== id))
      }
      onMicPress={() => setMicHint('La voce non è ancora disponibile.')}
      testID={`${testID}-composer`}
    />
  );

  const asides = (
    <>
      {error ? <OraError message={error} /> : null}
      {micHint ? (
        <Text style={[styles.micHint, { color: colors.textTertiary }]}>{micHint}</Text>
      ) : null}
    </>
  );

  return (
    <FocusScreen testID={testID} maxWidth={READING_MAX_WIDTH}>
      <LocationPermissionSheet
        visible={locPermVisible}
        onAllow={() => resolveLocationPreference(true)}
        onDeny={() => resolveLocationPreference(false)}
      />
      {/*
        No offset, because there is nothing left to offset.

        `keyboardVerticalOffset` is the distance from the top of the window to
        the top of this view. FocusScreen already wraps everything in a
        SafeAreaView that consumes the top inset, so passing `insets.top + 48`
        counted the notch a second time and added 48 points on top of that —
        on a modern iPhone that is around 107 points of empty space pushed
        between the last turn and the keyboard. The product's two other
        conversation surfaces, Life Setup and login, sit in the same kind of
        container and pass nothing; this now matches them.
      */}
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.wrap}>
          <View style={styles.headerPad}>
            {devHarness ? (
              <Text style={[styles.devBanner, { color: colors.textTertiary }]} testID="ora-dev-banner">
                DEV / diagnostica — usa /ora in produzione
              </Text>
            ) : null}
            <OraHeader context={context} onBack={goBack} />
          </View>

          {emptyStart ? (
            <View
              style={[styles.startBlock, { paddingBottom: Math.max(insets.bottom, 8) }]}
              testID={`${testID}-start`}
            >
              {/* Uneven spacers: the block sits above centre so the header
                  keeps company instead of floating alone at the top. */}
              <View style={styles.startSpacerTop} />
              <View style={styles.startIntro}>
                {opening}
                {asides}
              </View>
              {composer}
              <View style={styles.startSpacerBottom} />
            </View>
          ) : (
            <>
              <ScrollView
                ref={scrollRef}
                style={styles.scroll}
                contentContainerStyle={styles.scrollContent}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
                testID={`${testID}-scroll`}
                onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
              >
                {boot ? (
                  <OraWorking hint="Sto recuperando la conversazione…" />
                ) : (
                  <>
                    {opening}
                    <OraTurns turns={turns} onRetry={(t) => void retry(t)} />
                    {busy ? <OraWorking hint={workingHint} /> : null}
                    {asides}
                  </>
                )}
              </ScrollView>

              <View style={{ paddingBottom: Math.max(insets.bottom, 8) }}>{composer}</View>
            </>
          )}
        </View>
      </KeyboardAvoidingView>
    </FocusScreen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  wrap: { flex: 1, width: '100%' },
  headerPad: { paddingHorizontal: tokens.spacing.lg, paddingTop: tokens.spacing.sm },
  scroll: { flex: 1 },
  scrollContent: {
    paddingHorizontal: tokens.spacing.lg,
    paddingTop: tokens.spacing.xs,
    paddingBottom: tokens.spacing.xxl,
  },
  /**
   * Invitation and composer as one block, held in the space that is there.
   *
   * Biased above centre on purpose: dead-centre leaves the header stranded at
   * the top of the page with nothing beneath it, which is the same "suspended"
   * feeling in a different place.
   */
  startBlock: { flex: 1, gap: tokens.spacing.lg },
  /**
   * The gap above is capped. On a tall desktop window a truly centred block
   * pushes the invitation half a screen below the header, which leaves the
   * header stranded — the same suspended feeling the centring was meant to
   * remove. On short windows the cap never binds and the block sits centred.
   */
  startSpacerTop: { flex: 2, maxHeight: 140 },
  startSpacerBottom: { flex: 3 },
  startIntro: { paddingHorizontal: tokens.spacing.lg },
  devBanner: { fontSize: 12, paddingBottom: 4 },
  micHint: { fontSize: 13, lineHeight: 19, marginTop: tokens.spacing.md },
});
