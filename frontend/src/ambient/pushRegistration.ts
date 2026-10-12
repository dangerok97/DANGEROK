/** Native push effects. Only enablePush may request an OS permission. */
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

import { api } from '@/src/api/client';
import { storage } from '@/src/utils/storage';
import { createInstallationHandle, createRegistrationRevision } from './installationHandle';
import { createPushLifecycle, type PushPermission, type PushSession } from './pushLifecycle';
import { createSessionCleanup, PENDING_SESSION_CLEANUP_KEY as CLEANUP_KEY, type PendingSessionCleanup } from '../auth/sessionCleanup';

export type { PushOutcome, PushSnapshot } from './pushLifecycle';
export type PushCapability = 'native' | 'unsupported';
export function capability(): PushCapability {
  return Platform.OS === 'ios' || Platform.OS === 'android' ? 'native' : 'unsupported';
}
function projectId(): string | undefined {
  const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;
  const eas = (extra.eas ?? {}) as Record<string, unknown>;
  return (typeof eas.projectId === 'string' ? eas.projectId : undefined)
    || Constants.easConfig?.projectId;
}
function permissionValue(value: Notifications.NotificationPermissionsStatus): PushPermission {
  const granted = value.granted
    || value.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL
    || value.ios?.status === Notifications.IosAuthorizationStatus.EPHEMERAL;
  return {
    status: granted ? 'granted' : value.status === 'denied' ? 'denied' : 'undetermined',
    canAskAgain: value.canAskAgain,
  };
}
async function bounded<T>(work: Promise<T>): Promise<T> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      work,
      new Promise<never>((_, reject) => { timeout = setTimeout(() => reject(new Error('push_timeout')), 12_000); }),
    ]);
  } finally { if (timeout) clearTimeout(timeout); }
}

const deviceHandle = createInstallationHandle(Platform.OS, SecureStore, () => Crypto.randomUUID());
const registrationRevision = createRegistrationRevision(SecureStore);
async function stopNative(): Promise<void> {
  if (capability() !== 'native') return;
  // Stop Expo's own persisted token auto-registration before unregistering.
  // Otherwise a later native token event can silently opt the device back in.
  const auto = await Promise.allSettled([bounded(Notifications.setAutoServerRegistrationEnabledAsync(false))]);
  const native = await Promise.allSettled([bounded(Notifications.unregisterForNotificationsAsync())]);
  if (auto[0].status === 'rejected' || native[0].status === 'rejected') {
    throw new Error('push_stop_pending');
  }
}

export const pushLifecycle = createPushLifecycle({
  native: capability() === 'native', projectId,
  permission: async () => permissionValue(await Notifications.getPermissionsAsync()),
  requestPermission: async () => permissionValue(await Notifications.requestPermissionsAsync()),
  prepareChannel: async () => {
    if (Platform.OS === 'android') await Notifications.setNotificationChannelAsync('default', {
      name: 'Aggiornamenti ORA', importance: Notifications.AndroidImportance.DEFAULT,
    });
  },
  device: deviceHandle,
  token: async id => {
    const work = Notifications.getExpoPushTokenAsync({ projectId: id });
    // Expo has no AbortSignal parameter. If it finishes after our deadline
    // and logout, undo its auto-registration without touching a new account.
    void work.then(() => {
      if (!pushLifecycle.hasSession()) return stopNative().catch(() => undefined);
    }).catch(() => undefined);
    return (await bounded(work)).data;
  },
  register: async (session, token, device, requestDeliveryPermission) => api.registerPushDevice({
    token, device, platform: Platform.OS, permission_state: 'granted',
    device_revision: await registrationRevision(),
    request_delivery_permission: requestDeliveryPermission,
  }, session.token),
  release: (session, device) => api.releasePushDevice(device, session.token),
  stopNative,
});

export const sessionCleanup = createSessionCleanup({
  read: async () => {
    // Use the throwing native API here: an inaccessible keychain is not an
    // empty queue and must never cause an older pending revocation to be lost.
    const raw = capability() === 'native'
      ? await SecureStore.getItemAsync(CLEANUP_KEY)
      : await storage.secureGet<string>(CLEANUP_KEY, '');
    if (!raw) return [];
    const rows: unknown = JSON.parse(raw);
    if (!Array.isArray(rows)) throw new Error('invalid_session_cleanup');
    return rows.filter((row): row is PendingSessionCleanup =>
      row && typeof row.token === 'string' && row.token.length > 0
      && (row.device === null || typeof row.device === 'string')
      && (row.expiresAt === null || (typeof row.expiresAt === 'number' && Number.isFinite(row.expiresAt))));
  },
  write: async rows => {
    if (capability() === 'native') {
      if (rows.length) await SecureStore.setItemAsync(CLEANUP_KEY, JSON.stringify(rows));
      else await SecureStore.deleteItemAsync(CLEANUP_KEY);
    } else {
      const ok = rows.length
        ? await storage.secureSet(CLEANUP_KEY, JSON.stringify(rows))
        : await storage.secureRemove(CLEANUP_KEY);
      if (!ok) throw new Error('session_cleanup_storage_failed');
    }
  },
  revoke: async job => {
    // The captured old credential is only used for its own device/session.
    // Never read the current authToken while finishing somebody else's exit.
    if (job.device) {
      try { await api.releasePushDevice(job.device, job.token); } catch { /* logout below is the session fence */ }
    }
    try {
      const result = await api.logout(job.token);
      if (!result.ok) throw new Error('session_cleanup_pending');
    } catch (error) {
      // An already-invalid credential cannot own an active bound endpoint.
      if ((error as { status?: number })?.status !== 401) throw error;
    }
  },
  now: Date.now,
});

function tokenExpiry(token: string): number | null {
  try {
    const raw = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const claims = JSON.parse(atob(raw.padEnd(Math.ceil(raw.length / 4) * 4, '=')));
    return typeof claims.exp === 'number' && Number.isFinite(claims.exp) ? claims.exp * 1000 : null;
  } catch { return null; }
}

export function activatePushSession(session: PushSession): void {
  pushLifecycle.setSession(session);
}
export function enablePush() { return pushLifecycle.reconcile(true); }
export function reconcilePush() { return pushLifecycle.reconcile(false); }
export function releasePush() { return pushLifecycle.release(); }

/** Stage a protected retry before local credentials are removed; never block exit on network. */
export async function endPushSession(token: string | null): Promise<void> {
  const release = releasePush();
  if (capability() === 'native') void Promise.allSettled([
    Notifications.dismissAllNotificationsAsync(), Notifications.clearLastNotificationResponseAsync(),
  ]);
  // Native cleanup is also attempted while offline. Its outcome does not
  // turn a pending server revocation into a claimed success.
  void release.catch(() => undefined);
  if (token) {
    const device = capability() === 'native' ? await deviceHandle().catch(() => null) : null;
    await sessionCleanup.add({ token, device, expiresAt: tokenExpiry(token) });
  }
  void sessionCleanup.flush();
}
