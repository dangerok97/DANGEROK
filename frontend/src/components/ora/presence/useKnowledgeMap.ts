import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState } from 'react-native';
import { api } from '@/src/api/client';
import { newStars, type KnowledgeMap } from './knowledge';

/** No persistent copy of personal information; late responses cannot cross accounts. */
export function useKnowledgeMap(userId?: string, active = true, refreshKey?: unknown) {
  const [result, setResult] = useState<{ owner: string; data: KnowledgeMap; added: number } | null>(null);
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
        const data = await api.knowledgeMap();
        if (live && generation.current === ticket && readId === latestRead) {
          setResult(prev => ({ owner: userId, data, added: newStars(prev?.owner === userId ? prev.data : null, data).length }));
          setError(false);
        }
      } catch { if (live && generation.current === ticket && readId === latestRead) setError(true); }
    };
    void read();
    const app = AppState.addEventListener('change', state => { if (state === 'active') void read(); });
    return () => { live = false; app.remove(); };
  }, [userId, active, refreshKey, retry]);
  const reload = useCallback(() => setRetry(v => v + 1), []);
  return { data: result && result.owner === userId ? result.data : null, added: result && result.owner === userId ? result.added : 0, error, reload };
}
