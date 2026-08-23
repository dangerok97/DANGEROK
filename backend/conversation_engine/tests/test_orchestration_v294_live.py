"""Provider-real end-to-end smoke for V2.9.4 orchestration (opt-in,
quota-bearing).

Deliberately small. V2.9.2 and V2.9.3 already have their own provider-real
gates for the QUALITY of the reasoning and of the attention judgement; this
file only asks whether the assembled pipeline really runs on a live provider,
end to end, from a persisted signal to a persisted decision.

Two scenarios and at most four AI calls total — one that should reach a
decision, and one that proves an idle user costs nothing.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from life_orchestration.service import OrchestrationService  # noqa: E402
from life_signals.service import LifeSignalService  # noqa: E402

pytestmark = pytest.mark.skipif(
    not (os.environ.get("GEMINI_API_KEY") or "").strip(),
    reason="GEMINI_API_KEY absent — provider-real V2.9.4 not executed",
)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")

_VALID_DELIVERIES = {"silent", "defer", "home", "ask_user", "propose_action", "notify"}


def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _cleanup(db, user_id):
    for col in (
        "life_change_signals", "life_impact_assessments",
        "life_attention_decisions", "life_orchestration_state",
        "proactive_suggestions", "proactive_learning", "situations",
    ):
        await db[col].delete_many({"user_id": user_id})


@pytest.fixture(autouse=True)
def _freeze_local_hour(monkeypatch):
    """Pin the attention clock so the smoke does not depend on what time the
    suite happens to run — the gate's quiet-hours behaviour has its own
    deterministic coverage."""
    import life_attention.context as ctx_mod

    async def _fixed(db, user_id):
        return datetime.now(timezone.utc), "Europe/Rome", 15

    monkeypatch.setattr(ctx_mod, "resolve_local_time", _fixed)


@pytest.mark.asyncio
async def test_provider_real_pipeline_runs_end_to_end():
    """A persisted signal really becomes an assessment and a decision, using
    the live Provider Manager for both reasoning steps."""
    client, db = _db()
    user = f"u_live_{uuid.uuid4().hex[:8]}"
    try:
        from situations.models import SituationUpdate
        from situations.service import SituationService

        # Real Situation so the Context Broker has genuine evidence to find.
        created = await SituationService(db).apply(
            user_id=user, session_id="s_live", reasoning_epoch="ep_live",
            update=SituationUpdate(
                operation="create",
                summary="Sto organizzando una mostra fotografica di quartiere per l'autunno.",
            ),
        )
        sid = created["situation"]["id"]
        await LifeSignalService(db).emit(
            user_id=user, source_ref=f"situation:{sid}",
            source_system="situation", change_kind="created",
            dedupe_key=f"situation:{sid}:r1",
        )

        report = await OrchestrationService(db).run_user_pass(user)

        assert report.ran is True
        assert report.impact_runs == 1
        assert report.ai_calls >= 1
        assert not report.failures, f"pipeline reported failures: {report.failures}"

        # The signal was really consumed by a really-persisted assessment.
        assert await LifeSignalService(db).list_pending(user) == []
        assessments = await db.life_impact_assessments.find(
            {"user_id": user}, {"_id": 0},
        ).to_list(10)
        assert len(assessments) == 1
        assert assessments[0]["focal_refs"] == [f"situation:{sid}"]

        # ...and attention really reached a typed decision.
        assert report.attention_runs == 1
        decisions = await db.life_attention_decisions.find(
            {"user_id": user}, {"_id": 0},
        ).to_list(10)
        assert len(decisions) == 1
        decision = decisions[0]
        assert decision["delivery"] in _VALID_DELIVERIES
        # The system's choice is never louder than the model's.
        from life_attention.models import DELIVERY_ORDER

        assert DELIVERY_ORDER.index(decision["delivery"]) <= DELIVERY_ORDER.index(
            decision["ai_delivery"]
        )
        # A silent decision surfaces nothing; anything louder went through the
        # existing Proactive Engine gate rather than around it.
        surfaced = await db.proactive_suggestions.count_documents({"user_id": user})
        if decision["delivery"] == "silent":
            assert surfaced == 0
        else:
            assert surfaced <= 1
    finally:
        await _cleanup(db, user)
        client.close()


@pytest.mark.asyncio
async def test_provider_real_idle_user_costs_nothing():
    """The cost guarantee, checked against the live provider path: with
    nothing pending, the pass must return without calling anything."""
    client, db = _db()
    user = f"u_live_{uuid.uuid4().hex[:8]}"
    try:
        report = await OrchestrationService(db).run_user_pass(user)
        assert report.ran is False
        assert report.ai_calls == 0
        assert report.skipped_reason == "no_pending_work"
        # Not even a lease document was written for an idle user.
        assert await db.life_orchestration_state.count_documents({"user_id": user}) == 0
    finally:
        await _cleanup(db, user)
        client.close()
