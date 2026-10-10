/** Presentation-only month helpers: no provider, network or account dependency. */
export type CalendarSourceFilter = 'all' | 'ora' | 'google' | 'apple' | 'other';

export function monthCells(month: string): Array<string | null> {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) return [];
  const [year, m] = month.split('-').map(Number);
  const first = new Date(Date.UTC(year, m - 1, 1));
  const lead = (first.getUTCDay() + 6) % 7; // Monday first
  const days = new Date(Date.UTC(year, m, 0)).getUTCDate();
  const cells: Array<string | null> = Array(lead).fill(null);
  for (let day = 1; day <= days; day++) {
    cells.push(`${month}-${String(day).padStart(2, '0')}`);
  }
  while (cells.length % 7) cells.push(null);
  return cells;
}

export function localDayKey(day: Date): string {
  return `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
}

export function monthHeading(month: string): string {
  const [year, m] = month.split('-').map(Number);
  if (!year || !m || m < 1 || m > 12) return month;
  return new Date(Date.UTC(year, m - 1, 1))
    .toLocaleDateString('it-IT', { month: 'long', year: 'numeric', timeZone: 'UTC' });
}

export function selectSource<T extends { source_type?: string | null }>(
  events: T[], filter: CalendarSourceFilter,
): T[] {
  if (filter === 'all') return events;
  return events.filter((event) => (event.source_type || 'other') === filter);
}
