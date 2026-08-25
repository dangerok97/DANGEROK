/**
 * Vita — the view model, composed from what ORA already knows.
 *
 * Two payloads that already exist feed this page: the Life Map (which areas of
 * a life ORA can see, and what is happening in them right now) and Life Memory
 * (the individual things it has learned, each already carrying a human
 * sentence and a human provenance label). Nothing here classifies, ranks or
 * infers — it selects, groups and orders what the backend has already decided,
 * and refuses to show anything it cannot source.
 *
 * Deliberately import-free so the shaping can be checked without a network,
 * a theme or a bundler.
 */

/* -------------------------------------------------------------------------- */
/* Inputs — the shapes the two APIs already return                            */
/* -------------------------------------------------------------------------- */

export type LifeMapLike = {
  areas?: Array<{
    id: string;
    domain: string;
    title: string;
    identity?: string | null;
    visual?: { status?: string; url?: string | null } | null;
  }>;
  situations?: Array<{
    id: string;
    kind?: string;
    title: string;
    temporal?: string | null;
    summary?: string | null;
    href?: string | null;
    visual?: { status?: string; url?: string | null } | null;
  }>;
};

export type LifeMemoryLike = {
  memories?: Array<{
    id: string;
    statement?: string;
    belief_statement?: string | null;
    status?: string;
    domain?: string | null;
    group_label?: string | null;
    provenance_label?: string | null;
    clarifiable?: boolean;
    clarification_goal?: string | null;
    learned_at?: string | null;
    updated_at?: string | null;
  }>;
  groups?: Array<{ id: string; label: string; domain?: string | null; memory_ids?: string[] }>;
  partial?: boolean;
};

/* -------------------------------------------------------------------------- */
/* Outputs                                                                    */
/* -------------------------------------------------------------------------- */

export type VitaSituation = {
  id: string;
  title: string;
  summary?: string | null;
  temporal?: string | null;
  href?: string | null;
  kind?: string | null;
  visualUrl?: string | null;
  visualPending: boolean;
};

export type VitaFact = {
  id: string;
  /** The sentence ORA would say out loud. */
  statement: string;
  /** "Me l'hai detto tu" · "Da un documento" — already human, never a provider. */
  provenance?: string | null;
  /** ORA is not sure about this one. */
  uncertain: boolean;
};

export type VitaArea = {
  id: string;
  /** Stable key for the detail route — never shown. */
  domain: string;
  title: string;
  identity?: string | null;
  /** A few salient things, not the whole record. */
  facts: VitaFact[];
  /** How many more ORA holds beyond the ones shown. */
  moreCount: number;
  visualUrl?: string | null;
  visualPending: boolean;
};

export type VitaQuestion = {
  /** The memory this question is about — feeds the existing clarify flow. */
  memoryId: string;
  question: string;
};

export type VitaUpdate = {
  id: string;
  statement: string;
  /** Which part of life it belongs to, when known. */
  areaTitle?: string | null;
  at: string;
};

export type VitaSummaryRow = { label: string; value: number };

export type VitaModel = {
  situations: VitaSituation[];
  areas: VitaArea[];
  questions: VitaQuestion[];
  updates: VitaUpdate[];
  summary: VitaSummaryRow[];
};

/* -------------------------------------------------------------------------- */

/** Shown per area card — enough to recognise the state, far short of a dump. */
export const FACTS_PER_AREA = 3;
const MAX_QUESTIONS = 4;
const MAX_UPDATES = 4;

const LIVE_STATUSES = new Set(['known', 'likely', 'ambiguous']);

function ts(value?: string | null): number {
  if (!value) return 0;
  const t = Date.parse(value);
  return Number.isNaN(t) ? 0 : t;
}

function clean(value?: string | null): string {
  return String(value || '').trim();
}

/**
 * Which few facts to show for an area.
 *
 * Not "the first three rows". Recency is the only ordering signal both APIs
 * agree on, and it is the honest one here: what ORA learned or revised most
 * recently is what best describes where this part of a life currently stands.
 * Uncertain items sink — a card is a summary, and leading it with something
 * ORA is unsure of misrepresents what it knows. They are not hidden: they
 * surface in DA CHIARIRE, where they can actually be resolved.
 */
export function salientFacts(
  memories: NonNullable<LifeMemoryLike['memories']>,
): VitaFact[] {
  return [...memories]
    .sort((a, b) => {
      const au = a.status === 'ambiguous' ? 1 : 0;
      const bu = b.status === 'ambiguous' ? 1 : 0;
      if (au !== bu) return au - bu;
      return (
        Math.max(ts(b.updated_at), ts(b.learned_at)) -
        Math.max(ts(a.updated_at), ts(a.learned_at))
      );
    })
    .map((m) => ({
      id: m.id,
      statement: clean(m.belief_statement) || clean(m.statement),
      provenance: clean(m.provenance_label) || null,
      uncertain: m.status === 'ambiguous',
    }))
    .filter((f) => !!f.statement);
}

/**
 * The whole page, from the two payloads.
 *
 * Areas come from the Life Map, which is what decides that a part of a life
 * exists at all — memories only furnish the ones already there. That ordering
 * matters: grouping by whatever domains happen to appear on memory records
 * would let a stray fact invent a life area, which is the taxonomy invention
 * this page is not allowed to do.
 */
export function buildVita(map: LifeMapLike | null, memory: LifeMemoryLike | null): VitaModel {
  const situations: VitaSituation[] = (map?.situations || [])
    .filter((s) => clean(s.title))
    .map((s) => ({
      id: s.id,
      title: clean(s.title),
      summary: clean(s.summary) || null,
      temporal: clean(s.temporal) || null,
      href: clean(s.href) || null,
      kind: s.kind || null,
      visualUrl: s.visual?.status === 'ready' ? s.visual.url || null : null,
      visualPending: s.visual?.status === 'queued' || s.visual?.status === 'generating',
    }));

  const usable = (memory?.memories || []).filter(
    (m) => LIVE_STATUSES.has(m.status || 'known') && clean(m.belief_statement || m.statement),
  );

  const byDomain = new Map<string, typeof usable>();
  for (const m of usable) {
    const key = clean(m.domain).toLowerCase();
    if (!key) continue;
    const bucket = byDomain.get(key);
    if (bucket) bucket.push(m);
    else byDomain.set(key, [m]);
  }

  const areas: VitaArea[] = (map?.areas || [])
    .filter((a) => clean(a.title))
    .map((a) => {
      const all = salientFacts(byDomain.get(clean(a.domain).toLowerCase()) || []);
      return {
        id: a.id,
        domain: clean(a.domain),
        title: clean(a.title),
        identity: clean(a.identity) || null,
        facts: all.slice(0, FACTS_PER_AREA),
        moreCount: Math.max(0, all.length - FACTS_PER_AREA),
        visualUrl: a.visual?.status === 'ready' ? a.visual.url || null : null,
        visualPending: a.visual?.status === 'queued' || a.visual?.status === 'generating',
      };
    });

  // Only real open questions, and only ones the existing clarify flow can act
  // on — a question with nowhere to go would be theatre.
  const questions: VitaQuestion[] = (memory?.memories || [])
    .filter((m) => m.status === 'ambiguous' && m.clarifiable)
    .map((m) => ({
      memoryId: m.id,
      // `statement` is the phrasing the backend already writes for something
      // ORA is unsure of — "Mi risulta che…, ma non ne sono ancora sicura."
      // `clarification_goal` sits next to it and is tempting, but it is an
      // instruction addressed to the reasoning core, in English, about the
      // user. Putting it on this page would be the clearest possible way to
      // make a page about trust feel like a console.
      question: clean(m.statement) || clean(m.belief_statement),
    }))
    .filter((q) => !!q.question)
    .slice(0, MAX_QUESTIONS);

  const areaTitleByDomain = new Map(
    (map?.areas || []).map((a) => [clean(a.domain).toLowerCase(), clean(a.title)]),
  );

  const updates: VitaUpdate[] = usable
    .map((m) => ({
      id: m.id,
      statement: clean(m.belief_statement) || clean(m.statement),
      areaTitle: areaTitleByDomain.get(clean(m.domain).toLowerCase()) || null,
      at: clean(m.updated_at) || clean(m.learned_at),
      _t: Math.max(ts(m.updated_at), ts(m.learned_at)),
    }))
    .filter((u) => u._t > 0)
    .sort((a, b) => b._t - a._t)
    .slice(0, MAX_UPDATES)
    .map(({ _t, ...u }) => u);

  // Only what can be counted correctly from what is on this page. No metric
  // exists here that the user cannot verify by looking just above it.
  const summary: VitaSummaryRow[] = [];
  if (situations.length) summary.push({ label: 'Situazioni in corso', value: situations.length });
  const withHorizon = situations.filter((s) => !!s.temporal).length;
  if (withHorizon) summary.push({ label: 'Con una scadenza', value: withHorizon });
  if (questions.length) summary.push({ label: 'Da chiarire', value: questions.length });

  return { situations, areas, questions, updates, summary };
}

/** True when there is genuinely nothing to show yet. */
export function isVitaEmpty(m: VitaModel): boolean {
  return !m.situations.length && !m.areas.length;
}

/** "Oggi, 09:12" · "Ieri, 18:45" · "12 set" — never an ISO string. */
export function whenLabel(value: string, now: Date = new Date()): string | null {
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const d = new Date(t);
  const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return `Oggi, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `Ieri, ${time}`;
  return d.toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
}
