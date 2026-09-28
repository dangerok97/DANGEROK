import type { HomeItem } from '@/src/api/client';

type FocusDates = Pick<HomeItem, 'start_at' | 'end_at' | 'due_at' | 'location' | 'meta'>;

/** Calendar facts already carried by Home, phrased for a compact chat card. */
export function focusDetails(focus: FocusDates | null | undefined): { when: string | null; place: string | null } {
  if (!focus) return { when: null, place: null };
  const raw = focus.start_at || focus.due_at;
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw || '');
  const allDay = focus.meta?.all_day === true || dateOnly;
  // Date-only commitments name a calendar day, not UTC midnight.
  const start = raw ? new Date(allDay ? `${raw.slice(0, 10)}T12:00:00` : raw) : null;
  const place = typeof focus.location === 'string' ? focus.location.trim() || null : null;
  if (!start || Number.isNaN(start.getTime())) return { when: null, place };

  const day = (d: Date) => d.toLocaleDateString('it-IT', {
    weekday: 'long', day: 'numeric', month: 'long',
  });
  const time = (d: Date) => d.toLocaleTimeString('it-IT', {
    hour: '2-digit', minute: '2-digit',
  });
  if (allDay) return { when: `${day(start)} · Tutto il giorno`, place };

  const end = focus.start_at && focus.end_at ? new Date(focus.end_at) : null;
  const endValid = end && !Number.isNaN(end.getTime()) && end > start;
  const until = endValid && end!.toDateString() === start.toDateString()
    ? ` – ${time(end!)}` : '';
  return { when: `${day(start)} · ${time(start)}${until}`, place };
}
