/**
 * Web Push for ORA opened in a browser — above all, ORA added to the iPhone
 * Home Screen (iOS 16.4+), where Safari delivers real notifications with the
 * app closed.
 *
 * Only `enable` may show the browser permission prompt, and only after a tap.
 * The subscription is handed to the backend once and never stored here.
 */
export type WebPushSupport = 'supported' | 'install_required' | 'unsupported';

type Env = {
  navigator?: any;
  window?: any;
  Notification?: any;
};

function env(): Env {
  const g: any = typeof globalThis !== 'undefined' ? globalThis : {};
  return { navigator: g.navigator, window: g.window, Notification: g.Notification };
}

function isIos(nav: any): boolean {
  const ua = String(nav?.userAgent || '');
  // iPadOS reports itself as a Mac with touch.
  return /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && Number(nav?.maxTouchPoints || 0) > 1);
}

function isStandalone(win: any, nav: any): boolean {
  try {
    if (nav?.standalone === true) return true;
    return Boolean(win?.matchMedia?.('(display-mode: standalone)')?.matches);
  } catch { return false; }
}

export function webPushSupport(e: Env = env()): WebPushSupport {
  const { navigator: nav, window: win } = e;
  if (!nav || !win) return 'unsupported';
  const apis = 'serviceWorker' in nav && 'PushManager' in win && Boolean(e.Notification);
  // On iPhone the push APIs exist only once ORA is opened from the Home Screen.
  if (isIos(nav) && !isStandalone(win, nav)) return 'install_required';
  return apis ? 'supported' : 'unsupported';
}

export type WebPermission = { status: 'granted' | 'denied' | 'undetermined'; canAskAgain: boolean };

export function webPermission(e: Env = env()): WebPermission {
  const value = e.Notification?.permission;
  if (value === 'granted') return { status: 'granted', canAskAgain: true };
  // A browser never prompts again after "denied": the person must change it
  // in Settings, so the button must not pretend otherwise.
  if (value === 'denied') return { status: 'denied', canAskAgain: false };
  return { status: 'undetermined', canAskAgain: true };
}

export async function requestWebPermission(e: Env = env()): Promise<WebPermission> {
  if (!e.Notification?.requestPermission) return webPermission(e);
  await e.Notification.requestPermission();
  return webPermission(e);
}

function keyBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(base64url.length / 4) * 4, '=');
  const raw = atob(padded);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

async function registration(e: Env) {
  const container = e.navigator.serviceWorker;
  const existing = await container.getRegistration('/');
  const reg = existing || await container.register('/sw.js', { scope: '/' });
  return container.ready ? await container.ready : reg;
}

/** The subscription JSON the backend stores. Reuses one already made. */
export async function webSubscription(publicKey: string, e: Env = env()): Promise<string> {
  const reg = await registration(e);
  let sub = await reg.pushManager.getSubscription();
  if (sub && publicKey) {
    // A subscription made with another server key can never be used.
    const current = sub.options?.applicationServerKey;
    if (current) {
      const a = new Uint8Array(current);
      const b = keyBytes(publicKey);
      if (a.length !== b.length || a.some((v, i) => v !== b[i])) {
        await sub.unsubscribe();
        sub = null;
      }
    }
  }
  if (!sub) {
    sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: keyBytes(publicKey) });
  }
  return JSON.stringify(sub.toJSON ? sub.toJSON() : sub);
}

export async function stopWebPush(e: Env = env()): Promise<void> {
  if (webPushSupport(e) !== 'supported') return;
  const reg = await e.navigator.serviceWorker.getRegistration('/');
  const sub = reg ? await reg.pushManager.getSubscription() : null;
  if (sub) await sub.unsubscribe();
}

/** Register the worker early so a tap on a notification can open ORA. */
export async function ensureWebWorker(e: Env = env()): Promise<void> {
  if (webPushSupport(e) !== 'supported') return;
  try { await registration(e); } catch { /* the enable tap retries */ }
}
