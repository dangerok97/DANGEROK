/**
 * Life Setup Gate — application initial state (pre-Home).
 *
 * Home must remain unaware of Life Setup. All routing decisions after auth
 * go through this module.
 *
 * Persistence:
 * - Local AsyncStorage flag per user (`ora.lifeSetupCompleted.<userId>`)
 * - Synced with backend `/life-setup/status` when available
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Router } from 'expo-router';
import { api } from '@/src/api/client';

const STORAGE_PREFIX = 'ora.lifeSetupCompleted.';

export type LifeSetupGateTarget = 'life-setup' | 'home';

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
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
 * - Local completed → home (fast path)
 * - Backend disabled → home
 * - Backend should_show → life-setup
 * - Backend terminal (!should_show) → home + persist local
 * - Backend unreachable + not locally completed → life-setup (fail closed)
 */
export async function resolveLifeSetupGate(userId: string): Promise<LifeSetupGateTarget> {
  const local = await getLocalLifeSetupCompleted(userId);
  if (local === true) return 'home';

  try {
    const st = await api.lifeSetupStatus();
    if (st.enabled === false) {
      await setLocalLifeSetupCompleted(userId, true);
      return 'home';
    }
    if (st.should_show) {
      await setLocalLifeSetupCompleted(userId, false);
      return 'life-setup';
    }
    await setLocalLifeSetupCompleted(userId, true);
    return 'home';
  } catch {
    // Fail closed: do not leak new users into Home without a known completed flag
    return 'life-setup';
  }
}

/**
 * Mark setup completed (Sprint 1 placeholder / future conversation finish).
 * Best-effort backend session start+complete (or skip); always persists local flag.
 */
export async function completeLifeSetupGate(userId: string): Promise<void> {
  try {
    const start = await api.lifeSetupStart(false);
    if (!start.already_finished) {
      const done = await api.lifeSetupComplete();
      if (!done.ok) {
        await api.lifeSetupSkip({ postpone_all: true });
      }
    }
  } catch {
    try {
      await api.lifeSetupSkip({ postpone_all: true });
    } catch {
      // Local flag still allows Home; status will reconcile when API is back
    }
  }
  await setLocalLifeSetupCompleted(userId, true);
}

/** Navigate by gate — single entry used by login + cold start. */
export async function routeByLifeSetupGate(router: Router, userId: string): Promise<void> {
  const target = await resolveLifeSetupGate(userId);
  if (target === 'life-setup') {
    router.replace('/life-setup' as any);
    return;
  }
  router.replace('/(tabs)' as any);
}
