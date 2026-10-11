import type { HomeItem } from '@/src/api/client';

export type CalendarEntry = { item: HomeItem; at: Date };

/** Calendar appointments in the mixed Home payload; deadlines stay in Home. */
export function calendarEntries(items: readonly HomeItem[]): CalendarEntry[] {
  return items.flatMap((item) => {
    // A Life Graph node is a calendar event only when its adapter supplies
    // the event handle. Its presentation type may also be visit or travel.
    const calendarSource = item.source_type === 'google_calendar'
      || item.source_type === 'internal_calendar'
      || (item.source_type === 'life_node' && item.meta?.calendar_node_id === item.source_id);
    if (!calendarSource || !item.source_id?.trim() || !item.start_at) return [];

    // A due date or goal target is not an appointment's start time.
    const at = new Date(item.start_at);
    return Number.isNaN(at.getTime()) ? [] : [{ item, at }];
  });
}
