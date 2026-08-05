/**
 * Goal Engine Foundation — shadow Goals after Study/Travel confirm.
 * No new Goal screens / Home UX. Asserts Goals exist via API only.
 */
import { test, expect } from '@playwright/test';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';

async function register(prefix: string) {
  const email = `e2e_goal_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E Goal ${prefix}` }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { token: data.token as string, user_id: data.user_id as string, email };
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

/** Answer using option_id when chips exist (matches AE chip contract). */
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

  // Prep step: prefer skip when available (avoid multi-select luggage path)
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

  // Confirm chip may already have completed the session (creates Goal on confirm).
  // Only call confirm endpoint if still awaiting confirmation.
  const after = await getSession(token, sessionId);
  let cj: Record<string, unknown> = { ok: true, already: true, session: after };
  if (after.status !== 'completed' && after.status !== 'cancelled') {
    const conf = await fetch(`${API}/api/action-engine/sessions/${sessionId}/confirm`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({}),
    });
    cj = await conf.json();
  }
  return { sessionId, confirm: cj };
}

test.describe('Goal Engine shadow (no UX)', () => {
  test('Study confirm → Goal via API; no Goal screen required', async () => {
    test.setTimeout(120_000);
    const { token } = await register('study');
    await driveToConfirm(token, {
      title: 'Preparazione esame di Psicologia',
      description: "Devo preparare l'esame di Psicologia entro tre settimane",
      item_type: 'study',
    });

    const goalsRes = await fetch(`${API}/api/goals?goal_type=study`, {
      headers: auth(token),
    });
    expect(goalsRes.ok).toBeTruthy();
    const goalsBody = await goalsRes.json();
    const goals = goalsBody.goals || [];
    expect(goals.length).toBeGreaterThanOrEqual(1);
    const g = goals[0];
    expect(g.goal_type).toBe('study');
    expect(g.study_plan_id).toBeTruthy();
    expect(String(g.title).toLowerCase()).toMatch(/psicolog/);
  });

  test('Travel confirm → Goal via API; Home UX unchanged', async () => {
    test.setTimeout(120_000);
    const { token } = await register('travel');
    const start = new Date(Date.now() + 30 * 86400_000).toISOString().slice(0, 10);
    const end = new Date(Date.now() + 40 * 86400_000).toISOString().slice(0, 10);
    await driveToConfirm(token, {
      title: `Andrò in vacanza dal ${start} al ${end} in Calabria`,
      description: 'Vacanza estate — organizzare viaggio in Calabria',
      item_type: 'travel',
    });

    const goalsRes = await fetch(`${API}/api/goals?goal_type=travel`, {
      headers: auth(token),
    });
    expect(goalsRes.ok).toBeTruthy();
    const goalsBody = await goalsRes.json();
    const goals = goalsBody.goals || [];
    expect(goals.length).toBeGreaterThanOrEqual(1);
    const g = goals[0];
    expect(g.goal_type).toBe('travel');
    expect(g.travel_project_id).toBeTruthy();
    expect(String(g.title).toLowerCase()).toMatch(/calabria|vacanza/);
  });
});
