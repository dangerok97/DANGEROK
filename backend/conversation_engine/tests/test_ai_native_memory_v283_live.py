"""Opt-in real-provider evals for Memory Proposal & Governed Learning V2.8.3.

All persistence is isolated in memory; credentials and model payloads are never logged.
"""

from pathlib import Path

import pytest
from dotenv import load_dotenv

from conversation_engine.ai_core.loop import run_cognitive_loop
from conversation_engine.models import ConversationSession
from conversation_engine.tests.test_ai_native_memory_v283 import DB, candidate
from life_memory.governance import MemoryGovernanceService
from llm.manager import get_manager

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


async def available():
    return bool((await get_manager().status()).get("configured"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "expected_count"),
    [
        ("Da ora in poi ricordati che preferisco risposte brevi e dirette.", 1),
        ("Domani alle 15 devo passare in farmacia.", 0),
        ("Forse sono una persona che evita sempre i conflitti.", 0),
        ("Per i prossimi due giorni lavoro dalla biblioteca.", 0),
    ],
)
async def test_real_provider_selective_learning(message, expected_count):
    if not await available():
        pytest.skip("No real LLM provider configured")
    db = DB()
    sess = ConversationSession(id="eval", user_id="eval_memory", meta={"ai_core": {}})
    result = await run_cognitive_loop(sess=sess, user_message=message, db=db)
    assert result.ok and result.ora_text
    active = [d for d in db.memories.docs if d.get("status") == "active"]
    assert len(active) == expected_count


@pytest.mark.asyncio
async def test_real_provider_correction_and_cross_session_retrieval():
    if not await available():
        pytest.skip("No real LLM provider configured")
    db = DB()
    user = "eval_correction"
    first = ConversationSession(id="session_a", user_id=user, meta={"ai_core": {}})
    out1 = await run_cognitive_loop(
        sess=first, user_message="Ricordati che preferisco risposte dettagliate.", db=db
    )
    assert out1.ok and len(db.memories.docs) == 1
    second = ConversationSession(id="session_b", user_id=user, meta={"ai_core": {}})
    out2 = await run_cognitive_loop(
        sess=second,
        user_message="Mi correggo: in realtà preferisco risposte concise. Aggiorna ciò che ricordi.",
        db=db,
    )
    assert out2.ok and out2.ora_text
    active = [d for d in db.memories.docs if d.get("status") == "active"]
    superseded = [d for d in db.memories.docs if d.get("status") == "superseded"]
    assert len(active) == 1 and len(superseded) == 1, {
        "context_calls": out2.context_calls,
        "mode": out2.mode,
        "answer": out2.ora_text,
        "trace": out2.trace,
        "records": [
            {
                k: d.get(k)
                for k in (
                    "status",
                    "kind",
                    "authority",
                    "epistemic_status",
                    "supersedes_refs",
                )
            }
            for d in db.memories.docs
        ],
        "observations": [
            {
                "name": observation.get("name"),
                "status": observation.get("status"),
                "context_sources": sorted(
                    {
                        fact.get("source")
                        for fact in (observation.get("payload") or {}).get("facts")
                        or []
                    }
                ),
                "context_statuses": sorted(
                    {
                        fact.get("status")
                        for fact in (observation.get("payload") or {}).get("facts")
                        or []
                    }
                ),
                "source_hints": (
                    (observation.get("payload") or {}).get("context_need") or {}
                ).get("source_hints")
                or [],
            }
            for observation in (
                (second.meta.get("ai_core") or {}).get("observations") or []
            )
        ],
    }
    assert "concise" in active[0]["statement"].lower()


@pytest.mark.asyncio
async def test_real_provider_arbitrary_non_domain_learning():
    if not await available():
        pytest.skip("No real LLM provider configured")
    db = DB()
    sess = ConversationSession(
        id="arbitrary", user_id="eval_arbitrary", meta={"ai_core": {}}
    )
    result = await run_cognitive_loop(
        sess=sess,
        user_message=(
            "Ricordati stabilmente che, quando valutiamo opzioni, voglio vedere prima "
            "il principale compromesso e poi i dettagli."
        ),
        db=db,
    )
    assert (
        result.ok
        and len([d for d in db.memories.docs if d.get("status") == "active"]) == 1
    )


@pytest.mark.asyncio
async def test_real_provider_forget_uses_governed_ref_and_tombstones_only_target():
    if not await available():
        pytest.skip("No real LLM provider configured")
    db = DB()
    user = "eval_forget"
    target = await MemoryGovernanceService(db).apply(
        user_id=user,
        session_id="setup",
        reasoning_epoch="setup",
        candidate=candidate(),
        candidate_index=0,
    )
    other = await MemoryGovernanceService(db).apply(
        user_id=user,
        session_id="setup",
        reasoning_epoch="setup-other",
        candidate=candidate(
            summary="Preferisce esempi concreti",
            identity_key="example_style_preference",
        ),
        candidate_index=0,
    )
    sess = ConversationSession(id="forget_session", user_id=user, meta={"ai_core": {}})
    result = await run_cognitive_loop(
        sess=sess,
        user_message="Dimentica la preferenza che hai memorizzato sulle risposte concise.",
        db=db,
    )
    assert result.ok and result.ora_text
    by_id = {item["id"]: item for item in db.memories.docs}
    assert by_id[target.memory_id]["status"] == "forgotten"
    assert by_id[other.memory_id]["status"] == "active"
