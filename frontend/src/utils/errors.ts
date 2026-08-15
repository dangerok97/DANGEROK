/**
 * Traduce errori tecnici (HTTP status, OAuth codes, network) in messaggi
 * umani in italiano. Distingue: rete / config URL / HTTP / provider AI.
 */
type AnyErr = { status?: number; message?: string; detail?: any; code?: string; network?: boolean } | any;

function firstNonEmpty(...vals: any[]): string {
  for (const v of vals) if (typeof v === 'string' && v.trim().length) return v;
  return '';
}

function looksNetwork(msg: string): boolean {
  const m = msg.toLowerCase();
  return (
    m.includes('network request failed') ||
    m.includes('failed to fetch') ||
    m.includes('load failed') ||
    m.includes('networkerror') ||
    m.includes('typeerror: network') ||
    m.includes('offline')
  );
}

export function humanizeError(err: AnyErr, action: string = 'default'): string {
  if (!err) return 'Si è verificato un imprevisto. Riprova.';
  const status: number | undefined = err?.status;
  const code = String(err?.code || '').toLowerCase();
  const detail = err?.detail;
  const detailStr = typeof detail === 'string'
    ? detail
    : firstNonEmpty(detail?.error, detail?.message, detail?.code);
  const rawMsg = firstNonEmpty(err?.message, detailStr);
  const rawLow = rawMsg.toLowerCase();

  // Config: backend URL missing (never reached the server)
  if (code === 'backend_url_missing' || rawLow.includes('expo_public_backend_url')) {
    return 'ORA non sa dove trovare il server locale. Controlla EXPO_PUBLIC_BACKEND_URL e riavvia Expo.';
  }

  // Network unreachable (Failed to fetch) — distinct from HTTP errors
  if (code === 'network_unreachable' || err?.network || looksNetwork(rawLow)) {
    return 'Non riesco a raggiungere il server. Verifica che il backend sia avviato e l’URL sia corretto.';
  }

  // AI / reasoning provider (after request reached backend)
  if (
    code === 'provider_unavailable'
    || rawLow.includes('provider_unavailable')
    || rawLow.includes('motore di ragionamento')
    || rawLow.includes('llmnotconfigured')
    || rawLow.includes('gemini')
  ) {
    return 'Il motore di ragionamento non è disponibile in questo momento. Riprova tra poco.';
  }

  // OAuth-specific mappings (mai esporre state/redirect/code)
  if (rawLow.includes('state expired') || rawLow.includes('state_invalid') || rawLow.includes('oauth_state')) {
    return "Il collegamento è scaduto. Riprova a collegare Google Calendar.";
  }
  if (rawLow.includes('access_denied') || rawLow.includes('user_denied')) {
    return 'Non hai completato l\'accesso a Google. Riprova quando vuoi.';
  }
  if (rawLow.includes('redirect_uri_mismatch') || rawLow.includes('invalid_client') || rawLow.includes('Origin is not allowed')) {
    return 'Google ha rifiutato l\'URL di ritorno. In Cloud Console registra sia localhost sia 127.0.0.1 (stessa porta) tra origins e redirect URI.';
  }
  if (rawLow.includes('invalid_scope') || rawLow.includes('insufficient_scope')) {
    return 'Google non ha concesso i permessi necessari. Riprova selezionando tutti i consensi.';
  }
  if (rawLow.includes('token_expired') || rawLow.includes('invalid_token') || rawLow.includes('refresh')) {
    return 'La connessione con Google è scaduta. Ricollega Google Calendar per continuare.';
  }
  if (rawLow.includes('consent_revoked') || (rawLow.includes('consent') && rawLow.includes('revoke'))) {
    return 'Hai revocato il consenso. Ricollega Google Calendar per riprendere.';
  }
  if (rawLow.includes('quota') || rawLow.includes('rate limit') || rawLow.includes('rate_limit')) {
    return 'Troppe richieste in poco tempo. Attendi qualche minuto e riprova.';
  }

  // Provider / config
  if (status === 503 || rawLow.includes('provider_not_ready') || rawLow.includes('provider not configured')) {
    return 'Il servizio è temporaneamente non disponibile. Riprova tra poco.';
  }

  // Auth / permission — request reached backend
  if (status === 401 || code === 'unauthorized' || rawLow.includes('unauthorized') || rawLow.includes('missing bearer')) {
    return 'La tua sessione è scaduta. Accedi di nuovo per continuare.';
  }
  if (status === 403 || rawLow.includes('forbidden') || rawLow.includes('permission')) {
    if (action === 'sync') return 'Non abbiamo più accesso al tuo calendario. Ricollegalo per continuare.';
    if (action === 'connect') return 'Purtroppo Google ha rifiutato l\'accesso. Riprova quando vuoi.';
    return 'Questa azione non è consentita.';
  }
  if (status === 404) {
    if (action === 'sync' || action === 'calendars' || action === 'revoke') {
      return 'Il collegamento non è più attivo. Ricollega Google Calendar per riprendere.';
    }
    return 'Non troviamo più questo elemento.';
  }
  if (status === 409) {
    return 'L\'operazione non è possibile nello stato attuale.';
  }
  if (status && status >= 500) {
    return 'Il server ha restituito un errore. Riprova tra poco.';
  }
  if (status === 422) {
    return 'Alcuni dati non sono validi. Riprova.';
  }
  // HTTP error with status (reached backend) — not a network failure
  if (status) {
    return 'Qualcosa è andato storto. Riprova.';
  }

  // Contextual defaults
  switch (action) {
    case 'connect': return 'Non siamo riusciti a collegare il calendario. Riprova.';
    case 'sync': return 'Non siamo riusciti a sincronizzare. Riprova.';
    case 'select': return 'Non siamo riusciti a salvare la scelta. Riprova.';
    case 'calendars': return 'Non siamo riusciti a caricare i tuoi calendari. Riprova.';
    case 'revoke': return 'Non siamo riusciti a scollegare. Riprova.';
    default: return 'Qualcosa è andato storto. Riprova.';
  }
}
