import type { PresenceArea } from './state';

export type KnowledgeStar = {
  id: string; area: PresenceArea; branch_id: string | null; title: string;
  statement: string; status: 'known' | 'likely'; provenance: string; updated_at?: string;
};
export type KnowledgeBranch = {
  area_id: string; title: string; purpose: string; percent: number; area: PresenceArea;
  star_count: number; complete: boolean; state_label: string;
};
export type KnowledgeMap = {
  stars: KnowledgeStar[]; count: number; known_count: number; percent: number;
  branches: KnowledgeBranch[]; revision: string;
};
export type KnowledgeGeometry = { id: string; area: PresenceArea; kind: 'node' | 'branch'; tentative?: boolean; complete?: boolean };
/** Only geometry identifiers enter the canvas/WebView. Personal text stays in React. */
export function geometryFor(map: KnowledgeMap | null): KnowledgeGeometry[] {
  return [
    ...(map?.stars || []).map(({ id, area, status }) => ({ id, area, kind: 'node' as const, tentative: status === 'likely' })),
    ...(map?.branches || []).filter(b => b.star_count > 0).map(b => ({ id: `branch_${b.area_id}`, area: b.area, kind: 'branch' as const, complete: b.complete })),
  ];
}
export function newStars(previous: KnowledgeMap | null, next: KnowledgeMap): KnowledgeStar[] {
  if (!previous) return [];
  const ids = new Set(previous.stars.map(s => s.id));
  return next.stars.filter(s => !ids.has(s.id));
}
