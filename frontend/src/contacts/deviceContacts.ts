/**
 * Native address-book bridge.
 *
 * The system permission is requested only from an explicit user action.
 * Once enabled, foreground reconciliation may refresh the minimal callable
 * index without prompting again. The backend receives only names,
 * organisation/aliases and phone numbers — never email, address, notes,
 * birthday or photos.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

import { api } from '@/src/api/client';
import {
  minimalContact,
  permissionFromResponse,
  type ContactPermission,
  type MinimalContact,
} from './contract';

export { minimalContact, permissionFromResponse } from './contract';
export type { ContactPermission, MinimalContact } from './contract';

const ENABLED_KEY = 'ora.contacts.enabled.v1';
const REVOKE_PENDING_KEY = 'ora.contacts.revokePending.v1';
const MAX_CONTACTS = 2000;

function native(): boolean {
  return Platform.OS === 'ios' || Platform.OS === 'android';
}

async function contactsModule(): Promise<any> {
  return await import('expo-contacts');
}

export function support(): { supported: boolean; reason?: string } {
  if (!native()) {
    return {
      supported: false,
      reason: 'La rubrica del dispositivo è disponibile nell’app installata.',
    };
  }
  return { supported: true };
}

export async function isEnabled(): Promise<boolean> {
  try {
    return (await AsyncStorage.getItem(ENABLED_KEY)) === '1';
  } catch {
    return false;
  }
}

export async function permission(): Promise<ContactPermission> {
  if (!native()) return 'unavailable';
  try {
    const Contacts = await contactsModule();
    return permissionFromResponse(await Contacts.getPermissionsAsync());
  } catch {
    return 'unavailable';
  }
}

async function pushRevocation(state: ContactPermission): Promise<boolean> {
  try {
    await api.contactsSync({ permission: state, contacts: [] });
    await AsyncStorage.removeItem(REVOKE_PENDING_KEY);
    return true;
  } catch {
    await AsyncStorage.setItem(REVOKE_PENDING_KEY, state);
    return false;
  }
}

async function retryPendingRevocation(): Promise<void> {
  let pending: string | null = null;
  try {
    pending = await AsyncStorage.getItem(REVOKE_PENDING_KEY);
  } catch {
    return;
  }
  if (!pending) return;
  const state: ContactPermission =
    pending === 'denied' || pending === 'unavailable' || pending === 'not_requested'
      ? pending
      : 'not_requested';
  await pushRevocation(state);
}

export async function syncNow(): Promise<{ ok: boolean; stored?: number; reason?: string }> {
  await retryPendingRevocation();
  if (!native() || !(await isEnabled())) return { ok: false, reason: 'disabled' };

  const Contacts = await contactsModule();
  const state = permissionFromResponse(await Contacts.getPermissionsAsync());
  if (state !== 'granted' && state !== 'limited') {
    const deleted = await pushRevocation(state);
    if (deleted) await AsyncStorage.setItem(ENABLED_KEY, '0');
    return { ok: false, reason: state };
  }

  const fields = Contacts.Fields?.PhoneNumbers
    ? [Contacts.Fields.PhoneNumbers]
    : undefined;
  const result = await Contacts.getContactsAsync({
    fields,
    pageSize: MAX_CONTACTS,
    pageOffset: 0,
  });

  const contacts: MinimalContact[] = [];
  for (const raw of Array.isArray(result?.data) ? result.data : []) {
    const item = minimalContact(raw);
    if (item) contacts.push(item);
    if (contacts.length >= MAX_CONTACTS) break;
  }

  const synced = await api.contactsSync({ permission: state, contacts });
  return { ok: true, stored: synced.stored ?? contacts.length };
}

export async function enable(): Promise<{ ok: boolean; stored?: number; reason?: string }> {
  const can = support();
  if (!can.supported) return { ok: false, reason: can.reason };

  const Contacts = await contactsModule();
  let state = permissionFromResponse(await Contacts.getPermissionsAsync());
  if (state === 'not_requested') {
    state = permissionFromResponse(await Contacts.requestPermissionsAsync());
  }
  if (state !== 'granted' && state !== 'limited') {
    await AsyncStorage.setItem(ENABLED_KEY, '0');
    await pushRevocation(state);
    return {
      ok: false,
      reason:
        'Senza il permesso Rubrica ORA non può associare i nomi ai contatti salvati. Tutto il resto continua a funzionare.',
    };
  }

  await AsyncStorage.setItem(ENABLED_KEY, '1');
  return syncNow();
}

export async function disable(): Promise<void> {
  await AsyncStorage.setItem(ENABLED_KEY, '0');
  await AsyncStorage.setItem(REVOKE_PENDING_KEY, 'not_requested');
  await pushRevocation('not_requested');
}

export async function reconcile(): Promise<void> {
  await retryPendingRevocation();
  if (!(await isEnabled())) return;
  try {
    await syncNow();
  } catch {
    // Offline is ordinary. Enabled stays true so the next foreground pass retries.
  }
}

export async function state(): Promise<ContactsState> {
  const can = support();
  if (!can.supported) {
    return {
      supported: false,
      enabled: false,
      permission: 'unavailable',
      contacts: 0,
      reason: can.reason,
    };
  }

  const [enabled, permissionState] = await Promise.all([isEnabled(), permission()]);
  let count = 0;
  try {
    count = (await api.contactsStatus()).contacts ?? 0;
  } catch {
    // The native permission remains truthful even if the server is offline.
  }
  return {
    supported: true,
    enabled: enabled && (permissionState === 'granted' || permissionState === 'limited'),
    permission: permissionState,
    contacts: count,
  };
}
