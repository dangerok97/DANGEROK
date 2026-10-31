import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const page = readFileSync(new URL('./PuntoDelMattino.tsx', import.meta.url), 'utf8');
assert.ok(page.includes('api.morningToday()'), 'the page is rebuilt now, not the 8:00 snapshot');
assert.ok(page.includes('fallback'), 'without the server the stored text is still shown');
const detail = readFileSync(new URL('../../../app/aggiornamento/[id].tsx', import.meta.url), 'utf8');
assert.ok(detail.includes("mattino ? <PuntoDelMattino fallback={a.cosa} />"));
const client = readFileSync(new URL('../../api/client.ts', import.meta.url), 'utf8');
assert.ok(client.includes("'/brief/morning/today'"));
console.log('puntoDelMattino ok');
