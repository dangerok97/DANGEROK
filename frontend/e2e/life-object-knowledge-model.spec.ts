/**
 * Digital Twin Knowledge Model — Casa + mutuo path via API only.
 * No new UX / Home unchanged. Asserts facts|hypotheses|decisions|timeline|knowledge.
 * Confirm / reject / never_ask_again via thin write endpoints (no UI).
 */
import { test, expect } from '@playwright/test';

const API = process.env.EXPO_PUBLIC_BACKEND_URL || process.env.E2E_API_URL || 'http://127.0.0.1:8000';

async function register(prefix: string) {
  const email = `e2e_km_${prefix}_${Date.now()}@example.com`;
  const password = 'TestPass123!';
  const res = await fetch(`${API}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name: `E2E KM ${prefix}` }),
  });
  const data = await res.json();
  if (!res.ok || !data.token) throw new Error(`register failed: ${JSON.stringify(data)}`);
  return { token: data.token as string, user_id: data.user_id as string };
}

function auth(token: string) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

test.describe('Life Object Knowledge Model (API only)', () => {
  test('Casa + mutuo knowledge: facts/hypotheses/decisions/timeline + confirm/reject/never_ask', async () => {
    const { token } = await register('casa');

    const st = await fetch(`${API}/api/life-objects/status`, { headers: auth(token) }).then((r) => r.json());
    expect(st.home_ui_enabled).toBeFalsy();

    const created = await fetch(`${API}/api/life-objects`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        type: 'HOME',
        title: 'Casa Via Dante 8',
        origin: 'e2e',
        confidence: 0.9,
        identity: { address: 'Via Dante 8, Milano' },
        identity_keys: { address_norm: 'via dante 8 milano' },
        state: {
          lender: 'Banca E2E SpA',
          monthly_installment: '800',
          utility_supplier: 'Enel E2E',
        },
        properties: {
          address: 'Via Dante 8, Milano',
          cadastral_data: 'Foglio 1 Particella 2',
          lender: 'Banca E2E SpA',
          monthly_installment: '800',
          supplier: 'Enel E2E',
          utility_type: 'energia',
          document_type: 'mutuo',
        },
      }),
    }).then((r) => r.json());

    const homeId = created.object?.id;
    expect(homeId).toBeTruthy();

    const knowledge = await fetch(`${API}/api/life-objects/${homeId}/knowledge`, {
      headers: auth(token),
    }).then((r) => r.json());
    expect(knowledge.ok).toBeTruthy();
    expect(Array.isArray(knowledge.facts)).toBeTruthy();
    expect(Array.isArray(knowledge.hypotheses)).toBeTruthy();
    expect(Array.isArray(knowledge.decisions)).toBeTruthy();
    expect(Array.isArray(knowledge.memory)).toBeTruthy();
    expect(Array.isArray(knowledge.timeline)).toBeTruthy();
    expect(Array.isArray(knowledge.goals)).toBeTruthy();
    expect(knowledge.rules?.facts_never_deleted).toBeTruthy();
    expect(knowledge.rules?.hypotheses_never_auto_promoted).toBeTruthy();

    const facts = await fetch(`${API}/api/life-objects/${homeId}/facts`, {
      headers: auth(token),
    }).then((r) => r.json());
    expect(facts.ok).toBeTruthy();
    expect(facts.rule).toBe('facts_never_deleted');
    const factTypes = (facts.facts || []).map((f: { type: string }) => f.type);
    expect(
      factTypes.includes('address') ||
        factTypes.includes('lender') ||
        factTypes.includes('utility_supplier'),
    ).toBeTruthy();

    // Propose hypothesis → confirm → Fact
    const hyp = await fetch(`${API}/api/life-objects/${homeId}/hypotheses`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        type: 'utility_supplier',
        value: 'GreenPower E2E',
        confidence: 0.4,
        reason: 'Sospetto cambio fornitore',
        question_to_confirm: 'Il fornitore è GreenPower E2E?',
      }),
    }).then((r) => r.json());
    expect(hyp.ok).toBeTruthy();
    const hypId = hyp.hypothesis?.id;
    expect(hypId).toBeTruthy();

    const confirmed = await fetch(`${API}/api/life-objects/${homeId}/hypotheses/confirm`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ hypothesis_id: hypId, verified_by: 'user' }),
    }).then((r) => r.json());
    expect(confirmed.ok).toBeTruthy();
    expect(confirmed.fact?.value).toBe('GreenPower E2E');
    expect(confirmed.hypothesis?.status).toBe('confirmed');

    // Reject path
    const hyp2 = await fetch(`${API}/api/life-objects/${homeId}/hypotheses`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        type: 'utility_amount',
        value: '9999',
        confidence: 0.3,
        reason: 'Importo sospetto',
      }),
    }).then((r) => r.json());
    const rejected = await fetch(`${API}/api/life-objects/${homeId}/hypotheses/reject`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({ hypothesis_id: hyp2.hypothesis.id, reason: 'errato' }),
    }).then((r) => r.json());
    expect(rejected.ok).toBeTruthy();
    expect(rejected.hypothesis?.status).toBe('rejected');

    // Decision never_ask_again → suppressed on re-propose
    const dec = await fetch(`${API}/api/life-objects/${homeId}/decisions`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        title: 'Valuta surroga mutuo',
        reason: 'Tassi in calo',
        kind: 'suggestion',
      }),
    }).then((r) => r.json());
    expect(dec.ok).toBeTruthy();
    expect(dec.created || dec.decision).toBeTruthy();

    const outcome = await fetch(`${API}/api/life-objects/${homeId}/decisions/outcome`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        decision_id: dec.decision.decision_id,
        outcome: 'never_ask_again',
        user_choice: 'never',
      }),
    }).then((r) => r.json());
    expect(outcome.ok).toBeTruthy();
    expect(outcome.decision?.outcome).toBe('never_ask_again');

    const again = await fetch(`${API}/api/life-objects/${homeId}/decisions`, {
      method: 'POST',
      headers: auth(token),
      body: JSON.stringify({
        title: 'Valuta surroga mutuo',
        reason: 'Tassi in calo',
        kind: 'suggestion',
      }),
    }).then((r) => r.json());
    expect(again.ok).toBeTruthy();
    expect(again.suppressed).toBeTruthy();

    const timeline = await fetch(`${API}/api/life-objects/${homeId}/timeline`, {
      headers: auth(token),
    }).then((r) => r.json());
    expect(timeline.ok).toBeTruthy();
    expect(Array.isArray(timeline.timeline)).toBeTruthy();

    const decisions = await fetch(`${API}/api/life-objects/${homeId}/decisions`, {
      headers: auth(token),
    }).then((r) => r.json());
    expect(decisions.ok).toBeTruthy();

    const feed = await fetch(`${API}/api/life-objects/home-v3-feed`, {
      headers: auth(token),
    }).then((r) => r.json());
    expect(feed.enabled).toBeFalsy();
    expect(feed.cards || []).toEqual([]);
  });
});
