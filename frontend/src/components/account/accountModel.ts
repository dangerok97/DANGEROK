/**
 * The account, as something a person can read.
 *
 * Every value here comes from a system that already exists: the identity
 * store, the calendar connectors, the location preference, the documents
 * preference. Nothing is invented to fill a layout — a plan, a verified badge,
 * a backup, a device count and a 2FA state all have a natural place in a
 * composition like this one and none of them exist in ORA, so none of them
 * appear. The rule the whole module follows is that a row is built from a
 * capability, never the other way round.
 *
 * Pure and import-free on purpose: this is the part that decides what is true,
 * and it is testable without a renderer.
 */

/* -------------------------------------------------------------------------- */
/* Inputs                                                                     */
/* -------------------------------------------------------------------------- */

export type ConnectionState = 'connected' | 'disconnected' | 'absent';

export type ServiceModel = {
  id: string;
  /** What the person calls it. */
  name: string;
  state: ConnectionState;
  /** The account it is attached to, when the connector knows one. */
  account?: string | null;
  lastSyncAt?: string | null;
};

export type AccessMethod = {
  id: 'password' | 'google' | 'apple';
  label: string;
  linked: boolean;
  detail?: string | null;
  /** False when this is the last way in — unlinking it would lock the door. */
  canUnlink: boolean;
  /**
   * Whether this platform can offer to link it at all.
   *
   * Apple sign-in is not available on every platform, and a password cannot be
   * added to an account that never had one. A method that is neither linked
   * nor offerable is not a state worth reporting — it is a row that could
   * never change — so the rail and the page both drop it, from here.
   */
  offerable: boolean;
};

export type LocationMode = 'off' | 'while_using';

export type AccountSnapshot = {
  name?: string | null;
  email?: string | null;
  picture?: string | null;
  memberSince?: string | null;
  services: ServiceModel[];
  methods: AccessMethod[];
  location: LocationMode;
  /** ORA reading the documents you upload. A real, enforced preference. */
  documentAnalysis: boolean | null;
  /** Whether the calendar scope for writing was authorised at all. */
  calendarWriteAuthorised: boolean;
  /** Something in the snapshot could not be loaded. */
  partial: boolean;
};

/* -------------------------------------------------------------------------- */
/* Identity                                                                   */
/* -------------------------------------------------------------------------- */

const MONTHS = [
  'gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno',
  'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre',
];

/** "Membro da gennaio 2025", or nothing at all when the date is not known. */
export function memberSinceLabel(iso?: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const d = new Date(t);
  return `Membro da ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** The name if there is one; otherwise the email is the person's name here. */
export function displayName(snap: Pick<AccountSnapshot, 'name' | 'email'>): string {
  const n = (snap.name || '').trim();
  if (n) return n;
  const e = (snap.email || '').trim();
  return e || 'Il tuo profilo';
}

/* -------------------------------------------------------------------------- */
/* Services                                                                   */
/* -------------------------------------------------------------------------- */

const CONNECTION_LABEL: Record<ConnectionState, string> = {
  connected: 'Connesso',
  disconnected: 'Scollegato',
  absent: 'Non connesso',
};

export function connectionLabel(state: ConnectionState): string {
  return CONNECTION_LABEL[state];
}

/**
 * A connector instance's own status, translated once.
 *
 * `revoked` is the connector's word for an authorisation that used to exist
 * and no longer does; that is a different thing from never having connected,
 * and the difference matters because only one of the two has a reconnect path.
 */
export function connectionStateOf(
  instance: { status?: string | null } | null | undefined,
): ConnectionState {
  if (!instance) return 'absent';
  const s = String(instance.status || '').trim();
  if (!s) return 'absent';
  if (s === 'revoked') return 'disconnected';
  return 'connected';
}

const DAY_MS = 86_400_000;

/**
 * Da quanto ORA ha guardato, e se ci sta riuscendo.
 *
 *   CONNESSO NON VUOL DIRE AGGIORNATO.
 *
 * Sono due fatti diversi e il prodotto li ha sempre tenuti separati altrove:
 * una connessione perfettamente sana puo' reggere una fotografia di due
 * giorni fa, e una schermata che dice solo «Connesso» lascia credere il
 * contrario. Qui diventano una riga sola, con tre casi:
 *
 *   - sta andando       «Aggiornato automaticamente · 6 minuti fa»
 *   - vecchio           «Connesso · ultimo aggiornamento 2 giorni fa»
 *   - non ci riesce     «Connesso · non riesco ad aggiornarlo in questo momento»
 *
 * Non c'e' un quarto caso che dice «premi Sincronizza», perche' non c'e' piu'
 * niente da premere: se ORA non riesce ad aggiornare una sorgente, riprovare
 * e' compito suo.
 */
export function autoSyncLabel(
  source: { state?: string | null; last_read_at?: string | null } | null | undefined,
  now: Date = new Date(),
): string {
  const state = String(source?.state || '').trim();
  const age = humanAgo(source?.last_read_at, now);

  if (/non riesco/i.test(state)) {
    return 'Connesso · non riesco ad aggiornarlo in questo momento';
  }
  if (/vecchio/i.test(state)) {
    return age
      ? `Connesso · ultimo aggiornamento ${age}`
      : 'Connesso · ultimo aggiornamento molto tempo fa';
  }
  if (!age) return 'Aggiornato automaticamente';
  return `Aggiornato automaticamente · ${age}`;
}

/** «6 minuti fa». Mai un orario, mai una data. */
export function humanAgo(iso?: string | null, now: Date = new Date()): string {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '';
  const minutes = Math.floor((now.getTime() - t) / 60000);
  if (minutes < 1) return 'poco fa';
  if (minutes < 60) return minutes === 1 ? 'un minuto fa' : `${minutes} minuti fa`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "un'ora fa" : `${hours} ore fa`;
  const days = Math.floor(hours / 24);
  return days === 1 ? 'ieri' : `${days} giorni fa`;
}

/** "Sincronizzato oggi alle 09:41" — never a raw timestamp. */
export function lastSyncLabel(iso?: string | null, now: Date = new Date()): string {
  if (!iso) return 'Mai sincronizzato';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return 'Mai sincronizzato';
  const d = new Date(t);
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(d)) / DAY_MS);
  const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  if (days <= 0) return `Sincronizzato oggi alle ${time}`;
  if (days === 1) return `Sincronizzato ieri alle ${time}`;
  if (days < 7) return `Sincronizzato ${days} giorni fa`;
  return `Sincronizzato il ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function connectedServices(services: ServiceModel[]): ServiceModel[] {
  return services.filter((s) => s.state === 'connected');
}

/* -------------------------------------------------------------------------- */
/* Access                                                                     */
/* -------------------------------------------------------------------------- */

/**
 * How this person gets in.
 *
 * Signing in with Google and letting ORA read a Google calendar are two
 * different grants, and running them together is the easiest way to make a
 * settings screen lie. They live in separate sections for that reason, and
 * this function only ever looks at identities.
 */
export function primaryAccessLabel(methods: AccessMethod[]): string | null {
  const linked = methods.filter((m) => m.linked);
  if (!linked.length) return null;
  const first =
    linked.find((m) => m.id === 'google') || linked.find((m) => m.id === 'apple') || linked[0];
  return first.label;
}

export function linkedMethods(methods: AccessMethod[]): AccessMethod[] {
  return methods.filter((m) => m.linked);
}

/** What is worth showing: what you have, plus what you could add. */
export function shownMethods(methods: AccessMethod[]): AccessMethod[] {
  return methods.filter((m) => m.linked || m.offerable);
}

/** The reason an unlink is refused, in the words of the person it affects. */
export const LAST_METHOD_REFUSAL = 'Non puoi scollegare l’unico modo che hai per entrare in ORA.';

/* -------------------------------------------------------------------------- */
/* Permissions                                                                */
/* -------------------------------------------------------------------------- */

export function locationLabel(mode: LocationMode): string {
  return mode === 'while_using' ? 'Durante l’uso di ORA' : 'Disattivata';
}

/**
 * The same fact, in the width the rail has.
 *
 * "Durante l'uso di ORA" is the right sentence next to a radio button, and one
 * word too long for a summary column that must not grow. Cutting it to
 * "Durante l'uso" loses nothing — the reader is inside ORA — whereas letting
 * it truncate to "Durante l'uso di…" would leave the one line meant to be
 * reassuring looking like a bug.
 */
export function locationSummaryLabel(mode: LocationMode): string {
  return mode === 'while_using' ? 'Durante l’uso' : 'Disattivata';
}

/**
 * The calendar boundary, stated once and reused wherever it is relevant.
 *
 * Writing to a calendar is not a permission that gets switched on and then
 * forgotten: the backend asks for a confirmation on every single write and
 * refuses to be configured otherwise. A screen that showed this as a toggle
 * would describe a product that does not exist, and would quietly suggest the
 * confirmation could be turned off.
 */
/*
  Questa frase diceva «chiede sempre conferma», e ha smesso di essere vera.

  Adesso ORA agisce senza una seconda domanda in due casi soltanto, e sono
  entrambi una decisione della persona: quando gliel'ha appena chiesto, e
  quando le ha dato un permesso per il futuro. Lasciare la vecchia frase
  sarebbe stato peggio che non averla — un'app che rassicura su una garanzia
  che non offre più.
*/
export const CALENDAR_WRITE_BOUNDARY =
  'ORA scrive nel tuo calendario solo se glielo chiedi tu, o se le hai dato il permesso di farlo da sola. Non elimina mai un evento senza chiedertelo.';

/*
  La posta, e la meta' che toglie la paura vera.

  Cosa ORA legge lo dice gia' la scheda, in tutte e due le schermate dove
  compare. Ripeterlo qui voleva dire leggere la stessa frase due volte nello
  stesso riquadro — l'avevo scritta cosi', e negli screenshot si vedeva. Qui
  resta solo quello che nessun'altra riga dice: cosa ORA non fa. «Non
  risponde» e' la parola che una persona cerca davvero quando le si dice che
  un'intelligenza artificiale legge le sue email.
*/
export const MAIL_BOUNDARY =
  'ORA non scrive, non risponde e non archivia niente al posto tuo.';

export const DOCUMENT_SCOPE_BOUNDARY =
  'ORA legge solo i documenti che carichi tu. Non accede a cartelle o archivi sul tuo dispositivo.';

/* -------------------------------------------------------------------------- */
/* The landing                                                                */
/* -------------------------------------------------------------------------- */

export type SectionId = 'preferences' | 'connections' | 'permissions' | 'privacy';

export type Section = {
  id: SectionId;
  title: string;
  detail: string;
  href: string;
};

const SECTIONS: Section[] = [
  {
    id: 'preferences',
    title: 'Preferenze ORA',
    detail: 'Scegli come ORA lavora con le tue cose',
    href: '/account/preferenze',
  },
  {
    id: 'connections',
    title: 'Connessioni e servizi',
    detail: 'I servizi che hai collegato a ORA',
    href: '/settings',
  },
  {
    id: 'permissions',
    title: 'Permessi e accessi',
    detail: 'Cosa ORA può usare, e come entri nel tuo account',
    href: '/account/permessi',
  },
  {
    id: 'privacy',
    title: 'Privacy e dati',
    detail: 'Cosa ORA sa di te, e come puoi cambiarlo',
    href: '/account/privacy',
  },
];

/**
 * Which sections exist for this person right now.
 *
 * Notifiche and Dispositivi e sessioni belong in a composition like this one
 * and are missing from the list because ORA has neither: no notification
 * preference is stored anywhere, and no session or device API exists. A row
 * that opens onto nothing — or one greyed out with "prossimamente" — is a
 * promise made in the one place a person comes to check what is true.
 */
export function sectionsFor(snap: Pick<AccountSnapshot, 'documentAnalysis'>): Section[] {
  return SECTIONS.filter((s) => {
    // Preferences needs at least one preference that can actually be changed.
    if (s.id === 'preferences') return snap.documentAnalysis !== null;
    return true;
  });
}

/* -------------------------------------------------------------------------- */
/* The rail                                                                   */
/* -------------------------------------------------------------------------- */

export type SummaryRow = { key: string; label: string; value: string };

/** Only rows whose value is known. An unknown value is left out, not zeroed. */
export function summaryRows(snap: AccountSnapshot): SummaryRow[] {
  const rows: SummaryRow[] = [];
  if (snap.services.length) {
    rows.push({
      key: 'services',
      label: 'Servizi collegati',
      value: String(connectedServices(snap.services).length),
    });
  }
  const access = primaryAccessLabel(snap.methods);
  if (access) rows.push({ key: 'access', label: 'Accesso', value: access });
  rows.push({ key: 'location', label: 'Posizione', value: locationSummaryLabel(snap.location) });
  return rows;
}
