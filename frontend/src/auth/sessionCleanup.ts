/** A logout credential is kept only to finish its own revocation, never login. */
export const PENDING_SESSION_CLEANUP_KEY = 'ora.auth.pending-revocations.v1';
export type PendingSessionCleanup = {
  token: string;
  device: string | null;
  expiresAt: number | null;
};
type Dependencies = {
  read: () => Promise<PendingSessionCleanup[]>;
  write: (pending: PendingSessionCleanup[]) => Promise<void>;
  revoke: (pending: PendingSessionCleanup) => Promise<void>;
  now: () => number;
};

export function createSessionCleanup(deps: Dependencies) {
  let pending: PendingSessionCleanup[] = [];
  let loaded: Promise<void> | null = null;
  let loadSucceeded = false;
  let tail: Promise<unknown> = Promise.resolve();
  let flushing: Promise<void> | null = null;
  let snapshot = { pending: false, busy: false, storageError: false };
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<typeof snapshot> = {}) => {
    snapshot = { ...snapshot, pending: pending.length > 0, ...patch };
    listeners.forEach(listener => listener());
  };
  const ensureLoaded = () => loaded ??= deps.read().then(rows => {
    pending = [...rows, ...pending.filter(row => !rows.some(saved => saved.token === row.token))];
    loadSucceeded = true;
    publish();
  }).catch(() => {
    loaded = null;
    publish({ storageError: true });
  });
  const persist = async () => {
    if (!loadSucceeded) return;
    try { await deps.write(pending); publish({ storageError: false }); }
    catch { publish({ storageError: true }); }
  };
  const enqueue = <T>(work: () => Promise<T>): Promise<T> => {
    const next = tail.then(work, work);
    tail = next.catch(() => undefined);
    return next;
  };
  const add = (job: PendingSessionCleanup) => enqueue(async () => {
    await ensureLoaded();
    if (!pending.some(row => row.token === job.token)) pending.push(job);
    publish();
    await persist();
  });
  const flush = (): Promise<void> => {
    if (flushing) return flushing;
    flushing = (async () => {
      const jobs = await enqueue(async () => {
        await ensureLoaded();
        publish({ busy: pending.length > 0 });
        return [...pending];
      });
      for (const job of jobs) {
        // Expired bindings cannot deliver; do not retain unusable credentials.
        if (job.expiresAt === null || job.expiresAt > deps.now()) {
          try { await deps.revoke(job); }
          catch { continue; }
        }
        await enqueue(async () => {
          pending = pending.filter(row => row.token !== job.token);
          await persist();
          publish();
        });
      }
      await enqueue(persist);
      publish({ busy: false });
    })().finally(() => { flushing = null; });
    return flushing;
  };
  return {
    add, flush,
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  };
}
