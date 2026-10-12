import type { SituationOutcome } from '@/src/api/client';

export type SituationOutcomeView = {
  status: SituationOutcome['status'] | 'pending' | 'outdated' | 'stopped' | 'unavailable';
  label: string;
  headline: string;
  detail: string;
  window: string | null;
  basis: string;
  needsAttention: boolean;
};

type OutcomeInput = {
  outcome?: SituationOutcome | null;
  desiredOutcome?: string | null;
  situationRevision?: number;
  followupStatus?: string | null;
  /** The last read of this assessment's source failed; null outcome means something else. */
  readUnavailable?: boolean;
};

/**
 * All surfaces share the same assessment. No legacy prose, checkpoint, current
 * clock or temporal scope is promoted into an outcome estimate here.
 */
export function situationOutcomeView(input: OutcomeInput, now: number = Date.now()): SituationOutcomeView {
  if (input.readUnavailable) {
    return {
      status: 'unavailable', label: 'Ultima lettura non riuscita',
      headline: 'Stato non verificabile', detail: 'Le indicazioni precedenti non sono confermate.',
      window: null, basis: '', needsAttention: false,
    };
  }
  const desired = String(input.desiredOutcome || '').trim();
  const outcome = input.outcome;
  const validUntil = outcome ? Date.parse(outcome.valid_until) : NaN;
  const sameRevision = input.situationRevision === undefined
    || outcome?.situation_revision === input.situationRevision;
  const current = !!outcome && Number.isFinite(validUntil) && validUntil > now
    && sameRevision && !!outcome.headline.trim();
  if (!current || !outcome) {
    if (input.followupStatus === 'stopped') {
      return {
        status: 'stopped', label: 'Monitoraggio terminato',
        headline: 'Non sono previsti altri controlli', detail: desired,
        window: null, basis: '', needsAttention: false,
      };
    }
    return {
      status: outcome ? 'outdated' : 'pending',
      label: desired ? 'Risultato da raggiungere' : 'Situazione registrata',
      headline: outcome ? 'Stima da aggiornare' : 'Stima non ancora disponibile',
      detail: desired,
      window: null,
      basis: '',
      needsAttention: false,
    };
  }
  // A completed watch may have produced the very action the person needs.
  // The backend retains only verified final assessments after settlement;
  // ending the watch is not a reason to hide its still-current result.
  const missing = outcome.status === 'needs_input';
  const immediate = outcome.status === 'action_now';
  return {
    status: outcome.status,
    label: missing ? 'Mi serve un dato'
      : immediate ? (outcome.action_reason === 'early_risk' ? 'Intervieni prima del rischio' : 'È il momento di agire')
        : 'Stima aggiornata',
    headline: outcome.headline.trim(),
    detail: outcome.action_summary.trim() === outcome.headline.trim() ? '' : outcome.action_summary.trim(),
    // An early-risk deadline must never be shown as a completion window.
    window: outcome.status === 'estimated' ? outcome.window_label?.trim() || null : null,
    basis: missing ? '' : outcome.basis === 'direct_observation'
      ? 'Valutazione basata su un’osservazione diretta.'
      : 'Valutazione stimata dalle condizioni disponibili.',
    needsAttention: missing || immediate,
  };
}
