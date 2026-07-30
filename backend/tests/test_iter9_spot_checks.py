"""
Iter9 — spot-check invariants beyond the main suite.
Focuses on the "no plaintext token in instance doc" invariant via
GET /api/connectors/google-calendar/instances/{id} on a real-created
fake-mode instance, plus a couple of extra guards.
"""
import os
os.environ["CALENDAR_PROVIDER_MODE"] = "fake"
# Load real Fernet key from backend/.env if not already set
if not os.environ.get("TOKEN_VAULT_KEY"):
    from pathlib import Path
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TOKEN_VAULT_KEY="):
                os.environ["TOKEN_VAULT_KEY"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

import json
import uuid
import pytest
from fastapi.testclient import TestClient

# Import after env is set so the provider factory picks up 'fake'.
from server import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def token(client):
    email = f"iter9spot_{uuid.uuid4().hex[:8]}@ora.app"
    r = client.post("/api/auth/register",
                    json={"email": email, "password": "Passw0rd!123", "name": "Spot"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def _create_instance(client, tok, account_email="a@example.com"):
    # 1) oauth/start
    r = client.post("/api/connectors/google-calendar/oauth/start",
                    headers=_h(tok), json={})
    assert r.status_code == 200, r.text
    state = r.json()["state"]
    # 2) fake callback (only enabled in fake mode)
    r = client.post("/api/connectors/google-calendar/oauth/callback-fake",
                    headers=_h(tok),
                    json={"state": state, "code": "fake-code",
                          "fake_account": {"email": account_email}})
    assert r.status_code == 200, r.text
    return r.json()["instance"]


def test_instance_doc_has_no_plaintext_token(client, token):
    """Invariant (a): no plaintext tokens anywhere in the instance doc."""
    instance = _create_instance(client, token, "no-token@example.com")
    instance_id = instance["id"]

    r = client.get(f"/api/connectors/google-calendar/instances/{instance_id}",
                   headers=_h(token))
    assert r.status_code == 200, r.text
    body = r.json()
    doc = body.get("instance", body)

    dumped = json.dumps(doc)
    # Must contain a secret reference…
    assert "sv_" in dumped or "secret_reference" in doc or any(
        isinstance(v, str) and v.startswith("sv_") for v in _walk_values(doc)
    ), f"no secret_reference (sv_...) found in doc: {doc}"

    # …and must NOT contain plaintext token/secret keys anywhere.
    forbidden = ("access_token", "refresh_token", "client_secret")
    for k in forbidden:
        assert k not in dumped, f"forbidden field '{k}' leaked in instance doc: {doc}"


def test_provider_not_configured_shape_in_real_mode(client, token, monkeypatch):
    """Invariant (c): real mode + missing creds → 503 provider_not_configured."""
    monkeypatch.setenv("CALENDAR_PROVIDER_MODE", "real")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)

    r = client.post("/api/connectors/google-calendar/oauth/start",
                    headers=_h(token), json={})
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail.get("error") == "provider_not_configured"
    assert "message" in detail


def test_cross_user_isolation_returns_404(client, token):
    """Invariant (d): user B calling A's instance route → 404."""
    instance = _create_instance(client, token, "iso@example.com")
    instance_id = instance["id"]

    # Create user B
    r = client.post("/api/auth/register",
                    json={"email": f"iter9spotB_{uuid.uuid4().hex[:8]}@ora.app",
                          "password": "Passw0rd!123", "name": "B"})
    assert r.status_code == 200
    tok_b = r.json()["token"]

    r = client.get(f"/api/connectors/google-calendar/instances/{instance_id}",
                   headers=_h(tok_b))
    assert r.status_code == 404, f"expected 404 (not 403), got {r.status_code}: {r.text}"


def _walk_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_values(v)
    else:
        yield obj
