/**
 * Reading the context a conversation was opened with.
 *
 * The conversation is opened from somewhere — a goal, a piece of work ORA
 * prepared, a step of a plan — and the point of this module is that the user
 * should never have to re-explain that. It reads the plan bundle that already
 * exists (`getLifeOsPlan`) rather than adding a context service.
 */
import { useEffect, useState } from 'react';

import { api } from '@/src/api/client';
import { humanizeError } from '@/src/utils/errors';
import { contextFromPlanBundle, oraErrorSentence, type OraContextView } from './contextView';

export { contextFromPlanBundle, oraErrorSentence };
export type { OraContextView };

type Args = {
  planId?: string | null;
  objectId?: string | null;
  planItemId?: string | null;
};

/**
 * One fetch, only when there is a plan to fetch — no waterfall, and no request
 * at all for a conversation opened from the navigation bar.
 */
export function useOraContext({ planId, objectId, planItemId }: Args): {
  context: OraContextView | null;
  /** True while a plan was named but has not been read yet. */
  resolving: boolean;
} {
  const [ctx, setCtx] = useState<OraContextView | null>(null);
  // A conversation opened on a goal must not greet the user as if it had no
  // idea why they came — even for the half second the plan takes to arrive.
  const [resolving, setResolving] = useState(Boolean(planId));

  useEffect(() => {
    let cancelled = false;
    if (!planId) {
      setCtx(null);
      setResolving(false);
      return;
    }
    setResolving(true);
    (async () => {
      try {
        const res: any = await api.getLifeOsPlan(String(planId));
        if (cancelled) return;
        setCtx(contextFromPlanBundle(res, { objectId, planItemId }));
      } catch {
        // Context is an aid, never a precondition: if it cannot be read the
        // conversation still opens, just without the header.
        if (!cancelled) setCtx(null);
      } finally {
        if (!cancelled) setResolving(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [planId, objectId, planItemId]);

  return { context: ctx, resolving };
}

/** Failure as the person experiences it, falling back to the shared translator. */
export function oraErrorMessage(err: any): string {
  return oraErrorSentence(err) ?? humanizeError(err, 'default');
}
