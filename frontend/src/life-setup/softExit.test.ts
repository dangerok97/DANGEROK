/**
 * Tests A–D for Life Setup soft-exit visibility.
 * Run: node --experimental-strip-types src/life-setup/softExit.test.ts
 */
import assert from 'node:assert/strict';
// Node ESM strip-types needs the .ts extension; file is excluded from tsc.
import { computeAllowSoftExit, shouldShowSoftExit } from './softExit.ts';

// A — FIRST-RUN incomplete: hide Esci / Più tardi
assert.equal(
  shouldShowSoftExit({ resumed: false, resumeParam: undefined, done: false }),
  false,
  'A: brand-new first-run hides soft exit',
);
assert.equal(
  computeAllowSoftExit({ resumed: false, resumeParam: null }),
  false,
  'A: allowSoftExit false without resume signals',
);
assert.equal(
  shouldShowSoftExit({ allowSoftExit: false, done: false }),
  false,
  'A: precomputed allowSoftExit=false hides',
);

// B — RETURNING/RESUME: show while !done
assert.equal(
  shouldShowSoftExit({ resumed: false, resumeParam: '1', done: false }),
  true,
  'B: ?resume=1 shows soft exit',
);
assert.equal(
  shouldShowSoftExit({ resumed: true, resumeParam: undefined, done: false }),
  true,
  'B: start.resumed shows soft exit',
);
assert.equal(
  shouldShowSoftExit({ allowSoftExit: true, done: false }),
  true,
  'B: precomputed allowSoftExit=true shows',
);

// C — MLC wrap done: hide Esci (Entra in ORA only)
assert.equal(
  shouldShowSoftExit({ resumed: true, resumeParam: '1', done: true }),
  false,
  'C: wrap done hides soft exit even on resume',
);
assert.equal(
  shouldShowSoftExit({ allowSoftExit: true, done: true }),
  false,
  'C: allowSoftExit && done → hide',
);

// D — after Esci cancel + force start: no resumed, no resume param → stay hidden
assert.equal(
  shouldShowSoftExit({
    allowSoftExit: computeAllowSoftExit({ resumeParam: undefined, resumed: false }),
    done: false,
  }),
  false,
  'D: force restart without resume stays mandatory (hidden)',
);
assert.equal(
  shouldShowSoftExit({
    allowSoftExit: computeAllowSoftExit({ resumeParam: '1', resumed: false }),
    done: false,
  }),
  true,
  'D: force restart with ?resume=1 may keep soft exit',
);

console.log('softExit.test.ts: A–D passed');
