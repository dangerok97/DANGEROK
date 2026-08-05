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
  return { token: data.token as string };
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
  test('Study confirm → Home has one goal-linked representative', async () => {
    test.setTimeout(120_000);
    const { token } = await register('study');
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

    const homeRes = await fetch(`${API}/api/home`, { headers: auth(token) });
    expect(homeRes.ok).toBeTruthy();
    const home = await homeRes.json();
    expect(home.ranking_version).toBe('home-rank-1.1');

    const surface = collectSurface(home);
    const linked = surface.filter((i) => i.goal_id === goalId);
    expect(linked.length).toBe(1);
    expect(linked[0].goal_title).toBeTruthy();
    expect(String(linked[0].goal_title).toLowerCase()).toMatch(/psicolog/);

    // No Goals section / tab in payload shape
    expect(home.goals).toBeUndefined();
    expect(home.goal_list).toBeUndefined();
  });

  test('Travel confirm → Home collapses travel+project under one goal_id', async () => {
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
    const surface = collectSurface(home);
    const linked = surface.filter((i) => i.goal_id === goalId);
    expect(linked.length).toBe(1);
    expect(home.goals).toBeUndefined();
  });
});
