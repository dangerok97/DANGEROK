/**
 * Human labels for rule IDs, sensitivity, confidence, risk buckets.
 * Deterministic mapping — mirrors the backend rules/text layer.
 */
export const RULE_LABELS: Record<string, string> = {
  imminent_event: 'Evento imminente',
  deadline_soon: 'Scadenza vicina',
  deadline_overdue: 'Scadenza superata',
  quick_win: 'Attività rapida',
  available_time_slot: 'Tempo disponibile',
  travel_dependency: 'Collegata a un viaggio',
  busy_day: 'Giornata intensa',
  back_to_back: 'Impegni consecutivi',
  weekend: 'Weekend',
  high_urgency: 'Urgenza elevata',
  high_importance: 'Importanza elevata',
  postpone_risk_high: 'Rischio elevato se rimandata',
};

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: 'Alta',
  medium: 'Media',
  low: 'Bassa',
};

export const RISK_LABELS: Record<string, string> = {
  high: 'Alto',
  medium: 'Medio',
  low: 'Basso',
};

export const IMPACT_LABELS: Record<string, string> = {
  high: 'Alto',
  medium: 'Medio',
  low: 'Basso',
};

export const STATUS_LABELS: Record<string, string> = {
  pending: 'Da fare',
  open: 'Da fare',
  in_progress: 'In corso',
  partially_completed: 'Parziale',
  completed: 'Completata',
  postponed: 'Rimandata',
  dismissed: 'Ignorata',
  blocked: 'Bloccata',
};

export const USER_ACTION_LABELS: Record<string, string> = {
  start: 'Iniziata',
  complete: 'Completata',
  partial: 'Parzialmente completata',
  postpone: 'Rimandata',
  dismiss: 'Ignorata',
  block: 'Bloccata',
};

export const DAILY_SIGNAL_LABELS: Record<string, string> = {
  empty_day: 'Giornata libera',
  weekend: 'Weekend',
  holiday: 'Festivo',
  vacation: 'Ferie',
  many_meetings: 'Molte riunioni',
  many_travel_hours: 'Molte ore di viaggio',
  many_study_hours: 'Molte ore di studio',
  many_work_hours: 'Molte ore di lavoro',
  busy_day: 'Giornata piena',
  stressful_day: 'Giornata stressante',
  back_to_back_marathon: 'Maratona di impegni',
  relaxed_day: 'Giornata rilassata',
  light_day: 'Giornata leggera',
};

export const DAILY_WARNING_LABELS: Record<string, string> = {
  very_busy_day: 'Giornata molto piena',
  back_to_back_marathon: 'Impegni consecutivi',
  no_break: 'Poche pause',
};

export const DAILY_OPPORTUNITY_LABELS: Record<string, string> = {
  free_morning: 'Mattinata libera',
  free_afternoon: 'Pomeriggio libero',
  free_evening: 'Serata libera',
  long_lunch_available: 'Pausa pranzo disponibile',
};

export const ENERGY_LABELS: Record<string, string> = {
  high: 'Energia alta',
  medium: 'Energia media',
  low: 'Energia bassa',
};

export function ruleLabel(id: string): string {
  return RULE_LABELS[id] || id.replace(/_/g, ' ');
}

export function formatMinutes(m?: number | null): string {
  if (!m || m <= 0) return '—';
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return mm === 0 ? `${h} h` : `${h}h ${mm}min`;
}

export function formatDateTime(iso?: string | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

export function formatTime(iso?: string | null): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

/**
 * Human-readable "N secondi/minuti/ore/giorni fa" from a Date.
 */
export function formatRelativeAgo(from: Date | null): string {
  if (!from) return '';
  const diffMs = Date.now() - from.getTime();
  if (diffMs < 0) return 'ora';
  const s = Math.round(diffMs / 1000);
  if (s < 10) return 'ora';
  if (s < 60) return `${s} sec fa`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min fa`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h fa`;
  const d = Math.round(h / 24);
  return `${d} g fa`;
}
