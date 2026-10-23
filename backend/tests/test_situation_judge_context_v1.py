"""A Situation checkpoint must reach the model with its Situation and latest read.

Production 22-23/10/2026: one ordinary weather read (8 evidence rows) plus the
Situation preview exceeded the 9000-character bound. The compaction gave up and
sent the model a 334-byte stub (`source_context_unavailable`). Every checkpoint
then said "context truncated, reread a narrower source" and finally asked the
person for the location ORA already had. These tests use the real models and the
real `_dump`, with the shapes measured in production.
"""
import json
from datetime import datetime, timedelta, timezone

import agent.capabilities as caps
from agent.evidence import for_verification
from agent.models import ActionPlan, ActionStep, AgentEvidence, AutonomousGoal, ResultProvenance
from agent.reasoning import _SITUATION_CONTEXT_CHARS, _dump
from situations.models import SituationState

OWNER = "user_synthetic_judge"
SID = "sit_synthetic_judge"
GID = "gol_sit_synthetic_judge"
NOW = datetime(2026, 10, 23, 0, 47, 22, tzinfo=timezone.utc)
# Claim lengths of the eight rows of one production weather read.
CLAIM_LENGTHS = (266, 146, 93, 78, 231, 231, 39, 43)


# certainty_note measured at 121 characters in production.
PRODUCTION_NOTE = ("Previsione del fornitore per la località confermata: indica condizioni "
                   "probabili, non misura lo stato fisico dell'attività.")


def _weather_read(at, *, claim_lengths=CLAIM_LENGTHS, note=PRODUCTION_NOTE):
    return [
        AgentEvidence(
            owner_id=OWNER, goal_id=GID, step_id="stp_synthetic", kind="weather",
            claim=(f"Località sintetica, voce {i}: " + "x" * n)[:n],
            supports="Usare le fonti pertinenti disponibili",
            provenance=ResultProvenance(
                source_class="external_research", capability="weather.read",
                provider="open-meteo", observed_at=at.isoformat(),
                source_refs=["weather:open-meteo:0.0000,0.0000:synthetic", "place:synthetic:" + "q" * 24],
                freshness="fresh", weather_valid_until=(at + timedelta(hours=3)).isoformat(),
                certainty_note=note[:200],
            ),
            observed_at=at.isoformat(), expires_at=(at + timedelta(hours=3)).isoformat(),
        )
        for i, n in enumerate(claim_lengths)
    ]


def _situation():
    return SituationState(
        id=SID, user_id=OWNER, status="active", revision=1,
        summary="Attività all'aperto sintetica", semantic_kind="Attività sintetica",
        temporal_scope="oggi, fino al momento utile",
        attention_intent="valutare le condizioni per proteggere l'attività",
        desired_outcome="Sapere quando l'attività è pronta senza rischi",
        started_at="2026-10-22T23:47:00+02:00", icon_key="generic",
        tracking_summary="Tengo d'occhio le condizioni per dirti quando è il momento utile o se c'è un rischio.",
        location_label="Località sintetica",
        current_state_summary="L'attività è iniziata da poco all'aperto.",
        constraints=["Non deve essere esposta alla pioggia"],
        facts=["Iniziata alle 23:47", "All'aperto"], assumptions=["Condizioni ordinarie"],
        created_at="2026-10-22T21:47:02+00:00", updated_at="2026-10-22T21:47:02+00:00",
    )


def _payload(evidence, *, capability_repeat=1):
    goal = AutonomousGoal(
        id=GID, owner_id=OWNER, status="active", origin="agent_initiated",
        objective="Sapere quando l'attività è pronta senza rischi",
        desired_outcome="Sapere quando l'attività è pronta senza rischi",
        why_now="La situazione ha un'intenzione di attenzione ancora aperta.",
        success_criteria=[
            "Usare le fonti pertinenti disponibili, senza inventare condizioni o tempi.",
            "Scegliere un controllo successivo solo se ha un'utilità concreta.",
            "Un risultato fisico non si presume dal tempo trascorso.",
            "Consegnare una stima utile del momento d'azione o l'azione necessaria adesso; leggere una fonte da sola non completa il lavoro.",
            "Avvisare quando il risultato utile è plausibilmente raggiunto o compare un rischio.",
        ],
        stop_conditions=["La situazione viene risolta, annullata o l'attenzione revocata."],
        source_kind="situation_followup", source_refs=[f"situation:{SID}"],
        source_situation={"situation_id": SID, "situation_revision": "1",
                          "checkpoint_read_capability": "weather.read",
                          "checkpoint_due_at": NOW.isoformat()},
        rationale="valutare le condizioni per proteggere l'attività", decision_provenance="model",
    ).for_ai()
    situation = _situation()
    goal["source_context"] = [{"ref": f"situation:{SID}", "source": "situation", **situation.context_preview()}]
    goal["source_context_unavailable"] = False
    steps = [
        ActionStep(ordinal=0, intent="Leggere le condizioni attuali", step_type="inspect", capability_needed="weather.read"),
        ActionStep(ordinal=1, intent="Stimare il momento utile e avvisare", step_type="verify"),
    ]
    plan = ActionPlan(owner_id=OWNER, goal_id=GID, steps=steps, summary="Controllo sintetico")
    catalogue = [
        {"capability": name, "status": "available", "can_be_used_now": True,
         "really_does_something": True, "changes_something_in_the_world": facts.writes, "why_not": None}
        for name, facts in sorted(caps._FACTS.items())
    ] * capability_repeat
    return {
        "goal": goal, "plan": plan.for_ai(),
        "local_clock": {"timezone": "Europe/Rome", "local_now": "2026-10-23T02:47:22+02:00"},
        "still_to_do": [s.for_ai() for s in steps],
        "what_has_been_found": evidence, "what_ora_can_do": catalogue,
    }


def _shown(payload):
    text = _dump(payload)
    assert len(text) <= _SITUATION_CONTEXT_CHARS
    return json.loads(text)  # always valid JSON, never a clipped string


def test_production_shape_reaches_the_model_with_situation_and_weather():
    evidence = for_verification(_weather_read(NOW - timedelta(hours=2)) + _weather_read(NOW))
    shown = _shown(_payload(evidence))
    assert shown.get("source_context_unavailable") is not True
    context = shown["goal"]["source_context"][0]
    assert context["started_at"] == "2026-10-22T23:47:00+02:00"
    assert context["location_label"] == "Località sintetica"
    latest = [r for r in shown["what_has_been_found"] if r["observed_at"] == NOW.isoformat()]
    assert len(latest) == len(CLAIM_LENGTHS)
    assert shown["local_clock"]["timezone"] == "Europe/Rome"


def test_oversized_context_keeps_essentials_instead_of_a_blind_stub():
    # A latest read far larger than any real one: protected rows are irreducible
    # for the generic compaction, so the essentials path must take over.
    huge = _weather_read(NOW, claim_lengths=(600,) * 40, note="n" * 200)
    older = _weather_read(NOW - timedelta(hours=2))
    shown = _shown(_payload([e.for_ai() for e in older + huge], capability_repeat=6))
    assert shown.get("source_context_unavailable") is not True
    assert shown["context_truncated"] is True
    assert shown["goal"]["source_context"][0]["started_at"] == "2026-10-22T23:47:00+02:00"
    assert shown["local_clock"]["timezone"] == "Europe/Rome"
    assert [s["intent"] for s in shown["still_to_do"]][-1] == "Stimare il momento utile e avvisare"
    rows = shown["what_has_been_found"]
    assert rows and all(r["observed_at"] == NOW.isoformat() for r in rows)
    assert all(r["capability"] == "weather.read" and r["what_was_found"] for r in rows)
    assert "what_ora_can_do" not in shown


def test_non_situation_goals_keep_their_previous_bound():
    payload = {"goal": {"id": "gol_other", "source_kind": "opportunity"}, "blob": "z" * 20000}
    assert len(_dump(payload)) == 9000


def test_dump_does_not_mutate_the_callers_payload():
    evidence = for_verification(_weather_read(NOW, claim_lengths=(600,) * 40))
    payload = _payload(evidence, capability_repeat=6)
    before = json.dumps(payload, sort_keys=True, default=str)
    _dump(payload)
    assert json.dumps(payload, sort_keys=True, default=str) == before
