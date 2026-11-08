import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const card = readFileSync(new URL('./GiornataCard.tsx', import.meta.url), 'utf8');
assert.ok(card.includes('api.morningToday()'));
assert.ok(card.includes("const KEYS = ['today', 'reminders', 'deadlines', 'meals', 'watching', 'drying', 'tomorrow', 'done'];"),
  'no weather: the header already has it');
assert.ok(card.includes("if (!sezioni.length) return null;"), 'an empty day shows nothing');
const home = readFileSync(new URL('../../../app/(tabs)/index.tsx', import.meta.url), 'utf8');
assert.ok(home.includes('<GiornataCard />'));
const page = readFileSync(new URL('../../../app/giornata.tsx', import.meta.url), 'utf8');
assert.ok(page.includes('<PuntoDelMattino'));
console.log('giornataCard ok');
