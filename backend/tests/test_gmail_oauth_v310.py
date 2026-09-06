"""
V3.10 Sprint 3 — connecting a mailbox for real.

    ONE CLIENT, ONE STATE STORE, ONE VAULT — TWO CONSENTS.
    A CALLBACK WITHOUT A VALID STATE CREATES NOTHING.

The OAuth half. Nothing here talks to Google: the token exchange, the
userinfo call and the revoke are replaced, and what is checked is everything
around them — which scopes are asked for, what a state is worth, where the
tokens land, what the instance says afterwards, and that the calendar
connection is untouched by any of it.

The tests that matter most are the ones about a state being spent: it is the
only thing binding an unauthenticated callback to the person who started, so
a state that can be replayed, aged, or spent at the wrong flow's callback is
the whole flow's security gone.
"""

from __future__ import annotations

import ast
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)
QA = "qa.mailbox@example.com"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("connector_instances", "google_oauth_sessions",
                 "permission_consents", "permission_audit", "ingestion_events"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class Permissions:
    """What this flow actually asks of the permissions service."""

    class _Audit:
        def __init__(self):
            self.rows = []

        async def log(self, **kw):
            self.rows.append(kw)

    def __init__(self):
        self.audit = self._Audit()
        self.granted = []
        self.revoked = []

    async def check_access(self, **kw):
        return True

    async def grant(self, **kw):
        self.granted.append(kw)
        return {"ok": True}

    async def revoke(self, **kw):
        self.revoked.append(kw)
        return {"ok": True}


class Vault:
    """A vault that remembers, so a test can ask what was put in it."""

    def __init__(self):
        self.stored = {}
        self.revoked = []

    async def put(self, *, user_id, purpose, payload, metadata=None):
        ref = f"vault_{uuid.uuid4().hex[:8]}"
        self.stored[ref] = {"user_id": user_id, "purpose": purpose,
                            "payload": dict(payload), "metadata": metadata}
        return ref

    async def get(self, ref, *, user_id):
        return dict(self.stored[ref]["payload"])

    async def rotate(self, ref, *, payload):
        self.stored[ref]["payload"] = dict(payload)
        return ref

    async def revoke(self, ref):
        self.revoked.append(ref)
        self.stored.pop(ref, None)
        return True


def _service(db, *, permissions=None, vault=None):
    from connectors.gmail.service import GmailReadService

    return GmailReadService(
        db=db, permissions=permissions or Permissions(), vault=vault or Vault(),
        provider=object(),
    )


def _google(monkeypatch, *, scope="https://www.googleapis.com/auth/gmail.readonly openid email"):
    """Google's two answers, replaced. Nothing here reaches the network."""
    calls = {"exchange": [], "userinfo": 0, "revoked": []}

    async def exchange(*, code, code_verifier, redirect_uri=None):
        calls["exchange"].append({"code": code, "redirect_uri": redirect_uri})
        return {"access_token": "at-live", "refresh_token": "rt-live",
                "token_type": "Bearer", "expires_in": 3600, "scope": scope}

    async def userinfo(access_token):
        calls["userinfo"] += 1
        return {"sub": "google-sub-1", "email": QA, "name": "QA"}

    async def revoke(token):
        calls["revoked"].append(token)
        return True

    import connectors.gmail.service as svc

    monkeypatch.setattr(svc, "exchange_code_for_tokens", exchange)
    monkeypatch.setattr(svc, "fetch_userinfo", userinfo)
    monkeypatch.setattr(svc, "revoke_token", revoke)
    return calls


def _config(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/api/connectors/google-calendar/oauth/callback",
    )
    monkeypatch.delenv("GMAIL_OAUTH_REDIRECT_URI", raising=False)
    monkeypatch.delenv("GMAIL_OAUTH_REDIRECT_URIS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")


# ---------------------------------------------------------------------------
# Starting
# ---------------------------------------------------------------------------

def test_the_authorize_url_asks_for_reading_and_nothing_else(monkeypatch):
    """
    §3: `gmail.readonly`, and no verb that could change anybody's mailbox.

    This is the single most consequential line in the sprint: whatever is in
    that scope parameter is what a person is agreeing to, and it is the only
    thing standing between "ORA reads my mail" and "ORA can send mail as me".
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            _config(monkeypatch)
            out = await _service(db).start_oauth(
                user_id=uid, request_base="http://localhost:8000",
            )
            scopes = parse_qs(urlparse(out["authorize_url"]).query)["scope"][0].split()

            assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
            for forbidden in ("gmail.send", "gmail.modify", "gmail.compose",
                              "gmail.insert", "gmail.settings", "mail.google.com"):
                assert not any(forbidden in s for s in scopes), (
                    f"il consenso chiede {forbidden}"
                )
            # And nothing about the calendar: a mailbox is its own question.
            assert not any("calendar" in s for s in scopes)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_authorize_url_carries_pkce_and_a_registered_callback(monkeypatch):
    """§1/§7: the calendar's protections, unchanged, because they are the same code."""
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            _config(monkeypatch)
            out = await _service(db).start_oauth(
                user_id=uid, request_base="http://127.0.0.1:8000",
            )
            query = parse_qs(urlparse(out["authorize_url"]).query)

            assert query["code_challenge_method"] == ["S256"]
            assert query["code_challenge"][0]
            assert query["access_type"] == ["offline"]
            # Back to the host they came from, or Google refuses the exchange
            # after the person has already said yes.
            assert query["redirect_uri"] == [
                "http://127.0.0.1:8000/api/connectors/gmail/oauth/callback"
            ]
            # The state is owner-bound and stored, not just returned.
            row = await db.google_oauth_sessions.find_one(
                {"state": out["state"]}, {"_id": 0}
            )
            assert row["user_id"] == uid
            assert row["flow"] == "mail_gmail"
            assert row["consumed"] is False
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_gmail_callback_is_derived_from_the_calendar_one(monkeypatch):
    """
    §2: the pair to register with Google is a function of what is registered.

    Typing the second URI by hand is how the two drift, and the way that
    failure appears is `redirect_uri_mismatch` in somebody's browser after
    they have already consented.
    """
    from connectors.gmail.oauth import gmail_redirect_uris

    _config(monkeypatch)
    assert gmail_redirect_uris() == [
        "http://localhost:8000/api/connectors/gmail/oauth/callback",
        "http://127.0.0.1:8000/api/connectors/gmail/oauth/callback",
    ]

    # And an explicit setting overrides the derivation.
    monkeypatch.setenv(
        "GMAIL_OAUTH_REDIRECT_URI", "https://ora.example/api/connectors/gmail/oauth/callback",
    )
    assert gmail_redirect_uris()[0] == (
        "https://ora.example/api/connectors/gmail/oauth/callback"
    )


# ---------------------------------------------------------------------------
# Coming back
# ---------------------------------------------------------------------------

def test_a_completed_flow_makes_a_real_mailbox_instance(monkeypatch):
    """
    §5: an instance the connector can actually use, and consents to match.

    Owner-bound, the real granted scopes, the account it belongs to, and a
    reference to the vault — never a token.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            _config(monkeypatch)
            _google(monkeypatch)
            permissions, vault = Permissions(), Vault()
            service = _service(db, permissions=permissions, vault=vault)

            started = await service.start_oauth(
                user_id=uid, request_base="http://localhost:8000",
            )
            result = await service.handle_oauth_callback(
                state=started["state"], code="auth-code",
            )
            instance = result["instance"]

            assert instance["connector_id"] == "mail_gmail"
            assert instance["user_id"] == uid
            assert instance["status"] == "connected"
            assert instance["metadata"]["account_email"] == QA
            assert "gmail.readonly" in " ".join(instance["authorized_scopes"])
            assert instance["secret_reference"] in vault.stored

            granted = {g["capability_id"] for g in permissions.granted}
            assert granted == {"mail.metadata", "mail.read"}
            assert all(
                g["connector_instance_id"] == instance["id"]
                for g in permissions.granted
            ), "un consenso non legato a questa istanza"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_tokens_are_in_the_vault_and_nowhere_else(monkeypatch):
    """
    §6: not in the instance, not in the database, not in the audit trail.

    A refresh token in an ordinary collection is a permanent key to somebody's
    mailbox sitting in every backup.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            _config(monkeypatch)
            _google(monkeypatch)
            permissions, vault = Permissions(), Vault()
            service = _service(db, permissions=permissions, vault=vault)

            started = await service.start_oauth(user_id=uid)
            await service.handle_oauth_callback(
                state=started["state"], code="auth-code",
            )

            for collection in ("connector_instances", "google_oauth_sessions",
                               "permission_audit"):
                rows = await db[collection].find(
                    {"user_id": uid}, {"_id": 0}
                ).to_list(20)
                blob = str(rows)
                for secret in ("at-live", "rt-live"):
                    assert secret not in blob, f"un token è finito in {collection}"

            assert str(permissions.audit.rows).count("at-live") == 0
            stored = next(iter(vault.stored.values()))["payload"]
            assert stored["access_token"] == "at-live"
            assert stored["refresh_token"] == "rt-live"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_state_cannot_be_spent_twice(monkeypatch):
    """§7: one-time. A replayed callback creates nothing."""
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.oauth import OAuthStateInvalid

            _config(monkeypatch)
            _google(monkeypatch)
            service = _service(db)
            started = await service.start_oauth(user_id=uid)
            await service.handle_oauth_callback(state=started["state"], code="c1")

            with pytest.raises(OAuthStateInvalid):
                await service.handle_oauth_callback(state=started["state"], code="c1")

            assert await db.connector_instances.count_documents(
                {"user_id": uid, "connector_id": "mail_gmail"}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_unknown_or_expired_state_is_refused(monkeypatch):
    """§7: fail closed, both ways."""
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.oauth import OAuthStateInvalid

            _config(monkeypatch)
            _google(monkeypatch)
            service = _service(db)

            with pytest.raises(OAuthStateInvalid):
                await service.handle_oauth_callback(state="mai-esistito", code="c")

            started = await service.start_oauth(user_id=uid)
            await db.google_oauth_sessions.update_one(
                {"state": started["state"]},
                {"$set": {"expires_at": (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat()}},
            )
            with pytest.raises(OAuthStateInvalid):
                await service.handle_oauth_callback(
                    state=started["state"], code="c",
                )
            assert await db.connector_instances.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_calendar_state_cannot_connect_a_mailbox(monkeypatch):
    """
    §4/§7: the two flows share a store and must not share a state.

    They ask Google for different permissions. Honouring a calendar state at
    the mailbox callback would build a connection the person never agreed to,
    from an authorisation they gave for something else.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.oauth import (
                OAuthStateInvalid, OAuthStateStore,
            )

            _config(monkeypatch)
            _google(monkeypatch)
            calendar_state = await OAuthStateStore(db).create(
                user_id=uid,
                redirect_uri="http://localhost:8000/api/connectors/"
                             "google-calendar/oauth/callback",
            )

            with pytest.raises(OAuthStateInvalid):
                await _service(db).handle_oauth_callback(
                    state=calendar_state["state"], code="c",
                )
            assert await db.connector_instances.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_mailbox_state_cannot_connect_a_calendar(monkeypatch):
    """§4: and the other direction, which is the one that grants more."""
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.oauth import (
                OAuthStateInvalid, OAuthStateStore,
            )

            _config(monkeypatch)
            _google(monkeypatch)
            started = await _service(db).start_oauth(user_id=uid)

            with pytest.raises(OAuthStateInvalid):
                await OAuthStateStore(db).consume(
                    state=started["state"], expect_flow="calendar_google",
                )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_state_belongs_to_the_person_who_started(monkeypatch):
    """
    §7: the callback carries no credentials, so the state carries the owner.

    Whatever else happens, the instance is built for the user recorded when
    the flow began — never for whoever's browser arrives at the callback.
    """
    async def body():
        client, db = await _db()
        mine = f"g_{uuid.uuid4().hex[:8]}"
        theirs = f"g_{uuid.uuid4().hex[:8]}"
        try:
            _config(monkeypatch)
            _google(monkeypatch)
            service = _service(db)
            started = await service.start_oauth(user_id=mine)
            result = await service.handle_oauth_callback(
                state=started["state"], code="c",
            )

            assert result["instance"]["user_id"] == mine
            assert await db.connector_instances.count_documents(
                {"user_id": theirs}
            ) == 0
        finally:
            await _clean(db, mine)
            await _clean(db, theirs)
            client.close()

    _run(body())


def test_a_consent_without_gmail_is_refused_rather_than_half_connected(monkeypatch):
    """
    §5: a mailbox that cannot be read must not look connected.

    Google returns the union of granted scopes; somebody who unticks the
    mailbox box reaches the callback with a valid code and no permission to
    read anything. Building an instance then would produce a source that
    reports nothing, forever, while saying it is fine.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.oauth import OAuthConfigError

            _config(monkeypatch)
            _google(monkeypatch, scope="openid email profile")
            service = _service(db)
            started = await service.start_oauth(user_id=uid)

            with pytest.raises(OAuthConfigError):
                await service.handle_oauth_callback(
                    state=started["state"], code="c",
                )
            assert await db.connector_instances.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Living with it
# ---------------------------------------------------------------------------

def test_disconnecting_stops_the_reading_and_keeps_what_was_learned(monkeypatch):
    """
    §9: the token goes back, the consents go, the source says disconnected.

        DISCONNECTING IS NOT FORGETTING.

    What is deliberately untouched is everything already learned. An
    observation that went through governance is part of what ORA knows about
    this person's life, and unplugging a mailbox is not a request to forget
    their life.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connected.service import ConnectedLifeService

            _config(monkeypatch)
            calls = _google(monkeypatch)
            permissions, vault = Permissions(), Vault()
            service = _service(db, permissions=permissions, vault=vault)
            started = await service.start_oauth(user_id=uid)
            instance = (await service.handle_oauth_callback(
                state=started["state"], code="c",
            ))["instance"]

            await db.memories.insert_one({
                "id": "mem_1", "user_id": uid, "status": "known",
                "summary": "Lo studio ha cambiato indirizzo.",
                "provenance": ["connected_signal:sig_1"],
            })

            out = await service.revoke(user_id=uid, instance_id=instance["id"])

            assert out["ok"] is True
            assert calls["revoked"] == ["rt-live"], "il token non è stato revocato"
            assert vault.revoked == [instance["secret_reference"]]
            assert {r["capability_id"] for r in permissions.revoked} == {
                "mail.metadata", "mail.read",
            }

            source = next(
                (s for s in await ConnectedLifeService(db).sources.list(uid)
                 if s.source_type == "email"), None,
            )
            assert source is not None
            assert source.status == "disconnected"
            assert source.is_readable is False

            assert await db.memories.count_documents({"user_id": uid}) == 1, (
                "scollegare una casella ha cancellato quello che ORA aveva imparato"
            )
        finally:
            await db.memories.delete_many({"user_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_disconnected_mailbox_is_not_read_again(monkeypatch):
    """§9: no sync, and therefore no new signal, after disconnecting."""
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connected.service import ConnectedLifeService

            _config(monkeypatch)
            _google(monkeypatch)
            service = _service(db)
            started = await service.start_oauth(user_id=uid)
            instance = (await service.handle_oauth_callback(
                state=started["state"], code="c",
            ))["instance"]
            await service.revoke(user_id=uid, instance_id=instance["id"])

            out = await ConnectedLifeService(db).sync(uid, instance["id"])
            assert out["ok"] is False
            assert out["reason"] == "not_connected"
            assert await db.connected_signals.count_documents({"owner_id": uid}) == 0
        finally:
            await db.connected_signals.delete_many({"owner_id": uid})
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_expired_token_is_refreshed_through_the_path_that_already_existed(monkeypatch):
    """
    §6: one refresh implementation, and the rotated token goes back to the vault.

    A second refresh path is a second place for a token to be lost, and the
    way that failure shows up is a mailbox that quietly stops being read.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            import connectors.gmail.service as svc

            _config(monkeypatch)
            refreshed = {"n": 0}

            async def refresh(*, refresh_token):
                refreshed["n"] += 1
                assert refresh_token == "rt-live"
                return {"access_token": "at-new", "expires_in": 3600}

            monkeypatch.setattr(
                "connectors.google_calendar.oauth.refresh_access_token", refresh,
            )
            vault = Vault()
            ref = await vault.put(
                user_id=uid, purpose="mail_gmail:oauth",
                payload={"access_token": "at-old", "refresh_token": "rt-live",
                         "expires_at": "2000-01-01T00:00:00+00:00"},
            )
            service = _service(db, vault=vault)
            token = await service._access_token(
                user_id=uid, instance={"secret_reference": ref},
            )

            assert token == "at-new"
            assert refreshed["n"] == 1
            assert vault.stored[ref]["payload"]["access_token"] == "at-new"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_calendar_flow_is_untouched(monkeypatch):
    """
    §1: nothing about connecting a mailbox changed connecting a calendar.

    The shared helpers gained parameters; the calendar's own call sites did
    not change what they ask for. Checked rather than assumed, because "I only
    added an optional argument" is exactly how a working OAuth flow breaks.
    """
    from connectors.google_calendar.oauth import (
        allowed_oauth_redirect_uris, build_authorize_url,
    )
    from connectors.google_calendar.scopes import GOOGLE_CALENDAR_SCOPES

    _config(monkeypatch)
    assert allowed_oauth_redirect_uris() == [
        "http://localhost:8000/api/connectors/google-calendar/oauth/callback",
        "http://127.0.0.1:8000/api/connectors/google-calendar/oauth/callback",
    ]
    # No scopes argument → still the calendar's own scopes, unchanged.
    url = build_authorize_url(state="s", code_challenge="c")
    scopes = parse_qs(urlparse(url).query)["scope"][0].split()
    assert scopes == list(GOOGLE_CALENDAR_SCOPES)
    assert not any("gmail" in s for s in scopes), (
        "il consenso del calendario ha iniziato a chiedere la posta"
    )


def test_the_calendar_flow_still_connects_end_to_end(monkeypatch):
    """§1: and the whole calendar callback still builds a calendar instance."""
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.google_calendar.service import GoogleCalendarService

            _config(monkeypatch)
            monkeypatch.setenv("CALENDAR_PROVIDER_MODE", "fake")
            service = GoogleCalendarService(
                db=db, permissions=Permissions(), ingestion=None, vault=Vault(),
                provider=object(),
            )
            started = await service.start_oauth(user_id=uid)
            result = await service.handle_oauth_callback(
                state=started["state"], code="fake-code",
                fake_account={"sub": "cal-sub", "email": QA},
            )
            assert result["instance"]["connector_id"] == "calendar_google"
            assert result["instance"]["user_id"] == uid
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_no_write_scope_exists_anywhere_in_the_mail_connector():
    """
    §3: the strings that would let this application send mail do not exist.

    A behavioural test proves what today's code asks for. This proves that a
    future edit cannot ask for more without deleting a test that says why.
    """
    for name in ("scopes.py", "oauth.py", "service.py", "provider.py", "router.py"):
        source = (HERE / "connectors/gmail" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        for forbidden in ("gmail.send", "gmail.modify", "gmail.compose",
                          "gmail.insert", "gmail.settings", "mail.google.com"):
            assert not any(forbidden in text for text in literals), (
                f"connectors/gmail/{name} nomina lo scope {forbidden}"
            )


def test_the_mail_connector_builds_no_second_oauth_framework():
    """
    §1: one state store, one exchange, one refresh, one vault.

    The Gmail package must reach for the calendar's OAuth module rather than
    carry its own — a second implementation of PKCE or of state consumption
    is a second place for an OAuth mistake to live, and those are the
    expensive kind.
    """
    source = (HERE / "connectors/gmail/service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        (n.module or "") for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
    }
    assert "connectors.google_calendar.oauth" in imported

    whole = source + (HERE / "connectors/gmail/oauth.py").read_text(encoding="utf-8")
    for reimplemented in ("code_challenge = ", "secrets.token_urlsafe",
                          "hashlib.sha256", "GOOGLE_TOKEN_URL"):
        assert reimplemented not in whole, (
            f"il connettore Gmail rifà l'OAuth da solo: {reimplemented}"
        )


# ---------------------------------------------------------------------------
# What the connections screen is shown
# ---------------------------------------------------------------------------

def test_a_finished_reading_records_when_the_mailbox_was_last_read(monkeypatch):
    """
    The one fact the screen shows about a mailbox has to be true.

    `last_sync_at` was never written by a mail sync, so «Connessioni e
    servizi» would have said "Mai sincronizzato" under a mailbox that had
    just been read — a screen contradicting the thing it is describing.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.gmail.provider import FakeGmailProvider
            from connectors.gmail.service import GmailReadService

            mailbox = FakeGmailProvider()
            mailbox.add("m1", thread_id="t1", headers={"Subject": "Ciao"})
            now = datetime.now(timezone.utc).isoformat()
            instance_id = f"inst_{uuid.uuid4().hex[:8]}"
            await db.connector_instances.insert_one({
                "id": instance_id, "user_id": uid, "connector_id": "mail_gmail",
                "status": "connected", "secret_reference": "ref",
                "metadata": {"account_email": QA}, "cursor": {},
                "created_at": now, "updated_at": now, "last_sync_at": None,
            })
            vault = Vault()
            vault.stored["ref"] = {"user_id": uid, "purpose": "x", "payload": {
                "access_token": "at", "refresh_token": "rt",
                "expires_at": "2999-01-01T00:00:00+00:00"}, "metadata": {}}

            service = GmailReadService(
                db=db, permissions=Permissions(), vault=vault, provider=mailbox,
            )
            await service.sync(user_id=uid, instance_id=instance_id)

            found = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0}
            )
            assert found["last_sync_at"], "una lettura riuscita non è stata annotata"
            assert found["cursor"]["history_id"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_disconnected_mailbox_is_still_listed_so_the_screen_can_say_so(monkeypatch):
    """
    Disconnecting must leave something to look at.

    A connection that vanishes when you remove it never confirms to anybody
    that it was removed — and the person is left wondering whether ORA is
    still reading their mail.
    """
    async def body():
        client, db = await _db()
        uid = f"g_{uuid.uuid4().hex[:8]}"
        try:
            _config(monkeypatch)
            _google(monkeypatch)
            service = _service(db)
            started = await service.start_oauth(user_id=uid)
            instance = (await service.handle_oauth_callback(
                state=started["state"], code="c",
            ))["instance"]
            await service.revoke(user_id=uid, instance_id=instance["id"])

            listed = await service.list_instances(uid)
            assert len(listed) == 1
            assert listed[0]["status"] == "revoked"
            # Which is what the screen turns into «Non collegato».
            assert listed[0]["display_label"] == QA
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
