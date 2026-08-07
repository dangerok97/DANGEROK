/**
 * Build Focus Horizon buckets from HomeV2 temporal fields only.
 * No invented events — hide empty groups.
 */
import { HomeItem, HomePriorityGroup, HomeV2Response } from '@/src/api/client';

export type HorizonBucketKey = 'oggi' | 'domani' | 'settimana' | 'avanti';

export type HorizonItem = {
  id: string;
  title: string;
  whenLabel: string;
  at: Date;
};

export type HorizonBucket = {
  key: HorizonBucketKey;
  label: string;
  items: HorizonItem[];
};

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

function parseWhen(item: HomeItem): Date | null {
  const raw = item.start_at || item.due_at || item.goal_target_date;
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

function shortWhen(d: Date): string {
  return d.toLocaleString('it-IT', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function bucketFor(at: Date, now: Date): HorizonBucketKey {
  const sod = startOfDay(now).getTime();
  const day = startOfDay(at).getTime();
  const one = 86400_000;
  if (day === sod) return 'oggi';
  if (day === sod + one) return 'domani';
  if (day > sod && day < sod + 7 * one) return 'settimana';
  return 'avanti';
}

const LABELS: Record<HorizonBucketKey, string> = {
  oggi: 'Oggi',
  domani: 'Domani',
  settimana: 'Questa settimana',
  avanti: 'Più avanti',
};

export function buildFocusHorizon(home: HomeV2Response | null, now = new Date()): HorizonBucket[] {
  if (!home) return [];
  const seen = new Set<string>();
  const collected: HorizonItem[] = [];

  const push = (item: HomeItem | null | undefined) => {
    if (!item?.id || seen.has(item.id)) return;
    const at = parseWhen(item);
    if (!at) return;
    // Skip far-past noise (more than 1 day ago)
    if (at.getTime() < now.getTime() - 86400_000) return;
    seen.add(item.id);
    collected.push({
      id: item.id,
      title: item.title,
      whenLabel: shortWhen(at),
      at,
    });
  };

  push(home.primary_focus);
  for (const g of home.priorities || []) {
    for (const it of g.items || []) push(it);
  }

  collected.sort((a, b) => a.at.getTime() - b.at.getTime());

  const order: HorizonBucketKey[] = ['oggi', 'domani', 'settimana', 'avanti'];
  const map: Record<HorizonBucketKey, HorizonItem[]> = {
    oggi: [],
    domani: [],
    settimana: [],
    avanti: [],
  };
  for (const it of collected) {
    map[bucketFor(it.at, now)].push(it);
  }

  return order
    .map((key) => ({
      key,
      label: LABELS[key],
      items: map[key].slice(0, 2),
    }))
    .filter((b) => b.items.length > 0);
}

/** Flatten first N for narrow UI */
export function flattenHorizon(buckets: HorizonBucket[], max = 6): { bucket: string; item: HorizonItem }[] {
  const out: { bucket: string; item: HorizonItem }[] = [];
  for (const b of buckets) {
    for (const item of b.items) {
      out.push({ bucket: b.label, item });
      if (out.length >= max) return out;
    }
  }
  return out;
}

export type { HomePriorityGroup };
