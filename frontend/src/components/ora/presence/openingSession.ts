/** One entrance per conversation, independent of chat/voice/navigation mounts.
 * Web survives reload in the same tab; native resets on a cold launch. No tokens
 * or conversation content are stored. Storage denial falls back to process state.
 */
type Storage = Pick<globalThis.Storage, 'getItem' | 'setItem' | 'removeItem'>;
const KEY = 'ora.presence.opened.v1';
export function createOpeningSession(storage: () => Storage | undefined) {
  const seen = new Set<string>();
  return {
    claim(owner: string, conversation: string): boolean {
      if (!owner || !conversation) return false;
      const identity = `${owner}:${conversation}`;
      if (seen.has(identity)) return false;
      try {
        const saved: unknown = JSON.parse(storage()?.getItem(KEY) || '[]');
        if (Array.isArray(saved)) for (const item of saved.slice(-128)) if (typeof item === 'string') seen.add(item);
      } catch { /* Private mode or old storage. */ }
      const first = !seen.has(identity);
      seen.add(identity);
      while (seen.size > 128) seen.delete(seen.values().next().value!);
      try { storage()?.setItem(KEY, JSON.stringify([...seen])); } catch { /* Process state suffices. */ }
      return first;
    },
    reset() {
      seen.clear();
      try { storage()?.removeItem(KEY); } catch { /* Private mode. */ }
    },
  };
}
export const openingSession = createOpeningSession(() =>
  typeof window === 'undefined' ? undefined : window.sessionStorage);
