/**
 * A stable opaque identity for this app installation.
 *
 * Separate from app slug and runtime session ID: two phones using ORA must
 * never overwrite each other's registered push endpoints. No hardware ID,
 * user identity, push token, or other personal information is stored here.
 */
export const PUSH_DEVICE_KEY = 'ora:push:installation-handle:v2';

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
