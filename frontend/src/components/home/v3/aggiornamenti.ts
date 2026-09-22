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

export type GenereAggiornamento = 'lavoro' | 'suggerimento' | 'spunto' | 'occasione';

export type Aggiornamento = {
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
  preparazione?: { checked_at?: string; summary?: string; question?: string; limits?: string; options?: { event_id: string; title: string; starts_at: string; ends_at: string }[] };
  azione?: { kind: 'verify' | 'prepare' | 'suggestion' | 'route'; label: string; route?: string; params?: Record<string, unknown> };
};

const SENZA_FONTE = 'originale non disponibile';

/** Tutti gli aggiornamenti della Home, nello stesso ordine in cui si leggono. */
export function elencoAggiornamenti(home: HomeV2Response | null | undefined): Aggiornamento[] {
  if (!home) return [];

  const lavori: Aggiornamento[] = (home.agent_work || []).slice(0, 2).map((w) => ({
    id: w.id,
    genere: 'lavoro',
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

  const occasioni: Aggiornamento[] = (home.opportunities || []).slice(0, 2).map((o) => ({
    id: o.id,
    genere: 'occasione',
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
    cosa: s.title,
    perche: s.description || s.reason || '',
    fonte: s.source_label || SENZA_FONTE,
    stato: s.status === 'expired' ? 'Segnalazione superata' : s.meta?.preparation ? 'Alternative esaminate' : '',
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
  return [...lavori, ...occasioni, ...suggerimenti, ...spunti];
}

/** Come si chiama, per chi legge, il genere di un aggiornamento. */
export function comeSiChiama(genere: GenereAggiornamento): string {
  if (genere === 'lavoro') return 'Sto lavorando a questo';
  if (genere === 'occasione') return 'Una cosa che ho notato';
  if (genere === 'suggerimento') return 'Un consiglio';
  return 'Uno spunto';
}
