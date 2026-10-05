"""A number attributed to Francesco cannot silently become Asia's number."""
import pytest

from test_post_call_application_v315 import FintoDb
from preparation import trust
from preparation.preparation import by_id
from preparation.service import (
    as_a_card, change_number, confirm_number, resolve_identity_conflict,
    set_contact_number, start, turn_into_a_call,
)

NUMBER = "+393330000001"


@pytest.fixture
def db(monkeypatch):
    import preparation.readiness as readiness
    import preparation.contacts as contacts

    async def no_model(_prep):
        return None

    async def no_web(*args, **kwargs):
        return []

    monkeypatch.setattr(readiness, "_what_the_model_sees", no_model)
    monkeypatch.setattr(contacts.PublicWeb, "look_for", no_web)
    return FintoDb()


async def claim(db, name="Francesco", owner="owner"):
    return await trust.confirm(
        db, owner_id=owner, identity=trust.identity_of(name),
        display_name=name, number=NUMBER, source="user",
    )


async def prepare(db, name="Asia", suffix="", owner="owner", number="333 0000001"):
    prep, error = await start(
        db, owner_id=owner, counterparty=name, operation="deliver_message",
        user_request=f"Il numero di {name} è {number}. Chiama per il messaggio {suffix}",
        message="Arrivo alle 18.",
    )
    assert not error
    return prep


@pytest.mark.asyncio
async def test_cross_call_conflict_is_persisted_and_stops_preparation(db):
    await prepare(db, "Francesco")
    prep = await prepare(db)
    card = as_a_card(prep)
    assert "Francesco" in card["says"] and "Asia" in card["says"]
    assert "resolve_identity" in card["you_can_answer"]
    assert "confirm_number" not in card["you_can_answer"]
    assert not card["can_call"] and not card["number_confirmed"]
    reloaded = await by_id(db, "owner", prep.preparation_id)
    assert reloaded.identity_conflicts == prep.identity_conflicts
    call, why = await turn_into_a_call(db, reloaded)
    assert call is None and "Francesco" in why
    assert db["phone_calls"].righe == []
    assert not await trust.still_trusted(db, "owner", "asia", NUMBER)


@pytest.mark.asyncio
async def test_generic_yes_and_explicit_number_cannot_bypass_conflict(db):
    await claim(db)
    prep = await prepare(db)
    prep, _ = await confirm_number(db, prep, yes=True)
    assert prep.identity_conflicts and not prep.number_confirmed
    prep, _ = await set_contact_number(db, prep, number=NUMBER)
    assert prep.identity_conflicts and not prep.number_confirmed
    assert await trust.still_trusted(db, "owner", "francesco", NUMBER)
    assert not await trust.still_trusted(db, "owner", "asia", NUMBER)


@pytest.mark.asyncio
async def test_explicit_correction_retires_old_association_and_survives_new_call(db):
    await claim(db)
    prep = await prepare(db)
    prep, error = await resolve_identity_conflict(db, prep, resolution="replace")
    assert not error and prep.can_become_a_call()
    assert not await trust.still_trusted(db, "owner", "francesco", NUMBER)
    assert await trust.still_trusted(db, "owner", "asia", NUMBER)
    assert not (await prepare(db, suffix="domani")).identity_conflicts
    assert (await prepare(db, "Francesco", suffix="domani")).identity_conflicts


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [
    {}, {"to_number": "3330000009"}, {"identity_resolution": "replace"},
    {"number_is_right": True},
    {"give_number": "3330000009", "identity_resolution": "replace", "go_ahead": True},
])
async def test_new_number_in_current_turn_replaces_stale_conflict(db, extra):
    from telephone.caps import _through_the_preparation

    await claim(db)
    prep = await prepare(db)
    args = {"preparation_id": prep.preparation_id}
    runtime = {"session_id": "chat", "reasoning_epoch": "one", "user_message": prep.user_request}
    await _through_the_preparation(args, runtime, db, "owner")
    result = await _through_the_preparation(
        {**args, **extra},
        {**runtime, "reasoning_epoch": "two", "user_message": "No, il numero corretto è 3330000009"},
        db, "owner",
    )
    assert result.payload["contact"]["number"] == "+393330000009"
    assert not result.payload["identity_conflicts"]
    assert not result.payload["number_confirmed"]
    assert not result.payload["call_id"]
    assert not result.payload["not_accepted"]
    assert await trust.still_trusted(db, "owner", "francesco", NUMBER)
    assert db["phone_calls"].righe == []
    saved = await by_id(db, "owner", prep.preparation_id)
    assert saved.selected_contact.number == "+393330000009"


@pytest.mark.asyncio
async def test_changed_number_invalidates_previous_summary_even_if_already_trusted(db):
    from preparation.preparation import save

    prep = await prepare(db)
    prep, _ = await confirm_number(db, prep, yes=True)
    prep.summary_shown_in = "previous-turn"
    await save(db, prep)
    await trust.confirm(db, owner_id="owner", identity="asia", display_name="Asia",
                        number="+393330000009", source="user")
    prep, error = await change_number(db, prep, number="3330000009")
    assert not error
    assert prep.number_confirmed
    assert not prep.summary_shown_in


@pytest.mark.parametrize("message", [
    "Non usare 3330000009", "Il numero è 3330000009?",
    "Il numero di Carlo è 3330000009", "Usa 3330000009 oppure 3330000008",
])
def test_ambiguous_number_is_not_an_automatic_correction(message):
    from telephone.caps import _replacement_number_in
    from preparation.preparation import MissionPreparation
    from preparation.contacts import ContactCandidate

    prep = MissionPreparation(owner_id="owner", counterparty="Asia",
                              selected_contact=ContactCandidate(name="Asia", number=NUMBER))
    assert not _replacement_number_in(message, prep, {"to_number": "3330000009"})


@pytest.mark.asyncio
async def test_shared_number_keeps_both_people_without_repeated_warning(db):
    await claim(db)
    prep = await prepare(db)
    prep, _ = await resolve_identity_conflict(db, prep, resolution="shared")
    assert prep.can_become_a_call()
    assert await trust.still_trusted(db, "owner", "francesco", NUMBER)
    assert await trust.still_trusted(db, "owner", "asia", NUMBER)
    assert not (await prepare(db, suffix="domani")).identity_conflicts
    assert not (await prepare(db, "Francesco", suffix="domani")).identity_conflicts
    assert (await prepare(db, "Carlo", suffix="domani")).identity_conflicts


@pytest.mark.asyncio
async def test_extending_a_shared_number_keeps_the_previous_clarification(db):
    await claim(db)
    prep = await prepare(db)
    prep, _ = await resolve_identity_conflict(db, prep, resolution="shared")
    # A later call introduces a third attribution. Asia/Francesco have
    # already been acknowledged as sharing; only Carlo needs clarification.
    await claim(db, "Carlo")
    prep = await prepare(db, suffix="con Carlo")
    assert {c["name"] for c in prep.identity_conflicts} == {"Carlo"}
    prep, error = await resolve_identity_conflict(db, prep, resolution="shared")
    assert not error and prep.can_become_a_call()
    for name in ("Asia", "Francesco", "Carlo"):
        reopened = await prepare(db, name, suffix="dopo il chiarimento")
        assert not reopened.identity_conflicts, name
    assert db["phone_calls"].righe == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["stale", "rejected"])
async def test_extending_shared_number_does_not_restore_a_retired_person(db, status):
    await claim(db)
    prep = await prepare(db)
    prep, _ = await resolve_identity_conflict(db, prep, resolution="shared")
    if status == "stale":
        await trust.retire(db, owner_id="owner", identity="francesco", number=NUMBER,
                           why="non usa più questo numero")
    else:
        await trust.reject(db, owner_id="owner", identity="francesco",
                           display_name="Francesco", number=NUMBER)
    await claim(db, "Carlo")
    await claim(db, "Francesco", owner="other")
    prep = await prepare(db, suffix="con Carlo")
    prep, error = await resolve_identity_conflict(db, prep, resolution="shared")
    assert not error and prep.can_become_a_call()
    assert not await trust.still_trusted(db, "owner", "francesco", NUMBER)
    assert await trust.still_trusted(db, "other", "francesco", NUMBER)
    for name in ("Asia", "Carlo"):
        assert not (await prepare(db, name, suffix="dopo il chiarimento")).identity_conflicts
    row = await db[trust.TRUSTED].find_one({
        "_id": trust.key_for("owner", "asia", NUMBER),
    })
    assert "francesco" not in row["shared_with"]


@pytest.mark.asyncio
async def test_names_case_and_phone_format_are_normalized_and_owners_isolated(db):
    await claim(db, "ASIA", owner="other")
    await claim(db)
    same = await prepare(db, "FRANCESCO", number="0039 333 0000001")
    assert not same.identity_conflicts
    assert not (await prepare(db, owner="other")).identity_conflicts
    conflict = await prepare(db)
    assert {c["name"] for c in conflict.identity_conflicts} == {"Francesco"}


@pytest.mark.asyncio
async def test_legacy_history_conflict_and_correction_do_not_reappear(db):
    db["phone_calls"].righe.append({
        "id": "old", "owner_id": "owner", "to_number": NUMBER,
        "calling_whom": "Francesco", "state": "ended",
    })
    prep = await prepare(db)
    assert prep.identity_conflicts[0]["source"] == "past_call"
    prep, _ = await resolve_identity_conflict(db, prep, resolution="replace")
    assert prep.can_become_a_call()
    assert not (await prepare(db, suffix="domani")).identity_conflicts


@pytest.mark.asyncio
async def test_number_given_for_one_call_still_leaves_an_attribution(db):
    prep, _ = await start(
        db, owner_id="owner", user_request=f"Chiama Francesco al {NUMBER}",
        counterparty="Francesco", operation="deliver_message", message="Arrivo alle 18.",
    )
    assert prep.number_confirmed
    assert not await trust.still_trusted(db, "owner", "francesco", NUMBER)
    assert (await prepare(db)).identity_conflicts


@pytest.mark.asyncio
async def test_a_different_number_clears_conflict_without_touching_francesco(db):
    await claim(db)
    prep = await prepare(db)
    prep, _ = await change_number(db, prep, number="3330000009")
    assert not prep.identity_conflicts and not prep.number_confirmed
    prep, _ = await confirm_number(db, prep, yes=True)
    assert prep.can_become_a_call()
    assert await trust.still_trusted(db, "owner", "francesco", NUMBER)


@pytest.mark.asyncio
async def test_new_claim_while_dialog_open_needs_a_fresh_clarification(db):
    await claim(db)
    prep = await prepare(db)
    await claim(db, "Carlo")
    prep, _ = await resolve_identity_conflict(db, prep, resolution="replace")
    assert {c["name"] for c in prep.identity_conflicts} == {"Francesco", "Carlo"}
    assert not prep.number_confirmed
    assert await trust.still_trusted(db, "owner", "francesco", NUMBER)


@pytest.mark.asyncio
async def test_reopening_an_old_request_rechecks_new_associations(db):
    first = await prepare(db)
    assert first.can_become_a_call()
    await claim(db)
    reopened = await prepare(db)
    assert reopened.preparation_id == first.preparation_id
    assert reopened.identity_conflicts and not reopened.can_become_a_call()


@pytest.mark.asyncio
async def test_changing_number_does_not_reuse_prepared_call_for_old_number(db):
    from telephone.service import TelephoneService

    prep = await prepare(db)
    original, error = await turn_into_a_call(db, prep)
    assert original is not None and not error
    prep, _ = await change_number(db, prep, number="3330000009")
    prep, _ = await confirm_number(db, prep, yes=True)
    changed, error = await turn_into_a_call(db, prep)
    assert not error and changed.to_number == "+393330000009"
    assert changed.id != original.id
    assert (await TelephoneService(db).get("owner", original.id)).state == "expired"


@pytest.mark.asyncio
async def test_last_dial_gate_blocks_new_conflict_before_carrier(db, monkeypatch):
    from telephone.models import Mandate
    from telephone.service import TelephoneService
    from telephone.placing import dial
    from telephone import carrier

    async def must_not_call(**kwargs):
        pytest.fail("the carrier must not be invoked for a conflicting identity")

    monkeypatch.setattr(carrier, "place", must_not_call)
    call = await TelephoneService(db).prepare(
        "owner", to_number=NUMBER, calling_whom="Asia",
        mandate=Mandate(why_calling="chiedere un'informazione"),
    )
    await claim(db)
    result, error = await dial(db, "owner", call)
    assert result is None and "Francesco" in error and "Asia" in error
    assert call.state == "authorised"


@pytest.mark.asyncio
async def test_last_dial_gate_persists_warning_for_ui_refresh(db, monkeypatch):
    from telephone.placing import dial

    prep = await prepare(db)
    call, error = await turn_into_a_call(db, prep)
    assert call and not error
    await claim(db)
    result, error = await dial(db, "owner", call)
    assert result is None and "Francesco" in error
    refreshed = await by_id(db, "owner", prep.preparation_id)
    assert refreshed.identity_conflicts
    assert "resolve_identity" in as_a_card(refreshed)["you_can_answer"]


@pytest.mark.asyncio
async def test_unavailable_identity_read_never_places_a_call(db, monkeypatch):
    from telephone.models import Mandate
    from telephone.service import TelephoneService
    from telephone.placing import dial
    from telephone import carrier

    async def broken(*args, **kwargs):
        raise RuntimeError("unavailable")

    async def must_not_call(**kwargs):
        pytest.fail("the carrier must not be invoked without the identity check")

    monkeypatch.setattr(trust, "identity_conflicts", broken)
    monkeypatch.setattr(carrier, "place", must_not_call)
    call = await TelephoneService(db).prepare(
        "owner", to_number=NUMBER, calling_whom="Asia",
        mandate=Mandate(why_calling="chiedere un'informazione"),
    )
    result, error = await dial(db, "owner", call)
    assert result is None and "verificare" in error


def test_chat_requires_specific_clarification_and_reports_the_conflict():
    from preparation.preparation import MissionPreparation
    from preparation.contacts import ContactCandidate
    from telephone.caps import _identity_resolution_in, _the_sentence

    prep = MissionPreparation(owner_id="owner", selected_contact=ContactCandidate(name="Asia"))
    assert _identity_resolution_in("Sì, procedi", prep) == ""
    assert _identity_resolution_in("Non è di Asia", prep) == ""
    assert _identity_resolution_in("È di Asia?", prep) == ""
    assert _identity_resolution_in("Correggi: è di Asia", prep) == "replace"
    assert _identity_resolution_in("È un numero condiviso", prep) == "shared"
    card = {"identity_conflicts": [{"name": "Francesco"}], "says": "Prima Francesco, ora Asia?"}
    assert _the_sentence(card, False) == card["says"]


@pytest.mark.asyncio
async def test_chat_cannot_resolve_in_same_turn_or_dial_while_resolving(db):
    from telephone.caps import _through_the_preparation

    await claim(db)
    prep = await prepare(db)
    args = {"preparation_id": prep.preparation_id}
    runtime = {"session_id": "chat", "reasoning_epoch": "one", "user_message": prep.user_request}
    first = await _through_the_preparation(args, runtime, db, "owner")
    assert "Francesco" in first.payload["say_this"]
    resolution = {**args, "identity_resolution": "replace", "go_ahead": True}
    same_turn = await _through_the_preparation(
        resolution, {**runtime, "user_message": "Correggi: è di Asia"}, db, "owner",
    )
    assert same_turn.payload["not_accepted"]
    generic = await _through_the_preparation(
        resolution, {**runtime, "reasoning_epoch": "two", "user_message": "Sì, procedi"}, db, "owner",
    )
    assert generic.payload["not_accepted"]
    fixed = await _through_the_preparation(
        resolution, {**runtime, "reasoning_epoch": "three", "user_message": "Correggi: è di Asia"}, db, "owner",
    )
    assert fixed.payload["status"] == "ready"
    assert fixed.payload["call_id"] is None
    assert db["phone_calls"].righe == []
    assert await trust.still_trusted(db, "owner", "asia", NUMBER)


@pytest.mark.asyncio
async def test_chat_routes_current_number_to_owners_active_preparation(db):
    from conversation_engine.ai_core.loop import _phone_number_correction

    prep = await prepare(db)
    state = {"active_preparation_id": prep.preparation_id}
    text = "È sbagliato, il numero di Asia è 3330000009"
    assert await _phone_number_correction(db, "owner", state, text) == {
        "preparation_id": prep.preparation_id, "give_number": "+393330000009",
    }
    assert not await _phone_number_correction(db, "other", state, text)
    assert not await _phone_number_correction(db, "owner", {}, text)
    assert not await _phone_number_correction(db, "owner", state, "è quello di prima")


def test_spoken_phone_number_accepts_digit_by_digit_but_not_incomplete():
    from conversation_engine.ai_core.loop import _spoken_phone_number

    assert _spoken_phone_number("no, il numero corretto è 3 2 7 7 6 3 1 2 3 4") == "+393277631234"
    assert _spoken_phone_number("no, il numero corretto è 3 2 7 7 6 3") == ""


@pytest.mark.asyncio
async def test_plain_no_invalidates_selected_number_instead_of_repeating_it(db):
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation, remember
    from preparation.service import as_a_card, confirm_number

    candidate = ContactCandidate(
        name="Quindi", number=NUMBER, kind="person", source="user",
        confidence=1.0, why="Me l'hai scritto tu.", contact_identity="quindi",
    )
    prep = MissionPreparation(
        owner_id="owner",
        user_request="Chiama Quindi e dille che la amo",
        counterparty="Quindi",
        operation="deliver_message",
        message_to_deliver="la amo",
        selected_contact=candidate,
        contact_candidates=[candidate],
        number_source="user",
        contact_identity="quindi",
        number_confirmed=False,
    )
    prep = await remember(db, prep)

    prep, error = await confirm_number(db, prep, yes=False)
    assert not error
    card = as_a_card(prep)
    assert not prep.number_confirmed
    assert prep.selected_contact is None
    assert NUMBER not in card["says"]
    assert "dimmi tu quale" in card["says"].lower()


@pytest.mark.asyncio
async def test_active_phone_followup_routes_no_without_model(db):
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation, remember
    from conversation_engine.ai_core.loop import _phone_pending_followup

    candidate = ContactCandidate(
        name="Quindi", number=NUMBER, kind="person", source="user",
        confidence=1.0, why="Me l'hai scritto tu.", contact_identity="quindi",
    )
    prep = MissionPreparation(
        owner_id="owner",
        user_request="Chiama Quindi e dille che la amo",
        counterparty="Quindi",
        operation="deliver_message",
        message_to_deliver="la amo",
        selected_contact=candidate,
        contact_candidates=[candidate],
        number_source="user",
        contact_identity="quindi",
        number_confirmed=False,
    )
    prep = await remember(db, prep)

    state = {"active_preparation_id": prep.preparation_id}
    assert await _phone_pending_followup(db, "owner", state, "no") == {
        "preparation_id": prep.preparation_id,
        "number_is_right": False,
    }
    assert await _phone_pending_followup(
        db, "owner", state, "no, il numero corretto è 3 2 7 7 6 3"
    ) == {
        "preparation_id": prep.preparation_id,
        "number_is_right": False,
    }


@pytest.mark.asyncio
async def test_explicit_name_correction_retargets_active_preparation(db):
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation, remember
    from conversation_engine.ai_core.loop import _phone_pending_followup

    candidate = ContactCandidate(
        name="Quindi", number=NUMBER, kind="person", source="user",
        confidence=1.0, why="Me l'hai scritto tu.", contact_identity="quindi",
    )
    prep = MissionPreparation(
        owner_id="owner",
        user_request="Chiama la mia ragazza Quindi e dille che la amo",
        counterparty="Quindi",
        operation="deliver_message",
        message_to_deliver="la amo",
        selected_contact=candidate,
        contact_candidates=[candidate],
        contact_identity="quindi",
    )
    prep = await remember(db, prep)
    state = {"active_preparation_id": prep.preparation_id}

    assert await _phone_pending_followup(db, "owner", state, "il numero di Asia") == {
        "preparation_id": prep.preparation_id,
        "correct_counterparty": "Asia",
    }


def test_relationship_phrase_does_not_turn_quindi_into_a_contact_name():
    from telephone.requests import who_in

    assert who_in("Chiama la mia ragazza quindi e dille che la amo") == "la mia ragazza"



@pytest.mark.asyncio
async def test_ai_phone_dialogue_understands_relationship_alias_is_same_person(db, monkeypatch):
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation, remember
    from preparation.trust import identity_of
    from telephone.caps import _through_the_preparation

    await claim(db, "Asia")
    alias = "la mia ragazza"
    candidate = ContactCandidate(
        name=alias,
        number=NUMBER,
        kind="person",
        source="user",
        confidence=1.0,
        why="Me l'hai detto tu.",
        contact_identity=identity_of(alias),
    )
    prep = MissionPreparation(
        owner_id="owner",
        user_request="Chiama la mia ragazza e dille che la amo",
        counterparty=alias,
        operation="deliver_message",
        message_to_deliver="la amo",
        selected_contact=candidate,
        contact_candidates=[candidate],
        number_source="user",
        contact_identity=identity_of(alias),
        number_confirmed=False,
        identity_conflicts=[{
            "identity": identity_of("Asia"),
            "name": "Asia",
            "source": "user",
        }],
        identity_conflict_shown_in="chat:one",
    )
    prep = await remember(db, prep)

    async def classify(system, payload):
        assert "same_person" in system
        assert "la mia ragazza si chiama Asia" in payload
        return {"decision": "same_person", "canonical_name": "Asia"}

    monkeypatch.setattr("research.reasoning._ask_model", classify)

    result = await _through_the_preparation(
        {"preparation_id": prep.preparation_id},
        {
            "session_id": "chat",
            "reasoning_epoch": "two",
            "user_message": "è giusto perché la mia ragazza si chiama Asia",
        },
        db,
        "owner",
    )

    assert result.payload["identity_conflicts"] == []
    assert result.payload["contact"]["name"] == "Asia"
    assert result.payload["contact"]["number"] == NUMBER
    assert result.payload["number_confirmed"] is True
    assert result.payload["call_id"] is None
    assert "correzione o un numero condiviso" not in result.payload["say_this"].lower()


@pytest.mark.asyncio
async def test_ai_phone_identity_cannot_invent_a_canonical_person(db, monkeypatch):
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation
    from preparation.trust import identity_of
    from telephone.caps import _ai_identity_resolution

    prep = MissionPreparation(
        owner_id="owner",
        counterparty="la mia ragazza",
        selected_contact=ContactCandidate(
            name="la mia ragazza",
            number=NUMBER,
            contact_identity=identity_of("la mia ragazza"),
        ),
        identity_conflicts=[{
            "identity": identity_of("Asia"),
            "name": "Asia",
            "source": "user",
        }],
    )

    async def classify(*args, **kwargs):
        return {"decision": "same_person", "canonical_name": "Giulia"}

    monkeypatch.setattr("research.reasoning._ask_model", classify)
    assert await _ai_identity_resolution(
        "la mia ragazza si chiama Asia", prep
    ) == {"decision": "unclear", "canonical_name": ""}


@pytest.mark.asyncio
async def test_bare_yes_never_reassigns_phone_identity_even_if_model_would(db, monkeypatch):
    from preparation.contacts import ContactCandidate
    from preparation.preparation import MissionPreparation
    from preparation.trust import identity_of
    from telephone.caps import _ai_identity_resolution

    prep = MissionPreparation(
        owner_id="owner",
        counterparty="la mia ragazza",
        selected_contact=ContactCandidate(
            name="la mia ragazza",
            number=NUMBER,
            contact_identity=identity_of("la mia ragazza"),
        ),
        identity_conflicts=[{
            "identity": identity_of("Asia"),
            "name": "Asia",
            "source": "user",
        }],
    )

    called = False

    async def bad_model(*args, **kwargs):
        nonlocal called
        called = True
        return {"decision": "same_person", "canonical_name": "Asia"}

    monkeypatch.setattr("research.reasoning._ask_model", bad_model)
    assert await _ai_identity_resolution("sì", prep) == {
        "decision": "unclear", "canonical_name": ""
    }
    assert called is False


def test_phone_turn_does_not_get_generic_situation_followup():
    from conversation_engine.ai_core.loop import _with_situation_handoff

    situation = {
        "status": "success",
        "operation": "create",
        "situation": {
            "attention_intent": "verificare che la chiamata venga completata",
        },
    }
    phone_sentence = "Ho trovato Asia. È questo il numero corretto?"

    assert _with_situation_handoff(
        phone_sentence, situation, suppress=True
    ) == phone_sentence


def test_phone_conflict_guidance_does_not_require_magic_phrases():
    from telephone.caps import _what_to_say_now

    card = {
        "identity_conflicts": [{"name": "Asia"}],
        "contact": {"name": "la mia ragazza"},
        "ready": False,
        "candidates": [],
        "number_confirmed": False,
        "question": None,
    }
    guidance = _what_to_say_now(card, False).lower()
    assert "parole normali" in guidance
    assert "non pretendere formule" in guidance
