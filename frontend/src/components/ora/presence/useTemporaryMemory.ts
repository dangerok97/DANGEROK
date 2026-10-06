import { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState } from 'react-native';

import { api } from '@/src/api/client';
import type { KnowledgeStar } from './knowledge';

function stamp(star: KnowledgeStar): number {
  const value = star.updated_at ? new Date(star.updated_at).getTime() : 0;
  return Number.isFinite(value) ? value : 0;
}

export function useTemporaryMemory(active = true, refreshKey?: unknown) {
  const [stars, setStars] = useState<KnowledgeStar[]>([]);

  const refresh = useCallback(async () => {
    if (!active) return;
    try {
      const map = await api.knowledgeMap();
      const next = (map.stars || [])
        .filter((star) => star.temporary)
        .sort((a, b) => stamp(b) - stamp(a));
      setStars(next);
    } catch {
      // Temporary memory is an enrichment. Conversation remains usable.
    }
  }, [active]);

  useEffect(() => {
    if (!active) return;
    void refresh();
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void refresh();
    }, 15000);
    const app = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => {
      clearInterval(timer);
      app.remove();
    };
  }, [active, refresh, refreshKey]);

  return useMemo(
    () => ({ stars, latest: stars[0] || null, count: stars.length, refresh }),
    [stars, refresh],
  );
}
