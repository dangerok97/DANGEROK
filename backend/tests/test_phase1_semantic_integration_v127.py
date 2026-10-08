"""Prove the journey gate uses the actual final message."""
import pytest
from scripts import phase1_read_provider_eval as runner


@pytest.mark.asyncio
async def test_generated_advice_and_technical_result_are_separate():
    next_decision = await runner._scripted_model_factory()

    async def respond(system, user):
        decision = await next_decision(system, user)
        if decision.get("response_mode") == "answer":
            decision["message_to_user"] = (
                "Percorso 15 minuti; meteo 21 gradi. "
                "Parti ora per evitare il traffico."
            )
        return decision

    report = await runner.run_case(mode="scripted", decide=respond)
    assert report["verdict"]["technical_passed"] is True
    assert report["verdict"]["semantic_gate_passed"] is False
    assert "Parti ora per evitare il traffico" not in report["final_answer"]
    assert report["semantic_review"]["grounding_rewrites"] > 0


@pytest.mark.asyncio
async def test_scripted_reference_stays_technically_distinct():
    report = await runner.run_case(mode="scripted")
    assert report["verdict"]["passed"] is True, report
    assert report["semantic_review"]["automatically_accepted"] is False
    assert report["real_model_executed"] is False
