/**
 * A stable opaque identity for this app installation.
 *
 * Separate from app slug and runtime session ID: two phones using ORA must
 * never overwrite each other's registered push endpoints. No hardware ID,
 * user identity, push token, or other personal information is stored here.
 */
// SecureStore rejects ':' before reaching the keychain. The old key could
// never be written by its native API; use its documented safe alphabet.
export const PUSH_DEVICE_KEY = 'ora.push.installation-handle.v2';
export const PUSH_REVISION_KEY = 'ora.push.registration-revision.v1';

export type HandleStore = {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
};

export function createInstallationHandle(
  platform: string,
  storage: HandleStore,
  randomId: () => string,
): () => Promise<string> {
  let pending: Promise<string> | null = null;

  return () => {
    if (!pending) {
      pending = (async () => {
        const saved = await storage.getItemAsync(PUSH_DEVICE_KEY);
        const id = saved || randomId();
        if (!saved) await storage.setItemAsync(PUSH_DEVICE_KEY, id);
        return `${platform}:${id}`;
      })().catch(error => {
        pending = null;
        throw error;
      });
    }
    return pending;
  };
}

/** Persisted ordering survives logout/restart and fences delayed old HTTP writes. */
export function createRegistrationRevision(storage: HandleStore): () => Promise<number> {
  let tail: Promise<unknown> = Promise.resolve();
  return () => {
    const next = tail.then(async () => {
      const raw = await storage.getItemAsync(PUSH_REVISION_KEY);
      const previous = raw === null ? 0 : Number(raw);
      if (!Number.isSafeInteger(previous) || previous < 0 || previous >= Number.MAX_SAFE_INTEGER) {
        throw new Error('invalid_push_registration_revision');
      }
      const revision = previous + 1;
      await storage.setItemAsync(PUSH_REVISION_KEY, String(revision));
      return revision;
    });
    tail = next.catch(() => undefined);
    return next;
  };
}
