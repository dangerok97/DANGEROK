// Service worker minimo: mette in cache SOLO le risorse statiche, mai le pagine con dati.
const C='dgk-static-v1';
self.addEventListener('install',e=>e.waitUntil(caches.open(C).then(c=>c.addAll(['/static/style.css','/static/icon.svg']))));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(u.pathname.startsWith('/static/')){e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)))}});
