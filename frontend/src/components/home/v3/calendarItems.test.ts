import assert from 'node:assert/strict';
import test from 'node:test';
import type { HomeItem } from '@/src/api/client';
import { calendarEntries } from './calendarItems.ts';
import { allItems, todayItems } from './homeItemView.ts';

const start = '2026-10-12T10:00:00Z';

function item(id: string, fields: Partial<HomeItem> = {}): HomeItem {
  return {
    id, type: 'activity', title: `Fixture ${id}`, source_type: 'task', source_id: id,
    priority: 'today', urgency: 'soon', status: 'open', actions: [], reason_factors: [],
    ...fields,
  };
}

test('the rail counts calendar events without turning work on the same date into appointments', () => {
  const native = item('native', {
    type: 'event', source_type: 'life_node', start_at: start,
    meta: { calendar_node_id: 'native', kind: 'home_manual' },
  });
  const google = item('google', {
    type: 'event', source_type: 'google_calendar', start_at: start,
  });
  const task = item('task', { due_at: start });
  const reminder = item('reminder', { source_type: 'reminder', subtype: 'reminder', due_at: start });
  const checkpoint = item('checkpoint', { source_type: 'decision', subtype: 'admin', due_at: start });
  const goal = item('goal', { source_type: 'life_os_plan', goal_target_date: start });
  const candidate = item('candidate', { type: 'event', source_type: 'event_candidate', start_at: start });
  const scheduledTask = item('scheduled-task', { start_at: start, meta: { calendar_node_id: 'native' } });
  const home = [task, reminder, checkpoint, goal, candidate, scheduledTask, native, google];
  const before = structuredClone(home);

  const entries = calendarEntries(home);
  assert.deepEqual(entries.map(({ item }) => item.id), ['native', 'google']);
  assert.ok(entries.every(({ at }) => at.toISOString() === start.replace('Z', '.000Z')));
  assert.equal(entries[0].item, native, 'calendar rows retain the canonical item and its action');
  assert.deepEqual(home, before, 'the rail must not remove work from the Home payload');
  assert.deepEqual(allItems([{ items: home }]).map((entry) => entry.id), home.map((entry) => entry.id));
});

test('real calendar visits and travel remain appointments regardless of their presentation type', () => {
  const native = (id: string, type: HomeItem['type']) => item(id, {
    type, source_type: 'life_node', start_at: start, meta: { calendar_node_id: id },
  });
  const home = [
    native('visit', 'visit'), native('travel', 'travel'),
    item('legacy-calendar', { source_type: 'internal_calendar', start_at: start }),
    item('unrelated-node', { type: 'event', source_type: 'life_node', start_at: start }),
    item('wrong-node', {
      type: 'event', source_type: 'life_node', start_at: start,
      meta: { calendar_node_id: 'different-node' },
    }),
  ];

  assert.deepEqual(calendarEntries(home).map(({ item }) => item.id), ['visit', 'travel', 'legacy-calendar']);
});

test('a calendar source needs its own valid event start and source handle', () => {
  const home = [
    item('deadline-only', { source_type: 'google_calendar', due_at: start }),
    item('goal-only', { source_type: 'internal_calendar', goal_target_date: start }),
    item('invalid-start', { source_type: 'google_calendar', start_at: 'invalid', due_at: start }),
    item('missing-handle', { source_type: 'google_calendar', source_id: '', start_at: start }),
    item('blank-handle', { source_type: 'google_calendar', source_id: ' ', start_at: start }),
  ];

  assert.deepEqual(calendarEntries(home), []);
  assert.deepEqual(calendarEntries([]), []);
});

test('reminders and checkpoints remain visible in Home today without producing a calendar mark', () => {
  const due = new Date().toISOString();
  const home = [
    item('reminder', { source_type: 'reminder', due_at: due }),
    item('checkpoint', { source_type: 'decision', due_at: due }),
    item('goal', { goal_target_date: due }),
  ];

  assert.deepEqual(calendarEntries(home), []);
  assert.deepEqual(todayItems(home).map((entry) => entry.id), ['reminder', 'checkpoint', 'goal']);
});
