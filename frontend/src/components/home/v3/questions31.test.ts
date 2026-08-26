/**
 * V3.1 — the interface side of a question that blocks work.
 *
 * There are two kinds of row under "Domande per te" and they are easy to
 * confuse, which is exactly why this exists. One is a suggestion the attention
 * layer thought worth raising; the other is a blocker — a piece of work
 * stopped, waiting for this answer. They look alike and behave differently,
 * and only the second one has a continuation behind it.
 *
 * What the guards protect is the contract between the two sides:
 *
 *   the interface may say what a person typed and which question they were
 *   answering — and nothing else. Where the work resumes is the server's,
 *   because a client that could name a continuation target is a client that
 *   could be persuaded to name someone else's.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import { buildOraConversationHref, oraEntryPointFrom } from '../../../ora/oraNav.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

const HOME = 'app/(tabs)/index.tsx';
const SECTIONS = 'src/components/home/v3/HomeSections.tsx';
const ACTIVITY = 'app/(tabs)/attivita.tsx';
const ORA = 'src/components/ora/OraConversationScreen.tsx';
const CLIENT = 'src/api/client.ts';

// ---------------------------------------------------------------------------
// A — a question travels as a handle, never as a destination
// ---------------------------------------------------------------------------
{
  const href = buildOraConversationHref({
    sessionId: 's_abc123',
    questionId: 'q_def456',
    entryPoint: 'question',
  });
  assert.ok(href.startsWith('/ora/s_abc123'), 'the answer belongs in the thread that asked');
  assert.ok(href.includes('questionId=q_def456'));
  assert.ok(href.includes('entry=question'));

  // Only opaque ids survive. Anything else is dropped rather than passed on.
  const dirty = buildOraConversationHref({ questionId: 'q id/../other', entryPoint: 'question' });
  assert.ok(!dirty.includes('questionId'), 'a malformed id must not reach the URL');

  assert.equal(oraEntryPointFrom('question'), 'question');
  assert.equal(oraEntryPointFrom('nonsense'), 'ora');

  // The URL says which question. It never says where to continue.
  for (const forbidden of ['planId=', 'planItemId=', 'objectId=', 'resume']) {
    assert.ok(
      !href.includes(forbidden),
      `answering must not carry a resume target: ${forbidden}`,
    );
  }
}

// ---------------------------------------------------------------------------
// B — Home shows what ORA is waiting for, not what it inferred
// ---------------------------------------------------------------------------
{
  const home = readCode(HOME);
  assert.ok(
    home.includes('home?.open_questions'),
    'Home must read the real open questions from the payload',
  );
  assert.ok(
    /open=\{openQuestions\}/.test(home),
    'and hand them to the section as their own list',
  );
  // The old heuristic still feeds ordinary suggestions; what it must not do is
  // be the only source of "Domande per te".
  assert.ok(home.includes('splitSuggestions'), 'suggestions keep their own path');

  const sections = readCode(SECTIONS);
  assert.ok(/open\?: OpenQuestionItem\[\]/.test(sections), 'the section takes real questions');
  assert.ok(
    sections.indexOf('open.slice(0, 3)') < sections.indexOf('questions.slice(0, 3)'),
    'a blocker comes before a suggestion: only one of them has stopped work',
  );
  // A section with neither kind of row does not appear at all.
  assert.ok(
    /if \(!questions\.length && !open\.length\) return null;/.test(sections),
    'no empty section',
  );
  assert.ok(
    /count=\{questions\.length \+ open\.length\}/.test(sections),
    'the count must include both kinds or it contradicts the list under it',
  );
}

// ---------------------------------------------------------------------------
// C — Activity and Home are two views of one thing
// ---------------------------------------------------------------------------
{
  const activity = readCode(ACTIVITY);
  assert.ok(
    /q\.kind === 'question' && q\.question_id/.test(activity),
    'Activity must recognise a real blocker',
  );
  assert.ok(
    /questionId: q\.question_id/.test(activity),
    'and carry its handle into the thread',
  );
  assert.ok(
    /sessionId: q\.session_id/.test(activity),
    'answering belongs in the conversation that asked',
  );
  // Both surfaces route through the same navigation helper, so neither can
  // drift into a second way of answering.
  for (const file of [HOME, ACTIVITY]) {
    assert.ok(
      readCode(file).includes('buildOraConversationHref'),
      `${file} must use the shared route builder`,
    );
  }
}

// ---------------------------------------------------------------------------
// D — one answer contract
// ---------------------------------------------------------------------------
{
  const client = readCode(CLIENT);
  assert.ok(client.includes("request<{ ok: boolean; items: OpenQuestionItem[] }>('/questions/open')"));
  assert.ok(/\/questions\/\$\{encodeURIComponent\(questionId\)\}\/answer/.test(client));

  // The body is the words and the provenance. Nothing about the work.
  const fn = client.slice(client.indexOf('answerQuestion:'), client.indexOf('documentPreferences:'));
  assert.ok(/JSON\.stringify\(\{ answer, \.\.\.\(source \? \{ source \} : \{\}\) \}\)/.test(fn));
  // Only the request body is the client's to compose; the response may
  // legitimately mention the session it resumed.
  const body = fn.slice(fn.indexOf('body:'), fn.indexOf('}),', fn.indexOf('body:')));
  for (const forbidden of ['plan_id', 'plan_item_id', 'object_id', 'resume', 'session_id']) {
    assert.ok(!body.includes(forbidden), `the client must not send ${forbidden}`);
  }

  const ora = readCode(ORA);
  assert.ok(
    /await api\.answerQuestion\(qid, msg, 'ora'\)/.test(ora),
    'answering a blocker must not go through the generic send',
  );
  // Cleared only after it is accepted: a failed attempt is still an answer.
  assert.ok(
    ora.indexOf('await api.answerQuestion') < ora.indexOf('pendingQuestion.current = null'),
    'the question stays pending until the answer is accepted',
  );
  // What the person sees afterwards is the server's transcript, not a local
  // guess at what the continuation produced.
  assert.ok(/await api\.aiCoreGet\(sessionId\)/.test(ora.slice(ora.indexOf('answerQuestion'))));
}

// ---------------------------------------------------------------------------
// E — nothing here knows about any domain, and nothing leaks
// ---------------------------------------------------------------------------
{
  for (const file of [HOME, SECTIONS, ACTIVITY, ORA]) {
    const src = readCode(file);
    for (const word of ['mutuo', 'mortgage', 'casa', 'viaggio', 'travel']) {
      assert.ok(!src.toLowerCase().includes(word), `${file} must not name a domain: ${word}`);
    }
    // Implementation state stays out of what a person reads.
    for (const leak of ['waiting_user', 'WAITING_USER', 'resume_pointer', 'dedupe_key']) {
      assert.ok(!src.includes(leak), `${file} must not surface ${leak}`);
    }
  }
}

console.log('V3.1 question guards: all assertions passed');
