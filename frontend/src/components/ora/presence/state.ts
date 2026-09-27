/** Public work signals, never hidden reasoning or a claim about model neurons. */
export const AREA_LABELS = {
  memory: 'Memoria', calendar: 'Impegni', people: 'Persone', places: 'Luoghi',
  home: 'Casa', documents: 'Documenti', finances: 'Finanze', calls: 'Chiamate',
} as const;
export type PresenceArea = keyof typeof AREA_LABELS;
export type PresenceMode = 'idle' | 'listen' | 'think' | 'speak';
export type PresenceActivity = {
  request_id: string; sequence: number;
  phase: 'processing' | 'context' | 'tool' | 'done' | 'error';
  area: PresenceArea | null; touched: PresenceArea[]; updated_at: number;
};
export function readPresenceActivity(value: unknown, requestId: string, previous: PresenceActivity | null = null, now = Date.now()): PresenceActivity | null {
  if (!value || typeof value !== 'object') return null;
  const a = value as PresenceActivity;
  if (a.request_id !== requestId || !Number.isSafeInteger(a.sequence) || a.sequence < 1
    || !Number.isFinite(a.updated_at) || Math.abs(now / 1000 - a.updated_at) > 120
    || !['processing', 'context', 'tool', 'done', 'error'].includes(a.phase)) return null;
  if (previous?.request_id === requestId && previous.sequence > a.sequence) return previous;
  return { request_id: requestId, sequence: a.sequence, phase: a.phase, updated_at: a.updated_at,
    area: a.area && Object.hasOwn(AREA_LABELS, a.area) ? a.area : null,
    touched: Array.isArray(a.touched) ? a.touched.filter(x => Object.hasOwn(AREA_LABELS, x)).slice(0, 8) : [],
  };
}
export function presenceMode(busy: boolean, phase?: string): PresenceMode {
  if (phase === 'listening' || phase === 'asking') return 'listen';
  if (phase === 'speaking') return 'speak';
  if (busy || phase === 'thinking' || phase === 'heard' || phase === 'preparing') return 'think';
  return 'idle';
}
