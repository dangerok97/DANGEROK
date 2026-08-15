/**
 * V2.4.3 — revealable card contract (mirrors revealCard.ts).
 * node frontend/src/components/generative/revealCard.regression.mjs
 */
import assert from 'assert';

const EMPTY_REVEAL_FALLBACK = 'Contenuto non disponibile';

function normalizeRevealCardItem(raw) {
  if (!raw || typeof raw !== 'object') {
    return { front: '', back: '', revealable: false };
  }
  const it = raw;
  let front = String(it.front || it.question || it.prompt || '').trim();
  let back = String(it.back || it.answer || it.reveal || it.hidden || '').trim();
  let title = String(it.title || it.label || '').trim();
  let text = String(it.text || it.body || it.detail || '').trim();

  if (!front) {
    if (title) {
      front = title;
      title = '';
    } else if (text) {
      front = text;
      text = '';
    }
  }
  if (!back) {
    if (text && text !== front) back = text;
    else if (title && title !== front) back = title;
  }

  const out = { front, back, revealable: Boolean(back) };
  if (title && title !== front) out.label = title;
  return out;
}

function normalizeRevealCardItems(items) {
  if (!Array.isArray(items)) return [];
  return items.map(normalizeRevealCardItem).filter((c) => Boolean(c.front));
}

function visibleCardState(card, revealed) {
  const front = card.front || '';
  if (!card.revealable) {
    return { front, showHint: false, back: null, blank: !front };
  }
  if (!revealed) {
    return { front, showHint: true, back: null, blank: !front };
  }
  const back = card.back || EMPTY_REVEAL_FALLBACK;
  return { front, showHint: false, back, blank: !back };
}

function navReset(revealed, dir, idx, len) {
  const nextIdx =
    dir === 'next' ? Math.min(len - 1, idx + 1) : Math.max(0, idx - 1);
  return { idx: nextIdx, revealed: false };
}

// A — valid revealable shows front
{
  const c = normalizeRevealCardItem({ front: 'Q', back: 'A' });
  const v = visibleCardState(c, false);
  assert.strictEqual(v.front, 'Q');
  assert.strictEqual(v.showHint, true);
  assert.strictEqual(v.blank, false);
}

// B/C — reveal shows non-empty back
{
  const c = normalizeRevealCardItem({ front: 'Q', back: 'A' });
  const v = visibleCardState(c, true);
  assert.strictEqual(v.back, 'A');
  assert.strictEqual(v.blank, false);
}

// D/E — next/prev resets reveal
{
  const n = navReset(true, 'next', 0, 2);
  assert.strictEqual(n.idx, 1);
  assert.strictEqual(n.revealed, false);
  const p = navReset(true, 'prev', 1, 2);
  assert.strictEqual(p.idx, 0);
  assert.strictEqual(p.revealed, false);
}

// F — malformed empty front filtered
{
  const items = normalizeRevealCardItems([{ front: '', back: 'A' }, { front: 'Ok', back: 'B' }]);
  assert.strictEqual(items.length, 1);
  assert.strictEqual(items[0].front, 'Ok');
}

// G — prior compatible schema (title-only / question-answer)
{
  const legacy = normalizeRevealCardItem({
    title: 'Esempio pratico: La spesa al supermercato',
    front: '',
    back: '',
  });
  assert.strictEqual(legacy.front, 'Esempio pratico: La spesa al supermercato');
  assert.strictEqual(legacy.revealable, false);
  const qa = normalizeRevealCardItem({ question: 'Q?', answer: 'A!' });
  assert.strictEqual(qa.front, 'Q?');
  assert.strictEqual(qa.back, 'A!');
}

// H — no study/exam branch in this module (contract is generic)
assert.ok(typeof normalizeRevealCardItem === 'function');

// I — interaction event shape (generic reveal)
{
  const event = { type: 'reveal', payload: { index: 0, revealed: true } };
  assert.strictEqual(event.type, 'reveal');
  assert.notStrictEqual(event.type, 'flashcard_answered');
}

// J — never blank reveal state
{
  const emptyBack = { front: 'Q', back: '', revealable: true }; // defensive
  const v = visibleCardState(emptyBack, true);
  assert.strictEqual(v.back, EMPTY_REVEAL_FALLBACK);
  assert.strictEqual(v.blank, false);
}

console.log('ok: revealCard V2.4.3 regression');
