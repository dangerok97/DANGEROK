import assert from 'node:assert/strict';
import { focusDetails } from './focusDetails.ts';

const event = {
  start_at: '2026-09-30T18:00:00Z', end_at: '2026-09-30T18:45:00Z',
  location: '  Piazza del Comune  ',
};
const result = focusDetails(event);
const clock = (value: string) => new Date(value).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
assert.match(result.when || '', /30 settembre/);
assert.ok(result.when?.includes(`${clock(event.start_at)} – ${clock(event.end_at)}`));
assert.equal(result.place, 'Piazza del Comune');
assert.deepEqual(focusDetails({ due_at: '2026-10-08' }), {
  when: 'giovedì 8 ottobre · Tutto il giorno', place: null,
});
assert.deepEqual(focusDetails({ start_at: 'not-a-date', location: ' ' }), { when: null, place: null });
