"""Web Push reaches the iPhone Home Screen app without an App Store build.

Production 23/10/2026: zero registered push devices — ORA is used from
Safari, and the only channel was Expo (native builds only). "Ti avviso io"
could never arrive with the app closed. These tests pin the protocol pieces
(RFC 8291 encryption, RFC 8292 VAPID), the subscription allowlist, and the
way one delivery decision reaches every enabled channel.
"""
import asyncio
import base64
import json
import os
import struct

import jwt as pyjwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ambient import webpush
from ambient.webpush import (
    CompositeNotificationProvider, WebPushNotificationProvider, encrypt,
    is_web_push_token, parse_subscription, subscription_token,
)


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def raw_public(key) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


UA_KEY = ec.generate_private_key(ec.SECP256R1())
AUTH = os.urandom(16)
APPLE = {
    "endpoint": "https://web.push.apple.com/QGuQyavXutnMH9sAmmBDWDEH/device-token",
    "keys": {"p256dh": b64(raw_public(UA_KEY)), "auth": b64(AUTH)},
}


def set_vapid(monkeypatch):
    key = ec.generate_private_key(ec.SECP256R1())
    scalar = key.private_numbers().private_value.to_bytes(32, "big")
    monkeypatch.setenv("WEBPUSH_VAPID_PRIVATE_KEY", b64(scalar))
    return key


def decrypt(body: bytes) -> bytes:
    """The browser side of RFC 8291, written independently of the sender."""
    salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
    as_public = body[21:21 + idlen]
    ciphertext = body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public)
    shared = UA_KEY.exchange(ec.ECDH(), peer)
    ua_public = raw_public(UA_KEY)
    ikm = webpush._hkdf(AUTH, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = webpush._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = webpush._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    plain = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert plain.endswith(b"\x02")
    return plain[:-1]


def test_encryption_round_trips_like_a_browser_would_read_it():
    message = json.dumps({"title": "Panni", "body": "Pronti tra le 19:10 e le 19:40"}).encode()
    body = encrypt(message, APPLE["keys"]["p256dh"], APPLE["keys"]["auth"])
    assert decrypt(body) == message
    # A fresh salt and server key every time: two sends never look alike.
    assert encrypt(message, APPLE["keys"]["p256dh"], APPLE["keys"]["auth"])[:16] != body[:16]


def test_hkdf_matches_rfc5869_test_case_1():
    ikm = bytes.fromhex("0b" * 22)
    salt = bytes.fromhex("000102030405060708090a0b0c")
    info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
    okm = webpush._hkdf(salt, ikm, info, 32)
    assert okm.hex() == "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf"


def test_vapid_header_is_a_valid_es256_token_for_the_push_origin(monkeypatch):
    key = set_vapid(monkeypatch)
    monkeypatch.setenv("WEBPUSH_SUBJECT", "https://ora.example")
    header = webpush.vapid_authorization(APPLE["endpoint"], now=1_800_000_000)
    token = header.split("t=", 1)[1].split(",", 1)[0]
    k = header.split("k=", 1)[1]
    assert k == webpush.vapid_public_key() == b64(raw_public(key))
    claims = pyjwt.decode(token, key.public_key(), algorithms=["ES256"],
                          audience="https://web.push.apple.com",
                          options={"verify_exp": False})
    assert claims["sub"] == "https://ora.example"
    assert claims["exp"] - 1_800_000_000 <= 3600


def test_only_real_push_services_are_accepted():
    assert parse_subscription(APPLE)
    for bad in (
        "https://evil.example/push",
        "http://web.push.apple.com/x",
        "https://web.push.apple.com.evil.example/x",
        "https://user:pw@fcm.googleapis.com/x",
        "https://fcm.googleapis.com:8443/x",
    ):
        assert parse_subscription({**APPLE, "endpoint": bad}) is None, bad
    assert parse_subscription({**APPLE, "keys": {"p256dh": "AAAA", "auth": b64(AUTH)}}) is None
    assert parse_subscription("not json") is None


def test_stored_token_is_canonical_and_fits_the_endpoint_record():
    a = subscription_token(APPLE)
    b = subscription_token(json.dumps(APPLE))
    assert a == b and is_web_push_token(a) and len(a) <= 1200
    assert parse_subscription(a)["endpoint"] == APPLE["endpoint"]
    from ambient.push import _provider_for

    assert _provider_for(a) == "webpush"
    assert _provider_for("ExponentPushToken[abc]") == "expo"
    assert _provider_for("garbage") == "stub"


class Endpoint:
    def __init__(self, token, provider="webpush", id="pep_1"):
        self.token, self.provider, self.id = token, provider, id
        self.permission_state = "granted"


class Repo:
    def __init__(self, rows):
        self.rows, self.disabled = rows, []

    async def active_endpoints(self, owner_id):
        return self.rows

    async def disable_endpoint(self, *, token="", endpoint_id="", reason=""):
        self.disabled.append((endpoint_id, reason))
        return 1


def provider_with(rows, statuses):
    p = WebPushNotificationProvider.__new__(WebPushNotificationProvider)
    p.repo, p.timeout, p.posted = Repo(rows), 1.0, []

    async def post(sub, message):
        p.posted.append(json.loads(decrypt(encrypt(message, sub["p256dh"], sub["auth"]))))
        return statuses.pop(0)

    p._post = post
    return p


def send(p):
    return asyncio.run(p.send(owner_id="u1", plan_id="dlv_abcdef12", title="Interno",
                              body="Testo completo", deep_link="/", public_title="ORA",
                              public_body="I panni sono pronti"))


def test_accepted_send_carries_only_lock_screen_words(monkeypatch):
    set_vapid(monkeypatch)
    p = provider_with([Endpoint(subscription_token(APPLE))], [(201, True)])
    out = send(p)
    assert out["ok"] and out["provider_accepted"] == 1
    assert p.posted == [{"title": "ORA", "body": "I panni sono pronti",
                         "plan_id": "dlv_abcdef12", "deep_link": "/"}]


def test_gone_subscription_is_disabled_and_not_retried(monkeypatch):
    set_vapid(monkeypatch)
    p = provider_with([Endpoint(subscription_token(APPLE))], [(410, True)])
    out = send(p)
    assert not out["ok"] and out["safe_to_retry"] is False
    assert p.repo.disabled == [("pep_1", "webpush_410")]


def test_throttle_is_the_only_safe_retry(monkeypatch):
    set_vapid(monkeypatch)
    assert send(provider_with([Endpoint(subscription_token(APPLE))], [(429, True)]))["safe_to_retry"] is True
    assert send(provider_with([Endpoint(subscription_token(APPLE))], [(None, True)]))["safe_to_retry"] is False
    assert send(provider_with([Endpoint(subscription_token(APPLE))], [(None, False)]))["safe_to_retry"] is True


def test_no_web_endpoint_is_not_a_failure_of_the_channel(monkeypatch):
    set_vapid(monkeypatch)
    out = send(provider_with([Endpoint("ExponentPushToken[x]", provider="expo")], []))
    assert out == {"ok": False, "provider": "webpush", "reason": "no_endpoint"}


class Fake:
    def __init__(self, name, result):
        self.name, self.result, self.calls = name, result, 0

    async def send(self, **kw):
        self.calls += 1
        return self.result

    async def cancel(self, **kw):
        return {"ok": True}


def test_one_decision_reaches_every_channel():
    expo = Fake("expo", {"ok": False, "provider": "expo", "reason": "no_endpoint"})
    web = Fake("webpush", {"ok": True, "provider": "webpush", "provider_accepted": 1, "external_id": "w"})
    out = asyncio.run(CompositeNotificationProvider([expo, web]).send(
        owner_id="u", plan_id="p", title="t", body="b", deep_link="/"))
    assert out["ok"] and out["provider_accepted"] == 1 and expo.calls == web.calls == 1


def test_composite_failure_keeps_the_strict_retry_rule():
    absent = Fake("expo", {"ok": False, "provider": "expo", "reason": "no_endpoint"})
    throttled = Fake("webpush", {"ok": False, "provider": "webpush", "safe_to_retry": True,
                                 "transient": True, "reason": "webpush_not_accepted"})
    out = asyncio.run(CompositeNotificationProvider([absent, throttled]).send(
        owner_id="u", plan_id="p", title="t", body="b", deep_link="/"))
    assert out["ok"] is False and out["safe_to_retry"] is True
    unknown = Fake("expo", {"ok": False, "provider": "expo", "safe_to_retry": False,
                            "transient": True, "reason": "transport_acceptance_unknown"})
    out = asyncio.run(CompositeNotificationProvider([unknown, throttled]).send(
        owner_id="u", plan_id="p", title="t", body="b", deep_link="/"))
    assert out["safe_to_retry"] is False
    none = asyncio.run(CompositeNotificationProvider([absent]).send(
        owner_id="u", plan_id="p", title="t", body="b", deep_link="/"))
    assert none["reason"] == "no_endpoint" and none["safe_to_retry"] is False


def test_install_uses_web_push_only_when_configured(monkeypatch):
    from ambient import push
    from delivery import provider as delivery_provider

    monkeypatch.delenv("PUSH_PROVIDER", raising=False)
    monkeypatch.delenv("WEBPUSH_VAPID_PRIVATE_KEY", raising=False)
    previous = delivery_provider._provider
    try:
        assert push.install_provider(object()) == "stub"
        set_vapid(monkeypatch)
        assert push.install_provider(object()) == "webpush"
        monkeypatch.setenv("PUSH_PROVIDER", "expo")
        assert push.install_provider(object()) == "expo+webpush"
    finally:
        delivery_provider._provider = previous
