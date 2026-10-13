"""Boundary regressions, synthetic fixtures only."""
import asyncio
import copy
import pytest
from test_loyalty_wallet import service, card
from loyalty_wallet import WalletError, render_code, decode_image


def test_aggregate_size_guard_does_not_overwrite_existing_cards(monkeypatch):
    import loyalty_wallet
    async def run():
        svc, db = service()
        await svc.save("alice", card())
        previous = copy.deepcopy(db.loyalty_wallets.docs)
        monkeypatch.setattr(loyalty_wallet, "MAX_ENCRYPTED_BYTES", 1)
        with pytest.raises(WalletError) as e:
            await svc.save("alice", card(2))
        assert e.value.status == 409
        assert db.loyalty_wallets.docs == previous
    asyncio.run(run())


def test_leading_zero_ean_photo_exposes_ambiguity_without_dropping_digits():
    pytest.importorskip("zxingcpp")
    import base64
    code = "0042100005264"
    png = render_code("EAN_13", code)
    options = decode_image(base64.b64decode(png.split(",", 1)[1]))
    assert {"format": "EAN_13", "code": code} in options
    assert {"format": "UPC_A", "code": code[1:]} in options
