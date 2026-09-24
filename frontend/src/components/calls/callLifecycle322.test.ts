/** V3.22 — prepared call lifecycle product guard. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../../..');
const prep = fs.readFileSync(path.join(root, 'app/prepara-chiamata.tsx'), 'utf8');
const api = fs.readFileSync(path.join(root, 'src/api/client.ts'), 'utf8');

assert.ok(
  prep.includes('api.callDetail(chiamata)') &&
    prep.includes("presentation_status !== 'in_corso'"),
  'the preparation screen must follow the call until a terminal state',
);
assert.ok(
  prep.includes('router.replace(`/chiamate/${chiamata}`'),
  'a finished call must open its human-readable result',
);
assert.ok(
  prep.includes('api.hangupCall(chiamata)') && prep.includes('prep-hangup'),
  'the launching surface must be able to stop the call',
);
assert.ok(
  prep.includes('let callId = chiamata') &&
    prep.includes('if (!callId)') &&
    prep.includes('api.preparationToCall'),
  'retry must reuse the prepared call instead of minting another',
);
assert.ok(
  api.includes('hangupCall: (callId: string)') &&
    api.includes('/telephone/${callId}/hangup'),
  'the frontend API must expose the hangup endpoint',
);


const detail = fs.readFileSync(path.join(root, 'app/chiamate/[id].tsx'), 'utf8');

assert.ok(
  detail.includes('onDecided={(preparedCallId) =>') &&
    detail.includes('setNextCallId(preparedCallId)'),
  'a continuation decision must surface the prepared callback call id',
);
assert.ok(
  detail.includes('testID="continuation-place-call"') &&
    detail.includes('api.placeCall(nextCallId)'),
  'a callback must require a fresh explicit dial gesture',
);
assert.ok(
  detail.includes("call?.presentation_status !== 'in_corso'") &&
    detail.includes('setTimeout(() => void load(), 1500)'),
  'call detail must refresh itself while a call is still active',
);
