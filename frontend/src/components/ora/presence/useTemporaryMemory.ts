import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';

import { api } from '@/src/api/client';
import { useAuth } from '@/src/contexts/AuthContext';
import type { KnowledgeStar } from './knowledge';

type TemporaryMemoryRead = { owner: string; stars: KnowledgeStar[]; error: boolean };

function stamp(star: KnowledgeStar): number {
  const value = star.updated_at ? new Date(star.updated_at).getTime() : 0;
  return Number.isFinite(value) ? value : 0;
}

export function useTemporaryMemory(active = true, refreshKey?: unknown) {
  const { user } = useAuth();
  const owner = user?.user_id;
  const [result, setResult] = useState<TemporaryMemoryRead | null>(null);
  const generation = useRef(0);
  const latestRead = useRef(0);
  const live = useRef(false);
  const scope = useRef({ owner, active });
  // Fence a previous owner's completion even before effect cleanup runs.
  scope.current = { owner, active };

  const refresh = useCallback(async () => {
    if (!owner || !active || !live.current
      || scope.current.owner !== owner || !scope.current.active) return;
    const ticket = generation.current;
    const readId = ++latestRead.current;
    const isCurrent = () => live.current && scope.current.owner === owner
      && scope.current.active && generation.current === ticket && readId === latestRead.current;
    try {
      const map = await api.knowledgeMap();
      if (!isCurrent()) return;
      const stars = (map.stars || [])
        .filter((star) => star.temporary)
        .sort((a, b) => stamp(b) - stamp(a));
      setResult(previous => isCurrent() ? { owner, stars, error: false } : previous);
    } catch {
      // Keep context, but a failed current read cannot leave advice actionable.
      if (!isCurrent()) return;
      setResult(previous => isCurrent() ? {
        owner, stars: previous?.owner === owner ? previous.stars : [], error: true,
      } : previous);
    }
  }, [active, owner]);

  useEffect(() => {
    live.current = true;
    ++generation.current;
    if (!active || !owner) {
      return () => { live.current = false; ++generation.current; };
    }
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void refresh();
    }, 15000);
    const app = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => {
      live.current = false;
      ++generation.current;
      clearInterval(timer);
      app.remove();
    };
  }, [active, owner, refresh, refreshKey]);

  const current = active && result?.owner === owner ? result : null;
  return useMemo(
    () => ({
      stars: current?.stars || [], latest: current?.stars[0] || null,
      count: current?.stars.length || 0, error: current?.error || false, refresh,
    }),
    [current, refresh],
  );
}
