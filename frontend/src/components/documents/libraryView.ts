/**
 * Documenti — how the read model reads.
 *
 * The backend decided what each document is and what state it is in; this
 * turns those facts into the words and the ordering on screen. Import-free so
 * the wording and the filtering can be checked without a bundler.
 */

export type DocStatus = 'ready' | 'analyzing' | 'pending' | 'needs_review' | 'failed';

export type DocArea = { key: string; label: string };

export type DocItem = {
  id: string;
  title: string;
  kind: string;
  uploaded_at: string;
  status: string;
  summary?: string;
  areas?: DocArea[];
  expiry?: { at: string; title: string } | null;
  open_actions?: number;
};

/* -------------------------------------------------------------------------- */
/* Words                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * What ORA can honestly claim about a document.
 *
 * "Analizzato" is a real claim — the pipeline finished and there is something
 * to read. Everything else says what is actually true instead of dressing it
 * up: still working, needs a look, could not be read, or simply sitting there.
 */
export function statusLabel(status: string): string {
  switch (status) {
    case 'ready':
      return 'Analizzato';
    case 'analyzing':
      return 'Analisi in corso';
    case 'needs_review':
      return 'Da verificare';
    case 'failed':
      return 'Non sono riuscita ad analizzarlo';
    default:
      return 'Da analizzare';
  }
}

/** "28 ago 2026" — never an ISO string. */
export function uploadedLabel(value?: string | null): string | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString('it-IT', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

/** "Scade oggi" · "Scade domani" · "Scade tra 12 giorni". */
export function expiryLabel(value?: string | null, now: Date = new Date()): string | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(new Date(t)) - startOf(now)) / 86400000);
  if (days < 0) return 'Scaduta';
  if (days === 0) return 'Scade oggi';
  if (days === 1) return 'Scade domani';
  return `Scade tra ${days} giorni`;
}

/** "Scade il 31 ago" — the date itself, for the row's own status line. */
export function expiryDateLabel(value?: string | null): string | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const d = new Date(t).toLocaleDateString('it-IT', { day: 'numeric', month: 'short' });
  return `Scade il ${d}`;
}

/** The day badge on a deadline row: { day: "31", month: "AGO" }. */
export function dayBadge(value?: string | null): { day: string; month: string } | null {
  if (!value) return null;
  const t = Date.parse(value);
  if (Number.isNaN(t)) return null;
  const d = new Date(t);
  return {
    day: String(d.getDate()).padStart(2, '0'),
    month: d.toLocaleDateString('it-IT', { month: 'short' }).replace('.', '').toUpperCase(),
  };
}

/**
 * What kind of document this is, in Italian.
 *
 * The classifier's own vocabulary is English and internal — "administrative",
 * "receipt", "generic" — and none of it should reach a screen. This is a
 * translation of an enum the pipeline already assigns, not a second
 * classification: an unknown key falls through to nothing rather than being
 * guessed at.
 */
const CATEGORY_LABELS: Record<string, string> = {
  event: 'Evento',
  education: 'Studio',
  administrative: 'Amministrativo',
  financial: 'Finanziario',
  medical: 'Medico',
  travel: 'Viaggio',
  receipt: 'Ricevuta',
  contract: 'Contratto',
  legal: 'Legale',
  generic: 'Documento',
  unknown: 'Da classificare',
};

export function categoryLabel(macro?: string | null): string | null {
  const key = String(macro || '').trim().toLowerCase();
  if (!key) return null;
  return CATEGORY_LABELS[key] ?? null;
}

/* -------------------------------------------------------------------------- */
/* Filtering and ordering                                                     */
/* -------------------------------------------------------------------------- */

export type StatusFilter = 'all' | 'ready' | 'pending' | 'expiring';
export type SortOrder = 'recent' | 'expiring' | 'name';

export const STATUS_FILTERS: Array<{ id: StatusFilter; label: string }> = [
  { id: 'all', label: 'Tutti gli stati' },
  { id: 'ready', label: 'Analizzati' },
  { id: 'pending', label: 'Da analizzare' },
  { id: 'expiring', label: 'Con scadenza' },
];

export const SORT_ORDERS: Array<{ id: SortOrder; label: string }> = [
  { id: 'recent', label: 'Più recenti' },
  { id: 'expiring', label: 'Scadenza vicina' },
  { id: 'name', label: 'Nome' },
];

/**
 * Search across what this page actually holds.
 *
 * Title, file kind, the summary ORA wrote and the areas it belongs to — all of
 * it already in the payload, so the results are instant and the placeholder can
 * name exactly these things without over-promising. Full-text search over the
 * document body exists elsewhere in the product; it is a different, slower
 * contract and is not what this box does.
 */
export function matchesQuery(item: DocItem, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    item.title,
    item.kind,
    item.summary || '',
    ...(item.areas || []).map((a) => a.label),
  ]
    .join(' ')
    .toLowerCase();
  return haystack.includes(q);
}

export function matchesStatus(item: DocItem, filter: StatusFilter): boolean {
  switch (filter) {
    case 'ready':
      return item.status === 'ready';
    case 'pending':
      // Everything ORA has not finished understanding, however it got there.
      return item.status === 'pending' || item.status === 'analyzing' || item.status === 'failed';
    case 'expiring':
      return !!item.expiry;
    default:
      return true;
  }
}

export function sortItems(items: DocItem[], order: SortOrder): DocItem[] {
  const out = [...items];
  if (order === 'name') {
    out.sort((a, b) => a.title.localeCompare(b.title, 'it'));
    return out;
  }
  if (order === 'expiring') {
    // Documents with a real deadline first, soonest at the top; everything
    // without one keeps its place behind them rather than being pushed to an
    // arbitrary end of an imagined scale.
    out.sort((a, b) => {
      const at = a.expiry ? Date.parse(a.expiry.at) : Infinity;
      const bt = b.expiry ? Date.parse(b.expiry.at) : Infinity;
      if (at !== bt) return at - bt;
      return Date.parse(b.uploaded_at) - Date.parse(a.uploaded_at);
    });
    return out;
  }
  out.sort((a, b) => Date.parse(b.uploaded_at) - Date.parse(a.uploaded_at));
  return out;
}

/** Everything the list shows, after the controls above it. */
export function visibleItems(
  items: DocItem[],
  opts: { query: string; kind: string; status: StatusFilter; order: SortOrder },
): DocItem[] {
  const filtered = items.filter(
    (it) =>
      matchesQuery(it, opts.query) &&
      (opts.kind === 'all' || it.kind === opts.kind) &&
      matchesStatus(it, opts.status),
  );
  return sortItems(filtered, opts.order);
}

/* -------------------------------------------------------------------------- */
/* Upload                                                                     */
/* -------------------------------------------------------------------------- */

export type UploadPhase = 'idle' | 'uploading' | 'analyzing' | 'done' | 'failed';

/**
 * What to say while a file is on its way.
 *
 * The failure line matters most: an upload that succeeded and an analysis that
 * did not are different events, and telling someone their document is gone
 * when it is sitting safely in their library would be both wrong and alarming.
 */
export function uploadLabel(phase: UploadPhase): string | null {
  switch (phase) {
    case 'uploading':
      return 'Caricamento…';
    case 'analyzing':
      return 'Analisi in corso…';
    case 'done':
      return 'Pronto';
    case 'failed':
      return 'Il documento è salvato, ma non sono riuscita ad analizzarlo.';
    default:
      return null;
  }
}
