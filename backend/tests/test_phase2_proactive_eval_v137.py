"""V137: isolated proactive gate must preserve both useful action and silence."""
import pytest

from scripts.phase2_proactive_live_eval import (
    SCENARIOS, main, run_case,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", list(SCENARIOS))
async def test_scripted_proactive_admission_uses_real_repository_and_wakes(scenario):
    report = await run_case(scenario, mode="scripted")
    assert report["verdict"]["passed"], report
    assert report["scope"] == "isolated_synthetic_no_real_user_or_world_effects"
    assert report["llm_requests"] == 0
    assert report["action_intents"] == 0
    if scenario == "actionable_conflict":
        assert report["persisted_goals"] == report["pending_wakes"] == 1
    else:
        assert report["persisted_goals"] == report["pending_wakes"] == 0


@pytest.mark.asyncio
async def test_aggregate_scripted_uses_no_real_credentials(capsys):
    code = await main(mode="scripted", scenario="all")
    assert code == 0
    out = capsys.readouterr().out
    assert "ORA_PHASE2_PROACTIVE_SUMMARY" in out
    assert '"passed": true' in out
    assert '"real_model_executed": false' in out


@pytest.mark.asyncio
async def test_live_mode_refuses_to_claim_work_without_model_key(monkeypatch, capsys):
    for name in ("GEMINI_API_KEY", "GEMINI_API_KEY_2", "OPENAI_API_KEY",
                 "GROQ_API_KEY", "MISTRAL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    code = await main(mode="live", scenario="actionable_conflict")
    assert code == 3
    assert "live_credentials_unavailable" in capsys.readouterr().out
