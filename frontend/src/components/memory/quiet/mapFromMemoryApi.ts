/**
 * Memoria ← Life Memory API. Presentation only — no FE semantic invention.
 */

export type MemoryStatus = 'known' | 'likely' | 'ambiguous' | 'superseded';

export type MemoryRow = {
  id: string;
  statement: string;
  beliefStatement?: string | null;
  status: MemoryStatus;
  provenanceLabel?: string | null;
  domain?: string | null;
  clarifiable?: boolean;
};

export type MemoryGroupView = {
  id: string;
  label: string;
  domain?: string | null;
  items: MemoryRow[];
};

export type MemoryMapModel = {
  groups: MemoryGroupView[];
  partial: boolean;
};

export type LifeMemoryApiLike = {
  ok?: boolean;
  memories?: {
    id: string;
    statement: string;
    belief_statement?: string | null;
    status?: string;
    provenance_label?: string | null;
    domain?: string | null;
    clarifiable?: boolean;
  }[];
  groups?: {
    id: string;
    label: string;
    domain?: string | null;
    memory_ids?: string[];
  }[];
  partial?: boolean;
};

const STATUS_OK = new Set(['known', 'likely', 'ambiguous']);

export function mapFromMemoryApi(res: LifeMemoryApiLike): MemoryMapModel {
  const byId = new Map<string, MemoryRow>();
  for (const m of res.memories || []) {
    const statement = (m.statement || '').trim();
    if (!statement) continue;
    const status = (m.status || 'known') as MemoryStatus;
    if (status === 'superseded' || !STATUS_OK.has(status)) continue;
    byId.set(m.id, {
      id: m.id,
      statement,
      beliefStatement: m.belief_statement ?? null,
      status,
      provenanceLabel: m.provenance_label ?? null,
      domain: m.domain ?? null,
      clarifiable: !!m.clarifiable && status === 'ambiguous',
    });
  }

  const groups: MemoryGroupView[] = [];
  for (const g of res.groups || []) {
    const items = (g.memory_ids || [])
      .map((id) => byId.get(id))
      .filter((x): x is MemoryRow => !!x);
    if (!items.length) continue;
    groups.push({
      id: g.id,
      label: (g.label || '').trim() || 'Altro',
      domain: g.domain ?? null,
      items,
    });
    for (const it of items) byId.delete(it.id);
  }

  if (byId.size) {
    groups.push({
      id: 'group:other',
      label: 'Altro',
      domain: null,
      items: Array.from(byId.values()),
    });
  }

  return { groups, partial: !!res.partial };
}
