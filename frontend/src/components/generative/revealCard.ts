/**
 * Generic revealable-card contract (domain-neutral).
 *
 * Canonical item after normalize:
 *   { front: string, back: string, revealable: boolean, label?: string }
 *
 * Compat aliases (small set):
 *   front ← front | question | prompt | title | text
 *   back  ← back | answer | reveal | hidden | body | detail | text(if unused)
 */

export type RevealCardItem = {
  front: string;
  back: string;
  revealable: boolean;
  label?: string;
  meta?: Record<string, unknown>;
};

export function normalizeRevealCardItem(raw: unknown): RevealCardItem {
  if (!raw || typeof raw !== 'object') {
    return { front: '', back: '', revealable: false };
  }
  const it = raw as Record<string, unknown>;
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

  const out: RevealCardItem = {
    front,
    back,
    revealable: Boolean(back),
  };
  if (title && title !== front) out.label = title;
  if (it.meta && typeof it.meta === 'object') {
    out.meta = it.meta as Record<string, unknown>;
  }
  return out;
}

export function normalizeRevealCardItems(items: unknown[]): RevealCardItem[] {
  if (!Array.isArray(items)) return [];
  return items
    .map(normalizeRevealCardItem)
    .filter((c) => Boolean(c.front));
}

export const EMPTY_REVEAL_FALLBACK = 'Contenuto non disponibile';
