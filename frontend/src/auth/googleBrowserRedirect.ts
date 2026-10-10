/** Browser-only OAuth redirect helpers. No credentials, tokens or account data. */
export const GOOGLE_BROWSER_PROOF_KEY = 'ora:google:browser:proof';

export function isIOSWebBrowser(userAgent: string): boolean {
  return /iPhone|iPad|iPod/i.test(userAgent || '');
}

/** Accept only Google's own authorization endpoint returned by ORA backend. */
export function authorizedGoogleUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:'
      && parsed.hostname === 'accounts.google.com'
      && parsed.pathname === '/o/oauth2/v2/auth'
      && !!parsed.searchParams.get('state')
      && !!parsed.searchParams.get('code_challenge');
  } catch {
    return false;
  }
}

export function googleBrowserFailure(code: string): string {
  switch (code) {
    case 'account_link_required':
      return 'Questo indirizzo è già associato a un account ORA con password. Accedi con Email, poi collega Google dalle Impostazioni.';
    case 'google_login_cancelled':
      return 'Accesso Google annullato. Non è stato effettuato l’accesso.';
    case 'google_token_missing':
    case 'google_token_invalid':
      return 'Google non ha confermato l’identità. Riprova con il pulsante Google.';
    default:
      return 'Accesso Google non completato. Puoi riprovare o usare Email.';
  }
}
