/**
 * Asking to be reachable, and only when there is a reason.
 *
 * Two rules shape this file, and both are about restraint.
 *
 * The permission is never requested on launch. Asked then, the question is
 * about a feature and the honest answer is no; asked when ORA has actually
 * judged something worth reaching somebody for, it is about that thing. The
 * backend decides when that moment has come — `permission_moment` on Home is
 * present only while a real decision is waiting on it.
 *
 * And the web does not pretend. Expo push tokens are a native capability, and
 * a browser that asked for notification permission and then registered
 * nothing would be theatre. `capability()` says what this platform can
 * actually do so a surface can offer the truth.
 */
import { Platform } from 'react-native';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

import { api } from '@/src/api/client';

export type PushCapability = 'native' | 'unsupported';

export type PushOutcome =
  | { ok: true; state: 'granted' }
  | { ok: false; state: 'denied' | 'unsupported' | 'no_project' | 'error'; detail?: string };

/** What this platform can genuinely do about notifications. */
export function capability(): PushCapability {
  return Platform.OS === 'ios' || Platform.OS === 'android' ? 'native' : 'unsupported';
}

/**
 * The Expo project this build belongs to.
 *
 * A push token is issued against a project, so without an id there is nothing
 * to ask for. Returning undefined here — rather than inventing one — is what
 * makes the failure legible instead of mysterious.
 */
function projectId(): string | undefined {
  const extra = (Constants.expoConfig?.extra ?? {}) as Record<string, unknown>;
  const eas = (extra.eas ?? {}) as Record<string, unknown>;
  const fromEas = typeof eas.projectId === 'string' ? eas.projectId : undefined;
  return fromEas || (Constants as unknown as { easConfig?: { projectId?: string } })
    .easConfig?.projectId;
}

/** Whether the OS has already been asked, without asking again. */
export async function currentPermission(): Promise<'granted' | 'denied' | 'undetermined'> {
  if (capability() !== 'native') return 'denied';
  try {
    const { status } = await Notifications.getPermissionsAsync();
    if (status === 'granted') return 'granted';
    return status === 'denied' ? 'denied' : 'undetermined';
  } catch {
    return 'undetermined';
  }
}

/**
 * Ask, and if allowed, tell the backend which device to reach.
 *
 * The token goes straight to the server and is never stored on the device by
 * us: it is a capability to put text on this person's lock screen, and the
 * fewer places it exists, the better. If they say no, ORA carries on with
 * quiet presence and in-app cards, and nothing here asks again.
 */
export async function enablePush(): Promise<PushOutcome> {
  if (capability() !== 'native') {
    return { ok: false, state: 'unsupported' };
  }

  let status: string;
  try {
    const existing = await Notifications.getPermissionsAsync();
    status = existing.status;
    if (status !== 'granted') {
      const asked = await Notifications.requestPermissionsAsync();
      status = asked.status;
    }
  } catch (e) {
    return { ok: false, state: 'error', detail: String(e).slice(0, 120) };
  }

  if (status !== 'granted') {
    // Honest degradation: the decision layer is told, so a push it cannot
    // make becomes a quiet line rather than nothing at all.
    await api
      .registerPushDevice({ token: '', permission_state: 'denied' })
      .catch(() => {});
    return { ok: false, state: 'denied' };
  }

  const id = projectId();
  if (!id) {
    // No EAS project on this build. Nothing to invent — the permission is
    // granted and there is simply no address yet.
    return { ok: false, state: 'no_project' };
  }

  try {
    const token = (await Notifications.getExpoPushTokenAsync({ projectId: id })).data;
    await api.registerPushDevice({
      token,
      platform: Platform.OS === 'ios' ? 'ios' : 'android',
      device: deviceHandle(),
      permission_state: 'granted',
    });
    return { ok: true, state: 'granted' };
  } catch (e) {
    return { ok: false, state: 'error', detail: String(e).slice(0, 120) };
  }
}

/**
 * Release this device on the way out.
 *
 * A token left active for an account somebody just signed out of is how one
 * person's notification arrives on another person's phone.
 */
export async function releasePush(): Promise<void> {
  if (capability() !== 'native') return;
  await api.releasePushDevice(deviceHandle()).catch(() => {});
}

/**
 * A stable-enough handle for this installation.
 *
 * Only its hash is stored server-side. It exists to recognise the same phone
 * signing in again, not to identify anybody.
 */
function deviceHandle(): string {
  const id =
    (Constants as unknown as { sessionId?: string }).sessionId ||
    Constants.expoConfig?.slug ||
    'unknown';
  return `${Platform.OS}:${id}`;
}
