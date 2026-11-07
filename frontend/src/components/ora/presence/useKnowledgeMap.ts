import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { api } from '@/src/api/client';
import { changedStars, newStars, type KnowledgeMap } from './knowledge';

// Two presences can be mounted at once (the chat strip and the map behind it):
// on 6/11 every activity change fetched the map twice in the same instant. A
// read already in flight for the same account is shared, never kept.
// Only a read still on the way is shared: once it lands, the next read is a
// fresh one (a deleted node must disappear on the reload that follows).
let shared: { owner: string; promise: Promise<KnowledgeMap> } | null = null;
export function readKnowledgeMap(owner: string): Promise<KnowledgeMap> {
  if (shared && shared.owner === owner) return shared.promise;
  const promise = api.knowledgeMap();
  const mine = { owner, promise };
  shared = mine;
  const done = () => { if (shared === mine) shared = null; };
  promise.then(done, done);
  return promise;
}

/** No persistent copy of personal information; late responses cannot cross accounts. */
export function useKnowledgeMap(userId?: string, active = true, refreshKey?: unknown) {
  const [result, setResult] = useState<{ owner: string; data: KnowledgeMap; addedIds: string[]; changedIds: string[] } | null>(null);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const ticket = ++generation.current;
    if (!userId || !active) return;
    let live = true;
    let latestRead = 0;
    const read = async () => {
      const readId = ++latestRead;
      try {
        const data = await readKnowledgeMap(userId);
        if (live && generation.current === ticket && readId === latestRead) {
          setResult(prev => {
            const previous = prev?.owner === userId ? prev.data : null;
            return {
              owner: userId,
              data,
              addedIds: newStars(previous, data).map(star => star.id),
              changedIds: changedStars(previous, data).map(star => star.id),
            };
          });
          setError(false);
        }
      } catch { if (live && generation.current === ticket && readId === latestRead) setError(true); }
    };
    void read();
    const app = AppState.addEventListener('change', state => { if (state === 'active') void read(); });
    return () => { live = false; app.remove(); };
  }, [userId, active, refreshKey, retry]);
  const reload = useCallback(() => setRetry(v => v + 1), []);
  const current = result?.owner === userId ? result : null;
  const addedStars = useMemo(() => current?.data.stars.filter(star => current.addedIds.includes(star.id)) ?? [], [current]);
  const changed = useMemo(() => current?.data.stars.filter(star => current.changedIds.includes(star.id)) ?? [], [current]);
  return { data: current?.data ?? null, added: current?.addedIds.length ?? 0,
    addedStars, changedStars: changed, error, reload };
}
