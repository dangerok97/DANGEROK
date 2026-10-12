/** A browser callback is a hint; the owner-scoped connector read is the proof. */
export type ConnectorOAuthKind = 'gmail' | 'google_calendar';
export type ConnectorOAuthDestination = '/account/permessi' | '/settings';
export type ConnectorOAuthResult =
  | { state: 'connected'; instanceId: string }
  | { state: 'cancelled' | 'redirecting' };

type Instance = { id: string; status: string; consent_active?: boolean; provider_mode?: string };
export type ConnectorOAuthPorts = {
  platform: 'web' | 'native';
  webOrigin?: string;
  start: (options: { redirect_after: string }) => Promise<{ authorize_url: string }>;
  openAuthSession: (url: string, returnUrl: string) => Promise<{ type: string; url?: string }>;
  navigate: (url: string) => void;
  instances: () => Promise<{ items: Instance[] }>;
};

export class ConnectorOAuthError extends Error {
  constructor() {
    super('Non riesco a verificare il collegamento con Google. Riprova.');
    this.name = 'ConnectorOAuthError';
  }
}

export function connectorReturnUrl(destination: ConnectorOAuthDestination): string {
  return `ora://${destination.slice(1)}`;
}

function authorizationUrl(raw: string): string {
  const url = new URL(raw);
  if (url.protocol !== 'https:' || url.hostname !== 'accounts.google.com'
    || url.port || url.username || url.password || url.pathname !== '/o/oauth2/v2/auth') {
    throw new ConnectorOAuthError();
  }
  return url.href;
}

export async function runConnectorOAuth(
  kind: ConnectorOAuthKind,
  destination: ConnectorOAuthDestination,
  ports: ConnectorOAuthPorts,
): Promise<ConnectorOAuthResult> {
  const returnUrl = ports.platform === 'native'
    ? connectorReturnUrl(destination)
    : new URL(destination, ports.webOrigin).href;
  const started = await ports.start({ redirect_after: returnUrl });
  const authorizeUrl = authorizationUrl(started.authorize_url);
  if (ports.platform === 'web') {
    ports.navigate(authorizeUrl);
    return { state: 'redirecting' };
  }

  const response = await ports.openAuthSession(authorizeUrl, returnUrl);
  if (response.type === 'cancel' || response.type === 'dismiss') return { state: 'cancelled' };
  if (response.type !== 'success' || !response.url) throw new ConnectorOAuthError();
  const actual = new URL(response.url);
  const expected = new URL(returnUrl);
  // Custom-scheme URL origins are all "null": compare the actual destination.
  if (actual.protocol !== expected.protocol || actual.host !== expected.host
    || actual.pathname !== expected.pathname || actual.username || actual.password || actual.hash) {
    throw new ConnectorOAuthError();
  }
  const states = actual.searchParams.getAll(kind);
  if (states.length !== 1) throw new ConnectorOAuthError();
  if (states[0] === 'cancelled') return { state: 'cancelled' };
  const ids = actual.searchParams.getAll('instance_id');
  if (states[0] !== 'connected' || ids.length !== 1 || !ids[0]) throw new ConnectorOAuthError();
  const current = (await ports.instances()).items.find(instance => instance.id === ids[0]);
  if (!current || !['connected', 'syncing', 'active', 'healthy', 'authorized'].includes(current.status)
    || current.consent_active === false || current.provider_mode === 'fake') {
    throw new ConnectorOAuthError();
  }
  return { state: 'connected', instanceId: current.id };
}
