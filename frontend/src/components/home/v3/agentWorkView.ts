/** Origin is not execution. Labels come only from persisted progress facts. */
type Work = { progress_kind?: string | null; needs_you?: string | null; show_in_updates?: boolean };
export function isAgentUpdate(work: Work): boolean {
  return work.show_in_updates !== false;
}
export function agentWorkBadge(work: Work): string {
  if (work.needs_you || work.progress_kind === 'needs_input') return 'Serve una risposta';
  return ({
    update: 'Aggiornamento', completed: 'Risultato disponibile', executed: 'Attività eseguita',
    scheduled: 'Controllo programmato', running: 'Controllo in corso',
    problem: 'Controllo da verificare', stopped: 'Controllo terminato', pending: 'Da verificare',
  } as Record<string, string>)[work.progress_kind || ''] || 'Da verificare';
}
