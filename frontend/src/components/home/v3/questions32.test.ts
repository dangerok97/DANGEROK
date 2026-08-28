/**
 * V3.2 — "Domande per te" means one thing.
 *
 * Home showed three rows under that heading for a single blocker: the real
 * question, the same thing again as a suggestion written in English, and a
 * third notice about the same work. Two of the three could not be answered in
 * any way that moved anything, and the badge above them said "3" while the
 * rail beside them said "2" about the same idea.
 *
 * The rule these guard is small and has to hold in one place only: a real
 * question wins its section outright, the suggestions become what they always
 * were — notices — and every number on the page counts the same list.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../../..');
const readCode = (rel: string) =>
  readFileSync(resolve(FRONTEND, rel), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

const HOME = 'app/(tabs)/index.tsx';

// ---------------------------------------------------------------------------
// A — a real blocker is the only kind of question shown
// ---------------------------------------------------------------------------
{
  const home = readCode(HOME);

  assert.ok(
    /const pendingQuestions = openQuestions\.length \? \[\] : questions;/.test(home),
    'a real open question must clear the suggestion rows from the section',
  );
  assert.ok(
    /const demotedQuestions = openQuestions\.length \? questions : \[\];/.test(home),
    'and the suggestions it displaced must be kept, not dropped',
  );
  assert.ok(
    /\[\.\.\.demotedQuestions, \.\.\.updates\]/.test(home),
    'they belong in the updates feed, which is what a notice is',
  );
  assert.ok(
    /questions=\{pendingQuestions\}/.test(home),
    'the section must render the filtered list, not the raw one',
  );
  assert.ok(
    /suggestions=\{updateFeed\}/.test(home),
    'and the feed must render the combined one',
  );
}

// ---------------------------------------------------------------------------
// B — one number, one definition
// ---------------------------------------------------------------------------
{
  const home = readCode(HOME);

  assert.ok(
    /const pendingQuestionCount = openQuestions\.length \+ pendingQuestions\.length;/.test(home),
    'the count must be derived once, from exactly what is rendered',
  );
  assert.ok(
    !/questionCount=\{questions\.length\}/.test(home),
    'the rail must not count a different list from the section',
  );
  const railCounts = home.match(/questionCount=\{pendingQuestionCount\}/g) || [];
  assert.equal(railCounts.length, 2, 'both layouts read the same number');
  assert.ok(
    /\{pendingQuestionCount \? \(/.test(home),
    'and the section appears exactly when that number is non-zero',
  );
}

console.log('V3.2 question-projection guards: all assertions passed');
