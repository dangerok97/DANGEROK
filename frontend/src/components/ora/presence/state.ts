/** Public work signals, never hidden reasoning or a claim about model neurons. */
export const AREA_LABELS = {
  memory: 'Memoria', calendar: 'Impegni', people: 'Persone', places: 'Luoghi',
  home: 'Casa', documents: 'Documenti', finances: 'Finanze', calls: 'Chiamate',
} as const;
export type PresenceArea = keyof typeof AREA_LABELS;
export type PresenceMode = 'idle' | 'listen' | 'think' | 'speak';
export type PresenceActivity = {
  request_id: string; sequence: number;
  phase: 'processing' | 'context' | 'tool' | 'done' | 'error';
  area: PresenceArea | null; touched: PresenceArea[]; updated_at: number;
  basis?: 'topic' | 'tool' | null;
};
export function readPresenceActivity(value: unknown, requestId: string, previous: PresenceActivity | null = null, now = Date.now()): PresenceActivity | null {
  if (!value || typeof value !== 'object') return null;
  const a = value as PresenceActivity;
  if (a.request_id !== requestId || !Number.isSafeInteger(a.sequence) || a.sequence < 1
    || !Number.isFinite(a.updated_at) || Math.abs(now / 1000 - a.updated_at) > 120
    || !['processing', 'context', 'tool', 'done', 'error'].includes(a.phase)) return null;
  if (previous?.request_id === requestId && previous.sequence > a.sequence) return previous;
  return { request_id: requestId, sequence: a.sequence, phase: a.phase, updated_at: a.updated_at,
    area: a.area && Object.hasOwn(AREA_LABELS, a.area) ? a.area : null,
    basis: a.basis === 'topic' || a.basis === 'tool' ? a.basis : null,
    touched: Array.isArray(a.touched) ? a.touched.filter(x => Object.hasOwn(AREA_LABELS, x)).slice(0, 8) : [],
  };
}

export const COMPLETED_FOCUS_MS = 4000;
export function completionFocusKey(activity: PresenceActivity | null): string | null {
  return activity?.phase === 'done' && activity.area ? `${activity.request_id}:${activity.sequence}` : null;
}
/** Fast replies may deliver their first meaningful focus with the answer. */
export function presenceFocus(activity: PresenceActivity | null, mode: PresenceMode, expiredKey: string | null): PresenceArea | null {
  if (!activity || activity.phase === 'error' || mode === 'listen') return null;
  if (mode === 'think' || mode === 'speak') return activity.area;
  const key = completionFocusKey(activity);
  return key && key !== expiredKey ? activity.area : null;
}
export function presenceMode(busy: boolean, phase?: string): PresenceMode {
  if (phase === 'listening' || phase === 'asking') return 'listen';
  if (phase === 'speaking') return 'speak';
  if (busy || phase === 'thinking' || phase === 'heard' || phase === 'preparing') return 'think';
  return 'idle';
}

export const AREA_IDS = Object.keys(AREA_LABELS) as PresenceArea[];
export type PresenceNode = { index: number; area: PresenceArea; kind: 'area' | 'node' | 'branch'; id?: string };
export const AREA_DETAILS: Record<PresenceArea, { description: string; prompt: string }> = {
  memory: { description: 'Il contesto che hai condiviso con ORA: preferenze, informazioni e cose da tenere presenti.', prompt: 'Riepiloga le informazioni che conosci su di me e indicami da dove arrivano. Distingui ciò che sai dalle ipotesi.' },
  calendar: { description: 'Appuntamenti, scadenze e disponibilità: il tempo su cui organizzare la tua giornata.', prompt: 'Controlla i miei impegni e aiutami a organizzare la giornata. Prima di modificare qualcosa, mostrami la proposta.' },
  people: { description: 'Le persone e le relazioni di cui hai parlato con ORA, nei limiti delle informazioni disponibili.', prompt: 'Aiutami a ritrovare le informazioni disponibili sulle persone di cui ti ho parlato, distinguendo i dati confermati da quelli incerti.' },
  places: { description: 'I tuoi luoghi e gli spostamenti, con posizione, percorsi e condizioni disponibili.', prompt: 'Aiutami a preparare uno spostamento usando i luoghi disponibili. Chiedimi la destinazione se non è chiara.' },
  home: { description: 'La casa e ciò che la riguarda: informazioni, documenti e necessità che hai condiviso.', prompt: 'Riepiloga quello che sai della mia casa e aiutami a capire se c’è qualcosa da verificare, senza inventare informazioni mancanti.' },
  documents: { description: 'File e documenti disponibili: il materiale che ORA può consultare per aiutarti.', prompt: 'Aiutami a trovare o capire un documento. Dimmi quali informazioni sono disponibili e cosa serve approfondire.' },
  finances: { description: 'Spese, contratti e informazioni economiche disponibili, con fonti e stime distinguibili.', prompt: 'Riepiloga le informazioni disponibili sulle mie spese e sui contratti. Distingui i dati verificati dalle stime.' },
  calls: { description: 'Le telefonate che puoi preparare con ORA: destinatario, richiesta e riepilogo prima del tuo via.', prompt: 'Vorrei preparare una telefonata. Aiutami a chiarire destinatario e richiesta; non avviarla senza la mia conferma.' },
};
/** A WebView can report a selection only. It cannot request an action or provide content. */
export function readPresenceNode(value: unknown, geometry: readonly { id: string; area: PresenceArea; kind: string }[] = []): PresenceNode | null {
  if (!value || typeof value !== 'object') return null;
  const node = value as PresenceNode;
  if (!Number.isSafeInteger(node.index) || node.index < 0 || !Object.hasOwn(AREA_LABELS, node.area)) return null;
  if (node.index < 8) return node.kind === 'area' && AREA_IDS[node.index] === node.area
    ? { index: node.index, area: node.area, kind: 'area' } : null;
  const expected = geometry[node.index - 8];
  if (!expected || expected.id !== node.id || expected.area !== node.area || expected.kind !== node.kind) return null;
  return { index: node.index, area: node.area, kind: node.kind, id: node.id };
}
