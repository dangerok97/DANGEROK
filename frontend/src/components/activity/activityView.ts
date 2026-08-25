/**
 * Attività — how the read model reads.
 *
 * The backend already decided what belongs in each section and, crucially, who
 * did what. This module turns those facts into the words on screen, and its
 * whole job is to keep the honest distinctions intact one layer further:
 * a question is not a consent request, a postponed thing is not a blocked
 * thing, and "ORA ha fatto" is not the same claim as "risulta cambiato".
 *
 * Import-free on purpose, so the wording can be checked without a bundler.
 */

export type ActivityActor = 'ora' | 'observed';

/* -------------------------------------------------------------------------- */
/* Time, spoken                                                               */
/* -------------------------------------------------------------------------- */

/** "Oggi, 09:12" · "Ieri, 18:45" · "23 ago 2026, 16:20" — never an ISO string. */
export function whenLabel(value?: string | null, now: Date = new Date()): string | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const d = new Date(t);
  const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return `Oggi, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `Ieri, ${time}`;
  return `${d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' })}, ${time}`;
}

/** "Scade oggi" · "Scade domani" · "Scade tra 3 giorni" — a distance, not a date. */
export function dueLabel(value?: string | null, now: Date = new Date()): string | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const day = 86400000;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(new Date(t)) - startOf(now)) / day);
  if (days < 0) return 'Scaduta';
  if (days === 0) return 'Scade oggi';
  if (days === 1) return 'Scade domani';
  return `Scade tra ${days} giorni`;
}

/** The day badge on a deadline row: { day: "28", month: "AGO" }. */
export function dayBadge(value?: string | null): { day: string; month: string } | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const d = new Date(t);
  return {
    day: String(d.getDate()).padStart(2, '0'),
    month: d.toLocaleDateString('it-IT', { month: 'short' }).replace('.', '').toUpperCase(),
  };
}

/* -------------------------------------------------------------------------- */
/* Honest wording                                                             */
/* -------------------------------------------------------------------------- */

/**
 * What ORA is allowed to claim about a change.
 *
 * Attribution is a trust question, not a copy question. If ORA prepared
 * something it may say so in the first person; if it merely registered that
 * the world changed — because the user did something, or a document said so —
 * then saying "Ho aggiornato" would take credit for someone else's action.
 * The backend records which of the two happened; this only spends it.
 */
export function updateLead(actor: string, title: string): string {
  return actor === 'ora' ? title : title;
}

/** The small label above an update saying who moved. */
export function actorLabel(actor: string): string {
  return actor === 'ora' ? 'ORA' : 'Risulta aggiornato';
}

/**
 * What the row asks of the person.
 *
 * A consent request is not a question with a different colour: ORA has already
 * done the work and is holding the last step because taking it unasked would
 * be acting on the user's behalf without permission. The label has to say that
 * plainly, and the action has to read as granting permission, not as replying.
 */
export function questionCta(needsConsent: boolean): string {
  return needsConsent ? 'Conferma' : 'Rispondi';
}

export function questionEyebrow(needsConsent: boolean): string | null {
  return needsConsent ? 'Serve la tua conferma' : null;
}

/**
 * What something is waiting on, in words.
 *
 * Falls back to a date when the dependency is simply that the day has not
 * arrived, and to a plain statement when the backend knows there is a blocker
 * but not what to call it. Never invents a reason.
 */
export function waitingLabel(waitingFor?: string | null, when?: string | null): string {
  const named = String(waitingFor || '').trim();
  if (named) return `In attesa di ${named}`;
  // The countdown lives on the pill beside this line; repeating it here said
  // the same thing twice. What the sentence adds is *why* it is waiting.
  if (when) return 'In attesa della data prevista';
  return 'In attesa di procedere';
}

/* -------------------------------------------------------------------------- */
/* Structure                                                                  */
/* -------------------------------------------------------------------------- */

type Sections = {
  attention?: unknown | null;
  questions?: unknown[];
  waiting?: unknown[];
  updates?: unknown[];
  deadlines?: unknown[];
  completed?: unknown[];
};

/** True when there is genuinely nothing for this page to say. */
export function isActivityEmpty(a: Sections | null | undefined): boolean {
  if (!a) return true;
  return (
    !a.attention &&
    !(a.questions || []).length &&
    !(a.waiting || []).length &&
    !(a.updates || []).length &&
    !(a.deadlines || []).length &&
    !(a.completed || []).length
  );
}

/**
 * The primary action for the hero.
 *
 * Only what Home already offers for this item, and never one of the actions
 * that dismiss or defer it — those belong in an overflow, not on the one
 * button that says what to do about the thing.
 */
const NEVER_PRIMARY = new Set(['snooze', 'ignore', 'correct', 'dismiss', 'dismiss_banner']);
const PRIMARY_PRIORITY = ['resume', 'continue', 'confirm', 'guide', 'open', 'navigate', 'complete'];

export function heroAction(
  actions: Array<{ kind: string; label: string; route?: string | null }> | undefined | null,
): { kind: string; label: string; route?: string | null } | null {
  const list = (actions || []).filter((a) => a?.kind && !NEVER_PRIMARY.has(a.kind));
  if (!list.length) return null;
  for (const kind of PRIMARY_PRIORITY) {
    const hit = list.find((a) => a.kind === kind);
    if (hit) return hit;
  }
  return list[0];
}
