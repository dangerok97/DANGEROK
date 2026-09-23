import { api } from '@/src/api/client';
import type { Aggiornamento } from './aggiornamenti';

/** Close the update at its canonical source, so it stays gone after refresh. */
export async function rimuoviAggiornamento(a: Aggiornamento): Promise<void> {
  if (a.genere === 'lavoro') {
    await api.cancelAgentGoal(a.id);
    return;
  }
  if (a.genere === 'occasione') {
    await api.dismissOpportunity(a.id);
    return;
  }
  if (a.genere === 'suggerimento') {
    await api.dismissSuggestion(a.id);
    return;
  }
  await api.homeAction({ item_id: a.id, action: 'ignore', reason: 'user_dismissed' });
}
