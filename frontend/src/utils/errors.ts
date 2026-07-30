/**
 * Traduce errori tecnici (HTTP status, OAuth codes, network) in messaggi
 * umani in italiano. Mai esporre codici, header, provider names all'utente.
 */
type AnyErr = { status?: number; message?: string; detail?: any } | any;

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
  const detail = err?.detail;
  const detailStr = typeof detail === 'string'
    ? detail
    : firstNonEmpty(detail?.error, detail?.message, detail?.code);
  const rawMsg = firstNonEmpty(err?.message, detailStr).toLowerCase();

  // Network
  if (looksNetwork(rawMsg) || (!status && !detailStr)) {
    return 'Sembra che tu sia offline. Controlla la connessione e riprova.';
  }

  // OAuth-specific mappings (mai esporre state/redirect/code)
  if (rawMsg.includes('state expired') || rawMsg.includes('state_invalid') || rawMsg.includes('oauth_state')) {
    return "Il collegamento è scaduto. Riprova a collegare Google Calendar.";
  }
  if (rawMsg.includes('access_denied') || rawMsg.includes('user_denied')) {
    return 'Non hai completato l\'accesso a Google. Riprova quando vuoi.';
  }
  if (rawMsg.includes('redirect_uri_mismatch') || rawMsg.includes('invalid_client')) {
    return 'Non siamo riusciti a completare il collegamento. Ci stiamo lavorando — riprova più tardi.';
  }
  if (rawMsg.includes('invalid_scope') || rawMsg.includes('insufficient_scope')) {
    return 'Google non ha concesso i permessi necessari. Riprova selezionando tutti i consensi.';
  }
  if (rawMsg.includes('token_expired') || rawMsg.includes('invalid_token') || rawMsg.includes('refresh')) {
    return 'La connessione con Google è scaduta. Ricollega Google Calendar per continuare.';
  }
  if (rawMsg.includes('consent_revoked') || rawMsg.includes('consent') && rawMsg.includes('revoke')) {
    return 'Hai revocato il consenso. Ricollega Google Calendar per riprendere.';
  }
  if (rawMsg.includes('quota') || rawMsg.includes('rate limit') || rawMsg.includes('rate_limit')) {
    return 'Troppe richieste in poco tempo. Attendi qualche minuto e riprova.';
  }

  // Provider / config
  if (status === 503 || rawMsg.includes('provider_not_ready') || rawMsg.includes('provider not configured')) {
    return 'Il servizio è temporaneamente non disponibile. Riprova tra poco.';
  }

  // Auth / permission
  if (status === 401 || rawMsg.includes('unauthorized')) {
    return 'La tua sessione è scaduta. Accedi di nuovo per continuare.';
  }
  if (status === 403 || rawMsg.includes('forbidden') || rawMsg.includes('permission')) {
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
    return 'Qualcosa non ha funzionato dalla nostra parte. Riprova tra poco.';
  }
  if (status === 422) {
    return 'Alcuni dati non sono validi. Riprova.';
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
