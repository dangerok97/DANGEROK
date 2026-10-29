/**
 * Gruppi della bacheca Aggiornamenti (approvata il 23/10/2026), senza React:
 * la stessa regola per Home e pagina, verificabile con un test Node.
 */
import type { Aggiornamento } from './aggiornamenti';

export type GruppoAggiornamento = 'adesso' | 'per_te' | 'in_corso' | 'da_sapere';

export const ORDINE: GruppoAggiornamento[] = ['adesso', 'per_te', 'in_corso', 'da_sapere'];
export const TITOLI: Record<GruppoAggiornamento, string> = {
  adesso: 'Adesso',
  per_te: 'Serve te',
  in_corso: 'ORA ci sta pensando',
  da_sapere: 'Da sapere',
};
const STATI_CHE_CHIEDONO = new Set(['Serve una risposta', 'Serve la tua scelta']);

/** In quale gruppo va un aggiornamento. Una sola regola per tutte le superfici. */
export function gruppoDi(a: Aggiornamento): GruppoAggiornamento {
  const esito = a.situazione?.outcome;
  if (esito?.status === 'action_now') return 'adesso';
  // A reminder that arrived is about now; a call outcome is news to read.
  if (a.promemoria === 'reminder') return 'adesso';
  if (a.promemoria === 'phone_call' || a.promemoria === 'morning_brief') return 'da_sapere';
  if (
    esito?.status === 'needs_input'
    || a.cosa_serve.trim()
    || STATI_CHE_CHIEDONO.has(a.stato)
    || (a.genere === 'occasione' && !a.solo_informazione)
    || a.genere === 'suggerimento'
  ) return 'per_te';
  if (a.genere === 'lavoro') return 'in_corso';
  return 'da_sapere';
}

export function raggruppa(righe: Aggiornamento[]) {
  const gruppi: Record<GruppoAggiornamento, Aggiornamento[]> = { adesso: [], per_te: [], in_corso: [], da_sapere: [] };
  for (const a of righe) gruppi[gruppoDi(a)].push(a);
  return gruppi;
}

/** Riassunto in una riga: «1 cosa per te · 2 le segue ORA». */
export function sintesiAggiornamenti(righe: Aggiornamento[]): string {
  const g = raggruppa(righe);
  const parti: string[] = [];
  if (g.adesso.length) parti.push(g.adesso.length === 1 ? '1 cosa urgente' : `${g.adesso.length} cose urgenti`);
  if (g.per_te.length) parti.push(g.per_te.length === 1 ? '1 cosa per te' : `${g.per_te.length} cose per te`);
  if (g.in_corso.length) parti.push(g.in_corso.length === 1 ? '1 la segue ORA' : `${g.in_corso.length} le segue ORA`);
  if (g.da_sapere.length) parti.push(g.da_sapere.length === 1 ? '1 da sapere' : `${g.da_sapere.length} da sapere`);
  return parti.join(' · ');
}
