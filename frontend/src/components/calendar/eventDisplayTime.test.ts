import assert from 'node:assert/strict';
import { agendaEventTime, eventDisplayDay, eventDisplayTime } from './eventDisplayTime.ts';

// The user's 18:00 booking is shown at 18:00 even when the checking browser
// runs in North America. This was observed as a six-hour discrepancy live.
const romeEvent = '2026-10-20T18:00:00+02:00';
const romeEnd = '2026-10-20T18:10:00+02:00';
assert.equal(eventDisplayDay(romeEvent, 'Europe/Rome'), 'martedì 20 ottobre');
assert.equal(eventDisplayTime(romeEvent, romeEnd, false, true, 'Europe/Rome'), '18:00 – 18:10');
assert.equal(eventDisplayTime('2026-10-20T16:00:00Z', '2026-10-20T16:10:00Z', false, true, 'Europe/Rome'), '18:00 – 18:10');

// An event without a resolvable timezone still retains its source wall time.
// A device's locale/zone is not silently substituted for the event's.
assert.equal(eventDisplayTime(romeEvent, romeEnd), '18:00 – 18:10');
assert.equal(eventDisplayDay(romeEvent), 'martedì 20 ottobre');
assert.equal(eventDisplayTime(romeEvent, romeEnd, false, true, 'Invalid/Zone'), '18:00 – 18:10');
assert.equal(eventDisplayTime(romeEvent, romeEnd, true), 'Tutto il giorno');
assert.equal(eventDisplayTime(romeEvent, romeEnd, false, false, 'Europe/Rome'), '18:00');

// Midnight and daylight-saving boundaries preserve the event's OWN day.
assert.equal(eventDisplayDay('2026-10-25T00:30:00+02:00', 'Europe/Rome'), 'domenica 25 ottobre');
assert.equal(eventDisplayTime('2026-10-25T08:00:00+01:00', null, false, false, 'Europe/Rome'), '08:00');
assert.equal(eventDisplayTime('2026-10-20T18:00:00+02:00', 'bad', false, true), '18:00');
assert.equal(eventDisplayTime(null), '');
assert.equal(eventDisplayDay(null), '');

// Joined view contract: the Agenda row is no longer allowed to show a
// stale legacy label in Chicago when the event detail is 18:00 in Rome.
const storedSourceEvent = {
  starts_at: '2026-10-20T16:00:00+00:00',
  ends_at: '2026-10-20T16:10:00+00:00',
  timezone: 'Europe/Rome',
  time_label: '12:00 – 12:10', // wrong browser-local legacy presentation
};
assert.equal(agendaEventTime(storedSourceEvent), '18:00 – 18:10');
assert.equal(
  agendaEventTime(storedSourceEvent),
  eventDisplayTime(storedSourceEvent.starts_at, storedSourceEvent.ends_at,
    false, true, 'Europe/Rome'),
);
assert.equal(agendaEventTime({
  starts_at: romeEvent, ends_at: romeEnd, timezone: 'Europe/Rome',
}), '18:00 – 18:10');
assert.equal(agendaEventTime({
  starts_at: romeEvent, ends_at: romeEnd, end_time_known: false, timezone: 'Europe/Rome',
}), '18:00');
assert.equal(agendaEventTime({
  starts_at: '2026-10-20', all_day: true, time_label: 'wrong',
}), 'Tutto il giorno');
assert.equal(agendaEventTime({
  starts_at: null, time_label: 'Solo ora dalla fonte non strutturata',
}), 'Solo ora dalla fonte non strutturata');
assert.equal(agendaEventTime({}), '—');

console.log('ORA event timezone presentation: all regression assertions passed');
