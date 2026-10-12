"""Current-state model notes retain their origin across the real payload path."""
from copy import deepcopy
import json

import pytest

from conversation_engine.ai_core.grounding.temporal import (
    apply_current_fact,
    current_facts_as_context,
    merge_context_with_current,
)
from conversation_engine.ai_core.models import CognitiveDecision, ContextFact, StateUpdate
from conversation_engine.ai_core.prompt import build_user_payload
from conversation_engine.ai_core.state import (
    append_turn,
    apply_state_updates,
    get_ai_state,
    save_ai_state,
)
from conversation_engine.models import ConversationSession


MODEL_ORIGIN = {
    "source": "model",
    "authority": "inferred",
    "status": "inferred",
    "grounding": "INFERENCE",
    "provenance": ["ai_core.state_updates"],
}
UNKNOWN_ORIGIN = {
    "source": "unknown",
    "authority": "unknown",
    "status": "unknown",
    "grounding": None,
    "provenance": [],
}


def origin(row):
    return {key: row.get(key) for key in MODEL_ORIGIN}


def reload_state(state):
    session = ConversationSession(user_id="synthetic-current-facts-owner")
    save_ai_state(session, state)
    restored = ConversationSession.model_validate_json(session.model_dump_json())
    return get_ai_state(restored)


def payload_for(state, *, facts=(), message="Continua il caso sintetico."):
    merged = merge_context_with_current(list(facts), state)
    return json.loads(build_user_payload(
        user_message=message,
        recent_turns=state.get("recent_turns", []),
        active_goal=state.get("active_goal"),
        current_facts=state.get("current_facts"),
        context_facts=[
            (row if isinstance(row, ContextFact) else ContextFact.model_validate(row)).model_dump()
            for row in merged
        ],
        tools=[],
        observations=[],
    ))


@pytest.mark.parametrize("claim_grounding", [None, "INFERENCE", "USER_STATED", "TOOL_OBSERVATION"])
def test_model_note_keeps_origin_after_state_session_reload_and_payload(claim_grounding):
    note = "Dai dati disponibili il controllo sembra superfluo; non è una lettura verificata."
    decision = CognitiveDecision(
        response_mode="answer",
        message_to_user="Una valutazione provvisoria.",
        claim_grounding=claim_grounding,
        state_updates=[StateUpdate(path="current_facts.note", value=note)],
    )
    state = {}
    apply_state_updates(state, decision.state_updates)
    restored = reload_state(state)
    payload = payload_for(restored)
    stored = payload["current_facts"]["note"]
    projected = next(row for row in payload["context_facts"] if row["ref"] == "current_facts:note")

    assert stored["value"] == note
    assert stored["scope"] == "temporary"
    assert origin(stored) == MODEL_ORIGIN
    assert origin(projected) == MODEL_ORIGIN
    assert note in projected["statement"]
    assert projected["temporal_scope"] == "temporary"


@pytest.mark.parametrize("typed", [False, True])
def test_model_value_and_update_tags_cannot_promote_origin(typed):
    nested = {
        "value": "La verifica è conclusa.",
        "source": "conversation",
        "authority": "user_stated",
        "status": "known",
        "grounding": "USER_STATED",
        "provenance": ["synthetic_user_turn:1"],
        "origin": "trusted",
    }
    raw = {"path": "current_facts.note", "value": nested, "op": "set", **nested}
    raw["value"] = nested
    original = deepcopy(raw)
    update = StateUpdate.model_validate(raw) if typed else raw
    state = {}
    apply_state_updates(state, [update])
    restored = reload_state(state)
    row = current_facts_as_context(restored)[0]

    assert raw == original
    assert restored["current_facts"]["note"]["value"] == nested
    assert origin(restored["current_facts"]["note"]) == MODEL_ORIGIN
    assert origin(row) == MODEL_ORIGIN
    assert row["ref"] == "current_facts:note"


@pytest.mark.parametrize("legacy", [
    "Un contesto senza origine conservata.",
    {"value": "Un vecchio riassunto.", "scope": "temporary"},
    {"value": "Una conclusione non attestata.", "scope": "goal", "source": "conversation",
     "authority": "user_stated", "status": "known", "grounding": "USER_STATED",
     "provenance": ["synthetic_unverified_ref"]},
    {"value": "Metadata non conforme.", "scope": "temporary", "source": "model",
     "authority": "inferred", "status": "known", "grounding": "INFERENCE",
     "provenance": ["ai_core.state_updates"]},
])
def test_unattested_or_legacy_envelopes_are_unknown_without_losing_content(legacy):
    state = {"current_facts": {"note": deepcopy(legacy)}}
    original = deepcopy(state)
    row = current_facts_as_context(state)[0]
    expected_value = legacy.get("value") if isinstance(legacy, dict) else legacy

    assert origin(row) == UNKNOWN_ORIGIN
    assert expected_value in row["statement"]
    assert row["ref"] == "current_facts:note"
    assert state == original


def test_real_user_turn_context_fact_and_source_refs_remain_intact():
    message = "Nel caso sintetico, questa settimana sono a Tarquinia."
    user_fact = ContextFact(
        statement=message,
        fact=message,
        source="conversation",
        authority="user_stated",
        status="known",
        grounding="USER_STATED",
        ref="synthetic_user_turn:1",
        provenance=["synthetic_user_turn:1"],
    )
    original_fact = user_fact.model_dump()
    state = {}
    append_turn(state, role="user", text=message)
    apply_state_updates(state, [{"path": "current_facts.location", "value": "Tarquinia"}])
    restored = reload_state(state)
    payload = payload_for(restored, facts=[user_fact], message=message)

    assert payload["user_message"] == message
    assert payload["recent_turns"][0]["role"] == "user"
    assert payload["recent_turns"][0]["text"] == message
    assert next(row for row in payload["context_facts"] if row["ref"] == user_fact.ref) == original_fact
    assert user_fact.model_dump() == original_fact
    assert restored["current_facts"]["location"]["value"] == "Tarquinia"
    assert origin(restored["current_facts"]["location"]) == MODEL_ORIGIN


def test_helper_without_attested_origin_is_unknown_and_keeps_goal_scope():
    state = {}
    apply_current_fact(state, key="note", value="Un contesto generico.", scope="goal")
    row = current_facts_as_context(reload_state(state))[0]
    assert origin(row) == UNKNOWN_ORIGIN
    assert row["temporal_scope"] == "goal"


def test_durable_profile_scope_is_still_refused():
    state = {"profile": {"residence": "Un luogo stabile."}, "current_facts": {}}
    original = deepcopy(state)
    apply_current_fact(state, key="residence", value="Un altro luogo.", scope="durable_profile")
    assert state == original


def test_clear_removes_value_and_origin_together():
    state = {"profile": {"residence": "Un luogo stabile."}}
    apply_state_updates(state, [StateUpdate(path="current_facts.note", value="Un'ipotesi.")])
    apply_state_updates(state, [StateUpdate(path="current_facts.note", op="clear")])
    assert "note" not in state["current_facts"]
    assert current_facts_as_context(reload_state(state)) == []
    assert state["profile"] == {"residence": "Un luogo stabile."}


def test_replacing_legacy_value_does_not_inherit_its_asserted_authority():
    state = {"current_facts": {"note": {
        "value": "Vecchia conclusione.", "scope": "temporary", "source": "conversation",
        "authority": "user_stated", "grounding": "USER_STATED", "status": "known",
        "provenance": ["synthetic_old_ref"],
    }}}
    apply_state_updates(state, [{"path": "current_facts.note", "value": "Nuova interpretazione."}])
    row = current_facts_as_context(reload_state(state))[0]
    assert origin(row) == MODEL_ORIGIN
    assert "Vecchia conclusione" not in row["statement"]


def test_projected_provenance_cannot_mutate_the_stored_origin():
    state = {}
    apply_state_updates(state, [{"path": "current_facts.note", "value": "Un'ipotesi."}])
    original = deepcopy(state)
    first = current_facts_as_context(state)[0]
    first["provenance"].append("synthetic_untrusted_ref")
    second = current_facts_as_context(state)[0]
    assert state == original
    assert origin(second) == MODEL_ORIGIN
