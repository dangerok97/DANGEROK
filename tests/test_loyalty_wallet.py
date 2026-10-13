"""Synthetic cards only; no user accounts, notifications or external services."""
import asyncio
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from loyalty_wallet import CardInput, MAX_CARDS, WalletCipher, WalletError, WalletService, decode_image, render_code, validate_code

SECRET = "wallet-test-only-not-a-production-key-0123456789"


def card(number=1, **changes):
    return CardInput(id=f"{number:032x}", name="Tessera prova", format="CODE_128", code="00012345", static_confirmed=True, **changes)


class Duplicate(Exception):
    code = 11000


class Collection:
    def __init__(self):
        self.docs = {}

    async def find_one(self, query):
        await asyncio.sleep(0)
        doc = self.docs.get(query["_id"])
        return copy.deepcopy(doc) if doc and all(doc.get(k) == v for k, v in query.items()) else None

    async def insert_one(self, doc):
        await asyncio.sleep(0)
        if doc["_id"] in self.docs:
            raise Duplicate()
        self.docs[doc["_id"]] = copy.deepcopy(doc)

    async def replace_one(self, query, doc):
        await asyncio.sleep(0)
        previous = self.docs.get(query["_id"])
        match = previous and all(previous.get(k) == v for k, v in query.items())
        if match:
            self.docs[doc["_id"]] = copy.deepcopy(doc)
        return SimpleNamespace(matched_count=int(bool(match)))


def service():
    db = SimpleNamespace(loyalty_wallets=Collection())
    return WalletService(db, WalletCipher(SECRET), lambda fmt, value: "data:image/png;base64,synthetic-test-image"), db


@pytest.mark.parametrize("fmt,value", [("CODE_128", "00012345"), ("CODE_128", " ABC "), ("CODE_39", "ABC-001"), ("EAN_13", "5901234123457"), ("EAN_8", "96385074"), ("UPC_A", "042100005264"), ("ITF", "001122"), ("QR_CODE", "tessera-caffè-001")])
def test_valid_codes_preserve_exact_text(fmt, value):
    assert validate_code(fmt, value) == value


@pytest.mark.parametrize("fmt,value", [("EAN_13", "5901234123456"), ("EAN_13", "590123412345"), ("EAN_8", "96385075"), ("UPC_A", "042100005263"), ("ITF", "123"), ("CODE_39", "abc"), ("CODE_39", "A*B"), ("CODE_128", "é"), ("CODE_128", "A\nB"), ("CODE_128", "A" * 65), ("QR_CODE", "à" * 257), ("QR_CODE", ""), ("NFC", "123"), ("EAN_8", "１２３４５６７８")])
def test_bad_codes_are_rejected_not_repaired(fmt, value):
    with pytest.raises(ValueError):
        validate_code(fmt, value)


def test_static_confirmation_and_no_extra_payment_fields():
    data = card().model_dump()
    with pytest.raises(ValidationError):
        CardInput(**{**data, "static_confirmed": False})
    with pytest.raises(ValidationError):
        CardInput(**{**data, "cvv": "123"})
    with pytest.raises(ValidationError):
        CardInput(**{**data, "name": "   "})


def test_encryption_binds_owner_and_id_and_hides_payload():
    cipher = WalletCipher(SECRET)
    payload = {"id": "a" * 32, "code": "PRIVATE-12345", "name": "My shop"}
    entry = cipher.encrypt("owner-a", payload)
    assert cipher.decrypt("owner-a", entry) == payload
    assert "PRIVATE-12345" not in json.dumps(entry)
    assert "My shop" not in json.dumps(entry)
    assert cipher.encrypt("owner-a", payload)["ciphertext"] != entry["ciphertext"]
    for owner, candidate in [("owner-b", entry), ("owner-a", {**entry, "id": "b" * 32}), ("owner-a", {**entry, "ciphertext": entry["ciphertext"][:-8] + "AAAAAAAA"})]:
        with pytest.raises(WalletError):
            cipher.decrypt(owner, candidate)
    with pytest.raises(WalletError):
        WalletCipher("short")


def test_owner_isolation_idempotency_edit_stale_revision_and_delete():
    async def run():
        svc, db = service()
        original = card()
        saved = await svc.save("alice", original)
        assert saved["code"] == "00012345" and saved["revision"] == 1
        assert saved["acceptance"] == "not_verified_at_checkout"
        assert await svc.save("alice", original) == saved
        assert await svc.list_cards("bob") == []
        await svc.delete("bob", saved["id"], 1)
        assert len(await svc.list_cards("alice")) == 1
        data = original.model_dump()
        changed = await svc.save("alice", CardInput(**{**data, "name": "Nuovo nome", "favorite": True, "revision": 1}))
        assert changed["revision"] == 2 and changed["name"] == "Nuovo nome"
        with pytest.raises(WalletError) as e:
            await svc.save("alice", CardInput(**{**data, "revision": 1}))
        assert e.value.status == 409
        with pytest.raises(WalletError):
            await svc.delete("alice", saved["id"], 1)
        assert "00012345" not in json.dumps(db.loyalty_wallets.docs)
        assert "Nuovo nome" not in json.dumps(db.loyalty_wallets.docs)
        await svc.delete("alice", saved["id"], 2)
        await svc.delete("alice", saved["id"], 2)
        assert await svc.list_cards("alice") == []
        assert db.loyalty_wallets.docs["alice"]["cards"] == []
    asyncio.run(run())


def test_concurrent_creates_do_not_lose_cards():
    async def run():
        svc, _ = service()
        await asyncio.gather(*(svc.save("alice", card(i)) for i in range(1, 7)))
        assert len(await svc.list_cards("alice")) == 6
    asyncio.run(run())


def test_limit_is_enforced():
    async def run():
        svc, _ = service()
        for i in range(MAX_CARDS):
            await svc.save("alice", card(i + 1))
        with pytest.raises(WalletError) as e:
            await svc.save("alice", card(1001))
        assert e.value.status == 409
    asyncio.run(run())


def test_invalid_photo_rejected_before_decoder():
    with pytest.raises(WalletError):
        decode_image(b"not an image")
    with pytest.raises(WalletError) as e:
        decode_image(b"x" * (8 * 1024 * 1024 + 1))
    assert e.value.status == 413


@pytest.mark.parametrize("fmt,value", [("CODE_128", "00012345"), ("CODE_39", "ABC-001"), ("EAN_13", "5901234123457"), ("EAN_8", "96385074"), ("UPC_A", "042100005264"), ("ITF", "001122"), ("QR_CODE", "tessera-caffè-001")])
def test_real_codec_round_trip(fmt, value):
    pytest.importorskip("zxingcpp", reason="Install the pinned zxing-cpp dependency for real decoder tests")
    import base64
    png = render_code(fmt, value)
    candidates = decode_image(base64.b64decode(png.split(",", 1)[1]))
    assert {"format": fmt, "code": value} in candidates
