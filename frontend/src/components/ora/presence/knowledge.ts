import type { PresenceArea } from './state';

export type KnowledgeStar = {
  id: string; area: PresenceArea; branch_id: string | null; title: string;
  statement: string; status: 'known' | 'likely'; provenance: string;
  created_at?: string; updated_at?: string;
  /** Canonical backend refs this visible star represents; presentation lookup only. */
  source_refs?: string[];
  /** Active Situation projected into the map; never durable Memory. */
  temporary?: boolean;
  situation_id?: string;
  situation_revision?: number;
  semantic_kind?: string | null;
  /** Semantically selected by cognition; UI never infers it from statement keywords. */
  icon_key?: string | null;
  tracking_summary?: string | null;
  follow_up?: {
    status: string;
    next_check_at?: string | null;
    next_check_at_local?: string | null;
    next_check_label?: string | null;
    timezone?: string | null;
    timezone_authority?: string | null;
    last_checked_at?: string | null;
    purpose?: string | null;
    notify_when?: string | null;
    completion_when?: string | null;
    monitoring_goal?: string | null;
    ends_when?: string | null;
  };
  location_label?: string | null;
  current_state_summary?: string | null;
  expected_outcome_summary?: string | null;
  next_check_summary?: string | null;
  facts?: string[];
  constraints?: string[];
  /** Durable-memory presentation group; never used for routing. */
  group_kind?: string | null;
  group_items?: {
    memory_ref: string;
    label: string;
    month?: number | null;
    day?: number | null;
    date_label?: string | null;
  }[];
};
export type KnowledgeBranch = {
  area_id: string; title: string; purpose: string; percent: number; area: PresenceArea;
  star_count: number; complete: boolean; state_label: string;
};
export type KnowledgeMap = {
  stars: KnowledgeStar[]; count: number; known_count: number; temporary_count?: number; percent: number;
  branches: KnowledgeBranch[]; revision: string;
};
export type KnowledgeGeometry = { id: string; area: PresenceArea; kind: 'node' | 'branch'; tentative?: boolean; temporary?: boolean; complete?: boolean };
/** Only geometry identifiers enter the canvas/WebView. Personal text stays in React. */
export function geometryFor(map: KnowledgeMap | null): KnowledgeGeometry[] {
  return [
    ...(map?.stars || []).map(({ id, area, status, temporary }) => ({ id, area, kind: 'node' as const, tentative: status === 'likely', temporary: !!temporary })),
    ...(map?.branches || []).filter(b => b.star_count > 0).map(b => ({ id: `branch_${b.area_id}`, area: b.area, kind: 'branch' as const, complete: b.complete })),
  ];
}
export function newStars(previous: KnowledgeMap | null, next: KnowledgeMap): KnowledgeStar[] {
  if (!previous) return [];
  const ids = new Set(previous.stars.map(s => s.id));
  return next.stars.filter(s => !ids.has(s.id));
}


function visualStarKey(star: KnowledgeStar): string {
  return JSON.stringify({
    id: star.id,
    area: star.area,
    statement: star.statement,
    status: star.status,
    updated_at: star.updated_at || null,
    temporary: !!star.temporary,
    situation_revision: star.situation_revision || null,
    follow_up: star.follow_up || null,
    current_state_summary: star.current_state_summary || null,
    expected_outcome_summary: star.expected_outcome_summary || null,
    next_check_summary: star.next_check_summary || null,
    group_kind: star.group_kind || null,
    group_items: star.group_items || null,
    source_refs: star.source_refs || [],
  });
}

/** Newly created OR materially updated visible stars since the previous map read. */
export function changedStars(previous: KnowledgeMap | null, next: KnowledgeMap): KnowledgeStar[] {
  if (!previous) return [];
  const before = new Map(previous.stars.map(star => [star.id, visualStarKey(star)]));
  return next.stars.filter(star => before.get(star.id) !== visualStarKey(star));
}
