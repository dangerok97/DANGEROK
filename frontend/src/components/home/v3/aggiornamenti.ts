/**
 * Che cosa c'è dentro «Aggiornamenti di ORA», in una forma sola.
 *
 *     LO STESSO INSIEME IN HOME, NELLA PAGINA E NEL DETTAGLIO.
 *
 * Nella sezione finiscono quattro cose diverse: il lavoro che l'agente sta
 * seguendo, i suggerimenti, gli spunti e le occasioni. Il riquadro in Home le
 * conta tutte e quattro per scrivere «3 aggiornamenti»; se la pagina che si
 * apre cliccando quel numero le raccogliesse a modo suo, i due numeri
 * finirebbero per non coincidere — ed è esattamente il genere di scollamento
 * che fa smettere di credere a entrambi.
 *
 * Quindi l'elenco si costruisce qui, una volta, e lo usano tutte e tre le
 * superfici. Nessun campo viene inventato: quello che una sorgente non dice
 * resta vuoto, e l'interfaccia lo dichiara invece di riempirlo.
 */
import type { HomeV2Response } from '@/src/api/client';

export type GenereAggiornamento = 'situazione' | 'lavoro' | 'suggerimento' | 'spunto' | 'occasione';

export type Aggiornamento = {
  testo_preparato?: string;
  situazione_id?: string;
  situazione_revisione?: number;
  evidenza_verificata_at?: string;
  id: string;
  genere: GenereAggiornamento;
  /** Di che cosa si tratta, in una riga. */
  cosa: string;
  /** Perché conta adesso. Vuoto quando la sorgente non lo dice. */
  perche: string;
  /** Da dove viene, in italiano, o «originale non disponibile». */
  fonte: string;
  /** A che punto è, con parole umane. Vuoto quando non c'è uno stato. */
  stato: string;
  /** Che cosa ORA sta facendo adesso. */
  cosa_sta_facendo: string;
  /** Che cosa serve alla persona. Vuoto quando non serve niente. */
  cosa_serve: string;
  /** Che cosa ORA non sa ancora di questa cosa. */
  non_so: string;
  /** Il prossimo passo, quando esiste davvero. */
  prossimo_passo: string;
  quando: string;
  lavoro?: 'verify' | 'prepare';
  preparazione?: { checked_at?: string; summary?: string; question?: string; limits?: string; options?: { event_id: string; title: string; starts_at: string; ends_at: string }[] };
  azione?: { kind: 'verify' | 'prepare' | 'suggestion' | 'route'; label: string; route?: string; params?: Record<string, unknown> };
};

const SENZA_FONTE = 'originale non disponibile';

/** Tutti gli aggiornamenti della Home, nello stesso ordine in cui si leggono. */
export function elencoAggiornamenti(home: Partial<HomeV2Response> | null | undefined): Aggiornamento[] {
  if (!home) return [];

  // A monitoring Goal or a plan to check later is not an update. Show a
  // temporary Situation only when ORA has a fresh, sourced consequence that
  // actually matters to the person. All surfaces use this single projection.
  const situazioni: Aggiornamento[] = (home.situation_updates || []).slice(0, 3).map((u) => ({
    id: u.id,
    genere: 'situazione',
    situazione_id: u.situation_id,
    situazione_revisione: u.revision,
    evidenza_verificata_at: u.evidence_at,
    cosa: u.headline,
    perche: u.evidence_summary,
    fonte: u.source_label,
    stato: '',
    cosa_sta_facendo: '',
    cosa_serve: '',
    non_so: '',
    prossimo_passo: '',
    quando: u.created_at,
  }));
  // A Situation's ambient watch is private working state. If no fresh
  // verified consequence exists we show NOTHING about it; if one exists the
  // single situation_updates row below is its only visible representation.
  // Do not fall back to a Goal/Opportunity implementation status.

  const lavori: Aggiornamento[] = (home.agent_work || [])
    .filter((w) => !w.situation_id)
    .slice(0, 2).map((w) => ({
    id: w.id,
    genere: 'lavoro',
    testo_preparato: w.prepared_text || '',
    cosa: w.what,
    perche: w.why_now || '',
    fonte: w.source || SENZA_FONTE,
    stato: w.state || '',
    // Per un lavoro dell'agente, lo stato *è* quello che ORA sta facendo.
    cosa_sta_facendo: w.state || '',
    cosa_serve: w.needs_you || '',
    non_so: w.unknown || '',
    prossimo_passo: w.needs_you || w.outcome || '',
    azione: w.action?.route ? { kind: 'route', label: w.action.label, route: w.action.route, params: w.action.params } : undefined,
    quando: '',
  }));

  const occasioni: Aggiornamento[] = (home.opportunities || [])
    .filter((o) => !o.situation_id)
    .slice(0, 2).map((o) => ({
    id: o.id,
    genere: 'occasione',
    lavoro: 'verify',
    cosa: o.title,
    perche: o.why_now || '',
    fonte: o.sources?.join(' · ') || SENZA_FONTE,
    stato: ({ running: 'Verifica avviata', ready: 'Risposta disponibile', needs_user: 'Serve una risposta', failed: 'Verifica interrotta' } as Record<string, string>)[o.work_status || ''] || '',
    cosa_sta_facendo: '',
    cosa_serve: o.question || '',
    non_so: '',
    prossimo_passo: o.what_ora_can_do || '',
    azione: { kind: 'verify', label: 'Verifica con ORA' },
    quando: '',
  }));

  const suggerimenti: Aggiornamento[] = (home.ora_ti_consiglia || []).slice(0, 3).map((s) => ({
    id: s.id,
    genere: 'suggerimento',
    lavoro: s.action?.kind === 'prepare_change' ? 'prepare' : undefined,
    cosa: s.title,
    perche: s.description || s.reason || '',
    fonte: s.source_label || SENZA_FONTE,
    stato: s.work_status ? ({ running: 'Preparazione in corso', ready: 'Proposta disponibile', needs_user: 'Serve la tua scelta', failed: 'Verifica interrotta' } as Record<string, string>)[s.work_status] || s.work_status : s.status === 'expired' ? 'Segnalazione superata' : s.meta?.preparation ? 'Alternative esaminate' : '',
    cosa_sta_facendo: (s.meta?.preparation as Aggiornamento['preparazione'])?.summary || '',
    cosa_serve: (s.meta?.preparation as Aggiornamento['preparazione'])?.question || '',
    non_so: '',
    preparazione: s.meta?.preparation as Aggiornamento['preparazione'],
    prossimo_passo: (s.meta?.preparation as Aggiornamento['preparazione'])?.question || s.action?.label || '',
    azione: s.action && !['expired', 'dismissed', 'completed'].includes(s.status || '') ? { kind: s.action.kind === 'prepare_change' ? 'prepare' : 'suggestion', label: s.action.label, route: s.action.route || undefined, params: s.action.params } : undefined,
    quando: s.created_at || '',
  }));

  const spunti: Aggiornamento[] = (home.insights || []).map((i) => ({
    id: i.id,
    genere: 'spunto',
    cosa: i.text,
    perche: '',
    fonte: i.source || SENZA_FONTE,
    stato: i.status || '',
    cosa_sta_facendo: '',
    cosa_serve: '',
    non_so: '',
    prossimo_passo: i.action?.label || '',
    azione: i.action?.route ? { kind: 'route', label: i.action.label, route: i.action.route, params: i.action.params } : undefined,
    quando: i.created_at || '',
  }));

  // L'ordine è quello della sezione in Home: prima il lavoro, poi le occasioni
  // sollevate, poi i suggerimenti, poi gli spunti.
  return [...situazioni, ...lavori, ...occasioni, ...suggerimenti, ...spunti];
}

/** Come si chiama, per chi legge, il genere di un aggiornamento. */
export function comeSiChiama(genere: GenereAggiornamento): string {
  if (genere === 'situazione') return 'Da fare adesso';
  if (genere === 'lavoro') return 'Sto lavorando a questo';
  if (genere === 'occasione') return 'Una cosa che ho notato';
  if (genere === 'suggerimento') return 'Un consiglio';
  return 'Uno spunto';
}
