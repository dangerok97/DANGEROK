/**
 * Proactive Engine E2E — Study confirm → skip session → Home ORA TI CONSIGLIA → Accept
 * verifies recovery session / plan next_recovery_session_id.
 */
import { test, expect } from '@playwright/test';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';

async function register(prefix: string) {
  const email = `e2e_proactive_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E Proactive ${prefix}` }),
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
    const examDate = new Date(Date.now() + 14 * 86400_000).toISOString().slice(0, 10);
    return fetch(`${API}/api/action-engine/sessions/${sessionId}/answer`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ text: examDate }),
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

test.describe('Proactive Engine foundation', () => {
  test('skip session → Home ORA TI CONSIGLIA → Accept creates recovery', async () => {
    test.setTimeout(120_000);
    const { token } = await register('study');

    await driveToConfirm(token, {
      title: 'Preparazione esame di Psicologia',
      description: "Devo preparare l'esame di Psicologia entro due settimane",
      item_type: 'study',
    });

    const plansRes = await fetch(`${API}/api/study-plans`, { headers: auth(token) });
    expect(plansRes.ok).toBeTruthy();
    const plansBody = await plansRes.json();
    const plans = plansBody.items || plansBody.plans || [];
    expect(plans.length).toBeGreaterThanOrEqual(1);
    const planId = plans[0].id as string;

    const sessRes = await fetch(`${API}/api/study-plans/${planId}/sessions`, {
      headers: auth(token),
    });
    expect(sessRes.ok).toBeTruthy();
    const sessions = ((await sessRes.json()).sessions || []) as any[];
    const target = sessions.find((s) => s.status === 'planned') || sessions[0];
    expect(target?.id).toBeTruthy();

    const skipRes = await fetch(
      `${API}/api/study-plans/${planId}/sessions/${target.id}/action`,
      {
        method: 'POST',
        headers: auth(token),
        body: JSON.stringify({ action: 'skip' }),
      },
    );
    expect(skipRes.ok).toBeTruthy();

    const regen = await fetch(`${API}/api/suggestions/regenerate`, {
      method: 'POST',
      headers: auth(token),
    });
    expect(regen.ok).toBeTruthy();
    const regenBody = await regen.json();
    expect(regenBody.enabled).toBeTruthy();
    expect(regenBody.created).toBeGreaterThanOrEqual(1);

    const homeRes = await fetch(`${API}/api/home`, { headers: auth(token) });
    expect(homeRes.ok).toBeTruthy();
    const home = await homeRes.json();
    expect(home).toHaveProperty('ora_ti_consiglia');
    const list = home.ora_ti_consiglia || [];
    expect(list.length).toBeGreaterThanOrEqual(1);
    expect(list.length).toBeLessThanOrEqual(3);

    const sug = list.find((s: any) => s.type === 'study') || list[0];
    expect(sug.title).toBeTruthy();

    const acceptRes = await fetch(`${API}/api/suggestions/${sug.id}/accept`, {
      method: 'POST',
      headers: auth(token),
    });
    expect(acceptRes.ok).toBeTruthy();
    const accepted = await acceptRes.json();
    expect(accepted.ok).toBeTruthy();
    expect(accepted.status).toBe('accepted');
    expect(accepted.result?.effect).toBe('recovery_session_created');
    expect(accepted.result?.session_id).toBeTruthy();

    const planCheck = await fetch(`${API}/api/study-plans/${planId}`, {
      headers: auth(token),
    });
    expect(planCheck.ok).toBeTruthy();
    const planDoc = (await planCheck.json()).plan || {};
    expect(
      planDoc.next_recovery_session_id === accepted.result.session_id ||
        (planDoc.sessions || []).some((s: any) => s.id === accepted.result.session_id),
    ).toBeTruthy();
  });

  test('stub types never invent on regenerate', async () => {
    const { token } = await register('stub');
    const regen = await fetch(`${API}/api/suggestions/regenerate`, {
      method: 'POST',
      headers: auth(token),
    });
    expect(regen.ok).toBeTruthy();
    const body = await regen.json();
    for (const s of body.suggestions || []) {
      expect(['emails', 'finance', 'weather', 'health']).not.toContain(s.type);
    }
    const home = await (await fetch(`${API}/api/home`, { headers: auth(token) })).json();
    expect(Array.isArray(home.ora_ti_consiglia)).toBeTruthy();
    for (const s of home.ora_ti_consiglia || []) {
      expect(['emails', 'finance', 'weather', 'health']).not.toContain(s.type);
    }
  });
});
