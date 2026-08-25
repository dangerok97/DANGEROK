/**
 * Contesti Life Map V1 — FE deterministic compose / fallback.
 * Prefer GET /api/life-map (backend assemble). This module stays for:
 * - offline / API failure fallback
 * - Node strip-types unit tests (no relative imports)
 * Not a semantic engine — no Gemini, no invented taxonomy/scores.
 */

/** Presentation labels — mirrors backend DOMAIN_LABELS_IT; never invents empty areas. */
export const DOMAIN_LABELS_IT: Record<string, string> = {
  casa: 'Casa',
  auto: 'Auto',
  finanze: 'Finanze',
  studio: 'Studio',
  lavoro: 'Lavoro',
  salute: 'Salute',
  famiglia: 'Famiglia',
  animali: 'Animali',
  viaggi: 'Viaggi',
  documenti: 'Documenti',
  assicurazioni: 'Assicurazioni',
  abbonamenti: 'Abbonamenti',
  internet: 'Internet',
  servizi: 'Servizi',
};

export const DOMAIN_PRESENTATION_ORDER = [
  'lavoro',
  'studio',
  'casa',
  'auto',
  'famiglia',
  'salute',
  'finanze',
  'viaggi',
  'animali',
  'assicurazioni',
  'abbonamenti',
  'internet',
  'documenti',
  'servizi',
] as const;

export const HIDDEN_DOMAIN_KEYS = new Set(['mlc', 'doc']);

export function domainLabel(domain: string): string | null {
  const key = (domain || '').trim().toLowerCase();
  if (!key || HIDDEN_DOMAIN_KEYS.has(key)) return null;
  return DOMAIN_LABELS_IT[key] ?? null;
}

export type LifeAreaRow = {
  id: string;
  domain: string;
  title: string;
  identity?: string | null;
  /** Contextual visual owned by the area — reused, never re-commissioned. */
  visual?: { status?: string; url?: string | null } | null;
};

export type LiveSituationRow = {
  id: string;
  /** Open semantics — study | travel | inferred | … (no FE taxonomy switch). */
  kind: string;
  title: string;
  temporal?: string | null;
  summary?: string | null;
  /** Empty / missing → informational row (no fake detail). */
  href?: string | null;
  /** Contextual visual owned by the entity — reused, never re-commissioned. */
  visual?: { status?: string; url?: string | null } | null;
};

export type ContextsMapModel = {
  situations: LiveSituationRow[];
  areas: LifeAreaRow[];
};

type ProfileFact = { key?: string; value?: unknown };
type DomainProfile = {
  domain?: string;
  objects?: Record<string, ProfileFact>;
};
type LifeProfileLike = {
  domains?: Record<string, DomainProfile>;
};
type StudyPlanLike = {
  id: string;
  status?: string;
  exam_name?: string;
  subject?: string | null;
  exam_date?: string | null;
};
type TravelProjectLike = {
  id: string;
  status?: string;
  title?: string;
  destination?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  phase?: string;
  days_until?: number | null;
};

const LIVE_STATUSES = new Set(['active', 'paused']);

/** Human identity keys only — string values, never booleans/enums/codes. */
const IDENTITY_KEYS: Record<string, string[]> = {
  lavoro: ['lavoro.ruolo', 'ruolo'],
  studio: ['studio.universita', 'universita'],
  casa: ['casa.citta', 'citta'],
  auto: ['auto.modello', 'modello'],
  famiglia: ['famiglia.nucleo', 'nucleo'],
};

function isPresentValue(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (value === '') return false;
  if (Array.isArray(value) && value.length === 0) return false;
  return true;
}

function humanString(value: unknown): string | null {
  if (typeof value === 'string') {
    const t = value.trim();
    if (!t) return null;
    // Reject raw snake/enum-like codes
    if (/^[a-z][a-z0-9_]*$/.test(t) && t.includes('_')) return null;
    return t;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
}

function domainHasKnownFacts(dom: DomainProfile | undefined): boolean {
  if (!dom?.objects) return false;
  return Object.values(dom.objects).some((o) => isPresentValue(o?.value));
}

function identityForDomain(domain: string, dom: DomainProfile): string | null {
  const keys = IDENTITY_KEYS[domain] || [];
  for (const key of keys) {
    const fact = dom.objects?.[key];
    const human = humanString(fact?.value);
    if (human) return human;
  }
  for (const [key, fact] of Object.entries(dom.objects || {})) {
    if (/\.active$|^active$|\.owned$|\.purchased$/.test(key)) continue;
    const human = humanString(fact?.value);
    if (human && human.length <= 80) return human;
  }
  return null;
}

function parseDateOnly(iso?: string | null): Date | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

function formatItDate(d: Date): string {
  return d.toLocaleDateString('it-IT', { day: 'numeric', month: 'long' });
}

function formatDateRange(start?: string | null, end?: string | null): string | null {
  const a = parseDateOnly(start);
  const b = parseDateOnly(end);
  if (a && b) return `${formatItDate(a)} – ${formatItDate(b)}`;
  if (a) return `Dal ${formatItDate(a)}`;
  if (b) return `Fino al ${formatItDate(b)}`;
  return null;
}

function daysUntil(iso?: string | null, now = new Date()): number | null {
  const d = parseDateOnly(iso);
  if (!d) return null;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((target.getTime() - start.getTime()) / 86_400_000);
}

function travelPhaseLabel(
  phase?: string | null,
  days?: number | null,
): string | null {
  switch ((phase || '').toLowerCase()) {
    case 'during':
      return 'In corso';
    case 'departure_day':
      return 'Partenza oggi';
    case 'welcome_back':
      return 'Di ritorno';
    case 'days_until':
      if (typeof days === 'number' && days >= 0) {
        if (days === 0) return 'Partenza oggi';
        if (days === 1) return 'Partenza domani';
        return `Partenza tra ${days} giorni`;
      }
      return 'In arrivo';
    case 'upcoming':
      return 'In arrivo';
    default:
      return null;
  }
}

function studyTemporal(plan: StudyPlanLike, now = new Date()): string | null {
  const n = daysUntil(plan.exam_date, now);
  if (n === null) {
    const d = parseDateOnly(plan.exam_date);
    return d ? `Esame il ${formatItDate(d)}` : null;
  }
  if (n < 0) return null;
  if (n === 0) return 'Esame oggi';
  if (n === 1) return 'Esame domani';
  return `Esame tra ${n} giorni`;
}

export function buildLifeAreas(profile: LifeProfileLike | null | undefined): LifeAreaRow[] {
  if (!profile?.domains) return [];
  const rows: LifeAreaRow[] = [];
  for (const [domain, dom] of Object.entries(profile.domains)) {
    const key = domain.toLowerCase();
    if (HIDDEN_DOMAIN_KEYS.has(key)) continue;
    const title = domainLabel(key);
    if (!title) continue;
    if (!domainHasKnownFacts(dom)) continue;
    rows.push({
      id: `area:${key}`,
      domain: key,
      title,
      identity: identityForDomain(key, dom),
    });
  }
  const order = new Map<string, number>(
    DOMAIN_PRESENTATION_ORDER.map((d, i) => [d, i]),
  );
  rows.sort((a, b) => {
    const ia = order.get(a.domain) ?? 1000;
    const ib = order.get(b.domain) ?? 1000;
    if (ia !== ib) return ia - ib;
    return a.title.localeCompare(b.title, 'it');
  });
  return rows;
}

export function buildLiveSituations(
  studyPlans: StudyPlanLike[] | null | undefined,
  travelProjects: TravelProjectLike[] | null | undefined,
  now = new Date(),
): LiveSituationRow[] {
  const situations: LiveSituationRow[] = [];

  for (const plan of studyPlans || []) {
    if (!LIVE_STATUSES.has((plan.status || '').toLowerCase())) continue;
    const title = (plan.exam_name || plan.subject || '').trim();
    if (!title) continue;
    const n = daysUntil(plan.exam_date, now);
    if (n !== null && n < 0) continue;
    const temporal = studyTemporal(plan, now);
    situations.push({
      id: `study:${plan.id}`,
      kind: 'study',
      title,
      temporal,
      summary: plan.subject && plan.subject !== title ? plan.subject : null,
      href: `/study-plan/${plan.id}`,
    });
  }

  for (const project of travelProjects || []) {
    if (!LIVE_STATUSES.has((project.status || '').toLowerCase())) continue;
    const title = (project.title || project.destination || '').trim();
    if (!title) continue;
    const range = formatDateRange(project.start_date, project.end_date);
    const phaseSummary = travelPhaseLabel(project.phase, project.days_until ?? null);
    situations.push({
      id: `travel:${project.id}`,
      kind: 'travel',
      title,
      temporal: range || phaseSummary,
      summary:
        range && phaseSummary
          ? phaseSummary
          : project.destination && project.destination !== title
            ? project.destination
            : phaseSummary,
      href: `/travel-project/${project.id}`,
    });
  }

  situations.sort((a, b) => {
    if (!!a.temporal !== !!b.temporal) return a.temporal ? -1 : 1;
    return a.title.localeCompare(b.title, 'it');
  });

  return situations;
}

export function buildContextsMap(input: {
  profile?: LifeProfileLike | null;
  studyPlans?: StudyPlanLike[] | null;
  travelProjects?: TravelProjectLike[] | null;
  now?: Date;
}): ContextsMapModel {
  return {
    situations: buildLiveSituations(input.studyPlans, input.travelProjects, input.now),
    areas: buildLifeAreas(input.profile),
  };
}
