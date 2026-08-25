/**
 * Presentation-only readers over the Life OS plan bundle.
 *
 * Nothing here changes plan semantics, ordering or status — it only decides
 * how what already exists should be read by a person. Anything that would
 * change *which* step is next belongs to the backend.
 */

export type PlanItemView = {
  id: string;
  title: string;
  /** done · now · next — the three states a person actually needs. */
  state: 'done' | 'now' | 'next';
  when?: string | null;
};

type RawItem = {
  id: string;
  title: string;
  status?: string;
  order?: number;
  due_date?: string | null;
};

/** "sab 19 set" — never a raw YYYY-MM-DD. */
export function humanDate(value?: string | null): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: undefined });
}

/**
 * The plan as a progression rather than a list.
 *
 * `now` is whichever item the backend already chose as next — the interface
 * never re-derives it, because "what should I do next" is a decision the plan
 * owns. Everything before it reads as done, everything after as still to come.
 */
export function planProgression(
  items: RawItem[] | undefined | null,
  nextItemId?: string | null,
): PlanItemView[] {
  const list = [...(items || [])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  return list.map((it) => {
    const done = it.status === 'completed' || it.status === 'skipped';
    const isNow = !!nextItemId && it.id === nextItemId;
    return {
      id: it.id,
      title: it.title,
      state: isNow ? 'now' : done ? 'done' : 'next',
      when: humanDate(it.due_date),
    };
  });
}

export function completedCount(items: RawItem[] | undefined | null): number {
  return (items || []).filter((i) => i.status === 'completed').length;
}

/** True once there is genuinely nothing left to do. */
export function isPlanComplete(
  plan: { status?: string; items?: RawItem[] } | null | undefined,
  nextItem?: { id?: string } | null,
): boolean {
  if (!plan) return false;
  if (plan.status === 'completed') return true;
  const items = plan.items || [];
  if (!items.length) return false;
  const allDone = items.every((i) => i.status === 'completed' || i.status === 'skipped');
  return allDone && !nextItem?.id;
}

/**
 * Sources fit to show a person.
 *
 * The existing anti-identifier filter is kept verbatim: anything that still
 * looks like an internal reference is not a source the user can recognise, and
 * showing it would be leaking a database row into a sentence.
 */
export function publicSources(
  raw: Array<{ display_name?: string; authority_label?: string }> | undefined | null,
): Array<{ name: string; authority: string }> {
  return (raw || [])
    .map((s) => ({
      name: String(s.display_name || '').trim(),
      authority: String(s.authority_label || '').trim(),
    }))
    .filter((s) => s.name && !/^(lcf_|doc_|lop_|lgo_)/i.test(s.name));
}

export type MaterialView = { id: string; title: string; purpose?: string | null };

/** The objects ORA has produced, as things with names rather than records. */
export function materials(objects: any[] | undefined | null): MaterialView[] {
  return (objects || [])
    .filter((o) => o?.id)
    .map((o) => ({
      id: String(o.id),
      title: String(o.title || 'Materiale'),
      purpose: o.purpose ? String(o.purpose) : null,
    }));
}
