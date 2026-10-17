/**
 * Show an event at its OWN calendar wall-clock, never the browser's current
 * timezone. A remote browser, flight or travelling phone may be elsewhere.
 *
 * If no valid IANA zone is attached, preserve the offset-qualified wall
 * clock supplied by the source; do not silently convert to the viewer's zone.
 * This is presentation only: it cannot rewrite calendar storage or consent.
 */
function validDate(value?: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function calendarDay(value?: string | null, zone?: string | null): string | null {
  if (!value) return null;
  if (zone) {
    try {
      const date = validDate(value);
      if (date) {
        const parts = new Intl.DateTimeFormat('en-CA', {
          timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
        }).formatToParts(date);
        const valueOf = (type: string) => parts.find((part) => part.type === type)?.value;
        const year = valueOf('year'), month = valueOf('month'), day = valueOf('day');
        if (year && month && day) return `${year}-${month}-${day}`;
      }
    } catch { /* The event's timezone is invalid; do not assume device time. */ }
  }
  const match = /^(\d{4}-\d{2}-\d{2})(?:T|$)/.exec(value);
  return match ? match[1] : null;
}

function calendarTime(value?: string | null, zone?: string | null): string {
  if (!value) return '';
  if (zone) {
    try {
      const date = validDate(value);
      if (date) return new Intl.DateTimeFormat('it-IT', {
        timeZone: zone, hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
      }).format(date);
    } catch { /* Fallback retains source wall-clock. */ }
  }
  return /^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2})/.exec(value)?.[1] || '';
}

export function eventDisplayDay(value?: string | null, zone?: string | null): string {
  const day = calendarDay(value, zone);
  if (!day) return '';
  const [year, month, date] = day.split('-').map(Number);
  const local = new Date(Date.UTC(year, month - 1, date));
  if (!Number.isFinite(local.getTime())) return '';
  return new Intl.DateTimeFormat('it-IT', {
    timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long',
  }).format(local);
}

export function eventDisplayTime(
  start?: string | null,
  end?: string | null,
  allDay?: boolean,
  endTimeKnown?: boolean,
  zone?: string | null,
): string {
  if (allDay) return 'Tutto il giorno';
  const from = calendarTime(start, zone);
  if (!from) return '';
  if (endTimeKnown === false || !end) return from;
  const until = calendarTime(end, zone);
  return until ? `${from} – ${until}` : from;
}
