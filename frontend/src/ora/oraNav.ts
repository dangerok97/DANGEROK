/**
 * Canonical ORA navigation — opaque ids only, no PII in URLs.
 * Production conversation surface: /ora and /ora/{sessionId}
 * /ora-ai is DEV/diagnostic only.
 */

export type OraEntryPoint =
  | 'home'
  | 'ora'
  | 'goal_workspace'
  | 'continue'
  | 'focus'
  | 'object'
  | 'vita';

export type OraConversationParams = {
  sessionId?: string | null;
  planId?: string | null;
  objectId?: string | null;
  planItemId?: string | null;
  entryPoint?: OraEntryPoint;
};

const ENTRY_POINTS: OraEntryPoint[] = [
  'home',
  'ora',
  'goal_workspace',
  'continue',
  'focus',
  'object',
  'vita',
];

/** Read an entry point off a URL, falling back to a plain ORA opening. */
export function oraEntryPointFrom(raw?: string | string[] | null): OraEntryPoint {
  const v = Array.isArray(raw) ? raw[0] : raw;
  return ENTRY_POINTS.includes(String(v || '') as OraEntryPoint)
    ? (String(v) as OraEntryPoint)
    : 'ora';
}

const OPAQUE_ID = /^[A-Za-z0-9_-]{4,80}$/;

function opaque(id?: string | null): string | undefined {
  if (!id) return undefined;
  const s = String(id).trim();
  return OPAQUE_ID.test(s) ? s : undefined;
}

/** Build production ORA conversation href (never /ora-ai). */
export function buildOraConversationHref(p: OraConversationParams): string {
  const sessionId = opaque(p.sessionId);
  const base = sessionId ? `/ora/${sessionId}` : '/ora';
  const q = new URLSearchParams();
  const planId = opaque(p.planId);
  const objectId = opaque(p.objectId);
  const planItemId = opaque(p.planItemId);
  const entry = p.entryPoint;
  if (planId) q.set('planId', planId);
  if (objectId) q.set('objectId', objectId);
  if (planItemId) q.set('planItemId', planItemId);
  if (entry) q.set('entry', entry);
  const qs = q.toString();
  return qs ? `${base}?${qs}` : base;
}

export function buildGoalWorkspaceHref(planId: string): string {
  const id = opaque(planId);
  if (!id) return '/ora';
  return `/goal-workspace/${id}`;
}

/** True if href is the DEV AI harness (must not be used by production nav). */
export function isDevOraAiHref(href: string): boolean {
  return href === '/ora-ai' || href.startsWith('/ora-ai/');
}

export function assertNoSensitiveQuery(href: string): boolean {
  const lower = href.toLowerCase();
  const banned = ['name=', 'job=', 'exam=', 'location=', 'email=', 'phone='];
  return !banned.some((b) => lower.includes(b));
}
