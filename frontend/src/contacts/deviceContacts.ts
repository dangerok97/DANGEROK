import { Platform } from 'react-native';
import { api } from '@/src/api/client';

import { minimalContactsPayload } from './payload';

let syncing = false;
let lastSyncAt = 0;

export async function reconcileDeviceContacts(opts?: {
  requestIfUndetermined?: boolean;
  force?: boolean;
}): Promise<'synced' | 'denied' | 'unavailable' | 'skipped'> {
  if (Platform.OS !== 'ios' && Platform.OS !== 'android') return 'unavailable';
  if (syncing) return 'skipped';
  if (!opts?.force && Date.now() - lastSyncAt < 5 * 60_000) return 'skipped';

  syncing = true;
  try {
    const Contacts = await import('expo-contacts');
    let permission = await Contacts.getPermissionsAsync();

    if (permission.status === 'undetermined' && opts?.requestIfUndetermined) {
      permission = await Contacts.requestPermissionsAsync();
    }

    if (permission.status !== 'granted') {
      await api.contactsDeviceSync('denied', []).catch(() => undefined);
      lastSyncAt = Date.now();
      return 'denied';
    }

    const result = await Contacts.getContactsAsync({
      fields: [
        Contacts.Fields.Name,
        Contacts.Fields.PhoneNumbers,
        Contacts.Fields.Company,
      ],
    });

    const contacts = minimalContactsPayload(result.data || []);
    await api.contactsDeviceSync('granted', contacts);
    lastSyncAt = Date.now();
    return 'synced';
  } catch {
    return 'unavailable';
  } finally {
    syncing = false;
  }
}
