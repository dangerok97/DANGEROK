/**
 * Platform-safe wrapper around expo-calendar (EventKit on iOS).
 *
 * On Web/Android:
 *   - `isSupported()` returns false;
 *   - `getPermissionStatus()` returns 'unsupported';
 *   - `requestPermission()` returns 'unsupported';
 *   - all read methods throw `AppleCalendarUnsupportedError`.
 *
 * On iOS/iPadOS:
 *   - Actual EventKit access via `expo-calendar`.
 *
 * We NEVER pass the raw EKEvent object to the backend — always the
 * normalized `AppleRawEvent` shape defined in `src/api/client.ts`.
 *
 * MOCK MODE (dev only, `EXPO_PUBLIC_APPLE_CALENDAR_MOCK=1`):
 *   Returns a static set of fake calendars + events so the UI can be
 *   validated in Expo Go / Web previews. Never enabled by default.
 */
import { Platform } from 'react-native';
import type { AppleRawEvent, AppleCalendarInfo } from '@/src/api/client';

const MOCK_ENABLED = process.env.EXPO_PUBLIC_APPLE_CALENDAR_MOCK === '1';

export class AppleCalendarUnsupportedError extends Error {
  constructor(msg = 'Apple Calendar is only available on iPhone/iPad.') {
    super(msg);
    this.name = 'AppleCalendarUnsupportedError';
  }
}

export type PermissionState = 'granted' | 'denied' | 'undetermined' | 'unsupported';

export type PermissionResult = {
  status: PermissionState;
  canAskAgain: boolean;
};

export function isSupported(): boolean {
  if (MOCK_ENABLED) return true;
  return Platform.OS === 'ios';
}

// Lazy-require expo-calendar so bundling on Web doesn't crash if the
// native module isn't available.
function safeRequireExpoCalendar(): any | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('expo-calendar');
  } catch {
    return null;
  }
}

// -------------------------------------------------------------
// Mock data (only when EXPO_PUBLIC_APPLE_CALENDAR_MOCK=1)
// -------------------------------------------------------------
const MOCK_CALENDARS: AppleCalendarInfo[] = [
  { id: 'mock-cal-personal', title: 'Personale', color: '#FF3B30', allowsModifications: true, source: 'iCloud' },
  { id: 'mock-cal-work',     title: 'Lavoro',    color: '#007AFF', allowsModifications: true, source: 'iCloud' },
  { id: 'mock-cal-family',   title: 'Famiglia',  color: '#34C759', allowsModifications: false, source: 'Local' },
];

function mockEvents(calendarIds: string[]): AppleRawEvent[] {
  const now = new Date();
  const iso = (d: Date) => d.toISOString();
  const mk = (offsetDays: number, hour: number, dur: number, title: string, calId: string, extra: Partial<AppleRawEvent> = {}): AppleRawEvent => {
    const start = new Date(now);
    start.setDate(start.getDate() + offsetDays);
    start.setHours(hour, 0, 0, 0);
    const end = new Date(start.getTime() + dur * 60_000);
    return {
      id: `mock_${calId}_${offsetDays}_${hour}_${title.replace(/\s+/g, '_')}`,
      calendarId: calId,
      calendarTitle: MOCK_CALENDARS.find(c => c.id === calId)?.title || undefined,
      title,
      startDate: iso(start),
      endDate: iso(end),
      allDay: false,
      status: 'confirmed',
      ...extra,
    };
  };
  const all: AppleRawEvent[] = [
    mk(0,  9,  30, 'Standup team', 'mock-cal-work'),
    mk(0, 13, 60, 'Pranzo con Marco', 'mock-cal-personal', { location: 'Osteria del Sole' }),
    mk(1, 18, 90, 'Palestra',        'mock-cal-personal', { location: 'Fit Club' }),
    mk(2, 11, 60, 'Riunione clienti', 'mock-cal-work',   { notes: 'Preparare pitch' }),
    mk(3, 20, 120, 'Cena con Anna',   'mock-cal-family', { location: 'Casa' }),
  ];
  return all.filter(e => calendarIds.includes(e.calendarId!));
}

// -------------------------------------------------------------
// Public API
// -------------------------------------------------------------
export async function getPermissionStatus(): Promise<PermissionResult> {
  if (!isSupported() && !MOCK_ENABLED) {
    return { status: 'unsupported', canAskAgain: false };
  }
  if (MOCK_ENABLED) {
    return { status: 'granted', canAskAgain: true };
  }
  const Calendar = safeRequireExpoCalendar();
  if (!Calendar) return { status: 'unsupported', canAskAgain: false };
  const res = await Calendar.getCalendarPermissionsAsync();
  return {
    status: mapExpoStatus(res.status),
    canAskAgain: !!res.canAskAgain,
  };
}

export async function requestPermission(): Promise<PermissionResult> {
  if (!isSupported() && !MOCK_ENABLED) {
    return { status: 'unsupported', canAskAgain: false };
  }
  if (MOCK_ENABLED) {
    return { status: 'granted', canAskAgain: true };
  }
  const Calendar = safeRequireExpoCalendar();
  if (!Calendar) return { status: 'unsupported', canAskAgain: false };
  const res = await Calendar.requestCalendarPermissionsAsync();
  return {
    status: mapExpoStatus(res.status),
    canAskAgain: !!res.canAskAgain,
  };
}

export async function listCalendars(): Promise<AppleCalendarInfo[]> {
  if (MOCK_ENABLED) return MOCK_CALENDARS;
  if (!isSupported()) throw new AppleCalendarUnsupportedError();
  const Calendar = safeRequireExpoCalendar();
  if (!Calendar) throw new AppleCalendarUnsupportedError();
  const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes?.EVENT ?? 'event');
  return (cals || []).map((c: any): AppleCalendarInfo => ({
    id: String(c.id),
    title: c.title || null,
    color: c.color || null,
    allowsModifications: !!c.allowsModifications,
    source: c.source?.name || null,
  }));
}

/**
 * Read events for the given calendars within a symmetric window
 * (past N days .. future M days). Returns raw events in the shape the
 * backend expects.
 */
export async function readEvents(
  calendarIds: string[],
  opts: { pastDays?: number; futureDays?: number } = {},
): Promise<AppleRawEvent[]> {
  const pastDays = opts.pastDays ?? 30;
  const futureDays = opts.futureDays ?? 180;
  if (MOCK_ENABLED) return mockEvents(calendarIds);
  if (!isSupported()) throw new AppleCalendarUnsupportedError();
  if (!calendarIds || calendarIds.length === 0) return [];

  const Calendar = safeRequireExpoCalendar();
  if (!Calendar) throw new AppleCalendarUnsupportedError();
  const now = new Date();
  const from = new Date(now); from.setDate(from.getDate() - pastDays);
  const to = new Date(now);   to.setDate(to.getDate() + futureDays);
  const events = await Calendar.getEventsAsync(calendarIds, from, to);

  return (events || []).map((e: any): AppleRawEvent => ({
    id: String(e.id),
    calendarId: e.calendarId ? String(e.calendarId) : undefined,
    calendarTitle: e.calendarTitle || undefined,
    title: e.title || null,
    notes: e.notes || null,
    startDate: typeof e.startDate === 'string' ? e.startDate : new Date(e.startDate).toISOString(),
    endDate: typeof e.endDate === 'string' ? e.endDate : new Date(e.endDate).toISOString(),
    allDay: !!e.allDay,
    location: e.location || null,
    timeZone: e.timeZone || null,
    status: normalizeStatus(e.status),
    organizer: typeof e.organizer === 'string' ? e.organizer : (e.organizer?.name || null),
    attendees: Array.isArray(e.attendees) ? e.attendees.map((a: any) => a?.email || a?.name).filter(Boolean) : [],
    recurrenceRule: typeof e.recurrenceRule === 'string'
      ? e.recurrenceRule
      : (e.recurrenceRule?.frequency ? `FREQ=${e.recurrenceRule.frequency}` : null),
    lastModified: e.lastModifiedDate
      ? (typeof e.lastModifiedDate === 'string' ? e.lastModifiedDate : new Date(e.lastModifiedDate).toISOString())
      : null,
    availability: e.availability || null,
  }));
}

// -------------------------------------------------------------
// Helpers
// -------------------------------------------------------------
function mapExpoStatus(s: string | undefined): PermissionState {
  if (s === 'granted') return 'granted';
  if (s === 'denied') return 'denied';
  return 'undetermined';
}

function normalizeStatus(s: any): string {
  if (!s) return 'confirmed';
  const v = String(s).toLowerCase();
  if (v === 'cancelled' || v === 'canceled') return 'cancelled';
  if (v === 'tentative') return 'tentative';
  return 'confirmed';
}
