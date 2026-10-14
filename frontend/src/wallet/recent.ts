import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';

/**
 * Only opaque card IDs are remembered on this device; NEVER codes, images,
 * names, or decoded barcode payloads. Scoped to the signed-in owner.
 * This is an ordering aid, NOT an offline copy of the wallet.
 */
const VALID_ID = /^[0-9a-f]{32}$/;
const MAX_RECENT = 8;
let writeQueue: Promise<unknown> = Promise.resolve();

export function cleanRecent(input: unknown): string[] {
  if (!Array.isArray(input)) return [];
  return [...new Set(input.filter((id): id is string =>
    typeof id === 'string' && VALID_ID.test(id)))].slice(0, MAX_RECENT);
}

export function orderCards<T extends { id: string; favorite: boolean; name: string }>(
  cards: readonly T[], recent: readonly string[],
): T[] {
  const ranks = new Map(cleanRecent([...recent]).map((id, index) => [id, index]));
  return [...cards].sort((a, b) =>
    Number(b.favorite) - Number(a.favorite)
    || (ranks.get(a.id) ?? 999) - (ranks.get(b.id) ?? 999)
    || a.name.localeCompare(b.name, 'it', { sensitivity: 'base' })
    || a.id.localeCompare(b.id));
}

async function storageKey(owner: string): Promise<string> {
  const digest = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, owner);
  return 'ora_wallet_recent_v1_' + digest;
}

async function read(key: string): Promise<string[]> {
  const raw = await AsyncStorage.getItem(key);
  if (!raw) return [];
  try { return cleanRecent(JSON.parse(raw)); } catch { return []; }
}

export async function getRecent(owner: string): Promise<string[]> {
  const key = await storageKey(owner);
  await writeQueue.catch(() => undefined);
  return read(key);
}

export function recordRecent(owner: string, id: string): Promise<string[]> {
  if (!VALID_ID.test(id)) return Promise.resolve([]);
  const operation = writeQueue.then(async () => {
    const key = await storageKey(owner);
    const current = await read(key);
    const updated = cleanRecent([id, ...current]);
    await AsyncStorage.setItem(key, JSON.stringify(updated));
    return updated;
  });
  writeQueue = operation.catch(() => undefined);
  return operation;
}

export function forgetRecent(owner: string, id: string): Promise<string[]> {
  const operation = writeQueue.then(async () => {
    const key = await storageKey(owner);
    const updated = (await read(key)).filter(value => value !== id);
    await AsyncStorage.setItem(key, JSON.stringify(updated));
    return updated;
  });
  writeQueue = operation.catch(() => undefined);
  return operation;
}

export async function clearRecent(owner: string): Promise<void> {
  await writeQueue.catch(() => undefined);
  await AsyncStorage.removeItem(await storageKey(owner));
}
