/**
 * PX1.8 — Profilo / Impostazioni / Permessi contract guards.
 *
 * The account screen is the one place in ORA where a person goes specifically
 * to find out what is true. Every other surface can be forgiven a hopeful
 * label; this one cannot, because the whole reason to open it is to check.
 *
 * So the failures worth guarding against are all the same failure wearing
 * different clothes: a control that does not control anything. A plan the
 * product does not sell, a backup it does not take, a device list it cannot
 * produce, a "always allow" for a write that asks every time. Each of those is
 * easy to add by copying a reference composition, and each of them turns this
 * page from a report into an advertisement.
 */
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import {
  CALENDAR_WRITE_BOUNDARY,
  DOCUMENT_SCOPE_BOUNDARY,
  LAST_METHOD_REFUSAL,
  connectionLabel,
  connectionStateOf,
  connectedServices,
  displayName,
  lastSyncLabel,
  linkedMethods,
  locationLabel,
  locationSummaryLabel,
  memberSinceLabel,
  primaryAccessLabel,
  sectionsFor,
  shownMethods,
  summaryRows,
  type AccessMethod,
  type AccountSnapshot,
} from './accountModel.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(HERE, '../../..');
const read = (rel: string) => readFileSync(resolve(FRONTEND, rel), 'utf8');
const readCode = (rel: string) =>
  read(rel)
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/\{\/\*[\s\S]*?\*\/\}/g, '');

const LANDING = 'app/(tabs)/profilo.tsx';
const CONNECTIONS = 'app/settings.tsx';
const PERMISSIONS = 'app/account/permessi.tsx';
const PRIVACY = 'app/account/privacy.tsx';
const PREFERENCES = 'app/account/preferenze.tsx';
const MODEL = 'src/components/account/accountModel.ts';
const PARTS = 'src/components/account/AccountParts.tsx';
const AUTH = 'src/components/account/AuthMethods.tsx';

const SURFACES = [LANDING, CONNECTIONS, PERMISSIONS, PRIVACY, PREFERENCES, MODEL, PARTS, AUTH];

const method = (over: Partial<AccessMethod> & Pick<AccessMethod, 'id'>): AccessMethod => ({
  label: over.id,
  linked: false,
  canUnlink: false,
  offerable: true,
  ...over,
});

const SNAP: AccountSnapshot = {
  name: 'Chi usa ORA',
  email: 'persona@example.com',
  memberSince: '2025-01-14T12:00:00Z',
  services: [
    { id: 'google_calendar', name: 'Google Calendar', state: 'connected', account: 'a@b.it' },
  ],
  methods: [
    method({ id: 'password', label: 'Email e password', linked: true }),
    method({ id: 'google', label: 'Google', linked: true, canUnlink: true }),
    method({ id: 'apple', label: 'Apple' }),
  ],
  location: 'off',
  documentAnalysis: true,
  calendarWriteAuthorised: false,
  partial: false,
};

// ---------------------------------------------------------------------------
// A — a capability that does not exist does not appear
// ---------------------------------------------------------------------------
{
  // Every one of these is in the reference composition and in no part of ORA.
  const invented = [
    'Premium',
    'Piano ORA',
    'Verificato',
    'Backup',
    '2FA',
    'Autenticazione a due fattori',
    'Dispositivi attivi',
    'Ultimo accesso',
    'Quiet hours',
    'Elimina il mio account',
    'Esporta i miei dati',
  ];
  for (const file of SURFACES) {
    const src = readCode(file);
    for (const claim of invented) {
      assert.ok(
        !new RegExp(claim, 'i').test(src),
        `${file} must not claim a capability ORA does not have: ${claim}`,
      );
    }
  }

  // And no row may be shown as a future promise instead of being left out.
  for (const file of [LANDING, PERMISSIONS, PRIVACY, PREFERENCES, CONNECTIONS]) {
    const src = readCode(file);
    assert.ok(
      !/prossimamente|in arrivo|coming soon|presto disponibile/i.test(src),
      `${file} must not advertise a roadmap`,
    );
  }
}

// ---------------------------------------------------------------------------
// B — the landing is built from capabilities, not from a layout
// ---------------------------------------------------------------------------
{
  const withPrefs = sectionsFor({ documentAnalysis: true }).map((s) => s.id);
  const withoutPrefs = sectionsFor({ documentAnalysis: null }).map((s) => s.id);

  assert.ok(withPrefs.includes('preferences'));
  assert.ok(
    !withoutPrefs.includes('preferences'),
    'a preferences page with nothing to set must not be offered',
  );
  // The sections that are always real stay through the sparse case.
  for (const id of ['connections', 'permissions', 'privacy']) {
    assert.ok(withoutPrefs.includes(id as any), `${id} must survive a sparse account`);
  }

  // Notifications and devices are not merely hidden by a flag — they are not
  // in the list at all, because nothing behind them exists to switch on.
  const model = readCode(MODEL);
  assert.ok(!/'notifications'|'devices'|'sessions'/.test(model));

  // Every section must open a route that exists on disk.
  for (const s of sectionsFor({ documentAnalysis: true })) {
    const route = s.href.replace(/^\//, '');
    const candidates = [`app/${route}.tsx`, `app/(tabs)/${route.replace('(tabs)/', '')}.tsx`];
    assert.ok(
      candidates.some((c) => existsSync(resolve(FRONTEND, c))),
      `${s.id} points at a route that does not exist: ${s.href}`,
    );
  }
}

// ---------------------------------------------------------------------------
// C — signing in with Google is not the same as ORA reading your calendar
// ---------------------------------------------------------------------------
{
  const connections = readCode(CONNECTIONS);
  // The connections page must not touch identities at all.
  for (const identityCall of ['authIdentities', 'linkGoogle', 'linkApple', 'unlinkProvider']) {
    assert.ok(
      !connections.includes(identityCall),
      `connections must not handle sign-in (${identityCall})`,
    );
  }
  // ...and the access methods live where access is discussed.
  const permissions = readCode(PERMISSIONS);
  assert.ok(permissions.includes('AuthMethods'), 'access methods belong to Permessi e accessi');
  assert.ok(
    /Accedere con Google o Apple non dà a ORA accesso ai loro servizi/i.test(permissions),
    'the difference between an identity and a service must be said out loud',
  );

  // A connector's plumbing never reaches a screen.
  for (const file of [CONNECTIONS, PERMISSIONS, LANDING]) {
    const src = readCode(file);
    for (const leak of ['connector_id', 'capability_id', 'scopes', 'access_token', 'provider_subject']) {
      assert.ok(!src.includes(leak), `${file} must not surface connector internals: ${leak}`);
    }
  }
}

// ---------------------------------------------------------------------------
// D — the calendar consent boundary is never weakened
// ---------------------------------------------------------------------------
{
  // Non più «chiede sempre»: ORA agisce da sola quando gliel'hanno chiesto o
  // permesso. Quello che resta garantito, e che il test continua a sorvegliare,
  // è che le due strade siano entrambe una decisione della persona e che
  // cancellare non sia mai fra le cose che fa da sé.
  assert.ok(/se glielo chiedi tu/i.test(CALENDAR_WRITE_BOUNDARY));
  assert.ok(/permesso di farlo da sola/i.test(CALENDAR_WRITE_BOUNDARY));
  assert.ok(/non elimina mai/i.test(CALENDAR_WRITE_BOUNDARY));
  assert.ok(
    /calendario/i.test(CALENDAR_WRITE_BOUNDARY),
    'the promise must name every write it covers, not just creation',
  );

  for (const file of SURFACES) {
    const src = readCode(file);
    // The backend refuses to store an unattended-write preference at all; a
    // control for it would be a switch wired to nothing.
    assert.ok(!src.includes('calendar_auto_add'), `${file} must not reach for unattended writes`);
    assert.ok(
      !/consenti sempre|permetti sempre|non chiedermelo più|auto[- ]?conferma/i.test(src),
      `${file} must not offer to pre-authorise a write`,
    );
    // A confidence score is not consent.
    assert.ok(!/soglia|threshold|confidence/i.test(src), `${file} must not expose a score`);
  }

  // Documents are volunteered, so the boundary is a statement of scope.
  assert.ok(/solo i documenti che carichi tu/i.test(DOCUMENT_SCOPE_BOUNDARY));
}

// ---------------------------------------------------------------------------
// E — human states, never the connector's own words
// ---------------------------------------------------------------------------
{
  assert.equal(connectionStateOf(null), 'absent');
  assert.equal(connectionStateOf({ status: 'connected' }), 'connected');
  // "revoked" means it was connected once — a different offer from never.
  assert.equal(connectionStateOf({ status: 'revoked' }), 'disconnected');
  assert.equal(connectionStateOf({ status: '' }), 'absent');

  assert.equal(connectionLabel('connected'), 'Connesso');
  assert.equal(connectionLabel('absent'), 'Non connesso');
  assert.equal(connectionLabel('disconnected'), 'Scollegato');
  const labels = (['connected', 'disconnected', 'absent'] as const).map(connectionLabel);
  assert.equal(new Set(labels).size, 3, 'each state needs words of its own');

  // Midday timestamps on purpose: an instant near midnight lands on a
  // different local day than the UTC string suggests, and the test would then
  // be asserting the runner's timezone rather than the label.
  const now = new Date('2026-08-26T12:00:00');
  assert.match(lastSyncLabel('2026-08-26T09:41:00', now), /^Sincronizzato oggi alle /);
  assert.match(lastSyncLabel('2026-08-25T21:18:00', now), /^Sincronizzato ieri alle /);
  assert.equal(lastSyncLabel('2026-08-23T12:00:00', now), 'Sincronizzato 3 giorni fa');
  assert.equal(lastSyncLabel('2026-08-01T12:00:00', now), 'Sincronizzato il 1 agosto');
  assert.equal(lastSyncLabel(null), 'Mai sincronizzato');
  assert.equal(lastSyncLabel('non-una-data'), 'Mai sincronizzato');

  assert.equal(memberSinceLabel('2025-01-14T12:00:00Z'), 'Membro da gennaio 2025');
  // An account old enough to predate the field says nothing rather than 1970.
  assert.equal(memberSinceLabel(null), null);
  assert.equal(memberSinceLabel(''), null);
  assert.equal(memberSinceLabel('boh'), null);

  assert.equal(locationLabel('off'), 'Disattivata');
  assert.equal(locationLabel('while_using'), 'Durante l’uso di ORA');
  // The rail says the same thing in the width it has, rather than truncating.
  assert.equal(locationSummaryLabel('while_using'), 'Durante l’uso');
  assert.equal(locationSummaryLabel('off'), 'Disattivata');
  assert.ok(locationSummaryLabel('while_using').length < locationLabel('while_using').length);
}

// ---------------------------------------------------------------------------
// F — the rail reports, it does not decorate
// ---------------------------------------------------------------------------
{
  const rows = summaryRows(SNAP);
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r.value]));
  assert.equal(byKey.services, '1');
  assert.equal(byKey.access, 'Google');

  // No services known at all → no count invented, not even a zero.
  const bare = summaryRows({ ...SNAP, services: [], methods: [] });
  assert.ok(!bare.some((r) => r.key === 'services'));
  assert.ok(!bare.some((r) => r.key === 'access'));
  assert.equal(bare.length, 1, 'a sparse account keeps only what it knows');

  assert.equal(connectedServices([
    { id: 'a', name: 'A', state: 'connected' },
    { id: 'b', name: 'B', state: 'absent' },
  ]).length, 1);

  assert.equal(byKey.location, 'Disattivata');
  assert.equal(
    summaryRows({ ...SNAP, location: 'while_using' }).find((r) => r.key === 'location')?.value,
    'Durante l’uso',
  );

  // The identity is the person's, never a placeholder.
  assert.equal(displayName(SNAP), 'Chi usa ORA');
  assert.equal(displayName({ name: '  ', email: 'x@y.it' }), 'x@y.it');
  assert.equal(displayName({}), 'Il tuo profilo');

  const landing = readCode(LANDING);
  assert.ok(
    !/@example\.com|@gmail\.com|Elena Rossi|Mario Rossi/i.test(landing),
    'no invented identity may be baked into the page',
  );

  /*
    Casing is presentation. Someone who typed "francesco" is greeted as
    "Francesco" on the card and in the rail, from the one helper both use —
    and nothing writes the corrected spelling back.
  */
  const parts = readCode(PARTS);
  assert.ok(parts.includes('titleCase'), 'the identity card must use the shared casing helper');
  assert.ok(
    /import \{ Avatar, titleCase \} from '@\/src\/shell'/.test(parts),
    'it must be the same helper the rail uses, not a second copy',
  );
  assert.ok(
    !/api\.|uploadAvatar|update|save/i.test(
      parts.slice(parts.indexOf('export function IdentityCard'), parts.indexOf('const SECTION_ICONS')),
    ),
    'the identity card must never write the name back',
  );
  // An address is left alone: capitalising one would be wrong, not polite.
  assert.ok(
    parts.includes("snapshot.name?.trim() ? titleCase(snapshot.name) : displayName(snapshot)"),
    'casing must apply to a name, never to the email standing in for one',
  );
}

// ---------------------------------------------------------------------------
// G — you cannot lock yourself out
// ---------------------------------------------------------------------------
{
  const auth = readCode(AUTH);
  assert.ok(auth.includes('LAST_METHOD_REFUSAL'), 'the refusal must be stated, not improvised');
  assert.ok(/unico modo/i.test(LAST_METHOD_REFUSAL));
  // The unlink action is withheld, not merely met with an error afterwards.
  assert.ok(
    /can_unlink\.google\s*$|can_unlink\.google\n|can_unlink\.google\s*\?/m.test(auth),
    'the unlink affordance must be gated on the backend’s own answer',
  );
  assert.ok(
    auth.includes('identities.can_unlink.apple'),
    'the same gate must apply to every provider',
  );

  const only = [method({ id: 'google', label: 'Google', linked: true, canUnlink: false })];
  assert.equal(primaryAccessLabel(only), 'Google');
  assert.equal(linkedMethods(only).length, 1);
  assert.equal(primaryAccessLabel([]), null, 'no linked method means no claim about access');

  // A method this platform can neither offer nor has linked is not a state;
  // it is a row that could never change, and the rail drops it exactly as the
  // page does — from the same function, so the two cannot disagree.
  const mixed = [
    method({ id: 'password', label: 'Email e password', linked: false, offerable: false }),
    method({ id: 'google', label: 'Google', linked: true }),
    method({ id: 'apple', label: 'Apple', linked: false, offerable: false }),
  ];
  assert.deepEqual(shownMethods(mixed).map((m) => m.id), ['google']);
  // ...but one you actually use is always shown, offerable or not.
  const withPassword = [method({ id: 'password', label: 'Email e password', linked: true, offerable: false })];
  assert.equal(shownMethods(withPassword).length, 1);

  const landingSrc = readCode(LANDING);
  assert.ok(
    landingSrc.includes('shownMethods'),
    'the rail must use the same filter the page does',
  );
}

// ---------------------------------------------------------------------------
// H — the engine is not the user's problem
// ---------------------------------------------------------------------------
{
  for (const file of SURFACES) {
    const src = readCode(file);
    for (const name of ['Gemini', 'OpenAI', 'Ollama', 'Emergent', 'LLM', 'modello AI']) {
      // The connections page still mounts the dev-only block by name; what it
      // must not do is present any provider as a choice in its own words.
      if (file === CONNECTIONS && name === 'LLM') continue;
      assert.ok(!src.includes(name), `${file} must not name the inference stack: ${name}`);
    }
  }
  const dev = read('src/components/dev/DevDiagnostics.tsx');
  assert.ok(
    /if\s*\(!__DEV__\)\s*return null;/.test(dev),
    'diagnostics must not be built into a consumer bundle',
  );
}

// ---------------------------------------------------------------------------
// I — one avatar store, one way out
// ---------------------------------------------------------------------------
{
  const photo = readCode('src/components/account/PhotoDialog.tsx');
  assert.ok(
    photo.includes('useProfilePhoto'),
    'the account surface must reuse the existing avatar flow, not open a second one',
  );
  assert.ok(
    !photo.includes('uploadAvatar') && !photo.includes('removeAvatar'),
    'there must be exactly one place that calls the avatar endpoints',
  );

  const landing = readCode(LANDING);
  assert.ok(landing.includes('LogoutRow'), 'logout must stay reachable');
  assert.ok(
    readCode(PARTS).includes('testID="profile-logout-button"'),
    'the logout testID must stay stable for the flows that check it',
  );
  // ...and must not be the loudest thing on the page.
  assert.ok(
    landing.indexOf('LogoutRow') > landing.indexOf('IdentityCard'),
    'logout belongs at the end of the page, not among the sections',
  );
  const parts = readCode(PARTS);
  const logout = parts.slice(parts.indexOf('export function LogoutRow'));
  assert.ok(
    !/colors\.error/.test(logout.slice(0, logout.indexOf('export function SubpageShell'))),
    'signing out is ordinary, not an alarm',
  );
}

// ---------------------------------------------------------------------------
// J — a subpage always knows the way back
// ---------------------------------------------------------------------------
{
  const parts = readCode(PARTS);
  assert.ok(
    parts.includes("router.replace('/(tabs)/profilo' as any)"),
    'a subpage opened without history must still have a way back',
  );
  for (const file of [PERMISSIONS, PRIVACY, PREFERENCES, CONNECTIONS]) {
    assert.ok(readCode(file).includes('SubpageShell'), `${file} must use the shared subpage shell`);
  }
}

console.log('PX1.8 account guards: all assertions passed');
