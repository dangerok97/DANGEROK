/**
 * PX1.7 — Documenti contract guards.
 *
 * The failure this page has to avoid is looking like a file manager that
 * happens to be inside ORA. Two things keep it from becoming one, and both are
 * easy to lose by accident: a deadline must be a date something actually
 * found, and a document's place in someone's life must be a link something
 * actually recorded. Guessing either from a filename would produce a page that
 * looks smarter and is less trustworthy.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  categoryLabel,
  dayBadge,
  expiryDateLabel,
  expiryLabel,
  matchesQuery,
  matchesStatus,
  sortItems,
  statusLabel,
  uploadLabel,
  uploadedLabel,
  visibleItems,
  type DocItem,
} from './libraryView.ts';
import { buildOraConversationHref, oraEntryPointFrom } from '../../ora/oraNav.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const BACKEND = resolve(FRONTEND, '../backend');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readBackend = (rel: string) => readFileSync(resolve(BACKEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '');
const readBackendCode = (rel: string) =>
  readBackend(rel)
    .replace(/^\s*#.*$/gm, '')
    .replace(/"""[\s\S]*?"""/g, '');

const ROUTE = 'app/(tabs)/documenti.tsx';
const PARTS = 'src/components/documents/LibraryParts.tsx';
const DETAIL = 'app/document/[id].tsx';
const MODEL = 'documents/library.py';

const now = new Date('2026-08-25T12:00:00Z');

const ITEMS: DocItem[] = [
  {
    id: 'a',
    title: 'Contratto affitto casa',
    kind: 'PDF',
    uploaded_at: '2026-08-22T10:00:00Z',
    status: 'ready',
    summary: 'Locazione quadriennale.',
    areas: [{ key: 'casa', label: 'Casa' }],
    expiry: null,
  },
  {
    id: 'b',
    title: 'Bollo auto 2026',
    kind: 'PDF',
    uploaded_at: '2026-08-12T10:00:00Z',
    status: 'ready',
    summary: 'Avviso di pagamento.',
    areas: [{ key: 'auto', label: 'Auto' }],
    expiry: { at: '2026-09-06T00:00:00Z', title: 'Bollo auto 2026' },
  },
  {
    id: 'c',
    title: 'Preventivo ristrutturazione',
    kind: 'PDF',
    uploaded_at: '2026-08-04T10:00:00Z',
    status: 'pending',
  },
  {
    id: 'd',
    title: 'Scansione ricevuta',
    kind: 'PDF',
    uploaded_at: '2026-08-23T10:00:00Z',
    status: 'failed',
  },
];

// ---------------------------------------------------------------------------
// A — A deadline is found, never inferred
// ---------------------------------------------------------------------------
{
  const model = readBackendCode(MODEL);
  const expiryFn = model.slice(model.indexOf('def _expiry_of'), model.indexOf('def _summary_of'));
  assert.ok(
    expiryFn.includes('(ev.get("category") or "") != "deadline"'),
    'only a candidate the extractor marked as a deadline may become an expiry',
  );
  assert.ok(
    !/filename|title\.lower|scadenz|bollo|polizza/i.test(expiryFn),
    'an expiry must never be guessed from a name',
  );
  // An ordinary event on a document is a date, not an expiry.
  assert.ok(
    expiryFn.includes('start_datetime'),
    'the expiry is the persisted datetime, not a re-parse',
  );
}

// ---------------------------------------------------------------------------
// B — A life area is a recorded link, never a keyword
// ---------------------------------------------------------------------------
{
  const model = readBackendCode(MODEL);
  const areasFn = model.slice(
    model.indexOf('async def _areas_by_document'),
    model.indexOf('async def build_library'),
  );
  assert.ok(
    areasFn.includes('linked_doc_ids') && areasFn.includes('source_document_id'),
    'the link must come from the Life Profile fact that names the document',
  );
  assert.ok(
    !/filename|original_filename|in title|lower\(\)\s*\.find/.test(areasFn),
    'an area must never be derived from the file name',
  );
  // The vocabulary belongs to the Life Map; this module only knows the keys.
  assert.ok(
    /domain_labels/.test(model) && !/"Casa"|"Auto"|"Finanze"|"Salute"/.test(model),
    'Documenti must not name life domains itself',
  );
}

// ---------------------------------------------------------------------------
// C — Human statuses, and the honest failure
// ---------------------------------------------------------------------------
{
  assert.equal(statusLabel('ready'), 'Analizzato');
  assert.equal(statusLabel('pending'), 'Da analizzare');
  assert.equal(statusLabel('analyzing'), 'Analisi in corso');
  assert.equal(statusLabel('needs_review'), 'Da verificare');
  assert.equal(statusLabel('failed'), 'Non sono riuscita ad analizzarlo');
  // Every state has words of its own — colour is never the only signal.
  const labels = ['ready', 'pending', 'analyzing', 'needs_review', 'failed'].map(statusLabel);
  assert.equal(new Set(labels).size, labels.length);

  // An upload that stored the file but could not read it has not lost it.
  const failed = uploadLabel('failed') || '';
  assert.ok(/salvato/i.test(failed), 'a failed analysis must say the document is still there');
  assert.ok(!/perso|eliminat/i.test(failed));
  assert.equal(uploadLabel('idle'), null);
}

// ---------------------------------------------------------------------------
// D — The classifier's vocabulary never reaches a screen
// ---------------------------------------------------------------------------
{
  assert.equal(categoryLabel('administrative'), 'Amministrativo');
  assert.equal(categoryLabel('receipt'), 'Ricevuta');
  // An unknown key produces nothing rather than a guess or a raw enum.
  assert.equal(categoryLabel('something_new'), null);
  assert.equal(categoryLabel(''), null);
  assert.equal(categoryLabel(null), null);

  const surface = readCode(ROUTE) + readCode(PARTS);
  for (const leak of [
    'macro_category',
    'pipeline_status',
    'storage_key',
    'file_id',
    'awaiting_confirmation',
    'confidence',
  ]) {
    assert.ok(!surface.includes(leak), `internal state must not reach the UI: ${leak}`);
  }

  // The detail is older and reads the raw pipeline state to know when to stop
  // polling, which is legitimate. What must never happen is rendering it: the
  // backend already writes a human label beside it, and that is what shows.
  const detail = readCode(DETAIL);
  assert.ok(
    /\{analysis\?\.pipeline_status_label \|\| ins\.type_label\}/.test(detail),
    'the detail must render the human label, never the raw status',
  );
  assert.ok(
    !/\{analysis\?\.pipeline_status\}|\{doc\.pipeline_status\}/.test(detail),
    'the raw pipeline status must never be rendered',
  );
  assert.ok(
    !/\{analysis\?\.analysis\?\.macro_category\}|` · \$\{analysis\.analysis\.macro_category\}`/.test(detail),
    'the raw classifier category must never be rendered',
  );

  // The extractor's own ranking inputs are not facts about the document.
  const panel = readCode('src/components/documents/DocumentUtilityPanel.tsx');
  assert.ok(
    !/k="Priorità"|k="Urgenza"|k="Timezone"/.test(panel),
    'candidate scoring and plumbing must not be rendered as document fields',
  );
}

// ---------------------------------------------------------------------------
// E — Time is spoken
// ---------------------------------------------------------------------------
{
  const up = uploadedLabel('2026-08-22T10:00:00Z') || '';
  assert.ok(up && !/\d{4}-\d{2}-\d{2}/.test(up) && /2026/.test(up));
  assert.equal(uploadedLabel(null), null);

  assert.equal(expiryLabel('2026-08-25T12:00:00Z', now), 'Scade oggi');
  assert.equal(expiryLabel('2026-08-26T12:00:00Z', now), 'Scade domani');
  assert.equal(expiryLabel('2026-09-06T12:00:00Z', now), 'Scade tra 12 giorni');
  assert.equal(expiryLabel('2026-08-20T12:00:00Z', now), 'Scaduta');
  assert.equal(expiryLabel(undefined), null);

  const d = expiryDateLabel('2026-09-06T12:00:00Z') || '';
  assert.ok(/^Scade il /.test(d) && !/\d{4}-\d{2}-\d{2}/.test(d));

  const badge = dayBadge('2026-09-06T12:00:00Z');
  assert.equal(badge?.day, '06');
  assert.ok(badge && /^[A-Z]{3}$/.test(badge.month));
}

// ---------------------------------------------------------------------------
// F — Search and filters only promise what they do
// ---------------------------------------------------------------------------
{
  // The box searches the payload on screen: title, kind, summary, areas.
  assert.equal(matchesQuery(ITEMS[0], 'affitto'), true);
  assert.equal(matchesQuery(ITEMS[0], 'PDF'), true);
  assert.equal(matchesQuery(ITEMS[0], 'quadriennale'), true, 'the summary is searchable');
  assert.equal(matchesQuery(ITEMS[0], 'Casa'), true, 'the area is searchable');
  assert.equal(matchesQuery(ITEMS[0], 'bollo'), false);
  assert.equal(matchesQuery(ITEMS[0], '   '), true, 'an empty query filters nothing');

  const parts = read(PARTS);
  assert.ok(
    /placeholder="Cerca per nome, tipo o riepilogo…"/.test(parts),
    'the placeholder must name exactly what is searched',
  );
  assert.ok(
    !/contenuto…|nel contenuto/.test(parts),
    'a filter over a loaded list must not promise content search',
  );

  assert.equal(matchesStatus(ITEMS[1], 'expiring'), true);
  assert.equal(matchesStatus(ITEMS[0], 'expiring'), false);
  assert.equal(matchesStatus(ITEMS[3], 'pending'), true, 'a failed read is still not analysed');
  assert.equal(matchesStatus(ITEMS[0], 'ready'), true);

  const byExpiry = sortItems(ITEMS, 'expiring');
  assert.equal(byExpiry[0].id, 'b', 'a real deadline leads');
  const byRecent = sortItems(ITEMS, 'recent');
  assert.equal(byRecent[0].id, 'd', 'newest first');
  assert.equal(sortItems(ITEMS, 'name')[0].title, 'Bollo auto 2026');

  const filtered = visibleItems(ITEMS, {
    query: '',
    kind: 'PDF',
    status: 'expiring',
    order: 'recent',
  });
  assert.deepEqual(filtered.map((i) => i.id), ['b']);
}

// ---------------------------------------------------------------------------
// G — Only real capabilities are offered
// ---------------------------------------------------------------------------
{
  const route = readCode(ROUTE);
  assert.ok(/api\.documentUpload/.test(route), 'upload must use the pipeline that exists');
  assert.ok(
    !/Scansiona|scanner|Collega da app|connected apps/i.test(route + readCode(PARTS)),
    'no affordance may be shown for a capability that does not exist',
  );
  const parts = readCode(PARTS);
  assert.ok(
    !/presto|prossimamente|in arrivo|coming soon/i.test(parts),
    'the capability panel must not promise anything future',
  );
}

// ---------------------------------------------------------------------------
// H — A document opens a conversation already holding it
// ---------------------------------------------------------------------------
{
  assert.equal(
    buildOraConversationHref({ documentId: 'doc_abc123', entryPoint: 'document' }),
    '/ora?documentId=doc_abc123&entry=document',
  );
  assert.equal(oraEntryPointFrom('document'), 'document');
  // Opaque identifiers only — a filename would say a great deal about someone.
  assert.equal(
    buildOraConversationHref({ documentId: 'contratto affitto.pdf' }),
    '/ora',
    'anything that is not an opaque id must be dropped from the route',
  );

  const detail = readCode(DETAIL);
  assert.ok(
    /buildOraConversationHref\(\{ documentId: doc\.id, entryPoint: 'document' \}\)/.test(detail),
    'the detail must hand the document to ORA by id',
  );

  const screen = readCode('src/components/ora/OraConversationScreen.tsx');
  assert.ok(
    /\[\.\.\.pendingAttach, \{ document_id: String\(documentId\) \}\]/.test(screen),
    'the document must travel as an attachment on the first turn',
  );
  assert.ok(
    /documentId \? \{ documentId: String\(documentId\) \} : \{\}/.test(screen),
    'the replaced URL must keep the document, or a reload loses the context',
  );
}

// ---------------------------------------------------------------------------
// I — Composition, states and one read
// ---------------------------------------------------------------------------
{
  const route = read(ROUTE);
  const rail = Number(/const RAIL_WIDTH = (\d+)/.exec(route)?.[1]);
  const twoCol = Number(/const TWO_COLUMN_MIN = (\d+)/.exec(route)?.[1]);
  assert.ok(rail >= 280 && rail <= 320, `context rail must stay a rail (${rail})`);
  assert.ok(twoCol - rail - 24 * 3 >= 700, 'main area too narrow at the two-column threshold');

  const fetches = (readCode(ROUTE).match(/await api\.\w+\(/g) || []).filter(
    (f) => !f.includes('documentUpload'),
  );
  assert.deepEqual(
    fetches,
    ['await api.getDocumentsLibrary('],
    'the page must load from one request',
  );

  for (const state of ['LibrarySkeleton', 'ErrorState', 'LibraryEmpty', 'NoMatches']) {
    assert.ok(route.includes(state), `the ${state} state must be reachable`);
  }
  const parts = read(PARTS);
  for (const guard of [
    'if (!rows.length) return null',
    'if (!expiring.length) return null',
    'if (!present.length) return null',
  ]) {
    assert.ok(parts.includes(guard), `missing empty guard: ${guard}`);
  }

  const model = readBackendCode(MODEL);
  for (const cap of ['MAX_DOCUMENTS', 'MAX_EXPIRING', 'EXPIRY_HORIZON_DAYS']) {
    assert.ok(new RegExp(`${cap} = \\d+`).test(model), `${cap} must bound the read`);
  }
}

console.log('documents17: all assertions passed');
