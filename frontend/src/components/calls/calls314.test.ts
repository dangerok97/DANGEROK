/**
 * The words on the way into Chiamate, and the words inside it.
 *
 * Run with: node --experimental-strip-types src/components/calls/calls314.test.ts
 *
 * Pure functions only, the way the other model tests here work. What is being
 * held still is placement and hierarchy: where Chiamate sits in the shell,
 * when it counts as the current place, how a duration is said, and which
 * state is allowed to raise its voice. Those are the decisions that make this
 * a report rather than a log, and they are exactly the kind that drift back
 * to defaults months later.
 */
import assert from 'node:assert/strict';

import { AMBIENT_NAV_ITEMS } from '../../shell/navItems.ts';
import { howLong, toneOf, whenItHappened } from './callPresentation.ts';

/* -------------------------------------------------------------------------- */
/* Where Chiamate sits, and when it is lit                                    */
/* -------------------------------------------------------------------------- */

// Between ORA and Attività: a call is something ORA did for you, so it sits
// with the doing — after the place you ask, before the place you watch.
const ordine = AMBIENT_NAV_ITEMS.map((i) => i.key);
assert.deepEqual(ordine, [
  'index',
  'contesti',
  'ora',
  'chiamate',
  'attivita',
  'documenti',
]);

const chiamate = AMBIENT_NAV_ITEMS.find((i) => i.key === 'chiamate')!;

// The rail only. The phone bar is full, and this project already wrote down
// why: six labelled items do not fit 375px, and the first label to truncate
// would be Documenti. A destination that earns a place on the rail does not
// automatically earn one down there.
assert.equal(chiamate.railOnly, true);
assert.equal(chiamate.label, 'Chiamate');

// It is a tab route, not a loose address.
//
// It started as one, outside `(tabs)`, and the page came up with no rail and
// no way back: a screen outside the navigator does not get the shell. Living
// inside it — invisible to the phone bar via `href: null` there and `railOnly`
// here — is what makes it a section rather than a dead end.
assert.equal(chiamate.href, undefined);
assert.equal(chiamate.route, 'chiamate');

// And nobody else is rail-only: the rule exists for this one case, and a
// second silent user of it would be a navigation that quietly differs between
// desktop and phone.
assert.deepEqual(
  AMBIENT_NAV_ITEMS.filter((i) => i.railOnly).map((i) => i.key),
  ['chiamate'],
);

/**
 * Mirrors AmbientTabBar's rule for destinations that carry an address.
 *
 * Chiamate no longer needs it — it is a tab, and the navigator says which tab
 * is current. The rule is kept under test because the field that triggers it
 * is still there for the next destination that genuinely lives elsewhere, and
 * the `startsWith` is its whole point: without it a rail goes blank the moment
 * you open a detail page, which reads as having left the section you are
 * plainly still inside.
 */
function lit(href: string, pathname: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

assert.equal(lit('/chiamate', '/chiamate'), true);
assert.equal(lit('/chiamate', '/chiamate/tel_6eaae7b9cc4040'), true);

// And not lit for a neighbour that merely begins the same way.
assert.equal(lit('/chiamate', '/chiamate-vecchie'), false);
assert.equal(lit('/chiamate', '/attivita'), false);
assert.equal(lit('/chiamate', '/'), false);

/* -------------------------------------------------------------------------- */
/* How long it lasted                                                         */
/* -------------------------------------------------------------------------- */

// "00:46" is a stopwatch; "46 s" is an answer.
assert.equal(howLong(46), '46 s');
assert.equal(howLong(52), '52 s');
assert.equal(howLong(60), '1 min');
assert.equal(howLong(72), '1 min 12 s');
assert.equal(howLong(180), '3 min');

// A call nobody answered has no duration. Printing "0 s" would suggest a
// conversation that lasted no time rather than one that never started.
assert.equal(howLong(null), '');
assert.equal(howLong(undefined), '');

/* -------------------------------------------------------------------------- */
/* When it happened                                                           */
/* -------------------------------------------------------------------------- */

// Someone opening this screen is almost always looking for the call from an
// hour ago, so today and yesterday get names instead of dates.
const oggi = new Date();
oggi.setHours(9, 42, 0, 0);
assert.match(whenItHappened(oggi.toISOString()), /^Oggi · \d{2}:\d{2}$/);

const ieri = new Date();
ieri.setDate(ieri.getDate() - 1);
ieri.setHours(17, 3, 0, 0);
assert.match(whenItHappened(ieri.toISOString()), /^Ieri · \d{2}:\d{2}$/);

// Further back, a date — and never a crash on something that is not one.
assert.equal(whenItHappened(''), '');
assert.equal(whenItHappened(null), '');
assert.equal(whenItHappened('non è una data'), '');

/* -------------------------------------------------------------------------- */
/* Which state is allowed to raise its voice                                  */
/* -------------------------------------------------------------------------- */

// Exactly one. `serve_una_decisione` earns `attention` because nothing moves
// until the person does something; everything else is information, and
// information that competes for attention stops being information.
assert.equal(toneOf('serve_una_decisione'), 'attention');

assert.equal(toneOf('completata'), 'positive');
assert.equal(toneOf('in_corso'), 'neutral');

// A call nobody answered is not a failure anybody needs to feel. Quiet.
assert.equal(toneOf('nessuna_risposta'), 'quiet');
assert.equal(toneOf('occupato'), 'quiet');
assert.equal(toneOf('segreteria'), 'quiet');

// And a mission that did not succeed is stated, not alarmed about: the line
// worked, the errand did not, and red would blame the wrong one.
assert.equal(toneOf('non_riuscita'), 'neutral');
assert.equal(toneOf('interrotta'), 'neutral');

console.log('calls314: all assertions passed');
