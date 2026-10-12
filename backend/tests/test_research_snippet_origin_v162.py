"""Retrieval provenance survives real search/research code, with no real I/O.

Provider search and model answers are controlled; the web-search adapter,
research planning/assessment/synthesis, persistence and reload are real.
These tests attest transport, not whether a generated statement is true.
"""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from conversation_engine.ai_core.observations.external import ExternalObservation, ExternalSource
from conversation_engine.ai_core.tools import web_search
from conversation_engine.ai_core.tools.providers.base import ProviderResult, RawHit
from research import reasoning
from research.models import EvidenceSource, ResearchNeed, ResearchRun
from research.repository import ResearchRepository
from research.service import ResearchService


OWNER = "snippet-origin-synthetic-owner"
QUERY = "condizioni pubbliche della nota sintetica"
TEXT = "Il servizio di ricerca attribuisce questa sintesi alla pagina indicata."
URL = "https://example.gov/synthetic-source"
MISSING = object()


async def run_roundtrip(monkeypatch, hit):
    db = AsyncMongoMockClient().snippet_origin_synthetic
    calls, observations, model_inputs = [], [], []
    original_hit = deepcopy(vars(hit))
    monkeypatch.setenv("RESEARCH_ENABLED", "1")
    monkeypatch.setattr(web_search.tavily, "configured", lambda: False)
    monkeypatch.setattr(web_search.brave, "configured", lambda: False)
    monkeypatch.setattr(web_search.gemini_search, "configured", lambda: True)

    async def search(query, *, max_results):
        calls.append((query, max_results))
        return ProviderResult(ok=True, provider="gemini_search", hits=[hit])

    monkeypatch.setattr(web_search.gemini_search, "search", search)
    actual_execute = web_search.execute_web_search

    async def observe(arguments, runtime):
        result = await actual_execute(arguments, runtime)
        observations.append(deepcopy(result.payload))
        return result

    monkeypatch.setattr(web_search, "execute_web_search", observe)

    async def model(system, encoded):
        payload = json.loads(encoded)
        model_inputs.append((system, payload))
        if "what_was_found" in payload:
            # Model-authored classifications cannot overwrite retrieval facts.
            return {
                "sufficiency": "sufficient", "reason": "Risposta sintetica controllata.",
                "source_kind": "verified_primary", "snippet_origin": "search_snippet",
                "sources": [{"source_id": payload["what_was_found"][0]["source_id"],
                    "source_kind": "verified_primary", "snippet_origin": "search_snippet"}],
            }
        if "sources" in payload:
            return {
                "answer": "La ricerca restituisce una sintesi attribuita, da qualificare.",
                "claims": [{"statement": "Una sintesi attribuita è stata restituita.",
                    "supported_by": [payload["sources"][0]["source_id"]],
                    "scope": "general_inference", "certainty": "Risposta controllata."}],
                "snippet_origin": "search_snippet", "source_kind": "verified_primary",
            }
        return {
            "goal": "Leggere il materiale pubblico per la domanda sintetica.",
            "questions": [{"ref": "question", "question": "Quale materiale è disponibile?",
                "queries": [QUERY]}],
        }

    monkeypatch.setattr(reasoning, "_ask_model", model)
    run = await ResearchService(db).run(
        OWNER, ResearchNeed(question="Quale materiale è disponibile?"), allow_reuse=False,
    )
    saved = await ResearchRepository(db).get(OWNER, run.id)
    assert saved and run.status == saved.status == "completed"
    assert await ResearchRepository(db).get("another-owner", run.id) is None
    assert calls == [(QUERY, 5)] and len(observations) == 1 and len(model_inputs) == 3
    assert vars(hit) == original_hit
    assert len(run.sources) == len(saved.sources) == 1
    assert run.sources[0].source_kind is None  # Not adopted from either answer.
    return run, saved, observations[0], model_inputs


def assert_roundtrip(run, saved, observation, inputs, origin):
    external = observation["external"]
    row, = external["sources"]
    assert row["snippet_origin"] == origin
    assert row["snippet"] == TEXT and row["url"] == URL
    assert "provider_internal" not in external
    assert observation["memory_eligible"] is False
    assert run.sources[0].snippet_origin == saved.sources[0].snippet_origin == origin
    assert saved.sources[0].snippet == TEXT and saved.sources[0].url == URL
    assessed = inputs[1][1]["what_was_found"]
    synthesized = inputs[2][1]["sources"]
    for rows in (assessed, synthesized):
        source, = rows
        assert source["source_id"] == saved.sources[0].source_id
        assert source["snippet_origin"] == origin
        assert source["snippet"] == TEXT and source["url"] == URL
    for system, _ in inputs[1:]:
        assert "grounded_model_segment" in system
        assert "generated" in system and "not a literal quotation" in system
        assert "source_kind" in system and "unknown" in system


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["grounded_model_segment", "search_snippet"])
async def test_snippet_origin_survives_search_research_and_both_model_reads(monkeypatch, origin):
    hit = RawHit(title="Synthetic source", url=URL, snippet=TEXT)
    # Gemini also attaches this fact only after associating a segment to a hit.
    hit.snippet_origin = origin
    result = await run_roundtrip(monkeypatch, hit)
    assert_roundtrip(*result, origin)


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [MISSING, None, "verified_primary", {"origin": "search_snippet"}],
    ids=["legacy_missing", "null", "unsupported", "wrong_type"])
async def test_unattested_adapter_origin_stays_unknown_without_changing_text(monkeypatch, origin):
    hit = SimpleNamespace(title="Synthetic source", url=URL, snippet=TEXT)
    if origin is not MISSING:
        hit.snippet_origin = origin
    result = await run_roundtrip(monkeypatch, hit)
    assert_roundtrip(*result, "unknown")


@pytest.mark.asyncio
async def test_old_records_default_to_unknown_and_keep_model_source_kind():
    assert RawHit().snippet_origin == "unknown"
    old = {"title": "Legacy source", "url": URL, "snippet": TEXT}
    source = ExternalSource.model_validate(old)
    assert source.snippet_origin == "unknown"
    external = ExternalObservation(capability="web_search", sources=[source]).to_loop_payload()
    assert external["sources"][0]["snippet_origin"] == "unknown"
    assert external["sources"][0]["snippet"] == TEXT

    db = AsyncMongoMockClient().snippet_origin_legacy
    run = ResearchRun(user_id=OWNER, need=ResearchNeed(question="Legacy question"))
    record = run.model_dump()
    record["sources"] = [{**old, "source_id": "rs_legacy", "source_kind": "primary_source"}]
    await db.research_runs.insert_one(record)
    saved = await ResearchRepository(db).get(OWNER, run.id)
    assert saved.sources[0].snippet_origin == "unknown"
    assert saved.sources[0].source_kind == "primary_source" and saved.sources[0].snippet == TEXT
    assert "snippet_origin" not in (await db.research_runs.find_one({"id": run.id}))["sources"][0]
    # The stronger-looking semantic label remains separate from provenance.
    declared = EvidenceSource(**old, source_kind="primary_source", snippet_origin="grounded_model_segment")
    assert declared.source_kind == "primary_source" and declared.snippet_origin == "grounded_model_segment"
