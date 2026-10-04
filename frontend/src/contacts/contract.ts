export type ContactPermission =
  | 'granted'
  | 'limited'
  | 'denied'
  | 'unavailable'
  | 'not_requested';

export type MinimalContact = {
  device_contact_id: string;
  name: string;
  organization: string;
  aliases: string[];
  phones: Array<{ number: string }>;
};

const MAX_PHONES = 4;
const MAX_ALIASES = 6;

function cleanText(value: unknown, max = 160): string {
  return String(value ?? '').replace(/\s+/g, ' ').trim().slice(0, max);
}

export function permissionFromResponse(response: any): ContactPermission {
  if (!response) return 'unavailable';
  const status = String(response.status ?? '').toLowerCase();
  if (status === 'granted') {
    return String(response.accessPrivileges ?? '').toLowerCase() === 'limited'
      ? 'limited'
      : 'granted';
  }
  if (status === 'denied') return 'denied';
  if (status === 'undetermined') return 'not_requested';
  return 'unavailable';
}

export function minimalContact(raw: any): MinimalContact | null {
  const deviceId = cleanText(raw?.id, 200);
  if (!deviceId) return null;

  const name =
    cleanText(raw?.name) ||
    cleanText([raw?.firstName, raw?.middleName, raw?.lastName].filter(Boolean).join(' '));
  const organization = cleanText(raw?.company || raw?.organization);

  const aliases: string[] = [];
  const addAlias = (value: unknown) => {
    const alias = cleanText(value, 120);
    if (alias && alias !== name && !aliases.includes(alias) && aliases.length < MAX_ALIASES) {
      aliases.push(alias);
    }
  };
  addAlias(raw?.nickname);
  addAlias(raw?.firstName);
  if (raw?.firstName && raw?.lastName) {
    addAlias(`${cleanText(raw.firstName, 60)} ${cleanText(raw.lastName, 60)}`);
  }

  const phones: Array<{ number: string }> = [];
  for (const item of Array.isArray(raw?.phoneNumbers) ? raw.phoneNumbers : []) {
    const number = cleanText(item?.number, 40);
    if (!number || phones.some((p) => p.number === number)) continue;
    phones.push({ number });
    if (phones.length >= MAX_PHONES) break;
  }

  if (!(name || organization) || !phones.length) return null;
  return {
    device_contact_id: deviceId,
    name: name || organization,
    organization,
    aliases,
    phones,
  };
}
