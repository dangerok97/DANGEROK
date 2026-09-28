import type { HomeOpportunity } from '@/src/api/client';

/** Keep Home's order; never make a button for an invalid or finished record. */
export function pickOraOpportunity(items?: HomeOpportunity[]): HomeOpportunity | null {
  return (items || []).find((o) =>
    /^[A-Za-z0-9_-]{4,80}$/.test(o.id || '') && Boolean(o.title?.trim()) &&
    o.status !== 'dismissed' && o.status !== 'resolved') || null;
}
