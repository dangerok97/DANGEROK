"""Iteration 9.1 — Diagnostic endpoint tests for
GET /api/connectors/google-calendar/config-status

Runs against the live preview backend (which is what the user will hit).
All assertions are strictly boolean/metadata — the endpoint must NEVER
leak values, secrets, tokens or partial credentials.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_BACKEND_URL")
            or "https://ora-decision-engine.preview.emergentagent.com").rstrip("/")

CONFIG_STATUS_PATH = "/api/connectors/google-calendar/config-status"


# --- helpers ---------------------------------------------------------------

def _read_env_file() -> dict:
    """Parse /app/backend/.env into a dict WITHOUT executing anything."""
    env = {}
    try:
        with open("/app/backend/.env", "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                env[k.strip()] = v
    except FileNotFoundError:
        pass
    return env


@pytest.fixture(scope="module")
def env_vals():
    return _read_env_file()


@pytest.fixture(scope="module")
def auth_token():
    """Register a fresh ephemeral user to obtain a valid bearer token."""
    email = f"cfgstat_{int(time.time())}_{uuid.uuid4().hex[:6]}@ora.app"
    r = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "Passw0rd!", "name": "CfgStat"
    }, timeout=30)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return r.json()["token"]


# --- tests -----------------------------------------------------------------

class TestAuthRequired:
    """(1) The endpoint must reject unauthenticated requests."""

    def test_no_auth_returns_401(self):
        r = requests.get(f"{BASE_URL}{CONFIG_STATUS_PATH}", timeout=30)
        assert r.status_code == 401, f"expected 401, got {r.status_code} {r.text}"

    def test_bad_token_returns_401(self):
        r = requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": "Bearer not-a-real-token"},
            timeout=30,
        )
        assert r.status_code == 401


class TestShapeAndTypes:
    """(2) Authenticated response shape & types."""

    EXPECTED_KEYS = {
        "provider_mode",
        "client_id_configured",
        "client_secret_configured",
        "redirect_uri_configured",
        "token_vault_ready",
        "provider_ready",
        "missing_requirements",
        "environment",
        "connector_id",
        "capability_id",
    }

    def test_200_with_valid_token(self, auth_token):
        r = requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": f"Bearer {auth_token}"}, timeout=30,
        )
        assert r.status_code == 200, r.text

    def test_exact_key_set(self, auth_token):
        r = requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": f"Bearer {auth_token}"}, timeout=30,
        )
        body = r.json()
        assert set(body.keys()) == self.EXPECTED_KEYS, (
            f"unexpected keys: extra={set(body)-self.EXPECTED_KEYS}, "
            f"missing={self.EXPECTED_KEYS-set(body)}"
        )

    def test_types_and_enums(self, auth_token):
        r = requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": f"Bearer {auth_token}"}, timeout=30,
        )
        b = r.json()
        assert b["provider_mode"] in {"real", "fake"}
        for k in ("client_id_configured", "client_secret_configured",
                  "redirect_uri_configured", "token_vault_ready", "provider_ready"):
            assert isinstance(b[k], bool), f"{k} not bool: {type(b[k])}"
        assert isinstance(b["missing_requirements"], list)
        for item in b["missing_requirements"]:
            assert isinstance(item, str)
        assert b["environment"] in {"preview", "production", "test"}
        assert b["connector_id"] == "calendar_google"
        assert b["capability_id"] == "calendar.read"


class TestCurrentEnvState:
    """(3) With the current .env (real mode, no Google creds), the values
    must reflect the missing configuration precisely."""

    def test_env_snapshot(self, auth_token):
        r = requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": f"Bearer {auth_token}"}, timeout=30,
        )
        b = r.json()
        assert b["provider_mode"] == "real", b
        assert b["client_id_configured"] is False
        assert b["client_secret_configured"] is False
        assert b["redirect_uri_configured"] is True
        assert b["token_vault_ready"] is True
        assert b["provider_ready"] is False
        assert "GOOGLE_OAUTH_CLIENT_ID" in b["missing_requirements"]
        assert "GOOGLE_OAUTH_CLIENT_SECRET" in b["missing_requirements"]
        assert b["environment"] == "preview"


class TestNoLeakage:
    """(4) The raw response body MUST NOT contain any value/secret."""

    def _raw(self, token):
        return requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": f"Bearer {token}"}, timeout=30,
        ).text

    def test_no_redirect_uri_leak(self, auth_token, env_vals):
        raw = self._raw(auth_token).lower()
        redirect = (env_vals.get("GOOGLE_OAUTH_REDIRECT_URI") or "").lower()
        if redirect:
            assert redirect not in raw, "redirect URI leaked in response body"
        # Also make sure no URL scheme leaks that could carry the value.
        assert "oauth/callback" not in raw

    def test_no_token_vault_key_leak(self, auth_token, env_vals):
        raw = self._raw(auth_token)
        vault_key = env_vals.get("TOKEN_VAULT_KEY") or ""
        if vault_key:
            # Full key must NEVER appear.
            assert vault_key not in raw
            # Any contiguous 20-char slice of the key must NEVER appear.
            for i in range(0, max(1, len(vault_key) - 20)):
                assert vault_key[i:i + 20] not in raw, (
                    f"vault-key substring of length 20 starting at {i} leaked"
                )

    def test_no_common_secret_labels(self, auth_token):
        raw = self._raw(auth_token).lower()
        for needle in ("client_secret=", "access_token=", "refresh_token=",
                       "authorization: bearer", "bearer "):
            assert needle not in raw, f"forbidden substring leaked: {needle!r}"

    def test_no_partial_credential_leak(self, auth_token, env_vals):
        """If GOOGLE_OAUTH_CLIENT_ID/SECRET were set, no portion should leak.
        Currently both are empty strings; this test is defensive."""
        raw = self._raw(auth_token)
        for key in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"):
            v = env_vals.get(key) or ""
            if len(v) >= 6:
                assert v not in raw
                # any 6-char slice must not leak
                for i in range(0, len(v) - 6 + 1):
                    assert v[i:i + 6] not in raw


class TestNoRegressionOfExistingKeys:
    """(2c) Sanity: no secret-shaped keys accidentally exposed."""

    def test_no_secret_keys_present(self, auth_token):
        r = requests.get(
            f"{BASE_URL}{CONFIG_STATUS_PATH}",
            headers={"Authorization": f"Bearer {auth_token}"}, timeout=30,
        )
        b = r.json()
        # These keys must NEVER be part of the diagnostic payload.
        for forbidden in ("client_id", "client_secret", "redirect_uri",
                          "token_vault_key", "access_token", "refresh_token"):
            assert forbidden not in b, f"forbidden key exposed: {forbidden}"
