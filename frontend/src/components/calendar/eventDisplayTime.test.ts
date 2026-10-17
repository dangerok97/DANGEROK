import assert from 'node:assert/strict';
import { eventDisplayDay, eventDisplayTime } from './eventDisplayTime.ts';

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

console.log('ORA event timezone presentation: 12 regression assertions passed');
