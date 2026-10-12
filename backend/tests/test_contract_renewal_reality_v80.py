"""A6 Reality Gate: contract/policy close to renewal.

Controlled model/provider judgements, real document read and real agent
persistence. No domain router turns "renewal" into work: the opportunity and
plan are model-owned and the code only enforces evidence/authority boundaries.
"""

from unittest.mock import AsyncMock
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import pytest
from test_preparation_passages_v162 import source_claim
from mongomock_motor import AsyncMongoMockClient

from agent import reasoning
from agent.models import ResultProvenance
from agent.providers import CapabilityOutcome, Claim
from agent.service import AgentService
from opportunities.service import OpportunityService
from opportunities import reasoning as opportunity_reasoning
from opportunities.snapshot import _documents


OWNER = "alice"
_LOCAL = ZoneInfo("Europe/Rome")
_TODAY = datetime.now(_LOCAL).date()
_RENEWAL = _TODAY + timedelta(days=15)
_CUTOFF = _TODAY + timedelta(days=5)
_MONTHS = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre")
RENEWAL_LABEL = f"{_RENEWAL.day} {_MONTHS[_RENEWAL.month - 1]} {_RENEWAL.year}"
CUTOFF_LABEL = f"{_CUTOFF.day} {_MONTHS[_CUTOFF.month - 1]} {_CUTOFF.year}"
CUTOFF_EXPIRES = datetime.combine(_CUTOFF, time(23, 59, 59), tzinfo=_LOCAL).isoformat()


def _document(text: str):
    return {
        "id": "policy_v80",
        "user_id": OWNER,
        "filename": "polizza_casa.txt",
        "display_title": "Polizza casa",
        "extracted_text": text,
        "created_at": datetime.now(_LOCAL).isoformat(),
        "updated_at": datetime.now(_LOCAL).isoformat(),
        "archived": False,
        "deleted": False,
    }


async def _snapshot(db):
    docs = await _documents(db, OWNER, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    return {
        "documents": docs,
        "unavailable_sources": [],
        "clock": {"local_date": _TODAY.isoformat(), "timezone": "Europe/Rome"},
        "what_changed": [{
            "source": "documents",
            "kind": "document.updated",
            "entity_ref": "policy_v80",
        }],
    }


@pytest.mark.asyncio
async def test_near_renewal_becomes_grounded_autonomous_comparison(monkeypatch):
    import mongomock.collection
    from agent import providers

    original = mongomock.collection.Collection.find_one_and_update

    def update(self, *args, **kwargs):
        # Existing agent tests already compensate for this mongomock mismatch:
        # production Mongo supports the projection exactly as written.
        kwargs.pop("projection", None)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(mongomock.collection.Collection, "find_one_and_update", update)

    db = AsyncMongoMockClient().test
    await db.agent_runs.create_index("goal_id", unique=True)
    await db.documents.insert_one(_document(
        "POLIZZA CASA. Premio annuo 420 euro. "
        f"Scadenza {RENEWAL_LABEL}. Rinnovo automatico attivo. "
        f"Disdetta entro il {CUTOFF_LABEL}. Copertura incendio e responsabilità civile."
    ))

    state = await _snapshot(db)

    async def opportunity_scan(snapshot, **kwargs):
        preview = snapshot["documents"][0]
        assert preview["ref"] == "document:policy_v80"
        assert RENEWAL_LABEL in preview["unverified_excerpt"]
        assert "Rinnovo automatico attivo" in preview["unverified_excerpt"]
        return {
            "opportunities": [{
                "identity_key": "policy-renewal-home",
                "what": "La polizza casa è vicina al rinnovo.",
                "why_it_matters": (
                    "Prima della finestra di disdetta è utile verificare condizioni "
                    "e alternative senza cambiare nulla automaticamente."
                ),
                "why_now": f"La scadenza dichiarata è il {RENEWAL_LABEL}.",
                "initiative": "prepare",
                "what_i_can_do": (
                    "Posso leggere le condizioni, cercare alternative attuali e "
                    "preparare un confronto con la finestra decisionale."
                ),
                "relevance": "high",
                "urgency": "soon",
                "time_sensitivity": "perishable",
                "confidence": "strong",
                "evidence_refs": ["document:policy_v80"],
                "requires_clarification": False,
                "clarifying_question": "",
                "needs_research": True,
                "research_question": "Alternative attuali compatibili per una polizza casa",
                "valid_until": CUTOFF_EXPIRES,
            }]
        }

    monkeypatch.setattr(opportunity_reasoning, "scan", opportunity_scan)
    scan = await OpportunityService(db).scan(
        OWNER,
        prepared_snapshot=state,
        source_context="reality_gate_v80",
    )
    assert len(scan.created) == 1
    opportunity = scan.created[0]

    monkeypatch.setattr(
        reasoning,
        "decide_goal",
        AsyncMock(return_value={
            "outcome": "create_goal",
            "objective": "Preparare la decisione sul rinnovo della polizza casa",
            "desired_outcome": (
                "Condizioni attuali, almeno un'alternativa applicabile e finestra "
                "decisionale documentate prima della scadenza"
            ),
            "why_now": "La finestra di disdetta indicata nel documento è vicina.",
            "success_criteria": [
                "Le condizioni attuali sono lette dal documento",
                "Le alternative provengono da ricerca esterna",
                "La finestra decisionale resta esplicita",
            ],
            "stop_conditions": ["Il rinnovo risulta già disattivato o la polizza non è più attiva"],
            "reasoning": "Il lavoro è interno e può ridurre il rischio di decidere tardi.",
        }),
    )

    service = AgentService(db)
    monkeypatch.setattr(service, "_note_ambient", AsyncMock())
    monkeypatch.setattr(service, "_consider_visibility", AsyncMock())
    monkeypatch.setattr(service, "_observe_life_change", AsyncMock())

    considered = await service.consider(
        OWNER,
        situation={
            "what": opportunity.semantic_summary,
            "why_it_matters": opportunity.why_it_matters,
        },
        origin="agent_initiated",
        opportunity_id=opportunity.id,
        source_kind="opportunity",
        source_refs=[e.ref for e in opportunity.evidence],
        language="it",
    )
    assert considered["outcome"] == "create_goal"
    goal_id = considered["goal_id"]

    async def make_plan(goal, *, capabilities, context, language="it"):
        assert "document:policy_v80" in goal["source_refs"]
        assert context["today"] == context["local_date"]
        assert context["timezone"] == "Europe/Rome"
        # Planning sees the opaque document handle, not a copied private body.
        assert "source_context" not in context
        return {
            "plan_summary": "Leggere il contratto e cercare un'alternativa attuale.",
            "expected_outcome": "Confronto utilizzabile prima della finestra decisionale.",
            "assumptions": [],
            "known_constraints": ["Nessuna modifica o disdetta automatica."],
            "steps": [
                {
                    "intent": "Leggere integralmente le condizioni rilevanti della polizza",
                    "step_type": "inspect",
                    "capability_needed": "document.read",
                    "input_refs": ["document:policy_v80"],
                    "parameters": {"document_offset": 0},
                    "expected_result": "Premio, rinnovo, scadenza e termine di disdetta",
                    "external_effect": False,
                    "reversibility": "easily",
                },
                {
                    "intent": "Cercare almeno un'alternativa attuale e compatibile",
                    "step_type": "research",
                    "capability_needed": "web.research",
                    "input_refs": [],
                    "parameters": {},
                    "expected_result": (
                        "Alternative attuali per polizza casa con coperture comparabili, "
                        "fonte e condizioni disponibili"
                    ),
                    "external_effect": False,
                    "reversibility": "easily",
                },
            ],
        }

    monkeypatch.setattr(reasoning, "make_plan", make_plan)
    monkeypatch.setattr(
        reasoning,
        "choose_next_action",
        AsyncMock(side_effect=lambda *args, candidates, **kwargs: {
            "decision": "execute",
            "step_id": candidates[0]["id"],
            "reasoning": "È il prossimo passo utile.",
            "asks": "",
            "ask_kind": None,
        }),
    )

    async def research(db_, owner_id, goal, step, *, reuse=True):
        assert owner_id == OWNER
        assert "Alternative attuali" in step.expected_result
        return CapabilityOutcome(
            status="succeeded",
            observation="Trovata un'alternativa attuale con fonte pubblica.",
            provenance=ResultProvenance(
                source_class="external_research",
                capability="web.research",
                provider="research",
                source_refs=["research:policy_alt_v80"],
                freshness="fresh",
                certainty_note="Preventivo finale da verificare col venditore.",
            ),
            claims=[
                Claim(
                    text=(
                        "Alternativa osservata: premio indicativo 360 euro annui, "
                        "coperture incendio e responsabilità civile; eleggibilità "
                        "e preventivo finale da confermare."
                    ),
                    supports="alternativa attuale comparabile",
                )
            ],
            data_ref="research:policy_alt_v80",
        )

    monkeypatch.setattr(providers, "do_research", research)

    prepared_content = (
        f"Polizza attuale: 420 euro annui; rinnovo automatico attivo il {RENEWAL_LABEL}. "
        f"Il documento indica disdetta entro il {CUTOFF_LABEL}. "
        "Alternativa osservata: circa 360 euro annui con coperture incendio e "
        "responsabilità civile; eleggibilità e preventivo finale vanno confermati. "
        f"Finestra decisionale: confrontare e decidere prima del {CUTOFF_LABEL}; "
        "nessuna disdetta o cambio è stato eseguito."
    )

    async def preparation_model(system, payload, *, response_schema=None):
        import json

        data = json.loads(payload)
        if "Audit this draft" in system:
            ids = [row["id"] for row in data["evidence"]]
            assert CUTOFF_LABEL in data["draft"]
            policy_quotes = ["Premio annuo 420 euro.",
                f"Scadenza {RENEWAL_LABEL}. Rinnovo automatico attivo.",
                f"Disdetta entro il {CUTOFF_LABEL}. Copertura incendio e responsabilità civile."]
            alternative_quote = (
                "Alternativa osservata: premio indicativo 360 euro annui, "
                "coperture incendio e responsabilità civile; eleggibilità "
                "e preventivo finale da confermare."
            )
            policy = next(row for row in data["evidence"] if policy_quotes[0] in source_claim(row))
            alternative = next(row for row in data["evidence"] if alternative_quote in source_claim(row))
            return {
                "verified": True,
                "content": prepared_content,
                "evidence_ids": ids,
                "claim_review": [
                    {"claim": "Premio attuale, rinnovo e finestra di disdetta sono indicati nel documento.",
                     "premises": "Le date e le condizioni si riferiscono alla polizza letta.",
                     "support": "stated", "correction": "", "evidence_ids": [policy["id"]],
                     "source_quotes": [{"evidence_id": policy["id"], "quote": quote} for quote in policy_quotes]},
                    {"claim": "L'alternativa osservata è indicativa e richiede conferma di eleggibilità e prezzo finale.",
                     "premises": "La ricerca non è un preventivo personale confermato.",
                     "support": "stated", "correction": "", "evidence_ids": [alternative["id"]],
                     "source_quotes": [{"evidence_id": alternative["id"], "quote": alternative_quote}]},
                ],
            }
        ids = [row["id"] for row in data["evidence"]]
        blob = str(data["evidence"])
        assert "420 euro" in blob
        assert "360 euro" in blob
        return {"content": prepared_content, "evidence_ids": ids}

    monkeypatch.setattr(reasoning, "_ask_model", preparation_model)

    async def verify(goal, *, evidence, **kwargs):
        blob = str(evidence)
        assert "420 euro" in blob
        assert "360 euro" in blob
        assert CUTOFF_LABEL in str(evidence["prepared_result"])
        return {
            "outcome": "achieved",
            "reasoning": "Condizioni, alternativa e finestra decisionale sono documentate con fonti.",
            "what_is_missing": "",
            "revisit_in_hours": None,
        }

    monkeypatch.setattr(reasoning, "verify_goal", verify)

    result = await service.advance(
        OWNER,
        goal_id,
        worker_id="ambient:v80",
        language="it",
    )

    assert result["state"] == "completed"
    saved = await service.repo.get_goal(OWNER, goal_id)
    assert saved is not None
    assert "420 euro" in saved.prepared_text
    assert "360 euro" in saved.prepared_text
    assert CUTOFF_LABEL in saved.prepared_text
    assert saved.prepared_sources
    assert await db.agent_receipts.count_documents({"owner_id": OWNER}) == 0


@pytest.mark.asyncio
async def test_renewal_disabled_is_not_manufactured_into_renewal_work(monkeypatch):
    db = AsyncMongoMockClient().test
    await db.documents.insert_one(_document(
        f"POLIZZA CASA. Scadenza {RENEWAL_LABEL}. "
        "Rinnovo automatico DISATTIVATO su richiesta del cliente. "
        "La copertura terminerà alla scadenza senza rinnovo."
    ))
    state = await _snapshot(db)

    async def opportunity_scan(snapshot, **kwargs):
        preview = snapshot["documents"][0]["unverified_excerpt"]
        assert "DISATTIVATO" in preview
        return {
            "opportunities": [],
            "reason_for_silence": (
                "Il documento dice che il rinnovo automatico è già disattivato; "
                "non c'è una decisione di rinnovo da preparare sulla base di questo fatto."
            ),
        }

    monkeypatch.setattr(opportunity_reasoning, "scan", opportunity_scan)
    scan = await OpportunityService(db).scan(
        OWNER,
        prepared_snapshot=state,
        source_context="reality_gate_v80_negative",
    )

    assert scan.silence is True
    assert scan.created == []
    assert "disattivato" in scan.reason_for_silence.lower()
    assert await db.agent_goals.count_documents({"owner_id": OWNER}) == 0
