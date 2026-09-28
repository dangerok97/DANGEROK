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
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { triggerHaptic } from '@/src/theme/haptics';

import { api, type AgentNeed, type HomeOpportunity } from '@/src/api/client';
import {
  OraComposer,
  PendingAttachment,
  AttachKind,
  pickOraAttachment,
} from '@/src/components/ora/OraComposer';
import { LocationPermissionSheet } from '@/src/components/ora/LocationPermissionSheet';
import { requestForegroundPosition } from '@/src/location/foregroundGeo';
import { FocusScreen } from '@/src/shell';
import type { OraNavigationOption, OraUiAction } from '@/src/components/ora/OraTurns';
import { useTheme, ThemeSurface } from '@/src/theme/ThemeProvider';
import { useVoice } from '@/src/voice/useVoice';
import { useLiveVoice } from '@/src/voice/useLiveVoice';
import { LiveVoiceScreen } from '@/src/voice/LiveVoiceScreen';
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
import { OraPresence } from './presence/OraPresence';
import { COMPLETED_FOCUS_MS, presenceMode, readPresenceActivity, type PresenceActivity } from './presence/state';
import type { OraJourneyView } from './OraJourney';
import { DesktopShell } from '@/src/shell';
import { useBreakpoint } from '@/src/theme/responsive';
import { presencePalette, presenceColors } from '@/src/theme/presence';

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
  activity?: PresenceActivity | null;
  ok?: boolean;
  session_id?: string;
  ora_text?: string;
  question?: string | null;
  sources?: Array<{ title?: string; url?: string }>;
  ui_actions?: OraUiAction[];
  working_hint?: string | null;
  client_actions?: ClientAction[];
  pending_turn?: PendingTurn;
  history?: Array<{
    role?: string;
    text?: string;
    kind?: string;
    message_id?: string;
    meta?: { attachments?: Array<{ name?: string }>; sources?: Array<{ title?: string; url?: string }>; navigation?: OraNavigationOption[]; journey?: OraJourneyView; ui_actions?: OraUiAction[] };
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
    meta?: { attachments?: Array<{ name?: string }>; sources?: Array<{ title?: string; url?: string }>; navigation?: OraNavigationOption[]; journey?: OraJourneyView; ui_actions?: OraUiAction[] };
  }>,
): Turn[] {
  return hist
    .filter((h) => h.text && (h.role === 'user' || h.role === 'ora'))
    .map((h) => ({
      role: h.role as 'user' | 'ora',
      text: h.text as string,
      messageId: h.message_id,
      attachments: h.meta?.attachments,
      sources: h.meta?.sources,
      navigation: h.meta?.navigation,
      journey: h.meta?.journey,
      uiActions: h.meta?.ui_actions,
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
/*
  Come arrivarci, tenuto come le fonti e i link.

  Lo storico non lo porta — nasce con la risposta — e senza questa memoria
  spariva alla prima ricostruzione della conversazione, cioè un istante dopo
  essere apparso.
*/
const lastJourney = new Map<string, { text: string; journey: OraJourneyView }>();

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
  if (last?.journey) {
    lastJourney.set(sessionId, { text: last.text, journey: last.journey });
  }
}

/** Hold what the last live answer carried, keyed on its own text. */
function rememberExtras(
  sessionId: string | null,
  text: string,
  sources: OraSourceRef[],
  navigation: OraNavigationOption[],
  journey?: OraJourneyView | null,
): void {
  if (!sessionId || !text.trim()) return;
  if (sources.length) lastSources.set(sessionId, { text, sources });
  if (navigation.length) lastNavigation.set(sessionId, { text, navigation });
  if (journey?.options?.length || journey?.unavailable) {
    lastJourney.set(sessionId, { text, journey });
  }
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

  const heldJourney = lastJourney.get(sessionId);
  if (heldJourney && !out[idx].journey && out[idx].text.trim() === heldJourney.text.trim()) {
    out = out === turns ? [...turns] : out;
    out[idx] = { ...out[idx], journey: heldJourney.journey };
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
  voiceTicket?: number;
  attachments: Array<{
    file_id: string;
    document_id?: string;
    display_name?: string;
    mime_type?: string;
  }>;
};

type Props = {
  sessionId?: string | null;
  /** First message already sent by Home; only the visual entrance is pending. */
  openingKey?: string | null;
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

export function OraConversationScreen(props: Props) {
  return <ThemeSurface scheme="dark" colors={presenceColors}><OraConversationBody key={props.sessionId || 'new'} {...props} /></ThemeSurface>;
}

function OraConversationBody({
  sessionId: paramId,
  openingKey: entryOpeningKey,
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
  const scrollRef = useRef<ScrollView>(null);

  const [sessionId, setSessionId] = useState<string | null>(paramId || null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const currentActivityRequest = useRef<string | null>(null);
  const [activityRequestId, setActivityRequestId] = useState<string | null>(null);
  const [openingTurn, setOpeningTurn] = useState<string | null>(entryOpeningKey || null);
  const firstOpening = useRef(false);
  const openingStartedAt = useRef(0);
  const focusCompletedAt = useRef(0);
  const [presenceActivity, setPresenceActivity] = useState<PresenceActivity | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [boot, setBoot] = useState(Boolean(paramId));
  const [workingHint, setWorkingHint] = useState<string | null>(null);
  /*
    Se la conversazione comincia parlando, la sessione nasce con origine
    «voice» — che il modello delle sessioni prevede da sempre. Non cambia
    niente di quello che succede dopo: è provenienza, non comportamento.
  */
  const startedByVoice = useRef(false);
  const lastLiveMessageId = useRef<string | null>(null);
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
        if (!alive) return;
        setNeed(n);
        /*
          A need is the first ORA turn of this conversation, not temporary
          chrome.  Keeping it in the transcript matters most after the person
          answers: otherwise the answer remains on screen while the question
          it answered appears to have been deleted.
        */
        const question = String(n?.says || '').trim();
        if (question) {
          setTurns((current) =>
            current.length
              ? current
              : [{ role: 'ora', text: question, messageId: `need_${String(needId)}` }],
          );
        }
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
      /*
        Accepting the missing fact only unblocks the goal.  It is not the
        result of the user's instruction and must never manufacture a generic
        "ho cercato" reply.  The same user turn continues below through AI
        Core, where capabilities (phone, calendar, mail, ...) are actually
        selected and their real outcome is returned.
      */
      void res;
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
                ((res as any).journey || null) as OraJourneyView | null,
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
                  return [...prev, { role: 'ora', text: ora, sources, navigation, uiActions: res.ui_actions }];
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

  const onAttach = useCallback(async (kind: AttachKind = 'any') => {
    setError(null);
    try {
      const picked = await pickOraAttachment(kind);
      if (!picked) return;
      const localId = `loc_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
      setAttachments((prev) => [
        ...prev,
        {
          localId,
          name: picked.name,
          mimeType: picked.type,
          status: 'uploading',
          // L'immagine si vede subito, mentre sale: chi l'ha appena scelta
          // vuole sapere di aver scelto quella giusta, non aspettare.
          previewUri: picked.type?.startsWith('image/') ? picked.uri : undefined,
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
      const needQuestion = String(need?.says || '').trim();
      if (
        needId &&
        needQuestion &&
        !rebuilt.some((turn) => turn.messageId === `need_${String(needId)}`)
      ) {
        rebuilt.unshift({
          role: 'ora',
          text: needQuestion,
          messageId: `need_${String(needId)}`,
        });
      }
      const sources = Array.isArray(res.sources) ? res.sources.slice(0, 5) : [];
      const navigation = Array.isArray((res as any).navigation)
        ? ((res as any).navigation as OraNavigationOption[]).slice(0, 3)
        : [];
      // Come arrivarci, confrontato: viaggia con la risposta, non con lo storico.
      const journey = ((res as any).journey || null) as OraJourneyView | null;
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
          ...(res.ui_actions?.length ? { uiActions: res.ui_actions } : {}),
          ...(journey?.options?.length || journey?.unavailable ? { journey } : {}),
        };
      }
      if (journey?.options?.length || journey?.unavailable) {
        rememberExtras(sid, rebuilt[lastOra]?.text || '', sources, navigation, journey);
      }
      rememberSources(sid, rebuilt);
      setTurns(withRememberedSources(sid, rebuilt));
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
        // Come arrivarci viaggia con la risposta anche quando non c'è storico.
        const journey = ((res as any).journey || null) as OraJourneyView | null;
        const next = ora
          ? [...cleared, {
              role: 'ora' as const, text: ora, sources, navigation, uiActions: res.ui_actions,
              ...(journey?.options?.length || journey?.unavailable ? { journey } : {}),
            }]
          : cleared;
        rememberSources(sid, next);
        return next;
      });
    }
    outbox.current.delete(clientMessageId);
  }, [need?.says, needId]);

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
      if (!sessionId && !firstOpening.current) {
        firstOpening.current = true;
        openingStartedAt.current = Date.now();
        setOpeningTurn(clientMessageId);
      }
      const requestId = newClientMessageId();
      currentActivityRequest.current = requestId;
      setActivityRequestId(requestId);
      setPresenceActivity(null);
      focusCompletedAt.current = 0;
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
            // Do not return: this very turn must continue into the operational
            // runtime.  Answering a blocker and carrying out the instruction
            // are two stages of one interaction, not two conversations.
          }
        }

        const qid = pendingQuestion.current;
        if (qid && sessionId && msg) {
          await api.answerQuestion(qid, msg, 'ora');
          pendingQuestion.current = null;
          const fresh = (await api.aiCoreGet(sessionId)) as AiCoreRes;
          setTurns(withRememberedSources(sessionId, historyToTurns(fresh.history || [])));
          liveRef.current?.answered(String(fresh.ora_text || fresh.question || ''), payload.voiceTicket);
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
            activity_request_id: requestId,
            response_channel: payload.voiceTicket !== undefined ? 'voice' : 'text',
            text: startText,
            origin: startedByVoice.current
              ? 'voice'
              : entryPoint === 'home'
                ? 'home'
                : 'text',
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

        } else {
          if (pendingAttach.length) setWorkingHint('Sto verificando…');
          res = await api.aiCoreMessage(sessionId, {
            activity_request_id: requestId,
            response_channel: payload.voiceTicket !== undefined ? 'voice' : 'text',
            text: msg || '',
            attachments: pendingAttach,
            client_message_id: clientMessageId,
          });
          res = await applyAiCoreResponse(res, sessionId);
        }
        const completedActivity = readPresenceActivity(res.activity, requestId);
        if (completedActivity?.phase === 'done' && completedActivity.area) focusCompletedAt.current = Date.now();
        setPresenceActivity(previous => readPresenceActivity(completedActivity, requestId, previous));
        applyTurns(res, clientMessageId, sessionId || res.session_id || null);
        // Se la domanda è stata fatta a voce, la risposta si ascolta — ed è
        // parola per parola quella che si legge sopra. Se è stata scritta,
        // questo non fa niente.
        liveRef.current?.answered(String(res.ora_text || res.question || ''), payload.voiceTicket);
        requestAnimationFrame(() => scrollRef.current?.scrollToEnd({ animated: true }));
      } catch (e: any) {
        // The turn is already on screen. Say plainly that it did not arrive
        // rather than leaving it looking answered.
        setTurns((prev) =>
          prev.map((t) => (t.messageId === clientMessageId ? { ...t, failed: true } : t)),
        );
        setError(oraErrorMessage(e));
        // Chi sta parlando a voce non vede l'errore scritto: senza questo
        // resterebbe davanti a «Sto pensando» finché non tocca lo schermo.
        liveRef.current?.stumbled(payload.voiceTicket);
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

  /**
   * Mandare delle parole a ORA, da qualunque parte arrivino.
   *
   *     STESSA CONVERSAZIONE, STESSA SESSIONE, STESSA AUTORITÀ.
   *
   * Quello che si dice e quello che si scrive passano di qui uguali. Una
   * seconda strada per la voce sarebbe stata più facile da scrivere e sarebbe
   * stata un secondo assistente: la stessa persona, con due memorie diverse a
   * seconda di come ha aperto bocca.
   */
  const sendWords = useCallback(
    async (words: string, voiceTicket?: number, retry = false) => {
      const msg = words.trim();
      if (sendingRef.current && voiceTicket !== undefined) throw new Error('voice_turn_busy');
      if (!msg || sendingRef.current) return;
      const previousId = retry ? lastLiveMessageId.current : null;
      const previous = previousId ? outbox.current.get(previousId) : null;
      if (previousId && previous && previous.text === msg) {
        sendingRef.current = true;
        const payload = { ...previous, voiceTicket };
        outbox.current.set(previousId, payload);
        await dispatch(previousId, payload);
        return;
      }
      sendingRef.current = true;
      const clientMessageId = newClientMessageId();
      setTurns((prev) => [...prev, { role: 'user', text: msg, messageId: clientMessageId }]);
      const payload = { text: msg, attachments: [], voiceTicket };
      if (voiceTicket !== undefined) lastLiveMessageId.current = clientMessageId;
      outbox.current.set(clientMessageId, payload);
      await dispatch(clientMessageId, payload);
    },
    [dispatch],
  );

  const voice = useVoice({
    speak: (words) => {
      startedByVoice.current = true;
      return sendWords(words);
    },
    busy,
  });
  /*
    La conversazione parlata passa per la stessa funzione del testo e della
    dettatura. Non è un secondo assistente e non è una seconda sessione: è la
    stessa, con la risposta detta ad alta voce invece che solo scritta.
  */
  const live = useLiveVoice({
    speak: (words, ticket, retry) => {
      startedByVoice.current = true;
      return sendWords(words, ticket, retry);
    },
  });
  const liveRef = useRef(live);
  liveRef.current = live;

  // A fast response is rendered immediately. Only URL replacement waits for
  // the entrance and final focus to finish; remounting sooner loses activity
  // because stored conversation history does not carry the live work signal.
  // Voice and any in-flight turn keep ownership of this screen until finished.
  useEffect(() => {
    if (!sessionId || paramId || live.on || busy) return;
    const q = new URLSearchParams({
      ...(planId ? { planId: String(planId) } : {}),
      ...(objectId ? { objectId: String(objectId) } : {}),
      ...(planItemId ? { planItemId: String(planItemId) } : {}),
      ...(documentId ? { documentId: String(documentId) } : {}),
      ...(opportunityId ? { opportunityId: String(opportunityId) } : {}),
      ...(needId ? { needId: String(needId) } : {}),
      ...(goalId ? { goalId: String(goalId) } : {}),
      entry: entryPoint,
    });
    const now = Date.now();
    const remaining = Math.max(0, openingStartedAt.current + 2800 - now,
      focusCompletedAt.current ? focusCompletedAt.current + COMPLETED_FOCUS_MS - now : 0);
    const timer = setTimeout(() => router.replace(`/ora/${sessionId}?${q.toString()}` as any), remaining);
    return () => clearTimeout(timer);
  }, [sessionId, paramId, live.on, busy, planId, objectId, planItemId, documentId,
    opportunityId, needId, goalId, entryPoint, router]);

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

  /*
    Una telefonata partita da questa chat: si aspetta che finisca e poi si
    rilegge la conversazione, dove il backend ha scritto com'è andata.
    Nessuno stato tecnico sullo schermo — solo la riga di ORA quando arriva.
  */
  const lastOraText = [...turns].reverse().find((t) => t.role === 'ora')?.text || '';
  useEffect(() => {
    if (!sessionId || busy) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const started = Date.now();
    let sawCall = false;
    const check = async () => {
      try {
        const live = await api.chatCallLive(sessionId);
        if (cancelled) return;
        if (live?.calling) {
          sawCall = true;
          if (Date.now() - started < 30 * 60 * 1000) timer = setTimeout(check, 4000);
          return;
        }
        if (sawCall) {
          const fresh = (await api.aiCoreGet(sessionId)) as AiCoreRes;
          if (!cancelled && fresh?.history) {
            setTurns(withRememberedSources(sessionId, historyToTurns(fresh.history)));
          }
        }
      } catch {
        // Aspettare l'esito è una cortesia: se la domanda fallisce, la chat resta com'è.
      }
    };
    void check();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [sessionId, busy, lastOraText]);

  /*
    Mentre ORA lavora, si dice quello che sta facendo davvero.

    Il ciclo scrive sulla sessione lo strumento in corso — «Controllo il tuo
    calendario…», «Cerco il contatto…» — e qui lo si legge. Se non c'è niente
    di concreto da dire, resta il messaggio di attesa di sempre: nessuna
    attività inventata per riempire il silenzio.
  */
  useEffect(() => {
    if (!busy || !activityRequestId) return;
    let alive = true;
    let inFlight = false;
    const tick = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const progress = await api.aiCoreRequestProgress(activityRequestId);
        if (alive && currentActivityRequest.current === activityRequestId) {
          setPresenceActivity(previous => readPresenceActivity(progress.activity, activityRequestId, previous));
          setWorkingHint(progress.working_on || 'Sto ragionando…');
        }
      } catch {
        if (alive && currentActivityRequest.current === activityRequestId) setPresenceActivity(null);
      } finally { inFlight = false; }
    };
    const timer = setInterval(() => void tick(), 1000);
    void tick();
    return () => { alive = false; clearInterval(timer); };
  }, [busy, activityRequestId]);

  const emptyStart = !boot && turns.length === 0 && !busy;
  const bp = useBreakpoint();
  const wide = bp === 'desktop';

  /*
    Le scorciatoie sotto il composer. Non sono decorazione: due preparano
    un messaggio a ORA, una apre i documenti, una apre le chiamate.
    Niente bottoni che non fanno niente.
  */
  const quickActions: { label: string; run: () => void }[] = [
    {
      label: 'Pianifica la giornata',
      run: () => { setText('Pianifica la mia giornata di oggi.'); void triggerHaptic('selection'); },
    },
    {
      label: 'Riepiloga le mie attività',
      run: () => { setText('Riepiloga le mie attività aperte.'); void triggerHaptic('selection'); },
    },
    { label: 'Cerca un documento', run: () => router.push('/documenti' as any) },
    { label: 'Prepara una chiamata', run: () => router.push('/prepara-chiamata' as any) },
  ];

  const composer = (
    <OraComposer
      divider={false}
      appearance="presence"
      value={text}
      onChangeText={setText}
      onSend={() => void send()}
      busy={busy}
      placeholder="Scrivi a ORA…"
      showAttach
      attachments={attachments}
      onAttachPress={(kind) => void onAttach(kind)}
      onRemoveAttachment={(id) =>
        setAttachments((prev) => prev.filter((a) => a.localId !== id))
      }
      onMicPress={voice.toggle}
      onVoiceModePress={live.open}
      listening={voice.state.phase === 'listening' || voice.state.phase === 'asking'}
      speaking={live.state.phase === 'speaking'}
      interim={voice.state.interim}
      voiceHint={voice.hint}
      testID={`${testID}-composer`}
    />
  );

  const asides = (
    <>
      {error ? <OraError message={error} /> : null}
    </>
  );

  const composerBlock = (
    <View style={styles.composerWrap}>
      {composer}
      {emptyStart && !text ? <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.quickRow} testID="ora-quick-actions">
        {quickActions.map((q) => (
          <Pressable
            key={q.label}
            onPress={q.run}
            accessibilityRole="button"
            style={({ pressed, hovered }: any) => [
              styles.quickChip,
              hovered && { backgroundColor: presencePalette.border },
              pressed && { opacity: 0.7 },
            ]}
          >
            <Ionicons name="add" size={15} color={presencePalette.muted} />
            <Text style={{ fontSize: 12, color: presencePalette.muted }}>{q.label}</Text>
          </Pressable>
        ))}
      </ScrollView> : null}
    </View>
  );

  const schermo = (
    <FocusScreen testID={testID} maxWidth={2600} contentStyle={{ paddingHorizontal: 0 }}>
      <StatusBar style="light" />
      <LocationPermissionSheet
        visible={locPermVisible}
        onAllow={() => resolveLocationPreference(true)}
        onDeny={() => resolveLocationPreference(false)}
      />
      {/*
        La modalità vocale sta sopra questa schermata, non al posto suo: la
        conversazione continua a vivere qui sotto, e chiudendola i turni sono
        già tutti al loro posto perché non sono mai stati altrove.
      */}
      <LiveVoiceScreen live={live} activity={presenceActivity} openingKey={openingTurn} />
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
            {context ? <OraHeader context={context} onBack={goBack} /> : null}
          </View>

          <OraPresence
            openingKey={openingTurn}
            expanded
            onBack={!wide && !context ? goBack : undefined}
            mode={presenceMode(busy, voice.state.phase)}
            activity={presenceActivity}
            active={!live.on}
            onAreaPrompt={setText}
            footer={composerBlock}
            conversation={!emptyStart || context || need || raised || error ? (
              <ScrollView
                ref={scrollRef}
                style={styles.scroll}
                contentContainerStyle={styles.scrollContent}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator
                testID={`${testID}-scroll`}
                onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
              >
                {boot ? <OraWorking hint="Sto recuperando la conversazione…" /> : <>
                  {opening}
                  <OraTurns turns={turns} onRetry={(t) => void retry(t)} />
                  {busy ? <OraWorking hint={workingHint} /> : null}
                  {asides}
                </>}
              </ScrollView>
            ) : null}
          />
        </View>
      </KeyboardAvoidingView>
    </FocusScreen>
  );

  if (!wide) return schermo;

  return (
    <DesktopShell active="ora" immersive>
      {schermo}
    </DesktopShell>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minHeight: 0 },
  wrap: { flex: 1, minHeight: 0, width: '100%' },
  headerPad: { paddingHorizontal: 16 },
  scroll: { flex: 1 },
  scrollContent: {
    width: '100%', maxWidth: READING_MAX_WIDTH, alignSelf: 'center',
    paddingHorizontal: tokens.spacing.lg, paddingVertical: tokens.spacing.md,
  },
  composerWrap: { width: '100%', maxWidth: 860, alignSelf: 'center', gap: 8 },
  quickRow: { flexDirection: 'row', gap: 8, paddingHorizontal: 4 },
  quickChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 44,
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: 999,
  },
  devBanner: { fontSize: 12, paddingBottom: 4 },
});
