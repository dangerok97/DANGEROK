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

/** True only when the Life Setup is durably finished for gate purposes. */
export function isLifeSetupFullyCompleted(statusPayload: {
  enabled?: boolean;
  session?: unknown;
}): boolean {
  if (statusPayload.enabled === false) return true;
  return sessionStatus(statusPayload.session) === 'completed';
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
    if (isLifeSetupFullyCompleted(st)) {
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
export async function routeByLifeSetupGate(router: Router, userId: string): Promise<void> {
  const target = await resolveLifeSetupGate(userId);
  if (target === 'life-setup') {
    router.replace('/life-setup' as any);
    return;
  }
  router.replace('/(tabs)' as any);
}
