import type { HomeActionDef, HomeItem, ProactiveSuggestion } from '@/src/api/client';

/**
 * Presentation-only readers over the Home payload.
 *
 * No ranking, no filtering that changes meaning, no invented content — these
 * only decide how what already exists should be shown. Anything that would
 * change *which* item matters belongs to the backend.
 */

/**
 * The single action a card leads with.
 *
 * Order encodes intent, not preference: continuing something already underway
 * beats starting it, and both beat merely looking at it. Everything not chosen
 * here stays reachable in the overflow — one primary action is a hierarchy, not
 * a reduction.
 */
const PRIMARY_PRIORITY = [
  'resume',
  'continue',
  'guide',
  'confirm',
  'complete',
  'open',
  'navigate',
  'maps',
  'study',
];

/** Actions that must never be primary: they dismiss, defer or correct. */
const NEVER_PRIMARY = new Set(['snooze', 'ignore', 'correct', 'dismiss', 'dismiss_banner']);

export function primaryActionOf(item: HomeItem | null | undefined): HomeActionDef | null {
  const actions = item?.actions || [];
  if (!actions.length) return null;
  for (const kind of PRIMARY_PRIORITY) {
    const hit = actions.find((a) => a.kind === kind);
    if (hit) return hit;
  }
  return actions.find((a) => !NEVER_PRIMARY.has(a.kind)) || null;
}

export function overflowActionsOf(item: HomeItem | null | undefined): HomeActionDef[] {
  const actions = item?.actions || [];
  const primary = primaryActionOf(item);
  return actions.filter(
    (a) => a.kind !== primary?.kind && !NEVER_PRIMARY.has(a.kind),
  );
}

function parseWhen(item: HomeItem): Date | null {
  const raw = item.start_at || item.due_at || item.goal_target_date;
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "oggi alle 15:30" · "sab 19 set" — never a raw ISO string. */
export function whenLabel(item: HomeItem): string | null {
  const at = parseWhen(item);
  if (!at) return null;
  const now = new Date();
  const sameDay = at.toDateString() === now.toDateString();
  const time = at.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  if (sameDay) return `Oggi alle ${time}`;
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (at.toDateString() === tomorrow.toDateString()) return `Domani alle ${time}`;
  return at.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Days from today, for the quiet "tra N giorni" markers in the horizon. */
export function daysUntil(iso?: string | null): number | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  const a = new Date(); a.setHours(0, 0, 0, 0);
  const b = new Date(at); b.setHours(0, 0, 0, 0);
  return Math.round((b.getTime() - a.getTime()) / 86_400_000);
}

export function relativeDayLabel(iso?: string | null): string | null {
  const d = daysUntil(iso);
  if (d === null) return null;
  if (d < 0) return 'in ritardo';
  if (d === 0) return 'oggi';
  if (d === 1) return 'domani';
  return `${d} giorni`;
}

/** "2 ore fa" · "1 giorno fa" — how long ORA has been holding this. */
export function agoLabel(iso?: string | null): string | null {
  if (!iso) return null;
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return null;
  const mins = Math.round((Date.now() - at.getTime()) / 60_000);
  if (mins < 1) return 'ora';
  if (mins < 60) return `${mins} min fa`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} ${hours === 1 ? 'ora' : 'ore'} fa`;
  const days = Math.round(hours / 24);
  return `${days} ${days === 1 ? 'giorno' : 'giorni'} fa`;
}

/**
 * Suggestions ORA is genuinely *asking* about, as opposed to merely offering.
 *
 * V2.9.3 records this on the suggestion itself (`meta.delivery === 'ask_user'`)
 * — the attention layer already decided that this one needs an answer rather
 * than a glance. Reading that flag is how the interface stays a consumer of the
 * reasoning rather than a second guesser of it; when the flag is absent the
 * suggestion is simply an update, which is the safe direction to be wrong in.
 */
export function isQuestion(s: ProactiveSuggestion): boolean {
  const delivery = (s.meta as Record<string, unknown> | undefined)?.delivery;
  return delivery === 'ask_user' || delivery === 'propose_action';
}

export function splitSuggestions(list: ProactiveSuggestion[] | undefined | null) {
  const all = list || [];
  return {
    questions: all.filter(isQuestion),
    updates: all.filter((s) => !isQuestion(s)),
  };
}

/** Items whose moment is today — the "Oggi" strip. */
export function todayItems(items: HomeItem[]): HomeItem[] {
  const today = new Date().toDateString();
  return items
    .filter((i) => {
      const at = parseWhen(i);
      return !!at && at.toDateString() === today;
    })
    .sort((a, b) => (parseWhen(a)!.getTime() - parseWhen(b)!.getTime()));
}

/** Every item the payload carries, de-duplicated by id. */
export function allItems(groups: { items: HomeItem[] }[] | undefined | null): HomeItem[] {
  const seen = new Set<string>();
  const out: HomeItem[] = [];
  for (const g of groups || []) {
    for (const i of g.items || []) {
      if (seen.has(i.id)) continue;
      seen.add(i.id);
      out.push(i);
    }
  }
  return out;
}
