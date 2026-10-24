/*
 * ORA service worker — notifications only.
 *
 * It caches nothing and never touches app requests: its single job is to
 * show a notification the backend decided to send, and to open ORA on tap.
 * The payload carries lock-screen words, a delivery plan id and a route;
 * the route is validated here and again by the app before it is followed.
 */
const PLAN_ID = /^dlv_[A-Za-z0-9_-]{6,80}$/;
const ROUTE = /^\/(aggiornamento\/[A-Za-z0-9_-]{4,80}|ora\?sessionId=[A-Za-z0-9_-]{4,80}&entry=notification|ora\?needId=[A-Za-z0-9_-]{4,80}&goalId=[A-Za-z0-9_-]{4,80}&entry=agent_need)?$/;

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));

self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) { data = {}; }
  const title = typeof data.title === 'string' && data.title ? data.title.slice(0, 120) : 'ORA';
  const body = typeof data.body === 'string' ? data.body.slice(0, 300) : 'Hai un aggiornamento.';
  const planId = typeof data.plan_id === 'string' && PLAN_ID.test(data.plan_id) ? data.plan_id : '';
  const route = typeof data.deep_link === 'string' && ROUTE.test(data.deep_link) ? data.deep_link : '/';
  event.waitUntil(self.registration.showNotification(title, {
    body,
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: planId || undefined,
    data: { plan_id: planId, deep_link: route },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const data = event.notification.data || {};
  const target = data.plan_id
    ? '/notifica?p=' + encodeURIComponent(data.plan_id) + '&to=' + encodeURIComponent(data.deep_link || '/')
    : '/';
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
        await client.focus();
        if ('navigate' in client) return client.navigate(target);
        return undefined;
      }
    }
    return self.clients.openWindow(target);
  })());
});
