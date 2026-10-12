/** Auth is unknown during a failed read; only 401/403 disprove a session. */
export type SessionSnapshot<U> = {
  user: U | null;
  loading: boolean;
  refreshing: boolean;
  recovery: boolean;
};
type Dependencies<U> = {
  readToken: () => Promise<string | null>;
  writeToken: (token: string) => Promise<boolean>;
  clearToken: () => Promise<void>;
  me: (token: string) => Promise<U>;
  activate: (token: string, user: U) => void;
  end: (token: string | null, invalid: boolean) => Promise<void>;
  resetOpening: () => void;
};

export function createSessionLifecycle<U extends { user_id: string }>(deps: Dependencies<U>) {
  let snapshot: SessionSnapshot<U> = { user: null, loading: true, refreshing: false, recovery: false };
  let token: string | null = null;
  let revision = 0;
  let refreshing: { revision: number; promise: Promise<void> } | null = null;
  let ending: Promise<void> | null = null;
  let mutations = 0;
  let mutationTail: Promise<void> = Promise.resolve();
  const endedTokens = new Set<string>();
  const listeners = new Set<() => void>();
  function publish(patch: Partial<SessionSnapshot<U>>) {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach(listener => listener());
  }
  function mutate(work: () => Promise<void>): Promise<void> {
    mutations += 1;
    const result = mutationTail.then(work, work).finally(() => { mutations -= 1; });
    mutationTail = result.catch(() => undefined);
    return result;
  }
  async function endCurrent(invalid: boolean) {
    const previous = token ?? await deps.readToken().catch(() => null);
    if (previous) endedTokens.add(previous);
    try { await deps.end(previous, invalid); } catch {
      // The device layer stages an unfinished revocation in protected storage.
      // A failed network/keychain effect must never block local logout.
    }
    try { await deps.clearToken(); } catch { /* Local auth state still ends. */ }
    token = null;
    deps.resetOpening();
  }

  function signOut(invalid = false): Promise<void> {
    if (ending) return ending;
    const version = ++revision;
    publish({ loading: true, refreshing: false, recovery: false });
    const result = mutate(async () => {
      await endCurrent(invalid);
      if (version === revision) publish({ user: null, loading: false, refreshing: false, recovery: false });
    });
    ending = result.finally(() => { ending = null; });
    return ending;
  }

  function refresh(): Promise<void> {
    if (mutations) return mutationTail;
    const version = revision;
    if (refreshing?.revision === version) return refreshing.promise;
    publish({ refreshing: true });
    const run = async () => {
      try {
        const stored = await deps.readToken();
        if (version !== revision) return;
        token = stored;
        if (!stored || endedTokens.has(stored)) {
          deps.resetOpening();
          publish({ user: null, loading: false, refreshing: false, recovery: false });
          return;
        }
        const user = await deps.me(stored);
        if (version !== revision) return;
        deps.activate(stored, user);
        publish({ user, loading: false, refreshing: false, recovery: false });
      } catch (error) {
        if (version !== revision) return;
        const status = (error as { status?: number } | null)?.status;
        if (status === 401 || status === 403) await signOut(true);
        else publish({ loading: false, refreshing: false, recovery: true });
      }
    };
    const promise = run();
    refreshing = { revision: version, promise };
    void promise.finally(() => { if (refreshing?.promise === promise) refreshing = null; });
    return promise;
  }

  function signIn(next: string, user: U): Promise<void> {
    const version = ++revision;
    publish({ loading: true, refreshing: false, recovery: false });
    return mutate(async () => {
      if (version !== revision) return;
      const previous = token ?? await deps.readToken();
      if (previous && previous !== next) await endCurrent(false);
      if (version !== revision) return;
      const persisted = await deps.writeToken(next);
      if (!persisted) {
        if (version === revision) publish({ user: null, loading: false });
        throw new Error('auth_storage_failed');
      }
      // A later sign-in/logout is serialized behind this storage write, so
      // an old credential can never overwrite the winning account's token.
      token = next;
      if (version !== revision) return;
      endedTokens.delete(next);
      deps.resetOpening();
      deps.activate(next, user);
      publish({ user, loading: false, refreshing: false, recovery: false });
    });
  }

  return {
    refresh, signIn, signOut: () => signOut(),
    updateUser: (user: U) => publish({ user }),
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  };
}
