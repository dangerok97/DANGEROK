"""
V3.4 — going and finding out.

The thing being tested is a division of labour. The model decides whether to
look, what to look for, how to word the searches, whether what came back
settles the question, whether two sources disagree, whether to look again and
when to stop. The code holds the rope: it caps the rounds, refuses to run the
same search twice, keeps personal identifiers out of what leaves the machine,
writes down what was fetched and when, and hands the result back to the
reasoning that asked.

So the model is stubbed here, and what is asserted is that the code did not
quietly make any of those decisions on its own.

The scenarios below are a loan, an energy tariff and a language course. They
are three because one would prove nothing: the point is that the same code
runs all of them and contains no trace of any of them.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


def _now():
    return datetime.now(timezone.utc)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


# ---------------------------------------------------------------------------
# A model that says what a test needs it to say, and a search that returns what
# the test put there. Neither knows anything about the other.
# ---------------------------------------------------------------------------

class FakeModel:
    """Answers in order. Records what it was asked, so privacy can be checked."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    async def __call__(self, system, user):
        self.prompts.append(user)
        return self.answers.pop(0) if self.answers else None


def _plan(**over):
    plan = {
        "goal": "capire cosa è disponibile adesso",
        "reason": "quello che serve cambia nel tempo e non è nei miei archivi",
        "known_context": ["già detto dalla persona"],
        "unknowns": ["le condizioni correnti"],
        "questions": [
            {
                "ref": "q1",
                "question": "quali condizioni sono disponibili adesso",
                "evidence_needed": "valori pubblicati di recente",
                "queries": ["condizioni correnti", "requisiti aggiornati"],
            }
        ],
        "preferred_source_characteristics": ["pubblicazioni ufficiali recenti"],
        "freshness_requirement": "ultimi giorni: questi valori cambiano spesso",
        "valid_for_hours": 12,
        "geographic_scope": "Italia",
        "stop_condition": "quando due fonti recenti concordano",
        "disclosable_context": ["l'importo indicativo"],
        "withheld_context": ["il nome della persona: non cambia la risposta"],
    }
    plan.update(over)
    return plan


def _sufficient(**over):
    out = {"sufficiency": "sufficient", "reason": "le fonti rispondono", "missing_evidence": [], "conflicts": [], "next_queries": []}
    out.update(over)
    return out


def _synthesis(source_ids, **over):
    out = {
        "answer": "Ecco cosa risulta adesso.",
        "claims": [
            {
                "statement": "un valore corrente risulta in un certo intervallo",
                "supported_by": list(source_ids),
                "certainty": "coerente fra le fonti",
                "conflicts_with": [],
            }
        ],
        "unresolved": [],
        "caveats": ["può cambiare"],
    }
    out.update(over)
    return out


class FakeSearch:
    """Returns hits per query. Fails for whatever the test says fails."""

    def __init__(self, hits_by_query=None, fail_queries=(), default_hits=None):
        self.hits_by_query = hits_by_query or {}
        self.fail_queries = set(fail_queries)
        self.default_hits = default_hits
        self.queries = []

    async def __call__(self, arguments, runtime):
        from conversation_engine.ai_core.models import Observation

        query = arguments.get("query") or ""
        self.queries.append(query)
        if query in self.fail_queries:
            return Observation(
                kind="tool", name="web_search", status="failed",
                payload={"external": {"failure_code": "NETWORK", "sources": []}},
            )
        hits = self.hits_by_query.get(query)
        if hits is None:
            hits = self.default_hits if self.default_hits is not None else [
                {
                    "title": f"Risultato per {query}",
                    "url": f"https://esempio.example/{abs(hash(query)) % 999}",
                    "snippet": "un dato pubblicato",
                    "authority_hint": "REPUTABLE_SECONDARY",
                }
            ]
        return Observation(
            kind="tool", name="web_search", status="ok" if hits else "empty",
            payload={"external": {"sources": hits}},
        )


def _install(monkeypatch, model, search):
    import research.reasoning as reasoning
    from conversation_engine.ai_core.tools import web_search

    monkeypatch.setattr(reasoning, "_ask_model", model)
    monkeypatch.setattr(web_search, "execute_web_search", search)


def _need(question="quanto costa adesso", **over):
    from research.models import ResearchNeed

    return ResearchNeed(question=question, purpose="serve per il passo corrente", **over)


# ---------------------------------------------------------------------------
# The plan is the model's
# ---------------------------------------------------------------------------

def test_the_plan_comes_back_shaped_or_not_at_all(monkeypatch):
    """
    Structured output, validated and nothing more. What the model wrote is
    kept as written; what it did not write is not invented here.
    """
    import research.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", FakeModel([_plan()]))
    plan = _run(reasoning.plan_research(_need(), context_lines=[]))
    assert plan is not None
    assert plan.goal == "capire cosa è disponibile adesso"
    assert plan.questions[0].queries == ["condizioni correnti", "requisiti aggiornati"]
    assert plan.valid_for_hours == 12


def test_a_plan_with_nothing_to_run_is_not_a_plan(monkeypatch):
    import research.reasoning as reasoning

    empty = _plan(questions=[{"ref": "q1", "question": "x", "evidence_needed": "", "queries": []}])
    monkeypatch.setattr(reasoning, "_ask_model", FakeModel([empty]))
    assert _run(reasoning.plan_research(_need(), context_lines=[])) is None


def test_when_the_model_says_nothing_the_run_fails_honestly(monkeypatch):
    """
    No deterministic fallback. A plan written by code is exactly what this
    phase exists not to have, so the alternative to the model planning is
    saying so — never ORA searching something it chose by rule.
    """
    async def body():
        client, db = await _db()
        try:
            _install(monkeypatch, FakeModel([None]), FakeSearch())
            from research.service import ResearchService

            run = await ResearchService(db).run(f"u_{uuid.uuid4().hex[:8]}", _need(), allow_reuse=False)
            assert run.status == "failed"
            assert run.plan is None
            assert run.queries_run == []
            assert "Non sono riuscita" in run.outcome_note
        finally:
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------

def test_the_searches_run_are_the_ones_the_model_wrote(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_res_{uuid.uuid4().hex[:8]}"
        try:
            search = FakeSearch()
            _install(
                monkeypatch,
                FakeModel([_plan(), _sufficient(), _synthesis(["placeholder"])]),
                search,
            )
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert search.queries == ["condizioni correnti", "requisiti aggiornati"]
            assert run.queries_run == search.queries
            assert run.iterations == 1
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_not_enough_means_look_again_with_what_the_model_asks_for(monkeypatch):
    """
    The second round is the model's too: it says what is still missing and
    what to search for it. The code only refuses to repeat a search.
    """
    async def body():
        client, db = await _db()
        user = f"u_res2_{uuid.uuid4().hex[:8]}"
        try:
            search = FakeSearch()
            _install(
                monkeypatch,
                FakeModel([
                    _plan(),
                    {
                        "sufficiency": "insufficient",
                        "reason": "nessuna fonte parla del periodo giusto",
                        "missing_evidence": ["il dato aggiornato"],
                        "conflicts": [],
                        # One repeat and one genuinely new search.
                        "next_queries": ["condizioni correnti", "dato aggiornato ottobre"],
                    },
                    _sufficient(),
                    _synthesis(["x"]),
                ]),
                search,
            )
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert run.iterations == 2
            assert search.queries == [
                "condizioni correnti", "requisiti aggiornati", "dato aggiornato ottobre",
            ], search.queries
            assert run.queries_run.count("condizioni correnti") == 1
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_the_rounds_are_capped_and_the_result_is_called_what_it_is(monkeypatch):
    """
    A model that never declares itself satisfied still has to stop. The cap is
    a cost limit, so what it produces is `insufficient` — not an answer
    dressed up as a finished one.
    """
    async def body():
        client, db = await _db()
        user = f"u_cap_{uuid.uuid4().hex[:8]}"
        try:
            never = {
                "sufficiency": "insufficient", "reason": "ancora no",
                "missing_evidence": ["altro"], "conflicts": [],
                "next_queries": ["a", "b", "c", "d", "e", "f", "g", "h", "i"],
            }
            search = FakeSearch()
            _install(monkeypatch, FakeModel([_plan(), never, never, never, _synthesis(["x"])]), search)
            from research.service import ResearchService, MAX_ITERATIONS, MAX_QUERIES

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert run.iterations <= MAX_ITERATIONS
            assert len(run.queries_run) <= MAX_QUERIES
            assert run.status == "insufficient"
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Evidence, sources, citations
# ---------------------------------------------------------------------------

def test_only_what_a_claim_rests_on_may_be_shown_as_a_source(monkeypatch):
    """
    Several sources came back; the claim used one of them. Citing the rest
    would be claiming to have relied on something ORA ignored.
    """
    async def body():
        client, db = await _db()
        user = f"u_cite_{uuid.uuid4().hex[:8]}"
        try:
            import json as _json

            import research.reasoning as reasoning
            from conversation_engine.ai_core.tools import web_search

            hits = [
                {"title": "Usata", "url": "https://a.example/1", "snippet": "il dato"},
                {"title": "Non usata", "url": "https://b.example/2", "snippet": "altro"},
            ]
            used_id = {}
            step = {"n": 0}

            async def model(system, user_payload):
                step["n"] += 1
                if step["n"] == 1:
                    return _plan()
                if step["n"] == 2:
                    return _sufficient()
                # The synthesis names real ids, which is the whole point: the
                # model can only cite what it was actually shown.
                shown = _json.loads(user_payload)["sources"]
                used_id["value"] = shown[0]["source_id"]
                return _synthesis([shown[0]["source_id"]])

            monkeypatch.setattr(reasoning, "_ask_model", model)
            monkeypatch.setattr(
                web_search, "execute_web_search", FakeSearch(default_hits=hits)
            )
            from research.service import ResearchService, public_research_payload

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)

            assert len(run.sources) > 1, "the test needs more than one source to prove anything"
            citable = run.citable_sources()
            assert len(citable) == 1, citable
            cited = next(s for s in run.sources if s.source_id == used_id["value"])
            assert citable[0]["url"] == cited.url
            assert public_research_payload(run)["sources"] == citable
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_a_claim_with_no_source_never_becomes_a_finding(monkeypatch):
    """The model talking is not evidence, however plausible it sounds."""
    import research.reasoning as reasoning
    from research.models import EvidenceSource, ResearchAssessment, ResearchPlan

    sources = [EvidenceSource(source_id="rs_real", url="https://x.example", title="T")]
    monkeypatch.setattr(
        reasoning,
        "_ask_model",
        FakeModel([{
            "answer": "…",
            "claims": [
                {"statement": "sostenuta", "supported_by": ["rs_real"], "certainty": ""},
                {"statement": "inventata", "supported_by": [], "certainty": ""},
                {"statement": "fonte immaginaria", "supported_by": ["rs_nope"], "certainty": ""},
            ],
            "unresolved": [], "caveats": [],
        }]),
    )
    synthesis = _run(reasoning.synthesize(
        plan=ResearchPlan(goal="g"), sources=sources, assessment=ResearchAssessment(),
    ))
    assert [c.statement for c in synthesis.claims] == ["sostenuta"]


def test_the_run_is_written_down_and_belongs_to_one_person(monkeypatch):
    async def body():
        client, db = await _db()
        mine = f"u_own_{uuid.uuid4().hex[:8]}"
        yours = f"u_own_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([_plan(), _sufficient(), _synthesis(["x"])]), FakeSearch())
            from research.repository import ResearchRepository
            from research.service import ResearchService

            run = await ResearchService(db).run(mine, _need(), allow_reuse=False)
            repo = ResearchRepository(db)
            assert (await repo.get(mine, run.id)) is not None
            assert (await repo.get(yours, run.id)) is None, "a run was readable by the wrong person"

            stored = await repo.get(mine, run.id)
            assert stored.plan is not None and stored.plan.goal
            assert stored.queries_run and stored.started_at and stored.valid_until
        finally:
            await db.research_runs.delete_many({"user_id": mine})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Conflict, failure, reuse
# ---------------------------------------------------------------------------

def test_sources_that_disagree_are_reported_as_disagreeing(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_conf_{uuid.uuid4().hex[:8]}"
        try:
            conflicted = {
                "sufficiency": "conflicted",
                "reason": "due fonti danno numeri diversi",
                "missing_evidence": [],
                "conflicts": [{
                    "about": "il valore corrente",
                    "positions": ["una fonte dice X", "l'altra dice Y"],
                    "source_ids": [],
                    "resolution": "non riesco a stabilire quale sia aggiornata",
                    "resolved": False,
                }],
                "next_queries": [],
            }
            _install(monkeypatch, FakeModel([_plan(), conflicted, _synthesis(["x"])]), FakeSearch())
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert run.status == "partial"
            assert "non concordano" in run.outcome_note
            payload = run.to_reasoning_payload()
            assert payload["conflicts"] and payload["conflicts"][0]["about"] == "il valore corrente"
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_a_search_that_fails_is_never_narrated_as_a_search_that_worked(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_fail_{uuid.uuid4().hex[:8]}"
        try:
            search = FakeSearch(fail_queries=["condizioni correnti", "requisiti aggiornati"])
            _install(monkeypatch, FakeModel([_plan()]), search)
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert run.sources == []
            assert run.status == "failed"
            assert run.failures
            assert run.to_reasoning_payload()["evidence_is_real"] is False
            assert run.citable_sources() == []
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_one_source_unreachable_still_leaves_the_rest(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_part_{uuid.uuid4().hex[:8]}"
        try:
            search = FakeSearch(fail_queries=["condizioni correnti"])
            _install(monkeypatch, FakeModel([_plan(), _sufficient(), _synthesis(["x"])]), search)
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert run.sources, "one failed search took the whole run down"
            assert any(f.startswith("search_failed") for f in run.failures)
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_something_already_looked_up_is_offered_and_the_model_decides(monkeypatch):
    """
    The code discards what has expired — arithmetic. Whether what is left
    answers the new question is meaning, so the model is asked, and its answer
    is what happens.
    """
    async def body():
        client, db = await _db()
        user = f"u_reuse_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([_plan(), _sufficient(), _synthesis(["x"])]), FakeSearch())
            from research.service import ResearchService

            service = ResearchService(db)
            first = await service.run(user, _need(), allow_reuse=False)
            assert first.status == "completed"

            # Second ask: the model says the earlier run answers it.
            search = FakeSearch()
            _install(monkeypatch, FakeModel([{"reuse_run_id": first.id, "why": "stessa domanda"}]), search)
            again = await service.run(user, _need(), allow_reuse=True)
            assert again.id == first.id
            assert search.queries == [], "it searched again despite reusing"

            # And when the model says no, it goes and looks.
            search2 = FakeSearch()
            _install(
                monkeypatch,
                FakeModel([{"reuse_run_id": None}, _plan(), _sufficient(), _synthesis(["x"])]),
                search2,
            )
            third = await service.run(user, _need("una domanda diversa"), allow_reuse=True)
            assert third.id != first.id
            assert search2.queries
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_an_expired_run_is_not_even_offered(monkeypatch):
    """The one thing the code decides about reuse: whether a moment has passed."""
    async def body():
        client, db = await _db()
        user = f"u_exp_{uuid.uuid4().hex[:8]}"
        try:
            from research.models import ResearchNeed, ResearchRun
            from research.repository import ResearchRepository

            stale = ResearchRun(
                user_id=user,
                need=ResearchNeed(question="vecchia"),
                status="completed",
                valid_until=(_now() - timedelta(hours=1)).isoformat(),
            )
            fresh = ResearchRun(
                user_id=user,
                need=ResearchNeed(question="recente"),
                status="completed",
                valid_until=(_now() + timedelta(hours=1)).isoformat(),
            )
            repo = ResearchRepository(db)
            await repo.save(stale)
            await repo.save(fresh)
            offered = {r.id for r in await repo.still_valid(user)}
            assert fresh.id in offered
            assert stale.id not in offered
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------

def test_what_goes_out_is_what_the_search_needs_and_not_who_asked(monkeypatch):
    """
    The model is asked to say what may be disclosed and what must not. The
    sanitizer underneath is a backstop for the same rule, and it is what stops
    an identifier reaching a provider even if a plan asked for it.
    """
    from conversation_engine.ai_core.tools.sanitize import sanitize_external_query

    clean, reason = sanitize_external_query(
        "condizioni per mario.rossi@example.com con IBAN IT60X0542811101000000123456"
    )
    assert reason == "ok"
    assert "@" not in clean and "IT60X" not in clean

    rejected, why = sanitize_external_query(
        "mi chiamo Mario Rossi e abito a Tarquinia in via Roma 12 e vorrei sapere "
        "quali condizioni posso ottenere con il mio reddito"
    )
    assert rejected is None and why == "overpersonal_query"


def test_the_plan_says_what_it_is_prepared_to_disclose(monkeypatch):
    import research.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", FakeModel([_plan()]))
    plan = _run(reasoning.plan_research(_need(), context_lines=["reddito mensile 2200"]))
    assert plan.disclosable_context and plan.withheld_context


# ---------------------------------------------------------------------------
# Research is evidence, not work
# ---------------------------------------------------------------------------

def test_research_creates_no_work_anywhere(monkeypatch):
    """
    The V3.3 rule, extended: finding something out is not a reason to put
    something in front of somebody. A run leaves the day untouched, and what
    it found goes back to the reasoning that asked, which decides through the
    paths that already exist.
    """
    async def body():
        client, db = await _db()
        user = f"u_work_{uuid.uuid4().hex[:8]}"
        try:
            for col in ("documents", "tasks", "decisions", "home_item_state", "reminders", "users"):
                await db[col].delete_many({"user_id": user})
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})

            _install(monkeypatch, FakeModel([_plan(), _sufficient(), _synthesis(["x"])]), FakeSearch())
            from home.service import HomeService
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(), allow_reuse=False)
            assert run.status == "completed"

            svc = HomeService(db)
            await svc.ensure_indexes()
            home = await svc.build_home(user)
            assert home.primary_focus is None, home.primary_focus
            assert all(not g.items for g in home.priorities), "research put something in the day"
            assert not home.open_questions
            for col in ("tasks", "decisions", "reminders"):
                assert await db[col].count_documents({"user_id": user}) == 0, col
        finally:
            for col in ("documents", "tasks", "decisions", "home_item_state", "reminders", "users"):
                await db[col].delete_many({"user_id": user})
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_nothing_in_research_writes_work_or_memory():
    """
    Structural, so it stays true: the module never reaches for the collections
    that hold somebody's day, and never marks its findings as memory.
    """
    forbidden = ("home_item", "tasks", "reminders", "notifications", "attention", "decisions")
    for name in ("service.py", "repository.py", "reasoning.py", "models.py"):
        code = (HERE / "research" / name).read_text(encoding="utf-8")
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    code = code.replace(doc, "")
        body = "\n".join(l for l in code.splitlines() if not l.strip().startswith("#"))
        for word in forbidden:
            assert word not in body, f"research/{name} touches {word}"

    loop = (HERE / "conversation_engine" / "ai_core" / "loop.py").read_text(encoding="utf-8")
    branch = loop[loop.index('if mode == "research":'):loop.index('if mode == "context":')]
    assert '"memory_eligible": False' in branch


def test_the_work_it_belongs_to_is_carried_through_untouched(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_refs_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([_plan(), _sufficient(), _synthesis(["x"])]), FakeSearch())
            from research.service import ResearchService

            run = await ResearchService(db).run(
                user, _need(),
                session_id="sess_1", plan_id="plan_1",
                plan_item_id="item_1", situation_ref="sit_1", reasoning_epoch=7,
                allow_reuse=False,
            )
            assert (run.session_id, run.plan_id, run.plan_item_id) == ("sess_1", "plan_1", "item_1")
            assert run.situation_ref == "sit_1" and run.reasoning_epoch == 7
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_saving_the_same_run_twice_leaves_one_run(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_idem_{uuid.uuid4().hex[:8]}"
        try:
            from research.models import ResearchNeed, ResearchRun
            from research.repository import ResearchRepository

            run = ResearchRun(user_id=user, need=ResearchNeed(question="q"))
            repo = ResearchRepository(db)
            await repo.save(run)
            run.status = "completed"
            await repo.save(run)
            assert await db.research_runs.count_documents({"id": run.id}) == 1
            assert (await repo.get(user, run.id)).status == "completed"
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# The same code, three different lives
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "question,queries",
    [
        ("quali condizioni di finanziamento sono disponibili adesso",
         ["tassi mutuo ottobre", "requisiti finanziamento"]),
        ("quanto costa oggi l'energia per un consumo come questo",
         ["prezzo kwh mercato libero", "tariffe gas ottobre"]),
        ("quanto dura e quanto costa una certificazione di lingua",
         ["costo esame certificazione", "sessioni disponibili"]),
    ],
)
def test_the_same_engine_runs_lives_that_have_nothing_in_common(monkeypatch, question, queries):
    async def body():
        client, db = await _db()
        user = f"u_uni_{uuid.uuid4().hex[:8]}"
        try:
            plan = _plan(questions=[{
                "ref": "q1", "question": question, "evidence_needed": "dati recenti",
                "queries": queries,
            }])
            search = FakeSearch()
            _install(monkeypatch, FakeModel([plan, _sufficient(), _synthesis(["x"])]), search)
            from research.service import ResearchService

            run = await ResearchService(db).run(user, _need(question), allow_reuse=False)
            assert search.queries == queries
            assert run.status in ("completed", "partial")
            assert run.sources
        finally:
            await db.research_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Neutrality
# ---------------------------------------------------------------------------

_SUBJECTS = (
    "mortgage", "mutuo", "insurance", "polizza", "assicuraz", "energy", "energia",
    "utility", "bolletta", "job", "lavoro", "travel", "viaggio", "school", "scuola",
    "loan", "prestito", "tariff", "tariffa", "bank", "banca",
)


def _production_code(path: Path) -> str:
    """The file with its prose removed — guards must not trip on explanations."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))


def test_no_symbol_in_research_is_named_after_a_subject():
    for path in (HERE / "research").glob("*.py"):
        tree = ast.parse(_production_code(path))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.ClassDef):
                name = node.name
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                name = node.id
            if not name:
                continue
            for subject in _SUBJECTS:
                assert subject not in name.lower(), f"{path.name}:{name}"


def test_no_subject_is_written_anywhere_in_the_research_code():
    """
    The strongest form of the rule, and the one that actually holds: no part of
    a life is ever *named* in production research code. Not in a condition, not
    in a dict key, not in a query it would append "just for this case".

    A weaker guard, looking only for `== "mutuo"` and friends, let this through:

        if "mutuo" in need.question.lower():
            pending.append("tassi mutuo oggi")

    which is the entire thing this phase is not allowed to be. If a subject
    cannot be written down here, it cannot be branched on.
    """
    for path in (HERE / "research").glob("*.py"):
        tree = ast.parse(_production_code(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            text = node.value.lower()
            for subject in _SUBJECTS:
                assert subject not in text, (
                    f"{path.name} contains the subject {subject!r} in a string: "
                    f"{node.value[:60]!r}"
                )


def test_research_holds_no_map_from_a_subject_to_a_query():
    """
    The failure this prevents has a shape: a dict, or a chain of ifs, that
    turns "this is about X" into "so search for Y". Either one would move the
    decision out of the model and into the file.
    """
    for path in (HERE / "research").glob("*.py"):
        code = _production_code(path)
        assert "QUERY_TEMPLATES" not in code
        assert not re.search(r"queries\s*=\s*\{", code), path.name
        for subject in _SUBJECTS:
            assert not re.search(rf'==\s*["\'][^"\']*{subject}', code, re.I), f"{path.name}: {subject}"
            assert not re.search(rf'in\s*\(?["\'][^"\']*{subject}', code, re.I), f"{path.name}: {subject}"


def test_research_names_no_website_it_would_rather_read():
    for path in (HERE / "research").glob("*.py"):
        code = _production_code(path)
        hosts = re.findall(
            r"[a-z0-9][a-z0-9-]*\.(?:com|it|org|net|eu|gov|io)", code, re.I
        )
        assert not hosts, f"{path.name} names {hosts}"
        assert "http://" not in code and "https://" not in code, path.name


def test_the_queries_are_never_built_by_the_code():
    """
    Nothing here composes a search string. Every query that leaves is a
    string the model wrote, carried through unchanged — which is also why
    dedupe normalises a copy rather than editing the query itself.
    """
    code = _production_code(HERE / "research" / "service.py")
    assert 'f"' not in code.split("def _search_all")[1].split("def ")[0].replace(
        'f"search_error:{type(e).__name__}"', ""
    ).replace('f"search_failed:{payload.get(\'failure_code\') or \'UNKNOWN\'}"', ""), (
        "a query is being assembled in code"
    )


def test_the_decision_to_go_and_look_lives_in_the_model_contract():
    """
    §3: it is declared by the reasoning, in the same object as everything else
    it decides — not inferred by the loop from a plan type or a word.
    """
    models = _production_code(HERE / "conversation_engine" / "ai_core" / "models.py")
    assert "research_need: Optional[ResearchNeed]" in models
    assert '"research"' in models

    loop = _production_code(HERE / "conversation_engine" / "ai_core" / "loop.py")
    branch = loop[loop.index('if mode == "research":'):loop.index('if mode == "context":')]
    assert "decision.research_need" in branch
    for trigger in ("keyword", "document_type", "domain", "plan_type"):
        assert trigger not in branch, f"the loop is inferring research from {trigger}"


# ---------------------------------------------------------------------------
# A verdict on a person needs to know the person
# ---------------------------------------------------------------------------

def test_a_conclusion_about_this_person_that_names_nothing_about_them_is_dropped(monkeypatch):
    """
    Found in the mortgage QA. ORA read the market correctly and then wrote
    "essendo dipendente a tempo indeterminato hai un profilo lavorativo solido
    e standard per l'accesso al credito" — a verdict on somebody, from pages
    about a market, holding one fact about them and knowing nothing of their
    income or what else they owe.

    What such a conclusion needs is the model's judgement and is nowhere in
    this file. What is checked here is only that it said what it used.
    """
    import research.reasoning as reasoning
    from research.models import EvidenceSource, ResearchAssessment, ResearchPlan

    sources = [EvidenceSource(source_id="rs_1", url="https://x.example", title="T")]
    monkeypatch.setattr(reasoning, "_ask_model", FakeModel([{
        "answer": "…",
        "claims": [
            {
                "statement": "le rilevazioni mostrano tassi in un certo intervallo",
                "supported_by": ["rs_1"], "scope": "external_fact",
            },
            {
                "statement": "un contratto stabile e' generalmente valutato positivamente",
                "supported_by": ["rs_1"], "scope": "general_inference",
            },
            {
                "statement": "hai un profilo solido e standard per l'accesso al credito",
                "supported_by": ["rs_1"], "scope": "person_specific",
                "person_evidence_used": [],
            },
        ],
        "unresolved": [], "caveats": [],
    }]))
    synthesis = _run(reasoning.synthesize(
        plan=ResearchPlan(goal="g"), sources=sources, assessment=ResearchAssessment(),
    ))
    scopes = [c.scope for c in synthesis.claims]
    assert scopes == ["external_fact", "general_inference"], [c.statement for c in synthesis.claims]


def test_the_same_conclusion_stands_when_it_says_what_it_rests_on(monkeypatch):
    """The rule is not a ban on personal conclusions. It is a ban on unearned ones."""
    import research.reasoning as reasoning
    from research.models import EvidenceSource, ResearchAssessment, ResearchPlan

    sources = [EvidenceSource(source_id="rs_1", url="https://x.example", title="T")]
    monkeypatch.setattr(reasoning, "_ask_model", FakeModel([{
        "answer": "…",
        "claims": [{
            "statement": "con questi numeri rientri nei parametri che le fonti riportano",
            "supported_by": ["rs_1"], "scope": "person_specific",
            "person_evidence_used": [
                "reddito netto mensile dichiarato", "nessun altro finanziamento in corso",
                "importo e durata richiesti",
            ],
        }],
        "unresolved": [], "caveats": [],
    }]))
    synthesis = _run(reasoning.synthesize(
        plan=ResearchPlan(goal="g"), sources=sources, assessment=ResearchAssessment(),
    ))
    assert len(synthesis.claims) == 1
    assert synthesis.claims[0].scope == "person_specific"
    assert len(synthesis.claims[0].person_evidence_used) == 3


def test_what_a_personal_conclusion_needs_is_never_listed_in_the_code():
    """
    No schema of required fields for any subject. The model decides what its
    own conclusion would need; the code only checks that it named something.
    """
    code = _production_code(HERE / "research" / "reasoning.py")

    # The enforcement is exactly one line, and it asks whether the model named
    # anything at all — never whether it named the right things.
    assert 'claim.scope == "person_specific" and not claim.person_evidence_used' in code

    # And there is no table of what a conclusion requires. A guard on the words
    # themselves would be wrong: "income" appears in the privacy instruction
    # ("a public search does not need a name, an address, an income"), which is
    # the opposite of a requirements list. What must not exist is a structure
    # that pairs a kind of conclusion with the fields it needs.
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, (ast.Dict, ast.List, ast.Tuple, ast.Set)):
            continue
        for target in node.targets:
            name = getattr(target, "id", "") or ""
            for word in ("required", "needed", "slots", "fields", "criteria"):
                assert word not in name.lower(), f"a requirements table: {name}"


# ---------------------------------------------------------------------------
# What settles a question depends on the question
# ---------------------------------------------------------------------------

def test_a_plan_can_ask_for_different_kinds_of_source_in_one_run(monkeypatch):
    """
    §5. One question about what a rule requires and one about what things cost
    need different places to look, and the plan can say so per question. That
    is the whole mechanism: a sentence the model wrote, carried through.
    """
    import research.reasoning as reasoning

    two_halves = _plan(questions=[
        {
            "ref": "rule",
            "question": "quali sono i requisiti obbligatori",
            "evidence_needed": "il testo vigente",
            "source_fitness": "chi stabilisce la regola: la pubblicazione ufficiale",
            "queries": ["requisiti obbligatori testo vigente"],
        },
        {
            "ref": "price",
            "question": "quanto si paga in pratica",
            "evidence_needed": "prezzi realmente praticati",
            "source_fitness": "chi vende, o chi ha svolto una rilevazione di mercato",
            "queries": ["prezzi praticati confronto"],
        },
    ])
    monkeypatch.setattr(reasoning, "_ask_model", FakeModel([two_halves]))
    plan = _run(reasoning.plan_research(_need(), context_lines=[]))
    fitness = {q.ref: q.source_fitness for q in plan.questions}
    assert "ufficiale" in fitness["rule"]
    assert "vende" in fitness["price"]
    assert fitness["rule"] != fitness["price"], "fitness collapsed to one preference"


def test_what_settles_a_question_reaches_the_assessment(monkeypatch):
    """
    Declaring it and never looking at it again would be decoration. The
    assessor is told, per question, what would settle it — so it can say a
    source is the wrong kind for what it is being used for.
    """
    import research.reasoning as reasoning
    from research.models import EvidenceSource, ResearchPlan, ResearchQuestion

    seen = {}

    async def spy(system, user):
        seen["payload"] = user
        return _sufficient()

    monkeypatch.setattr(reasoning, "_ask_model", spy)
    plan = ResearchPlan(goal="g", questions=[
        ResearchQuestion(
            ref="rule", question="quali requisiti", evidence_needed="testo vigente",
            source_fitness="chi stabilisce la regola",
        )
    ])
    _run(reasoning.assess_evidence(
        plan=plan, sources=[EvidenceSource(source_id="rs_1")],
        already_run=[], iteration=1, iterations_left=2,
    ))
    assert "source_fitness" in seen["payload"]
    assert "chi stabilisce la regola" in seen["payload"]


def test_no_kind_of_source_is_privileged_by_the_code():
    """
    §5 again, from the other side: no whitelist, no score, no host. The word
    "official" may appear in a sentence the model wrote; it may never appear in
    a rule the code applies.
    """
    for path in (HERE / "research").glob("*.py"):
        code = _production_code(path)
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare):
                rendered = ast.dump(node).lower()
                for word in ("gov", "official", "wikipedia", "authority_hint", "publisher"):
                    assert word not in rendered, f"{path.name} compares against {word}"
        for token in ("score", "weight", "rank", "trust_level"):
            assert token not in code.lower(), f"{path.name} scores sources: {token}"


def test_the_reasoning_is_told_when_going_out_would_be_premature():
    """
    §6. Comparing what somebody pays against the market cannot be done before
    knowing what they pay, and searching first hands them figures instead of an
    answer. The judgement is the model's — this only checks it was told, and
    that both roads stay open to it.
    """
    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    text = COGNITIVE_SYSTEM_PROMPT
    lowered = text.lower()
    assert "before going, ask yourself whether going would help yet" in lowered
    assert "ask them first" in lowered
    # And it is never told to always ask first, which would be the same mistake
    # in the other direction.
    assert "moves the step forward on its own" in lowered

    from conversation_engine.ai_core.models import ResponseMode
    import typing

    modes = set(typing.get_args(ResponseMode))
    assert {"ask", "research"} <= modes
