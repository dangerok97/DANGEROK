// UI tour of the real exported ORA web app with an offline, simulated API.
// No real account or provider is contacted: every /api call is answered here,
// every non-local request is aborted.
const { chromium } = require('@playwright/test');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = process.argv[2];
const OUT = process.argv[3];
const PORT = 8094;
fs.mkdirSync(OUT, { recursive: true });

const mime = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json',
  '.png': 'image/png', '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.ico': 'image/x-icon' };
const server = http.createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  let f = path.resolve(ROOT, '.' + p);
  if (!f.startsWith(ROOT) || !fs.existsSync(f) || !fs.statSync(f).isFile()) f = path.join(ROOT, 'index.html');
  res.writeHead(200, { 'content-type': mime[path.extname(f)] || 'application/octet-stream' });
  res.end(fs.readFileSync(f));
}).listen(PORT, '127.0.0.1');

const now = new Date();
const iso = (h) => new Date(now.getTime() + h * 3600e3).toISOString();
const user = { user_id: 'tour', name: 'Francesco Esempio', first_name: 'Francesco', last_name: 'Esempio',
  email: 'tour@example.invalid', provider: 'password', identity_confirmed: true, knowledge_tutorial_version: 1 };
const weather = { available: true, label: 'Nuvoloso', condition: 'cloudy', icon: 'cloudy-outline', temperature_c: 14, place: 'Tarquinia' };
const opp = (id, title, why, extra = {}) => ({ id, title, why_now: why, created_at: iso(-2), status: 'active', ...extra });
const home = {
  primary_focus: null, explanation: null, current_situation: null, priorities: [], insights: [], resume_item: null,
  ora_ti_consiglia: [], open_questions: [], agent_work: [], connection_warnings: [], ambient: null,
  google_calendar: { connected: true, show_banner: false }, weather, generated_at: now.toISOString(),
  ranking_version: 'tour', partial: false,
  opportunities: [
    opp('o1', 'Buongiorno, ecco la tua giornata', 'Nuvoloso, 11–19 °C, niente pioggia. Niente in agenda oggi.', { reminder: { kind: 'morning_brief' } }),
    opp('o2', 'Chiamare il commercialista', 'Mi hai chiesto di ricordartelo alle 11:30.', { reminder: { kind: 'reminder' } }),
    opp('o3', 'È ora di metterti in moto per «Palestra» alle 17:00', 'Circa 12 min in auto da casa, con 10 min di margine.', { reminder: { kind: 'reminder', route_url: 'https://www.google.com/maps/dir/?api=1&destination=42.25,11.75' } }),
  ],
};
const brief = {
  greeting: 'Buongiorno, Francesco', day: 'Venerdì 6 novembre', headline: 'Nuvoloso, 11–19 °C, niente pioggia.',
  at: now.toISOString().slice(0, 16),
  sections: [
    { key: 'weather', icon: 'cloudy-outline', title: 'Il tempo a Tarquinia', lines: ['Nuvoloso, 11–19 °C, niente pioggia', 'Tramonto alle 17:02', 'Domani: Pioggia, 10–16 °C, pioggia 70%'] },
    { key: 'today', icon: 'calendar-outline', title: 'Oggi', lines: ['10:30 · Dentista (Viterbo) — parti alle 9:52', '17:00 · Palestra (Tarquinia)'] },
    { key: 'done', icon: 'sparkles-outline', title: 'Nelle ultime 24 ore, da sola', lines: ['Ho calcolato quando partire per 2 appuntamenti', 'Ho visto sul conto che hai pagato 1 bolletta: non te le ricordo più'] },
    { key: 'reminders', icon: 'alarm-outline', title: 'Promemoria di oggi', lines: ['Chiamare il commercialista alle 11:30'] },
    { key: 'deadlines', icon: 'time-outline', title: 'Scadenze', lines: ['Bolletta gas (€40): scade domani'] },
    { key: 'drying', icon: 'shirt-outline', title: 'Bucato', lines: ['Buona giornata per il bucato: se stendi alle 9, è asciutto verso le 14.'], good: true },
    { key: 'tomorrow', icon: 'calendar-clear-outline', title: 'Domani', lines: ['9:00 · Medico (Viterbo)'] },
  ],
};
const setup = { notifications: true, location: true, home: false, travel_mode: false, morning_brief: true, travel: 'drive',
  brief: { enabled: true, hour: 8 }, done: false, dismissed: false, missing: ['home', 'travel_mode'] };
const weatherDetail = { ...weather, feels_like_c: 13, humidity_pct: 72, wind_kmh: 14, condition_label: 'Nuvoloso',
  sunrise: '06:48', sunset: '17:02',
  hours: Array.from({ length: 8 }, (_, i) => ({ time: iso(i).slice(11, 16), temperature_c: 13 + (i % 4), rain_chance_pct: 5 * i, icon: 'cloudy-outline' })),
  days: Array.from({ length: 5 }, (_, i) => ({ date: iso(24 * i).slice(0, 10), label: ['Oggi', 'Domani', 'Dom', 'Lun', 'Mar'][i], min_c: 10 + i, max_c: 18 + (i % 2), rain_chance_pct: [0, 70, 30, 10, 0][i], icon: 'cloudy-outline' })) };

function answer(p, method) {
  if (p.includes('providers')) return { google: { configured: false, platforms: {} }, apple: { configured: false, platforms: {} }, password: { configured: true } };
  if (p.includes('/auth/') && method === 'POST') return { token: 'offline-tour-token', user };
  if (p.endsWith('/me') || p.endsWith('/auth/user')) return user;
  if (p === '/api/home') return home;
  if (p === '/api/brief/morning/today') return brief;
  if (p === '/api/brief/setup') return setup;
  if (p === '/api/brief/morning') return { enabled: true, hour: 8 };
  if (p === '/api/brief/evening') return { enabled: true, hour: 20 };
  if (p === '/api/ops/canary') return { runs: [{ day: now.toISOString().slice(0, 10), ok: true, checks: [] }] };
  if (p === '/api/ops/self-check') return { checked: true, at: now.toISOString(), watches: 2, healthy: true, items: [] };
  if (p === '/api/weather') return weatherDetail;
  if (p === '/api/opportunities') return { opportunities: home.opportunities };
  if (p === '/api/places') return { places: [], candidates: [], routines: [], pending_candidates: false, permission: { preference: 'off', state: 'off' } };
  if (p === '/api/financial/overview') return { collegamento: { stato: 'non_collegato', in_parole: 'Nessuna banca collegata.' }, conti: [], cosa_ho_capito: [], fonti_non_piu_collegate: [], collegato_alla_tua_vita: [], da_capire: [], movimenti_recenti: [], vale_la_pena_mostrarlo: false };
  if (p === '/api/calendar/events/home/month') return [];
  if (p === '/api/location/preference') return { ok: true, mode: 'while_using', background_available: false, native_available: false };
  if (p === '/api/recipes/items') return { items: [] };
  if (p === '/api/wallet/cards') return { cards: [] };
  if (p === '/api/energy-offers/monitoring') return { enabled: false, offers: [], items: [] };
  if (p === '/api/life-setup/status') return { ok: true, enabled: true, should_show: false, module_visible: true, wizard: false, session: { status: 'completed' } };
  if (p === '/api/life-profile/knowledge-map') return { stars: [
      { id: 's1', area: 'home', branch_id: null, title: 'Casa', statement: 'Vivi a Tarquinia', status: 'known', provenance: 'Detto da te', icon_key: 'home' },
      { id: 's2', area: 'work', branch_id: null, title: 'Lavoro', statement: 'Ufficio a Viterbo', status: 'known', provenance: 'Detto da te', icon_key: 'briefcase' },
      { id: 's3', area: 'health', branch_id: null, title: 'Salute', statement: 'Dentista ogni 6 mesi', status: 'known', provenance: 'Dal calendario', icon_key: 'medkit' },
      { id: 's4', area: 'memory', branch_id: null, title: 'Memoria temporanea', semantic_kind: 'Panni stesi', icon_key: 'shirt', statement: 'Panni stesi in giardino', status: 'known', provenance: 'Detto da te', temporary: true, situation_id: 'sit1', updated_at: now.toISOString() },
      { id: 's5', area: 'home', branch_id: null, title: 'Orto', statement: 'Pomodori in giardino', status: 'known', provenance: 'Detto da te', icon_key: 'leaf' },
      { id: 's6', area: 'work', branch_id: null, title: 'Collega', statement: 'Marco, stesso ufficio', status: 'known', provenance: 'Detto da te', icon_key: 'person' },
      { id: 's7', area: 'health', branch_id: null, title: 'Palestra', statement: 'Martedì e giovedì', status: 'known', provenance: 'Dal calendario', icon_key: 'barbell' },
      { id: 's8', area: 'people', branch_id: null, title: 'Asia', statement: 'Sorella', status: 'known', provenance: 'Detto da te', icon_key: 'heart' },
      { id: 's9', area: 'mobility', branch_id: null, title: 'Auto', statement: 'Revisione a marzo', status: 'known', provenance: 'Detto da te', icon_key: 'car' },
      { id: 's10', area: 'money', branch_id: null, title: 'Conto ING', statement: 'Conto principale', status: 'known', provenance: 'Dalla banca', icon_key: 'card' },
    ], count: 10, known_count: 10, temporary_count: 1, percent: 38, branches: [], revision: 'tour' };
  if (p === '/api/life-profile/setup') return { ok: true, percent: 38, areas: [], recommended: null, current_area_id: null, objective: null, transition: null };
  if (p === '/api/life-map') return { ok: true, areas: [] };
  if (p === '/api/opportunities/surface') return { opportunities: home.opportunities };
  if (p === '/api/activity') return { ok: true, attention: null, questions: [
      { id: 'q1', title: 'Vuoi che ti ricordi la pastiglia ogni giorno alle 20?', detail: 'Me l\'hai chiesto 3 volte questa settimana.', needs_consent: true, kind: 'habit', at: iso(-3) }],
    waiting: [{ id: 'w1', title: 'Lavatrice in funzione', waiting_for: 'Fine del ciclo', when: 'verso le 10:30' }],
    updates: [{ id: 'u1', title: 'Ho calcolato quando partire per il dentista', context: 'Parti alle 9:52', actor: 'ora', at: iso(-1) },
              { id: 'u2', title: 'Bolletta luce pagata', context: 'Vista sul conto', actor: 'observed', at: iso(-5) }],
    deadlines: [{ id: 'd1', title: 'Bolletta gas (€40)', at: iso(24) }], completed: [{ id: 'c1', title: 'Chiamare Asia', at: iso(-20) }],
    summary: [{ label: 'Fatte da sola', value: 6, icon: 'sparkles-outline' }, { label: 'In attesa', value: 1, icon: 'time-outline' }], generated_at: now.toISOString() };
  if (p === '/api/documents/library') return { ok: true, items: [
      { id: 'doc1', title: 'Carta d\'identità', kind: 'identity', uploaded_at: iso(-200), status: 'ready', summary: 'Scade il 12/03/2029', expiry: { at: '2029-03-12', title: 'Scadenza carta d\'identità' } },
      { id: 'doc2', title: 'Bolletta gas ottobre', kind: 'bill', uploaded_at: iso(-30), status: 'ready', summary: '€40, scade il 7/11' }] };
  if (p === '/api/connected-sources') return { sources: [{ id: 'g', what: 'Google Calendar', state: 'ok', last_read_at: iso(-0.2) },
      { id: 'm', what: 'Gmail', state: 'ok', last_read_at: iso(-0.3) }, { id: 'b', what: 'Conto ING', state: 'ok', last_read_at: iso(-1) }] };
  if (p.endsWith('/instances')) return { instances: [] };
  if (p === '/api/documents/calendar/google/status') return { connected: true };
  if (p === '/api/whatsapp/status') return { connected: false };
  if (p === '/api/siri/key') return { active: false };
  return {};
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: 'it-IT', timezoneId: 'Europe/Rome' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e.stack || e).slice(0, 900)));
  const unknown = new Set();
  await page.route(u => !['127.0.0.1', 'localhost'].includes(u.hostname) && u.protocol.startsWith('http'), r => r.abort());
  await page.route('**/api/**', async r => {
    const req = r.request();
    const p = new URL(req.url()).pathname;
    const h = { 'access-control-allow-origin': req.headers()['origin'] || `http://127.0.0.1:${PORT}`, 'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization, content-type', 'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS' };
    if (req.method() === 'OPTIONS') return r.fulfill({ status: 204, headers: h });
    const a = answer(p, req.method());
    if (a && typeof a === 'object' && !Array.isArray(a) && Object.keys(a).length === 0) unknown.add(req.method() + ' ' + p);
    return r.fulfill({ status: 200, headers: h, json: a });
  });
  const base = `http://127.0.0.1:${PORT}`;
  const shot = async (name, full = true) => {
    await page.waitForTimeout(2200);
    await page.screenshot({ path: path.join(OUT, name + '.png') });
    if (!full) return;
    for (let i = 1; i <= 3; i++) {
      await page.mouse.move(195, 420);
      await page.mouse.wheel(0, 700);
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(OUT, `${name}-${i}.png`) });
    }
  };
  await page.goto(base + '/login');
  await shot('01-login', false);
  try {
    await page.getByTestId('login-email-button').click({ timeout: 8000 });
    await page.getByTestId('login-email-input').fill('tour@example.invalid');
    await page.getByTestId('login-password-input').fill('OfflineTour123!');
    await shot('02-login-email', false);
    await page.getByTestId('login-submit-button').click();
    await page.waitForTimeout(3000);
  } catch (e) { errors.push('login: ' + String(e).slice(0, 120)); }
  for (const [name, route] of [['03-home', '/'], ['04-giornata', '/giornata'], ['05-inizia', '/inizia'], ['06-ora', '/ora'],
    ['07-vita', '/vita'], ['08-attivita', '/attivita'], ['09-documenti', '/documenti'], ['10-settings', '/settings'],
    ['11-meteo', '/meteo'], ['12-aggiornamenti', '/aggiornamenti'], ['13-luoghi', '/luoghi'], ['14-cucina', '/cucina'], ['15-portafoglio', '/portafoglio']]) {
    try { await page.goto(base + route); await shot(name); } catch (e) { errors.push(name + ': ' + String(e).slice(0, 120)); }
  }
  // The star map: two moments of the animation, then a star opened (focus).
  try {
    await page.goto(base + '/vita');
    await page.waitForTimeout(4500);
    await page.screenshot({ path: path.join(OUT, '20-mappa-a.png') });
    await page.waitForTimeout(1700);
    await page.screenshot({ path: path.join(OUT, '20-mappa-b.png') });
    let hit = null;
    for (let y = 150; y < 700 && !hit; y += 14) for (let x = 20; x < 380 && !hit; x += 14) {
      await page.mouse.move(x, y);
      const c = await page.evaluate(() => [...document.querySelectorAll('canvas')].map(k => k.style.cursor).join(','));
      if (c.includes('pointer')) hit = [x, y];
    }
    if (hit) {
      await page.mouse.click(hit[0], hit[1]);
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT, '21-mappa-focus-a.png') });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT, '21-mappa-focus-b.png') });
    } else errors.push('map: no star under the pointer');
  } catch (e) { errors.push('map: ' + String(e).slice(0, 160)); }
  console.log(JSON.stringify({ errors, unknown: [...unknown] }, null, 1));
  await browser.close();
  server.close();
})();
