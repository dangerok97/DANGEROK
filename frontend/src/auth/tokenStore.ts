/** A non-secret logout tombstone prevents a failed keychain delete from restoring a session. */
export function createTokenStore(deps: {
  readToken: () => Promise<string | null>;
  writeToken: (token: string) => Promise<void>;
  removeToken: () => Promise<void>;
  readSignedOut: () => Promise<boolean>;
  writeSignedOut: (value: boolean) => Promise<void>;
  isRevocationPending: (token: string) => Promise<boolean>;
}) {
  let signedOut = false;
  return {
    async get(): Promise<string | null> {
      if (signedOut) return null;
      if (await deps.readSignedOut()) { signedOut = true; return null; }
      const token = await deps.readToken();
      if (token && await deps.isRevocationPending(token)) {
        signedOut = true;
        return null;
      }
      return token;
    },
    async set(token: string): Promise<boolean> {
      try {
        await deps.writeToken(token);
        await deps.writeSignedOut(false);
        signedOut = false;
        return true;
      } catch { return false; }
    },
    async clear(): Promise<void> {
      // The in-memory fence takes effect before either asynchronous store.
      signedOut = true;
      await Promise.allSettled([deps.writeSignedOut(true), deps.removeToken()]);
    },
  };
}
