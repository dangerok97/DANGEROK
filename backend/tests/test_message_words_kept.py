"""The message to deliver keeps the person's words, casing included (6/11: «la AMo»)."""
import pytest

from test_phone_identity_conflict import db  # noqa: F401  (fixture)
from preparation.service import start


@pytest.mark.asyncio
async def test_the_model_casing_does_not_replace_the_persons_words(db):  # noqa: F811
    prep, _ = await start(db, owner_id="owner", user_request="Chiama Asia e dille che la amo",
                          counterparty="Asia", operation="deliver_message", message="la AMo")
    assert prep.message_to_deliver == "la amo"


@pytest.mark.asyncio
async def test_a_message_not_in_the_sentence_is_kept_as_given(db):  # noqa: F811
    prep, _ = await start(db, owner_id="owner", user_request="Chiama Asia per gli auguri",
                          counterparty="Asia", operation="deliver_message", message="Buon compleanno!")
    assert prep.message_to_deliver == "Buon compleanno!"
