import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const ev = readFileSync(new URL('./EveningBrief.tsx', import.meta.url), 'utf8');
assert.ok(ev.includes('api.eveningBrief()') && ev.includes('api.setEveningBrief(body)'));
assert.ok(ev.includes('EVENING_HOURS = [18, 19, 20, 21, 22]'));
const check = readFileSync(new URL('./OraCheck.tsx', import.meta.url), 'utf8');
assert.ok(check.includes('api.oraCheck()'));
const settings = readFileSync(new URL('../../../app/settings.tsx', import.meta.url), 'utf8');
assert.ok(settings.includes('<EveningBrief />') && settings.includes('<OraCheck />'));
const groups = readFileSync(new URL('../home/v3/gruppiAggiornamenti.ts', import.meta.url), 'utf8');
assert.ok(groups.includes("a.promemoria === 'evening_brief'") && groups.includes("a.promemoria === 'ora_check'"));
const detail = readFileSync(new URL('../../../app/aggiornamento/[id].tsx', import.meta.url), 'utf8');
assert.ok(detail.includes("|| a.promemoria === 'evening_brief' || a.promemoria === 'ora_check';"), 'news: Ok, no snooze');
console.log('eveningAndCheck ok');
