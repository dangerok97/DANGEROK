import test from 'node:test';
import assert from 'node:assert/strict';
import { matchesFilter, minutesLabel, scaleLine, stepTimerMinutes } from './cooking.ts';

test('scales the leading quantity only, never guesses', () => {
  assert.equal(scaleLine('200 g farina 00', 2), '400 g farina 00');
  assert.equal(scaleLine('1/2 cipolla', 2), '1 cipolla');
  assert.equal(scaleLine('½ limone', 3), '1,5 limone');
  assert.equal(scaleLine('1,5 l latte', 2), '3 l latte');
  assert.equal(scaleLine('3 uova', 0.5), '1,5 uova');
  assert.equal(scaleLine('sale q.b.', 3), 'sale q.b.');
  assert.equal(scaleLine('320 g spaghetti', 1), '320 g spaghetti');
});

test('reads the wait a step asks for', () => {
  assert.equal(stepTimerMinutes('Cuoci per 20 minuti a fuoco basso'), 20);
  assert.equal(stepTimerMinutes('Lascia lievitare 2 ore'), 120);
  assert.equal(stepTimerMinutes('Inforna per 25-30 min'), 30);
  assert.equal(stepTimerMinutes("Riposa mezz'ora"), 30);
  assert.equal(stepTimerMinutes('Taglia il guanciale'), null);
});

test('labels and filters', () => {
  assert.equal(minutesLabel(90), '1 h 30 min');
  assert.equal(minutesLabel(25), '25 min');
  const r = { favorite: true, status: 'cooked', total_minutes: 20, tags: ['Primo'] };
  assert.ok(matchesFilter(r, 'favorite') && matchesFilter(r, 'quick') && matchesFilter(r, 'tag:primo'));
  assert.ok(!matchesFilter(r, 'to_try'));
});

test('the week reads as days of a month, not an ISO date (8/11)', async () => {
  const { weekLabel } = await import('./cooking.ts');
  const y = new Date().getFullYear();
  assert.equal(weekLabel(`${y}-11-02`), '2–8 novembre');
  assert.equal(weekLabel(`${y}-11-30`), '30 novembre – 6 dicembre');
});

test('meals have Italian names', async () => {
  const { mealLabel } = await import('./cooking.ts');
  assert.equal(mealLabel('lunch'), 'Pranzo');
  assert.equal(mealLabel('dinner'), 'Cena');
});

test('the shopping list goes by aisle, the trolley at the end', async () => {
  const { shoppingAisles } = await import('./cooking.ts');
  const { aisles, done } = shoppingAisles([
    { name: 'zucchine', category: 'Frutta e verdura', checked: false },
    { name: 'detersivo', category: 'Altro', checked: false },
    { name: 'uova', category: 'Latticini e uova', checked: false },
    { name: 'guanciale', category: 'Carne e pesce', checked: true },
    { name: 'pecorino', category: 'Latticini e uova', checked: false },
  ]);
  assert.deepEqual(aisles.map(a => a.aisle), ['Frutta e verdura', 'Latticini e uova', 'Altro']);
  assert.deepEqual(aisles[1].items.map(i => i.name), ['pecorino', 'uova']);
  assert.deepEqual(done.map(i => i.name), ['guanciale']);
});
