import { Platform } from 'react-native';
import { api } from '@/src/api/client';

export type MinimalDeviceContact = {
  id: string;
  name: string;
  organization: string;
  aliases: string[];
  phones: string[];
  kind: 'person' | 'business';
};

export function minimalContactsPayload(rows: any[]): MinimalDeviceContact[] {
  const out: MinimalDeviceContact[] = [];
  for (const row of (rows || []).slice(0, 1500)) {
    const phones = (row?.phoneNumbers || [])
      .map((p: any) => String(p?.number || '').trim())
      .filter(Boolean)
      .slice(0, 3);
    if (!phones.length) continue;

    const first = String(row?.firstName || '').trim();
    const last = String(row?.lastName || '').trim();
    const name = String(row?.name || [first, last].filter(Boolean).join(' ')).trim();
    const organization = String(row?.company || '').trim();
    if (!name && !organization) continue;

    const aliases = Array.from(new Set([
      first,
      last,
      [first, last].filter(Boolean).join(' '),
    ].filter(Boolean))).slice(0, 4);

    out.push({
      id: String(row?.id || '').slice(0, 120),
      name: (name || organization).slice(0, 160),
      organization: organization.slice(0, 160),
      aliases: aliases.map((v) => String(v).slice(0, 120)),
      phones,
      kind: organization && !name ? 'business' : 'person',
    });
  }
  return out;
}

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
