/**
 * Document Actions — Iterazione 23.
 *
 * Puro layer di logica: prende gli `insights` (ResolvedField[] + threshold)
 * e produce una lista `Action[]` deduplicata, prioritizzata e cross-platform.
 *
 * Vincoli:
 *   - Azioni SOLO da `resolved_fields` con confidence ≥ threshold del backend.
 *   - MAI da entities grezze / hidden_fields / technical_identifiers
 *     (l'unica eccezione è la copia esplicita gestita separatamente
 *     dalla sezione Insights).
 *   - Nessuna azione automatica: il caller decide quando invocarle.
 *   - Ogni URL/email/telefono viene normalizzato + validato.
 *   - Su web ogni azione ha un fallback sicuro.
 */
import { Alert, Linking, Platform, Share } from 'react-native';
import * as Calendar from 'expo-calendar';
import * as Clipboard from 'expo-clipboard';
import * as WebBrowser from 'expo-web-browser';
import type { DocumentInsights, ResolvedField } from '@/src/api/client';

// ---------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------
export type ActionKind =
  | 'calendar_event'      // event_date + eventuale event_time
  | 'calendar_deadline'   // due_date / expiry_date
  | 'calendar_start'      // effective_date (decorrenza)
  | 'map'                 // venue / city / birth_place
  | 'copy_iban'
  | 'copy_amount'
  | 'copy_id'             // tax_id / document_number / invoice_number / order_number / ticket_number / receipt_number / pod
  | 'email'
  | 'phone'
  | 'url'
  | 'share';

export type DocumentAction = {
  kind: ActionKind;
  icon: string;                 // Ionicons name
  label: string;                // testo bottone
  a11yLabel: string;            // accessibilityLabel
  priority: number;             // 1..10 (basso = alto in ordine)
  // dati per l'esecuzione — mai esposti nella UI se sensibili
  payload: Record<string, any>;
};

// ---------------------------------------------------------------------
// Field-key mapping — quali resolved_fields innescano quale azione
// ---------------------------------------------------------------------
const CALENDAR_EVENT_KEY = 'event_date';
const CALENDAR_START_KEY = 'effective_date';
// Chiavi ignorate esplicitamente dalla barra calendario:
//   - birth_date, signature_date, issue_date → no azione (per spec §7)

const IBAN_KEY = 'iban';
const ID_KEYS = new Set([
  'tax_id', 'document_number', 'invoice_number',
  'order_number', 'ticket_number', 'receipt_number', 'pod',
]);
const EMAIL_KEY = 'email';
const PHONE_KEY = 'phone';
const URL_KEYS = new Set(['url']);

// Etichette copia contestualizzate (mai il valore nel toast di sistema)
const COPY_LABEL_BY_FIELD: Record<string, string> = {
  iban: 'IBAN copiato',
  total: 'Importo copiato',
  subtotal: 'Importo copiato',
  vat: 'IVA copiata',
  balance: 'Saldo copiato',
  price: 'Prezzo copiato',
  tax_id: 'Codice fiscale copiato',
  document_number: 'Numero documento copiato',
  invoice_number: 'Numero fattura copiato',
  order_number: 'Numero ordine copiato',
  ticket_number: 'Numero biglietto copiato',
  receipt_number: 'Numero ricevuta copiato',
  pod: 'POD copiato',
};

// ---------------------------------------------------------------------
// Public API — build actions from insights
// ---------------------------------------------------------------------
export function buildDocumentActions(ins: DocumentInsights): DocumentAction[] {
  const threshold = ins.classification?.threshold_visible ?? 60;
  const resolved = (ins.resolved_fields || []).filter(
    (f) => f && typeof f.value === 'string' && f.value.trim().length > 0
           && (f.confidence ?? 0) >= threshold,
  );
  if (resolved.length === 0) return [];

  const byKey = Object.fromEntries(resolved.map((f) => [f.field_key, f]));
  const raw: DocumentAction[] = [];

  // 1) Aggiungi al calendario — evento
  if (byKey[CALENDAR_EVENT_KEY]) {
    const title = byKey.event_title?.value
      || byKey.artist?.value
      || 'Evento';
    raw.push({
      kind: 'calendar_event',
      icon: 'calendar-outline',
      label: 'Aggiungi evento',
      a11yLabel: 'Aggiungi evento al calendario',
      priority: 1,
      payload: {
        title,
        dateText: byKey[CALENDAR_EVENT_KEY].value,
        timeText: byKey.event_time?.value ?? null,
        openingText: byKey.doors_open?.value ?? null,
        venue: byKey.venue?.value ?? null,
        city: byKey.city?.value ?? null,
        notesExtra: [
          byKey.order_number?.value ? `Ordine ${byKey.order_number.value}` : null,
          byKey.ticket_number?.value ? `Biglietto ${byKey.ticket_number.value}` : null,
        ].filter(Boolean).join(' · '),
      },
    });
  }

  // 1b) Scadenza — due_date / expiry_date (una sola azione, prima trovata)
  for (const key of ['due_date', 'expiry_date'] as const) {
    if (byKey[key]) {
      raw.push({
        kind: 'calendar_deadline',
        icon: 'alarm-outline',
        label: 'Aggiungi scadenza',
        a11yLabel: 'Aggiungi scadenza al calendario',
        priority: 2,
        payload: {
          title: _deadlineTitle(ins, byKey[key]!),
          dateText: byKey[key]!.value,
          allDay: true,
        },
      });
      break;
    }
  }

  // 1c) Decorrenza (contratti)
  if (byKey[CALENDAR_START_KEY]) {
    raw.push({
      kind: 'calendar_start',
      icon: 'play-outline',
      label: 'Aggiungi decorrenza',
      a11yLabel: 'Aggiungi decorrenza al calendario',
      priority: 3,
      payload: {
        title: `Decorrenza ${ins.type_label || 'documento'}`,
        dateText: byKey[CALENDAR_START_KEY].value,
        allDay: true,
      },
    });
  }

  // 2) Apri in Mappe — 1 sola azione (venue+city preferito)
  const venue = byKey.venue?.value?.trim();
  const city = byKey.city?.value?.trim();
  const birthPlace = byKey.birth_place?.value?.trim();
  const query =
    (venue && city && venue !== city) ? `${venue}, ${city}`
    : (venue || city || birthPlace || null);
  if (query) {
    raw.push({
      kind: 'map',
      icon: 'map-outline',
      label: 'Apri in Mappe',
      a11yLabel: `Apri ${query} in Mappe`,
      priority: 4,
      payload: { query },
    });
  }

  // 3) Copia IBAN
  if (byKey[IBAN_KEY]) {
    raw.push({
      kind: 'copy_iban',
      icon: 'card-outline',
      label: 'Copia IBAN',
      a11yLabel: 'Copia IBAN negli appunti',
      priority: 5,
      payload: {
        value: byKey[IBAN_KEY].value.replace(/\s+/g, ''),
        toast: COPY_LABEL_BY_FIELD.iban,
      },
    });
  }

  // 4) Email
  if (byKey[EMAIL_KEY]) {
    const email = _normalizeEmail(byKey[EMAIL_KEY].value);
    if (email) {
      raw.push({
        kind: 'email',
        icon: 'mail-outline',
        label: 'Email',
        a11yLabel: `Invia email a ${email}`,
        priority: 6,
        payload: { email },
      });
    }
  }

  // 5) Telefono
  if (byKey[PHONE_KEY]) {
    const tel = _normalizePhone(byKey[PHONE_KEY].value);
    if (tel) {
      raw.push({
        kind: 'phone',
        icon: 'call-outline',
        label: 'Telefono',
        a11yLabel: `Chiama ${tel}`,
        priority: 7,
        payload: { tel },
      });
    }
  }

  // 6) Apri link — URL sicuri (http/https) — de-dupe per URL
  const seenUrls = new Set<string>();
  for (const f of resolved) {
    if (!URL_KEYS.has(f.field_key)) continue;
    const url = _normalizeUrl(f.value);
    if (!url || seenUrls.has(url)) continue;
    seenUrls.add(url);
    raw.push({
      kind: 'url',
      icon: 'open-outline',
      label: 'Apri link',
      a11yLabel: `Apri ${url}`,
      priority: 8,
      payload: { url },
    });
  }

  // 7) Copia identificativo — 1 sola azione (prima trovata per priorità di schema)
  const idField = resolved.find((f) => ID_KEYS.has(f.field_key));
  if (idField) {
    raw.push({
      kind: 'copy_id',
      icon: 'copy-outline',
      label: 'Copia identificativo',
      a11yLabel: `Copia ${idField.label} negli appunti`,
      priority: 9,
      payload: {
        value: idField.value,
        toast: COPY_LABEL_BY_FIELD[idField.field_key] ?? `${idField.label} copiato`,
      },
    });
  }

  // 8) Copia importo — preferisci `total`, poi altri
  const amtField = ['total', 'balance', 'price', 'subtotal']
    .map((k) => byKey[k]).find(Boolean) as ResolvedField | undefined;
  if (amtField) {
    raw.push({
      kind: 'copy_amount',
      icon: 'cash-outline',
      label: 'Copia importo',
      a11yLabel: `Copia ${amtField.label} negli appunti`,
      priority: 10,
      payload: {
        value: amtField.value,
        toast: COPY_LABEL_BY_FIELD[amtField.field_key] ?? 'Importo copiato',
      },
    });
  }

  // 9) Condividi contenuto — sempre disponibile se abbiamo almeno il titolo
  raw.push({
    kind: 'share',
    icon: 'share-outline',
    label: 'Condividi contenuto',
    a11yLabel: 'Condividi il contenuto del documento',
    priority: 11,
    payload: {
      title: ins.classification?.type_label || ins.type_label || 'Documento',
      filename: ins.filename,
      summaryText: _buildShareText(ins, resolved),
    },
  });

  // Ordinamento per priorità (stabile)
  return raw
    .filter((a, i, arr) => arr.findIndex((b) => _actionKey(b) === _actionKey(a)) === i)
    .sort((a, b) => a.priority - b.priority);
}

// ---------------------------------------------------------------------
// Runner — esegue l'azione. Riceve un callback `onToast` per il feedback.
// ---------------------------------------------------------------------
export type ToastFn = (msg: string, kind?: 'success' | 'error') => void;

export async function runDocumentAction(
  action: DocumentAction,
  onToast: ToastFn,
): Promise<void> {
  try {
    switch (action.kind) {
      case 'calendar_event':
      case 'calendar_deadline':
      case 'calendar_start':
        return _runCalendar(action, onToast);
      case 'map':
        return _runMap(action, onToast);
      case 'copy_iban':
      case 'copy_amount':
      case 'copy_id':
        return _runCopy(action, onToast);
      case 'email':
        return _runOpen(`mailto:${action.payload.email}`, 'Impossibile aprire l\'app email', onToast);
      case 'phone':
        return _runOpen(`tel:${action.payload.tel}`, 'Impossibile avviare la chiamata', onToast);
      case 'url':
        return _runUrl(action.payload.url as string, onToast);
      case 'share':
        return _runShare(action, onToast);
    }
  } catch (e: any) {
    onToast(e?.message || 'Azione non disponibile', 'error');
  }
}

// ---------------------------------------------------------------------
// Individual runners
// ---------------------------------------------------------------------
async function _runCopy(action: DocumentAction, onToast: ToastFn) {
  await Clipboard.setStringAsync(String(action.payload.value ?? ''));
  onToast(action.payload.toast || 'Copiato', 'success');
}

async function _runOpen(url: string, errMsg: string, onToast: ToastFn) {
  const ok = await Linking.canOpenURL(url).catch(() => false);
  if (!ok) {
    onToast(errMsg, 'error');
    return;
  }
  await Linking.openURL(url);
}

async function _runUrl(url: string, onToast: ToastFn) {
  const safe = _normalizeUrl(url);
  if (!safe) {
    onToast('Link non sicuro', 'error');
    return;
  }
  if (Platform.OS === 'web') {
    // WebBrowser sul web apre solo in-app (no cross-origin control): usa nuova tab
    if (typeof window !== 'undefined') {
      window.open(safe, '_blank', 'noopener,noreferrer');
      return;
    }
  }
  try {
    await WebBrowser.openBrowserAsync(safe);
  } catch {
    await _runOpen(safe, 'Impossibile aprire il link', onToast);
  }
}

async function _runMap(action: DocumentAction, onToast: ToastFn) {
  const q = encodeURIComponent(String(action.payload.query ?? ''));
  const gmaps = `https://www.google.com/maps/search/?api=1&query=${q}`;
  if (Platform.OS === 'ios') {
    const apple = `http://maps.apple.com/?q=${q}`;
    return _runOpen(apple, 'Impossibile aprire Mappe', onToast);
  }
  if (Platform.OS === 'android') {
    // geo: è generalmente supportato ma il fallback è Google Maps web
    const ok = await Linking.canOpenURL(`geo:0,0?q=${q}`).catch(() => false);
    if (ok) { await Linking.openURL(`geo:0,0?q=${q}`); return; }
    return _runOpen(gmaps, 'Impossibile aprire Mappe', onToast);
  }
  // web
  if (typeof window !== 'undefined') { window.open(gmaps, '_blank', 'noopener,noreferrer'); return; }
  return _runOpen(gmaps, 'Impossibile aprire Mappe', onToast);
}

async function _runCalendar(action: DocumentAction, onToast: ToastFn) {
  const parsed = _parseDate(action.payload.dateText, action.payload.timeText);
  if (!parsed) {
    onToast('Data non valida', 'error');
    return;
  }
  const title = String(action.payload.title || 'Evento');
  const location = [action.payload.venue, action.payload.city].filter(Boolean).join(', ');
  const notes = [
    action.payload.openingText ? `Apertura porte: ${action.payload.openingText}` : null,
    action.payload.notesExtra || null,
  ].filter(Boolean).join('\n');

  // WEB: expo-calendar non funziona. Fallback: apri un template Google Calendar.
  if (Platform.OS === 'web') {
    const start = _fmtGCalDate(parsed.start);
    const end = _fmtGCalDate(parsed.end ?? new Date(parsed.start.getTime() + 60 * 60 * 1000));
    const params = new URLSearchParams({
      action: 'TEMPLATE',
      text: title,
      dates: `${start}/${end}`,
    });
    if (location) params.set('location', location);
    if (notes) params.set('details', notes);
    const url = `https://calendar.google.com/calendar/render?${params.toString()}`;
    if (typeof window !== 'undefined') { window.open(url, '_blank', 'noopener,noreferrer'); }
    onToast('Apri Google Calendar per confermare', 'success');
    return;
  }

  // Native — chiedi conferma contestuale con anteprima
  const preview = [
    `Titolo: ${title}`,
    `Quando: ${_fmtHuman(parsed.start, parsed.allDay)}`,
    location ? `Luogo: ${location}` : null,
  ].filter(Boolean).join('\n');

  const confirmed = await new Promise<boolean>((resolve) => {
    Alert.alert(
      'Aggiungi al calendario',
      preview,
      [
        { text: 'Annulla', style: 'cancel', onPress: () => resolve(false) },
        { text: 'Aggiungi', style: 'default', onPress: () => resolve(true) },
      ],
      { cancelable: true, onDismiss: () => resolve(false) },
    );
  });
  if (!confirmed) return;

  // Permesso contestuale — solo ora
  let perm = await Calendar.getCalendarPermissionsAsync();
  if (perm.status !== 'granted' && perm.canAskAgain) {
    perm = await Calendar.requestCalendarPermissionsAsync();
  }
  if (perm.status !== 'granted') {
    Alert.alert(
      'Permesso mancante',
      'Per creare eventi ORA ha bisogno del permesso Calendario. Puoi attivarlo dalle Impostazioni.',
      [
        { text: 'OK', style: 'cancel' },
        { text: 'Apri Impostazioni', onPress: () => Linking.openSettings().catch(() => {}) },
      ],
    );
    return;
  }

  // Trova un calendario scrivibile di default
  const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
  const target =
    cals.find((c) => c.allowsModifications && c.isPrimary)
    || cals.find((c) => c.allowsModifications)
    || cals[0];
  if (!target) {
    onToast('Nessun calendario disponibile', 'error');
    return;
  }
  await Calendar.createEventAsync(target.id, {
    title,
    startDate: parsed.start,
    endDate: parsed.end ?? new Date(parsed.start.getTime() + 60 * 60 * 1000),
    allDay: parsed.allDay,
    location: location || undefined,
    notes: notes || undefined,
  });
  onToast('Evento aggiunto', 'success');
}

async function _runShare(action: DocumentAction, onToast: ToastFn) {
  const title = String(action.payload.title || 'Documento');
  const message = String(action.payload.summaryText || '');

  if (Platform.OS === 'web') {
    // Prima prova navigator.share; fallback: clipboard
    const nav: any = (typeof navigator !== 'undefined') ? navigator : null;
    if (nav && typeof nav.share === 'function') {
      try {
        await nav.share({ title, text: message });
        onToast('Contenuto condiviso', 'success');
        return;
      } catch { /* user cancelled */ }
    }
    await Clipboard.setStringAsync(`${title}\n\n${message}`);
    onToast('Riepilogo copiato', 'success');
    return;
  }
  await Share.share({ title, message: `${title}\n\n${message}` });
}

// ---------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------
function _actionKey(a: DocumentAction): string {
  // usato per dedupe: kind + valore semantico
  const p = a.payload || {};
  return `${a.kind}|${p.value ?? p.query ?? p.url ?? p.email ?? p.tel ?? p.dateText ?? ''}`;
}

function _deadlineTitle(ins: DocumentInsights, f: ResolvedField): string {
  const t = ins.classification?.type_label || ins.type_label || 'documento';
  if (f.field_key === 'due_date') return `Scadenza pagamento — ${t}`;
  return `Scadenza — ${t}`;
}

function _buildShareText(ins: DocumentInsights, resolved: ResolvedField[]): string {
  const lines: string[] = [];
  const cap = 8; // massimo 8 campi per non condividere tutto il doc
  for (const f of resolved.slice(0, cap)) {
    // Non condividere valori evidentemente sensibili non richiesti
    lines.push(`${f.label}: ${f.value}`);
  }
  return lines.join('\n');
}

// -------- Normalizers / Validators --------
function _normalizeEmail(v: string): string | null {
  const s = (v || '').trim();
  return /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(s) ? s : null;
}

function _normalizePhone(v: string): string | null {
  const digits = (v || '').replace(/[^\d+]/g, '');
  if (!digits || digits.replace(/^\+/, '').length < 7) return null;
  return digits;
}

function _normalizeUrl(v: string): string | null {
  const s = (v || '').trim();
  if (!s) return null;
  // Blocca esplicitamente schemi pericolosi
  if (/^(javascript|data|file|vbscript):/i.test(s)) return null;
  if (/^https?:\/\//i.test(s)) return s;
  // "example.com/..." → aggiungi https
  if (/^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-z]{2,}(\/.*)?$/i.test(s)) return `https://${s}`;
  return null;
}

// -------- Date parser (Italian formats) --------
export function _parseDate(dateText: string, timeText?: string | null): {
  start: Date; end: Date | null; allDay: boolean;
} | null {
  if (!dateText) return null;
  const s = dateText.trim();
  const time = _parseTime(timeText || '');

  // ISO or dd/mm/yyyy or "30 giugno 2026"
  let d: Date | null = null;
  let m: RegExpMatchArray | null;

  // dd/mm/yyyy
  m = s.match(/^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$/);
  if (m) {
    const dd = parseInt(m[1], 10);
    const mm = parseInt(m[2], 10) - 1;
    let yy = parseInt(m[3], 10);
    if (yy < 100) yy += 2000;
    d = new Date(yy, mm, dd, time?.h ?? 0, time?.m ?? 0);
  }

  // yyyy-mm-dd
  if (!d) {
    m = s.match(/^(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})$/);
    if (m) d = new Date(parseInt(m[1], 10), parseInt(m[2], 10) - 1, parseInt(m[3], 10),
                       time?.h ?? 0, time?.m ?? 0);
  }

  // "30 giugno 2026"
  if (!d) {
    const months: Record<string, number> = {
      gennaio: 0, febbraio: 1, marzo: 2, aprile: 3, maggio: 4, giugno: 5,
      luglio: 6, agosto: 7, settembre: 8, ottobre: 9, novembre: 10, dicembre: 11,
      january: 0, february: 1, march: 2, april: 3, may: 4, june: 5, july: 6,
      august: 7, september: 8, october: 9, november: 10, december: 11,
    };
    m = s.match(/^(\d{1,2})\s+([a-zàé]+)\s+(\d{2,4})$/i);
    if (m) {
      const mo = months[m[2].toLowerCase()];
      if (mo != null) {
        let yy = parseInt(m[3], 10); if (yy < 100) yy += 2000;
        d = new Date(yy, mo, parseInt(m[1], 10), time?.h ?? 0, time?.m ?? 0);
      }
    }
  }

  if (!d || isNaN(d.getTime())) return null;
  const allDay = !time;
  const end = time ? new Date(d.getTime() + 90 * 60 * 1000)
                   : new Date(d.getFullYear(), d.getMonth(), d.getDate() + 1);
  return { start: d, end, allDay };
}

function _parseTime(v: string): { h: number; m: number } | null {
  const m = (v || '').match(/^(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?$/);
  if (!m) return null;
  const h = parseInt(m[1], 10), mm = parseInt(m[2], 10);
  if (h > 23 || mm > 59) return null;
  return { h, m: mm };
}

function _fmtGCalDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}00Z`;
}

function _fmtHuman(d: Date, allDay: boolean): string {
  const day = d.toLocaleDateString('it-IT', { day: '2-digit', month: 'long', year: 'numeric' });
  if (allDay) return day;
  const time = d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  return `${day} · ${time}`;
}

// Testable exports
export const __internal__ = {
  _normalizeEmail, _normalizePhone, _normalizeUrl, _parseDate, _parseTime,
};
