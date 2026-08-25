/**
 * Contesti ← Life Map API. Presentation only — no semantic taxonomy switch.
 * Self-contained for Node strip-types tests.
 */
import type { ContextsMapModel } from './buildContextsMap';

export type LifeMapApiLike = {
  areas?: {
    id: string;
    domain: string;
    title: string;
    identity?: string | null;
    /** Contextual visual owned by this area, when one exists. */
    visual?: { status?: string; url?: string | null } | null;
  }[];
  situations?: {
    id: string;
    kind?: string;
    title: string;
    temporal?: string | null;
    summary?: string | null;
    href?: string | null;
    /** Contextual visual state for this situation's entity, when known. */
    visual?: { status?: string; url?: string | null } | null;
  }[];
};

export function mapFromLifeMapApi(res: LifeMapApiLike): ContextsMapModel {
  return {
    areas: (res.areas || []).map((a) => ({
      id: a.id,
      domain: a.domain,
      title: a.title,
      identity: a.identity ?? null,
      visual: a.visual ?? null,
    })),
    situations: (res.situations || [])
      .filter((s) => !!(s.title || '').trim())
      .map((s) => ({
        id: s.id,
        kind: s.kind || 'inferred',
        title: s.title,
        temporal: s.temporal ?? null,
        summary: s.summary ?? null,
        href: s.href || null,
        visual: s.visual ?? null,
      })),
  };
}
