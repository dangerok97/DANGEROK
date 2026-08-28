/**
 * Life Setup Gate — application initial state (pre-Home).
 *
 * Home must remain unaware of Life Setup. All routing decisions after auth
 * go through this module.
 *
 * Persistence:
 * - Local AsyncStorage flag per user (`ora.lifeSetupCompleted.<userId>`)
 * - Synced with backend session status when available
 *
 * Sprint 2B: only backend `completed` (or feature disabled) unlocks Home.
 * `interrupted` / `skipped` / `cancelled` ≠ completed → stay on Life Setup.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Router } from 'expo-router';
import { api } from '@/src/api/client';
import { safeNextTarget } from '@/src/shell/nextTarget';

const STORAGE_PREFIX = 'ora.lifeSetupCompleted.';

export type LifeSetupGateTarget = 'life-setup' | 'home';

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

function sessionStatus(session: unknown): string | undefined {
  if (!session || typeof session !== 'object') return undefined;
  const s = (session as { status?: unknown }).status;
  return typeof s === 'string' ? s : undefined;
}

/**
 * Statuses that mean the first run is behind this person.
 *
 * V3.3: skipping is one of them. Someone who chose "salta per ora" on
 * everything has answered the only question the gate is entitled to ask — do
 * you want to do this now — and sending them back to the same screen on every
 * launch is the onboarding loop the sprint exists to remove. What they told
 * ORA is a separate matter: the Life Profile keeps its own figure, and Vita is
 * where they come back to it if they ever want to.
 */
const FIRST_RUN_OVER = ['completed', 'skipped', 'cancelled', 'interrupted'] as const;

/** True only when the Life Setup is durably finished for gate purposes. */
export function isLifeSetupFullyCompleted(statusPayload: {
  enabled?: boolean;
  session?: unknown;
}): boolean {
  if (statusPayload.enabled === false) return true;
  return sessionStatus(statusPayload.session) === 'completed';
}

/**
 * Whether this person may go straight into the app.
 *
 * Deliberately weaker than "completed": completion is about knowledge, and a
 * gate has no business holding somebody at the door until they have told ORA
 * enough about themselves.
 */
export function isFirstRunOver(statusPayload: {
  enabled?: boolean;
  session?: unknown;
}): boolean {
  if (statusPayload.enabled === false) return true;
  const status = sessionStatus(statusPayload.session);
  return !!status && (FIRST_RUN_OVER as readonly string[]).includes(status);
}

/** null = never set on this device */
export async function getLocalLifeSetupCompleted(userId: string): Promise<boolean | null> {
  try {
    const v = await AsyncStorage.getItem(storageKey(userId));
    if (v === '1') return true;
    if (v === '0') return false;
    return null;
  } catch {
    return null;
  }
}

export async function setLocalLifeSetupCompleted(
  userId: string,
  completed: boolean,
): Promise<void> {
  await AsyncStorage.setItem(storageKey(userId), completed ? '1' : '0');
}

/**
 * Resolve whether the user may enter Home.
 * Prefers backend session.status === 'completed' over legacy should_show.
 * Offline: trust local completed flag only; otherwise fail closed → life-setup.
 */
export async function resolveLifeSetupGate(userId: string): Promise<LifeSetupGateTarget> {
  const local = await getLocalLifeSetupCompleted(userId);

  try {
    const st = await api.lifeSetupStatus();
    if (isFirstRunOver(st)) {
      await setLocalLifeSetupCompleted(userId, true);
      return 'home';
    }
    // active / not_started / interrupted / skipped / cancelled / no session
    await setLocalLifeSetupCompleted(userId, false);
    return 'life-setup';
  } catch {
    if (local === true) return 'home';
    return 'life-setup';
  }
}

/**
 * Persist gate completion after a successful backend complete (or placeholder path).
 * Does NOT treat skip/interrupt as success. Throws if completion cannot be confirmed.
 */
export async function completeLifeSetupGate(userId: string): Promise<void> {
  const st = await api.lifeSetupStatus();
  if (isLifeSetupFullyCompleted(st)) {
    await setLocalLifeSetupCompleted(userId, true);
    return;
  }

  let start = await api.lifeSetupStart(false);
  if (start.already_finished) {
    const term = sessionStatus(start.session);
    if (term === 'completed') {
      await setLocalLifeSetupCompleted(userId, true);
      return;
    }
    // interrupted/skipped/cancelled — force a session so placeholder can finish
    start = await api.lifeSetupStart(true);
  }

  if (!start.already_finished) {
    const done = await api.lifeSetupComplete();
    if (!done.ok) {
      throw new Error('complete_failed');
    }
  }

  const verify = await api.lifeSetupStatus();
  if (!isLifeSetupFullyCompleted(verify)) {
    throw new Error('complete_unconfirmed');
  }
  await setLocalLifeSetupCompleted(userId, true);
}

/** Navigate by gate — single entry used by login, cold start, and Life Setup exits. */
/**
 * Where someone lands once they are in.
 *
 * `next` is where they were trying to go before being asked to sign in — a
 * shared document, a workspace. It is honoured only after Life Setup is
 * satisfied: the gate's semantics are unchanged, and an incomplete setup still
 * wins over any destination. A `next` that did not survive validation is
 * simply absent, and Home is the answer.
 */
export async function routeByLifeSetupGate(
  router: Router,
  userId: string,
  next?: string | null,
): Promise<void> {
  const target = await resolveLifeSetupGate(userId);
  if (target === 'life-setup') {
    router.replace('/life-setup' as any);
    return;
  }
  router.replace((safeNextTarget(next) || '/(tabs)') as any);
}
