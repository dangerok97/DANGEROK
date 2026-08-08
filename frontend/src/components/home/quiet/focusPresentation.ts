/**
 * Daily Focus presentation helpers — labels/meta only, no layout.
 */
import { HomeItem } from '@/src/api/client';
import { formatWhen } from '@/src/components/home/v2/homeNav';

const TYPE_LABELS: Record<string, string> = {
  bill: 'Bolletta',
  payment: 'Pagamento',
  event: 'Evento',
  visit: 'Visita',
  study: 'Studio',
  travel: 'Viaggio',
  needs_review: 'Da verificare',
  verify: 'Verifica',
  reply: 'Risposta',
  activity: 'Attività',
  generic: 'Priorità',
  resume: 'In corso',
};

const INTENT_LABELS: Record<string, string> = {
  study: 'Studio',
  exam_preparation: 'Studio · esame',
  travel: 'Viaggio',
  vacation: 'Viaggio',
  event: 'Evento',
  payment: 'Pagamento',
  financial: 'Pagamento',
  medical: 'Visita',
};

export function typeLabel(item: HomeItem): string {
  const intent = (item.meta as { intent?: string } | undefined)?.intent;
  const subtype = item.subtype || '';
  return (
    INTENT_LABELS[intent || ''] ||
    INTENT_LABELS[subtype] ||
    TYPE_LABELS[item.card_type || ''] ||
    TYPE_LABELS[item.type] ||
    item.type
  );
}

/** Pick ≤2 meta lines for progressive disclosure. */
export function focusMeta(item: HomeItem): string[] {
  const lines: string[] = [];
  const when = formatWhen(item.start_at || item.due_at || item.goal_target_date);
  if (when) {
    lines.push(item.due_at && !item.start_at ? `Scade ${when}` : when);
  }
  if (item.amount) lines.push(item.amount);
  else if (item.location) lines.push(item.location);
  else if (item.goal_blockers?.[0]) lines.push(item.goal_blockers[0]);
  else if (item.goal_next_action) lines.push(item.goal_next_action);
  return lines.slice(0, 2);
}
