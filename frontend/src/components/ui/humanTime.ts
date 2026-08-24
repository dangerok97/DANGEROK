/**
 * Human time — the vocabulary ORA uses when it asks "when should I bring this
 * back?".
 *
 * People do not think in hours. Asking someone to type "4" into a box labelled
 * "Rimanda (ore)" makes them do arithmetic on their own day — work the product
 * should be doing — and it leaks the backend's unit (`defer_hours`) into a
 * conversation about their life. These options carry the same information in
 * the terms someone actually holds their day in.
 *
 * The translation to an absolute ISO instant happens here, once, so every
 * surface that offers "rimanda" agrees on what "domani mattina" means and the
 * backend contract (an ISO timestamp) is unchanged.
 */

export type HumanSnoozeChoiceId = 'later_today' | 'tomorrow_morning' | 'this_weekend' | 'custom';

export type HumanSnoozeChoice = {
  id: HumanSnoozeChoiceId;
  label: string;
  /** Absolute moment this resolves to. `null` for the custom picker. */
  resolve: (now: Date) => Date | null;
};

/** Morning means 9am — early enough to act on, late enough not to be an alarm. */
const MORNING_HOUR = 9;
/** Later today means three hours on, unless that spills past the evening. */
const LATER_TODAY_HOURS = 3;
/** Past this hour "later today" is no longer today in any useful sense. */
const EVENING_CUTOFF_HOUR = 21;

function atHour(base: Date, hour: number): Date {
  const d = new Date(base);
  d.setHours(hour, 0, 0, 0);
  return d;
}

export function laterToday(now: Date): Date {
  const candidate = new Date(now.getTime() + LATER_TODAY_HOURS * 3600_000);

  // Past the evening, or rolled over midnight: the person meant tomorrow.
  if (candidate.getHours() >= EVENING_CUTOFF_HOUR || candidate.getDate() !== now.getDate()) {
    return tomorrowMorning(now);
  }

  // Small hours: someone still awake at 02:00 does not mean 05:00 by "later
  // today" — they mean later in the day they are about to have. Snap forward
  // to the morning rather than proposing a moment they will be asleep for.
  if (candidate.getHours() < MORNING_HOUR) {
    return atHour(candidate, MORNING_HOUR);
  }

  return candidate;
}

export function tomorrowMorning(now: Date): Date {
  const d = new Date(now);
  d.setDate(d.getDate() + 1);
  return atHour(d, MORNING_HOUR);
}

export function thisWeekend(now: Date): Date {
  const d = new Date(now);
  const day = d.getDay(); // 0 Sun … 6 Sat
  // Next Saturday; if today *is* Saturday, this means the next one, because
  // "questo weekend" said on a Saturday morning still means "not now".
  const offset = (6 - day + 7) % 7 || 7;
  d.setDate(d.getDate() + offset);
  return atHour(d, MORNING_HOUR);
}

export const HUMAN_SNOOZE_CHOICES: HumanSnoozeChoice[] = [
  { id: 'later_today', label: 'Più tardi oggi', resolve: laterToday },
  { id: 'tomorrow_morning', label: 'Domani mattina', resolve: tomorrowMorning },
  { id: 'this_weekend', label: 'Questo weekend', resolve: thisWeekend },
  { id: 'custom', label: 'Scegli data e ora', resolve: () => null },
];

/** The choices that resolve on their own — i.e. everything but the picker. */
export const HUMAN_SNOOZE_QUICK_CHOICES = HUMAN_SNOOZE_CHOICES.filter((c) => c.id !== 'custom');

/**
 * What the backend already accepts: an absolute ISO instant. Nothing about the
 * wire format changes — only what we ask the person.
 */
export function snoozeUntilIso(choice: HumanSnoozeChoice, now: Date = new Date()): string | null {
  const resolved = choice.resolve(now);
  return resolved ? resolved.toISOString() : null;
}

/** Short, lower-case gloss of the resolved moment, e.g. "domani alle 09:00". */
export function describeSnoozeTarget(target: Date, now: Date = new Date()): string {
  const hh = `${target.getHours()}`.padStart(2, '0');
  const mm = `${target.getMinutes()}`.padStart(2, '0');
  const time = `${hh}:${mm}`;
  const sameDay = target.toDateString() === now.toDateString();
  if (sameDay) return `oggi alle ${time}`;
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  if (target.toDateString() === tomorrow.toDateString()) return `domani alle ${time}`;
  const weekday = target.toLocaleDateString('it-IT', { weekday: 'long' });
  return `${weekday} alle ${time}`;
}
