import test from 'node:test';
import assert from 'node:assert/strict';
import { requestWebPermission, webPermission, webPushSupport, webSubscription } from './webPush.ts';

const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1';

function browser({ ua = IPHONE, standalone = false, permission = 'default', apis = true } = {}) {
  const calls: string[] = [];
  let subscription: any = null;
  const reg = {
    pushManager: {
      getSubscription: async () => subscription,
      subscribe: async (opts: any) => {
        calls.push('subscribe:' + opts.userVisibleOnly + ':' + opts.applicationServerKey.length);
        subscription = { options: { applicationServerKey: opts.applicationServerKey.buffer },
          toJSON: () => ({ endpoint: 'https://web.push.apple.com/x', keys: { p256dh: 'p', auth: 'a' } }),
          unsubscribe: async () => { calls.push('unsubscribe'); subscription = null; } };
        return subscription;
      },
    },
  };
  const navigator: any = { userAgent: ua, standalone, maxTouchPoints: 5 };
  if (apis) navigator.serviceWorker = {
    getRegistration: async () => null,
    register: async (url: string) => { calls.push('register:' + url); return reg; },
    ready: Promise.resolve(reg),
  };
  const window: any = { matchMedia: () => ({ matches: standalone }) };
  if (apis) window.PushManager = function PushManager() {};
  const Notification: any = apis ? { permission, requestPermission: async () => { calls.push('prompt'); Notification.permission = 'granted'; } } : undefined;
  return { env: { navigator, window, Notification }, calls };
}

// 65-byte uncompressed P-256 point, base64url — shape of a real VAPID key.
const KEY = 'BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBUYIHBQFLXYp5Nksh8U';

test('an iPhone in Safari must add ORA to the Home Screen first', () => {
  assert.equal(webPushSupport(browser({ standalone: false }).env), 'install_required');
  assert.equal(webPushSupport(browser({ standalone: true }).env), 'supported');
  assert.equal(webPushSupport(browser({ ua: 'Mozilla/5.0 (X11; Linux x86_64) Chrome/130', apis: false }).env), 'unsupported');
  assert.equal(webPushSupport({}), 'unsupported');
});

test('a denied browser permission is never presented as askable again', async () => {
  assert.deepEqual(webPermission(browser({ permission: 'denied' }).env), { status: 'denied', canAskAgain: false });
  const b = browser({ standalone: true });
  assert.equal((await requestWebPermission(b.env)).status, 'granted');
  assert.deepEqual(b.calls, ['prompt']);
});

test('subscribing registers the worker once and reuses the same subscription', async () => {
  const b = browser({ standalone: true, permission: 'granted' });
  const first = JSON.parse(await webSubscription(KEY, b.env));
  assert.equal(first.endpoint, 'https://web.push.apple.com/x');
  await webSubscription(KEY, b.env);
  assert.deepEqual(b.calls, ['register:/sw.js', 'subscribe:true:65', 'register:/sw.js']);
});
