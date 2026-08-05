/**
 * Home V2 Goal-aware smoke — after Study/Travel confirm, GET /api/home
 * shows one coherent goal-linked item (deduped). No Goal tab / screens.
 */
import { test, expect } from '@playwright/test';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';

async function register(prefix: string) {
  const email = `e2e_home_goal_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E HomeGoal ${prefix}` }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { token: data.token as string, email, password };
}

function auth(token: string) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

async function getSession(token: string, sessionId: string) {
  const cur = await fetch(`${API}/api/action-engine/sessions/${sessionId}`, {
    headers: auth(token),
  });
  const pub = await cur.json();
  return pub.session || pub;
}

async function answerTurn(token: string, sessionId: string, turn: any) {
  const tid = turn.id as string;
  const opts: Array<{ id: string; value?: unknown }> = turn.options || [];
  const prefer = [
    'confirm', 'accept', 'distributed', 'evening', 'no', '1h', 'none',
    'skip', 'solo', 'car', 'partial', 'connect_later',
  ];

  if (tid === 'exam_date' || tid === 'period' || tid === 'destination' || tid === 'departure_place' || tid === 'departure') {
    const examDate = new Date(Date.now() + 21 * 86400_000).toISOString().slice(0, 10);
    const start = new Date(Date.now() + 30 * 86400_000).toISOString().slice(0, 10);
    const end = new Date(Date.now() + 40 * 86400_000).toISOString().slice(0, 10);
    let text = examDate;
    if (tid === 'period') text = `${start} ${end}`;
    if (tid === 'destination') text = 'Calabria';
    if (tid === 'departure_place' || tid === 'departure') text = 'Roma';
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text }),
    }).then((r) => r.json());
  }

  if (tid === 'available_days') {
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ value: [0, 1, 2, 3, 4] }),
    }).then((r) => r.json());
  }

  if (tid === 'tools') {
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ value: ['study', 'review'] }),
    }).then((r) => r.json());
  }

  if (tid === 'select_materials') {
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ option_id: 'none', value: [] }),
    }).then((r) => r.json());
  }

  if (tid === 'prep' && opts.some((o) => o.id === 'skip')) {
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ option_id: 'skip' }),
    }).then((r) => r.json());
  }

  for (const id of prefer) {
    if (opts.some((o) => o.id === id)) {
      return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
        method: 'POST',
        headers: auth(token),
        body: JSON.stringify({ option_id: id }),
      }).then((r) => r.json());
    }
  }

  if (opts.length > 0) {
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ option_id: opts[0].id }),
    }).then((r) => r.json());
  }

  throw new Error(`cannot answer turn ${tid}`);
}

async function driveToConfirm(token: string, openBody: Record<string, unknown>) {
  const open = await fetch(`${API}/api/action-engine/open`, {
    method: 'POST',
    headers: auth(token),
    body: JSON.stringify({ ...openBody, force_new: true }),
  });
  const opened = await open.json();
  if (!open.ok) throw new Error(`open failed: ${JSON.stringify(opened)}`);
  const sessionId = opened.session?.id || opened.id;
  if (!sessionId) throw new Error(`no session: ${JSON.stringify(opened)}`);

  for (let i = 0; i < 40; i++) {
    const session = await getSession(token, sessionId);
    if (session.done || session.status === 'completed') break;
    const turn = session.current_turn;
    if (!turn) break;
    const aj = await answerTurn(token, sessionId, turn);
    if (aj.completed || aj.session?.done || aj.session?.status === 'completed') break;
  }

  const after = await getSession(token, sessionId);
  if (after.status !== 'completed' && after.status !== 'cancelled') {
    await fetch(`${API}/api/action-engine/sessions/${sessionId}/confirm`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({}),
    });
  }
  return sessionId;
}

function collectSurface(home: any) {
  const items: any[] = [];
  if (home.primary_focus) items.push(home.primary_focus);
  for (const g of home.priorities || []) {
    for (const it of g.items || []) items.push(it);
  }
  return items;
}

test.describe('Home V2 Goal-aware (no Goal UX)', () => {
  test('STUDY: confirm → Home session + Goal context → no dupes → Perché → open plan', async () => {
    test.setTimeout(120_000);
    const { token, email, password } = await register('study');
    await driveToConfirm(token, {
      title: 'Preparazione esame di Psicologia',
      description: "Devo preparare l'esame di Psicologia entro tre settimane",
      item_type: 'study',
    });

    const goalsRes = await fetch(`${API}/api/goals?goal_type=study`, { headers: auth(token) });
    expect(goalsRes.ok).toBeTruthy();
    const goals = ((await goalsRes.json()).goals || []) as any[];
    expect(goals.length).toBeGreaterThanOrEqual(1);
    const goalId = goals[0].id as string;

    let homeRes = await fetch(`${API}/api/home`, { headers: auth(token) });
    expect(homeRes.ok).toBeTruthy();
    let home = await homeRes.json();
    expect(home.ranking_version).toBe('home-rank-1.2');

    let surface = collectSurface(home);
    let linked = surface.filter((i) => i.goal_id === goalId);
    expect(linked.length).toBe(1);
    expect(linked[0].goal_title).toBeTruthy();
    expect(String(linked[0].goal_title).toLowerCase()).toMatch(/psicolog/);
    expect(linked[0].goal_type).toBe('study');
    // Goal as context on primary
    const primary = home.primary_focus;
    if (primary?.goal_id === goalId) {
      expect(
        (primary.description || '').includes('Obiettivo:') || primary.goal_title,
      ).toBeTruthy();
      const codes = (home.explanation?.factors || []).map((f: any) => f.code);
      expect(codes.some((c: string) => String(c).startsWith('goal_') || c === 'session_today')).toBeTruthy();
    }
    // Open plan action — not a Goal page
    const acts = linked[0].actions || [];
    const planAct = acts.find((a: any) => a.label === 'Apri piano' || (a.route || '').includes('/study-plan/'));
    expect(planAct).toBeTruthy();
    expect(acts.every((a: any) => !(a.route || '').includes('/goals'))).toBeTruthy();

    // No Goals section / tab in payload shape
    expect(home.goals).toBeUndefined();
    expect(home.goal_list).toBeUndefined();

    // Refresh — still one representative
    homeRes = await fetch(`${API}/api/home`, { headers: auth(token) });
    home = await homeRes.json();
    surface = collectSurface(home);
    linked = surface.filter((i) => i.goal_id === goalId);
    expect(linked.length).toBe(1);

    // Logout / login persistence
    await fetch(`${API}/api/auth/logout`, { method: 'POST', headers: auth(token) });
    const login = await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const logged = await login.json();
    expect(login.ok && logged.token).toBeTruthy();
    const home2 = await (await fetch(`${API}/api/home`, { headers: auth(logged.token) })).json();
    const linked2 = collectSurface(home2).filter((i) => i.goal_id === goalId);
    expect(linked2.length).toBe(1);
  });

  test('TRAVEL: confirm → next prep + vacation context → no dupes', async () => {
    test.setTimeout(120_000);
    const { token } = await register('travel');
    const start = new Date(Date.now() + 30 * 86400_000).toISOString().slice(0, 10);
    const end = new Date(Date.now() + 40 * 86400_000).toISOString().slice(0, 10);
    await driveToConfirm(token, {
      title: `Andrò in vacanza dal ${start} al ${end} in Calabria`,
      description: 'Vacanza estate — organizzare viaggio in Calabria',
      item_type: 'travel',
    });

    const goalsRes = await fetch(`${API}/api/goals?goal_type=travel`, { headers: auth(token) });
    const goals = ((await goalsRes.json()).goals || []) as any[];
    expect(goals.length).toBeGreaterThanOrEqual(1);
    const goalId = goals[0].id as string;

    const home = await (await fetch(`${API}/api/home`, { headers: auth(token) })).json();
    expect(home.ranking_version).toBe('home-rank-1.2');
    const surface = collectSurface(home);
    const linked = surface.filter((i) => i.goal_id === goalId);
    expect(linked.length).toBe(1);
    expect(linked[0].goal_type).toBe('travel');
    // Soft progress: phase/label OK; precise % not required
    if (linked[0].goal_progress != null) {
      expect(linked[0].goal_progress_label).toBeTruthy();
    }
    expect(home.goals).toBeUndefined();
    const routes = (linked[0].actions || []).map((a: any) => a.route || '');
    expect(routes.every((r: string) => !r.includes('/goals'))).toBeTruthy();
  });
});
