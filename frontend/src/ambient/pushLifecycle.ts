/** Session-bound push registration; native and HTTP effects are injected. */
export type PushSession = { ownerId: string; token: string };
export type PushPermission = {
  status: 'granted' | 'denied' | 'undetermined';
  canAskAgain: boolean;
};
export type PushState = 'idle' | 'granted' | 'denied' | 'undetermined'
  | 'unsupported' | 'no_project' | 'needs_consent' | 'delivery_unavailable' | 'error';
export type PushSnapshot = {
  ownerId: string | null;
  state: PushState;
  busy: boolean;
  canAskAgain: boolean;
};
export type PushOutcome = { ok: boolean; state: PushState };
export type PushRelease = { serverReleased: boolean; nativeStopped: boolean };

type Dependencies = {
  native: boolean;
  projectId: () => string | undefined;
  permission: () => Promise<PushPermission>;
  requestPermission: () => Promise<PushPermission>;
  prepareChannel: () => Promise<void>;
  device: () => Promise<string>;
  token: (projectId: string) => Promise<string>;
  register: (session: PushSession, token: string, device: string, requestDeliveryPermission: boolean) => Promise<{
    ok: boolean; delivery_allowed?: boolean; delivery_available?: boolean;
  }>;
  release: (session: PushSession, device: string) => Promise<{ ok: boolean }>;
  stopNative: () => Promise<void>;
};

export function createPushLifecycle(deps: Dependencies) {
  let session: PushSession | null = null;
  let generation = 0;
  let snapshot: PushSnapshot = {
    ownerId: null, state: deps.native ? 'idle' : 'unsupported', busy: false, canAskAgain: true,
  };
  const listeners = new Set<() => void>();
  let tail: Promise<unknown> = Promise.resolve();
  let pending: { generation: number; ask: boolean; promise: Promise<PushOutcome> } | null = null;

  function publish(next: PushSnapshot) {
    snapshot = next;
    listeners.forEach(listener => listener());
  }
  function enqueue<T>(work: () => Promise<T>): Promise<T> {
    const next = tail.then(work, work);
    tail = next.catch(() => undefined);
    return next;
  }
  function setSession(next: PushSession | null) {
    if (session?.ownerId === next?.ownerId && session?.token === next?.token) return;
    session = next;
    generation += 1;
    publish({
      ownerId: next?.ownerId ?? null, state: deps.native ? 'idle' : 'unsupported',
      busy: false, canAskAgain: true,
    });
  }

  async function releaseFor(previous: PushSession | null): Promise<PushRelease> {
    if (!deps.native) return { serverReleased: true, nativeStopped: true };
    const [server, native] = await Promise.allSettled([
      previous
        ? deps.device().then(device => deps.release(previous, device))
        : Promise.resolve({ ok: true }),
      deps.stopNative(),
    ]);
    return {
      serverReleased: server.status === 'fulfilled' && server.value.ok,
      nativeStopped: native.status === 'fulfilled',
    };
  }

  function release(): Promise<PushRelease> {
    const previous = session;
    // Fence immediately, before waiting for an in-flight token/HTTP request.
    // Any write already underway finishes before the exact old session is
    // released; a new login's registration is queued after that release.
    setSession(null);
    return enqueue(() => releaseFor(previous));
  }

  function reconcile(ask = false): Promise<PushOutcome> {
    if (!deps.native) return Promise.resolve({ ok: false, state: 'unsupported' });
    const current = session;
    const version = generation;
    if (!current) return Promise.resolve({ ok: false, state: 'idle' });
    if (pending?.generation === version && (!ask || pending.ask)) return pending.promise;

    const isCurrent = () => generation === version && session === current;
    const finish = (state: PushState, canAskAgain = snapshot.canAskAgain): PushOutcome => {
      if (!isCurrent()) return { ok: false, state: 'idle' };
      publish({ ownerId: current.ownerId, state, busy: false, canAskAgain });
      return { ok: state === 'granted', state };
    };
    const promise = enqueue(async () => {
      if (!isCurrent()) return { ok: false, state: 'idle' } as PushOutcome;
      publish({ ...snapshot, busy: true });
      try {
        let permission = await deps.permission();
        if (!isCurrent()) return { ok: false, state: 'idle' } as PushOutcome;
        const id = deps.projectId();
        if (ask && permission.status !== 'granted') {
          // Do not ask for OS permission when this build cannot register.
          if (!id) return finish('no_project', permission.canAskAgain);
          if (permission.canAskAgain) {
            await deps.prepareChannel();
            if (!isCurrent()) return { ok: false, state: 'idle' } as PushOutcome;
            permission = await deps.requestPermission();
          }
        }
        if (!isCurrent()) return { ok: false, state: 'idle' } as PushOutcome;
        if (permission.status !== 'granted') {
          // Permission may have been revoked in Settings since the last
          // foreground. Retire the old endpoint without prompting again.
          const result = await releaseFor(current);
          if (!result.serverReleased && !result.nativeStopped) return finish('error', permission.canAskAgain);
          return finish(permission.status, permission.canAskAgain);
        }
        if (!id) return finish('no_project', permission.canAskAgain);
        const device = await deps.device();
        if (!isCurrent()) return { ok: false, state: 'idle' } as PushOutcome;
        const token = await deps.token(id);
        if (!isCurrent()) return { ok: false, state: 'idle' } as PushOutcome;
        const result = await deps.register(current, token, device, ask);
        const state = !result.ok ? 'error'
          : result.delivery_available === false ? 'delivery_unavailable'
          : result.delivery_allowed === true ? 'granted' : 'needs_consent';
        return finish(state, permission.canAskAgain);
      } catch {
        return finish('error');
      }
    });
    pending = { generation: version, ask, promise };
    void promise.finally(() => { if (pending?.promise === promise) pending = null; });
    return promise;
  }

  return {
    setSession, reconcile, release,
    hasSession: () => session !== null,
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
  };
}

/** The Home reload does not own notification errors or hide their retry. */
export function pushRecovery(snapshot: PushSnapshot): {
  message: string; actionLabel: string | null; action: 'enable' | 'settings' | null;
} | null {
  switch (snapshot.state) {
    case 'error': return {
      message: 'Non sono riuscito ad attivare le notifiche su questo telefono. Gli aggiornamenti restano in ORA.',
      actionLabel: 'Riprova', action: 'enable',
    };
    case 'denied': return {
      message: 'Le notifiche sono disattivate su questo telefono. Puoi abilitarle quando vuoi.',
      actionLabel: snapshot.canAskAgain ? 'Attiva notifiche' : 'Apri impostazioni',
      action: snapshot.canAskAgain ? 'enable' : 'settings',
    };
    case 'needs_consent': return {
      message: 'Per ricevere gli aggiornamenti con ORA chiusa, attiva le notifiche per questo account.',
      actionLabel: 'Attiva notifiche', action: 'enable',
    };
    case 'delivery_unavailable': return {
      message: 'Le notifiche di ORA non sono disponibili in questo momento. Gli aggiornamenti restano nell’app.',
      actionLabel: null, action: null,
    };
    case 'no_project': return {
      message: 'Questa versione dell’app non è ancora collegata alle notifiche. Gli aggiornamenti restano in ORA.',
      actionLabel: null, action: null,
    };
    case 'unsupported': return {
      message: 'Le notifiche con ORA chiusa sono disponibili nell’app per telefono. Qui trovi gli aggiornamenti quando riapri ORA.',
      actionLabel: null, action: null,
    };
    default: return null;
  }
}
