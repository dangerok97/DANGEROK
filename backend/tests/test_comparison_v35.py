"""
V3.5 — evidence becoming a decision.

The thing being tested is again a division of labour, one step further along.
The model decides that this is a choice at all, what matters about it for this
particular person, which of those things are absolute and which are
preferences, what would have to be worked out, whether the options are even
comparable, whether there is a winner, and whether it knows enough to say. The
code does the arithmetic, checks the stated conditions against the stated
values, keeps the provenance, and refuses to let an exclusion stand that no
breach supports.

So the model is stubbed, and what is asserted is that the code did not quietly
decide any of it — and, just as importantly, that it did not let the model
skip the parts that are not its job.

The scenarios are a loan, an energy tariff and a language course. Three,
because one would prove nothing: the same code runs all of them and contains no
trace of any of them.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


# ---------------------------------------------------------------------------
# A model that says what a test needs it to say
# ---------------------------------------------------------------------------

class FakeModel:
    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    async def __call__(self, system, user):
        self.prompts.append(user)
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    import comparison.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


def _alt(name, **attrs):
    """
    An alternative whose attribute ids are predictable, so a test can refer to
    one the way the model would: `attr:costo`, never the label.
    """
    from comparison.models import Alternative, Attribute

    attributes = []
    for key, spec in attrs.items():
        if isinstance(spec, tuple):
            number, unit = spec
            attributes.append(
                Attribute(id=f"attr:{key}", name=key, value=f"{number} {unit}",
                          number=number, unit=unit, source_ids=["rs_x"])
            )
        else:
            attributes.append(
                Attribute(id=f"attr:{key}", name=key, value=str(spec), source_ids=["rs_x"])
            )
    return Alternative(name=name, attributes=attributes)


def _need(decision="quale conviene", **over):
    from comparison.models import ComparisonNeed

    return ComparisonNeed(decision=decision, purpose="serve per il passo corrente", **over)


def _framing(**over):
    out = {
        "criteria": [
            {"name": "costo", "why_it_matters": "pesa ogni mese", "importance": "major",
             "personal_basis": "il budget dichiarato", "attribute_id": "attr:costo"},
        ],
        "constraints": [],
        "computations": [],
        "not_comparable": [],
        "missing_from_the_world": [],
        "missing_from_them": [],
    }
    out.update(over)
    return out


def _assessment(ids, **over):
    out = {
        "assessments": [
            {"alternative_id": i, "strengths": ["costa meno"], "weaknesses": [],
             "excluded": False, "missing": []}
            for i in ids
        ],
        "trade_offs": [],
    }
    out.update(over)
    return out


def _recommendation(**over):
    out = {
        "verdict": "clear_choice", "confidence": "strong",
        "message": "Sceglierei la prima.", "deciding_factors": ["costa meno"],
        "conditional": [], "unresolved": [], "needed_to_decide": [],
    }
    out.update(over)
    return out


async def _service(db):
    from comparison.service import ComparisonService

    return ComparisonService(db)


# ---------------------------------------------------------------------------
# The criteria are the model's, and they are different every time
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "decision,criteria",
    [
        ("quale finanziamento conviene", ["costo totale", "sostenibilità della rata", "flessibilità"]),
        ("quale offerta luce conviene", ["prezzo al kWh", "durata del vincolo", "costi fissi"]),
        ("quale corso di lingua scegliere", ["orari compatibili", "riconoscimento del titolo", "distanza"]),
    ],
)
def test_what_matters_is_decided_per_decision(monkeypatch, decision, criteria):
    """
    §5 and §37. Three decisions with nothing in common, one code path, and
    criteria that come back completely different because the model wrote them.
    """
    async def body():
        client, db = await _db()
        user = f"u_cmp_{uuid.uuid4().hex[:8]}"
        try:
            framing = _framing(criteria=[
                {"name": c, "why_it_matters": "conta qui", "importance": "major",
                 "attribute_id": "attr:costo"}
                for c in criteria
            ])
            _install(monkeypatch, FakeModel([
                framing, _assessment(["a", "b"]), _recommendation(),
            ]))
            service = await _service(db)
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            a.id, b.id = "a", "b"
            run = await service.run(user, _need(decision), [a, b], allow_research=False)
            assert [c.name for c in run.criteria] == criteria
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_no_criterion_is_written_anywhere_in_the_code():
    """
    §1 and §37. The failure would look like a dict of criteria per subject, or
    a weight, or a formula. If a subject cannot be named here, it cannot be
    branched on.
    """
    subjects = (
        "mortgage", "mutuo", "insurance", "assicuraz", "polizza", "energy", "energia",
        "job", "lavoro", "travel", "viaggio", "vehicle", "car", "auto", "loan",
        "prestito", "taeg", "kwh",
    )
    for path in (HERE / "comparison").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for node in ast.walk(ast.parse(code)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value.lower()
                for subject in subjects:
                    # Whole words only: "care about most" is not a car, and
                    # "energia" would be, which is the point.
                    assert not re.search(rf"\b{subject}\b", text), (
                        f"{path.name}: {subject!r} in {node.value[:50]!r}"
                    )
        assert "CRITERIA" not in code
        assert "WEIGHTS" not in code


def test_the_code_never_scores_or_ranks_anything():
    """
    §6 and §13. No weighted sum, no ordering function, no number presented as
    a judgement. An option is better because a sentence says why.
    """
    # Scanned with every string constant removed. A word inside a prompt
    # cannot compute anything — the instruction to the model literally says
    # "you are not ranking products" — so what is being looked for here is the
    # word as an identifier or an operation, which is the only place it could
    # do any weighing.
    for path in (HERE / "comparison").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                node.value = ""
        code = ast.unparse(tree).lower()
        for banned in ("score", "weight", "rank", "sorted(", ".sort(", "argmax"):
            assert not re.search(rf"\b{re.escape(banned)}", code), (
                f"{path.name} contains {banned}"
            )

    # And there is no numeric confidence anywhere in the contract.
    from comparison.models import Recommendation

    field = Recommendation.model_fields["confidence"]
    assert field.annotation is not float


# ---------------------------------------------------------------------------
# Preference is not constraint, and the code checks the constraint
# ---------------------------------------------------------------------------

def test_the_model_says_what_is_absolute_and_the_code_says_who_breaches_it():
    """§7. Two halves of one decision, deliberately kept apart."""
    from comparison.constraints import breaches, check_all
    from comparison.models import Constraint

    over = _alt("Troppo cara", rata=(1180.0, "EUR/mese"))
    under = _alt("Sostenibile", rata=(940.0, "EUR/mese"))
    limit = Constraint(
        name="tetto mensile", attribute_id="attr:rata", operator="<=",
        number=1100.0, unit="EUR/mese", why="oltre non ce la fa",
    )
    checks = check_all([limit], [over, under])
    assert len(breaches(checks, over.id)) == 1
    assert breaches(checks, under.id) == []


def test_what_cannot_be_checked_is_not_a_breach():
    """
    §7 again, the half that matters more. An option whose figure is missing has
    not failed anything, and ruling it out would be inventing a fact about it.
    """
    from comparison.constraints import breaches, check_all, unverifiable
    from comparison.models import Alternative, Constraint

    unknown = Alternative(name="Senza dati")
    limit = Constraint(name="tetto", attribute_id="attr:rata", operator="<=", number=1100.0)
    checks = check_all([limit], [unknown])
    assert breaches(checks, unknown.id) == []
    assert len(unverifiable(checks, unknown.id)) == 1
    assert checks[0].satisfied is None


def test_a_limit_in_one_unit_is_not_checked_against_a_figure_in_another():
    """A monthly figure under an annual ceiling is a wrong answer that looks right."""
    from comparison.constraints import check
    from comparison.models import Constraint

    monthly = _alt("A", costo=(850.0, "EUR/mese"))
    annual_limit = Constraint(
        name="tetto annuo", attribute_id="attr:costo", operator="<=",
        number=1200.0, unit="EUR/anno",
    )
    result = check(annual_limit, monthly)
    assert result.satisfied is None
    assert "unit" in result.reason.lower()


def test_an_exclusion_the_checks_do_not_support_does_not_stand(monkeypatch):
    """
    The model may read the constraint results. It may not overrule them: an
    option ruled out on a condition nobody found breached would be a fact
    invented about it.
    """
    async def body():
        client, db = await _db()
        user = f"u_excl_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            a.id, b.id = "a", "b"
            _install(monkeypatch, FakeModel([
                _framing(),
                _assessment(["a"], assessments=[
                    {"alternative_id": "a", "strengths": [], "weaknesses": [],
                     "excluded": True, "excluded_because": "non mi convince", "missing": []},
                    {"alternative_id": "b", "strengths": [], "weaknesses": [],
                     "excluded": False, "missing": []},
                ]),
                _recommendation(chosen_alternative_id="b"),
            ]))
            service = await _service(db)
            run = await service.run(user, _need(), [a, b], allow_research=False)
            excluded = [x for x in run.assessments if x.excluded]
            assert excluded == [], "an exclusion stood with no breach behind it"
            kept = next(x for x in run.assessments if x.alternative_id == "a")
            assert "non mi convince" in " ".join(kept.missing)
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# The arithmetic is the code's
# ---------------------------------------------------------------------------

def test_the_model_names_the_figure_and_python_produces_it():
    """§8. It says which operation over which operands; the multiplication is here."""
    from comparison.arithmetic import compute
    from comparison.models import Computation

    monthly = _alt("A", rata=(850.0, "EUR/mese"))
    annual = compute(
        Computation(name="costo annuo", operation="product",
                    operands=["attr:rata", "12"], unit="EUR/anno"),
        monthly,
    )
    assert annual.result == 10200.0
    assert not annual.failed_reason


def test_a_missing_input_is_not_zero():
    from comparison.arithmetic import compute
    from comparison.models import Alternative, Computation

    empty = Alternative(name="A")
    attempt = compute(
        Computation(name="totale", operation="sum",
                    operands=["attr:rata", "attr:spese"]),
        empty,
    )
    assert attempt.result is None
    assert attempt.failed_reason
    assert attempt.inputs and attempt.inputs[0]["resolved"] is False


def test_dividing_by_nothing_says_so_instead_of_crashing():
    from comparison.arithmetic import compute
    from comparison.models import Computation

    zero = _alt("A", numeratore=(10.0, ""), denominatore=(0.0, ""))
    attempt = compute(
        Computation(name="rapporto", operation="quotient",
                    operands=["attr:numeratore", "attr:denominatore"]),
        zero,
    )
    assert attempt.result is None
    assert attempt.failed_reason


def test_the_operations_know_no_subject():
    """
    §8. Six generic operations. `percent_change` is the same function whether
    it is applied to a rate or a course fee, and nothing can tell which.
    """
    from comparison.models import Operation
    import typing

    assert set(typing.get_args(Operation)) == {
        "sum", "difference", "product", "quotient", "percent_of", "percent_change"
    }


# ---------------------------------------------------------------------------
# Not knowing, and not choosing
# ---------------------------------------------------------------------------

def test_it_can_say_it_does_not_know_enough(monkeypatch):
    """§16. Choosing anyway, because a recommendation was asked for, is the failure."""
    async def body():
        client, db = await _db()
        user = f"u_ins_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            a.id, b.id = "a", "b"
            _install(monkeypatch, FakeModel([
                _framing(), _assessment(["a", "b"]),
                _recommendation(verdict="insufficient", confidence="weak",
                                chosen_alternative_id=None,
                                message="Non posso ancora consigliarti.",
                                needed_to_decide=["per quanti anni ti serve"]),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.status == "insufficient"
            assert run.recommendation.verdict == "insufficient"
            assert run.recommendation.chosen_alternative_id is None
            assert run.recommendation.needed_to_decide
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_it_can_say_there_is_no_winner_and_say_what_would_decide_it(monkeypatch):
    """§14 and §15. A trade-off kept as a trade-off, and a conditional answer."""
    async def body():
        client, db = await _db()
        user = f"u_cond_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(140.0, "EUR"))
            a.id, b.id = "a", "b"
            _install(monkeypatch, FakeModel([
                _framing(),
                _assessment(["a", "b"], trade_offs=[{
                    "between": ["A", "B"], "about": "costo contro sicurezza",
                    "detail": "A costa meno, B copre un rischio che ti riguarda",
                    "decided_by": "quanto pesa per te quel rischio",
                }]),
                _recommendation(
                    verdict="conditional", confidence="tentative",
                    chosen_alternative_id=None,
                    message="Dipende da cosa conta di più per te.",
                    conditional=[
                        {"condition": "se conta soprattutto spendere meno",
                         "alternative_id": "a", "because": "costa 40 in meno"},
                        {"condition": "se conta coprire quel rischio",
                         "alternative_id": "b", "because": "lo copre"},
                    ],
                ),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.recommendation.verdict == "conditional"
            assert len(run.recommendation.conditional) == 2
            assert run.trade_offs and run.trade_offs[0].decided_by
            payload = run.to_reasoning_payload()
            assert payload["conditional"][0]["alternative"] == "A"
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_a_choice_has_to_be_one_of_the_things_on_the_table(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_ghost_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            a.id, b.id = "a", "b"
            _install(monkeypatch, FakeModel([
                _framing(), _assessment(["a", "b"]),
                _recommendation(chosen_alternative_id="qualcosa_che_non_esiste"),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.recommendation.chosen_alternative_id is None
            assert run.recommendation.verdict == "no_clear_winner"
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_nothing_is_compared_when_there_is_nothing_to_compare():
    async def body():
        client, db = await _db()
        user = f"u_none_{uuid.uuid4().hex[:8]}"
        try:
            run = await (await _service(db)).run(user, _need(), [], allow_research=False)
            assert run.status == "insufficient"
            assert not run.to_reasoning_payload()["comparison_is_real"]
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Asking, and not asking
# ---------------------------------------------------------------------------

def test_it_asks_only_for_what_would_change_the_answer(monkeypatch):
    """§11. A comparison that turns into an interview has failed twice."""
    async def body():
        client, db = await _db()
        user = f"u_ask_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            a.id, b.id = "a", "b"
            _install(monkeypatch, FakeModel([
                _framing(missing_from_them=["per quanti anni ti serve"]),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.status == "insufficient"
            assert run.recommendation.needed_to_decide == ["per quanti anni ti serve"]
            # And it stopped there rather than assessing and recommending on a
            # basis it had just said was incomplete.
            assert run.assessments == []
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_what_is_already_known_is_put_in_front_of_the_model(monkeypatch):
    """§10. Know before asking: it cannot avoid asking twice if it is not told."""
    async def body():
        client, db = await _db()
        user = f"u_know_{uuid.uuid4().hex[:8]}"
        try:
            model = FakeModel([_framing(), _assessment(["a"]), _recommendation()])
            _install(monkeypatch, model)
            a = _alt("A", costo=(100.0, "EUR"))
            b = _alt("B", costo=(110.0, "EUR"))
            a.id, b.id = "a", "b"
            await (await _service(db)).run(
                user,
                _need(already_known=["ha già detto la durata: 30 anni"]),
                [a, b],
                personal_context=["reddito netto mensile dichiarato"],
                allow_research=False,
            )
            framing_prompt = model.prompts[0]
            assert "30 anni" in framing_prompt
            assert "reddito netto mensile dichiarato" in framing_prompt
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_only_the_context_it_was_given_travels(monkeypatch):
    """
    §9. Minimum necessary context: the comparison sees the lines the broker
    selected, and there is no path by which it reaches for more.
    """
    async def body():
        client, db = await _db()
        user = f"u_min_{uuid.uuid4().hex[:8]}"
        try:
            model = FakeModel([_framing(), _assessment(["a"]), _recommendation()])
            _install(monkeypatch, model)
            a, b = _alt("A", costo=(1.0, "")), _alt("B", costo=(2.0, ""))
            a.id, b.id = "a", "b"
            run = await (await _service(db)).run(
                user, _need(), [a, b],
                personal_context=[f"fatto {i}" for i in range(40)],
                allow_research=False,
            )
            assert len(run.personal_context_used) <= 12
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Provenance, persistence, revision
# ---------------------------------------------------------------------------

def test_every_stated_fact_carries_where_it_came_from():
    """§12. A claim with no origin cannot be used in a recommendation."""
    from comparison.models import Alternative, Attribute, ComparisonNeed, ComparisonRun

    run = ComparisonRun(
        user_id="u",
        need=ComparisonNeed(decision="d"),
        alternatives=[
            Alternative(name="A", attributes=[
                Attribute(id="attr:costo", name="costo", value="100", number=100.0,
                          source_ids=["rs_1"]),
                Attribute(id="attr:durata", name="durata", value="30 anni",
                          stated_by_user=True),
            ])
        ],
    )
    assert run.cited_source_ids() == ["rs_1"]
    stated = run.alternatives[0].attribute("attr:durata")
    assert stated.stated_by_user and not stated.source_ids


def test_a_run_is_written_down_and_belongs_to_one_person(monkeypatch):
    async def body():
        client, db = await _db()
        mine = f"u_own_{uuid.uuid4().hex[:8]}"
        yours = f"u_own_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([_framing(), _assessment(["a"]), _recommendation()]))
            a, b = _alt("A", costo=(1.0, "")), _alt("B", costo=(2.0, ""))
            a.id, b.id = "a", "b"
            run = await (await _service(db)).run(mine, _need(), [a, b], allow_research=False)

            from comparison.repository import ComparisonRepository

            repo = ComparisonRepository(db)
            assert (await repo.get(mine, run.id)) is not None
            assert (await repo.get(yours, run.id)) is None, "readable by the wrong person"
        finally:
            await db.comparison_runs.delete_many({"user_id": mine})
            client.close()
    _run(body())


def test_a_second_decision_in_the_same_conversation_supersedes_the_first(monkeypatch):
    """
    §25. Not proactivity — just enough recorded that "I said A, now I would say
    B, because" is expressible later.
    """
    async def body():
        client, db = await _db()
        user = f"u_rev_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            a.id, b.id = "a", "b"
            service = await _service(db)

            _install(monkeypatch, FakeModel([
                _framing(), _assessment(["a", "b"]), _recommendation(chosen_alternative_id="a"),
            ]))
            first = await service.run(user, _need(), [a, b], session_id="ces_1", allow_research=False)
            assert first.revision == 1 and first.supersedes_run_id is None

            _install(monkeypatch, FakeModel([
                _framing(), _assessment(["a", "b"]),
                _recommendation(chosen_alternative_id="b", deciding_factors=["copre il rischio"]),
                {"what_changed": "Con quello che mi hai detto adesso preferisco la seconda."},
            ]))
            second = await service.run(user, _need(), [a, b], session_id="ces_1", allow_research=False)
            assert second.supersedes_run_id == first.id
            assert second.revision == 2
            assert "preferisco la seconda" in second.changed_because
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# What a comparison is not
# ---------------------------------------------------------------------------

def test_a_comparison_creates_no_work(monkeypatch):
    """
    §21. The V3.3/V3.4 rule, one step further: deciding something is not the
    same as taking it on. Home stays exactly as it was.
    """
    async def body():
        client, db = await _db()
        user = f"u_work_{uuid.uuid4().hex[:8]}"
        try:
            for col in ("tasks", "decisions", "reminders", "life_os_plans",
                        "conversation_sessions", "users", "home_item_state"):
                await db[col].delete_many({"user_id": user})
            await db.users.insert_one({"user_id": user, "email": f"{user}@t.ora"})

            _install(monkeypatch, FakeModel([_framing(), _assessment(["a"]), _recommendation()]))
            a, b = _alt("A", costo=(1.0, "")), _alt("B", costo=(2.0, ""))
            a.id, b.id = "a", "b"
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.status == "completed"

            from home.service import HomeService

            svc = HomeService(db)
            await svc.ensure_indexes()
            home = await svc.build_home(user)
            assert home.primary_focus is None, home.primary_focus
            assert all(not g.items for g in home.priorities)
            for col in ("tasks", "decisions", "reminders", "life_os_plans"):
                assert await db[col].count_documents({"user_id": user}) == 0, col
        finally:
            for col in ("tasks", "decisions", "reminders", "life_os_plans",
                        "conversation_sessions", "users", "home_item_state"):
                await db[col].delete_many({"user_id": user})
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_nothing_in_comparison_writes_work_memory_or_actions():
    """
    §21 and §22, structurally. It never reaches for the collections that hold
    somebody's day, and it executes nothing: no buying, booking or sending.
    """
    forbidden = (
        "home_item", "tasks", "reminders", "notifications", "attention",
        "life_os_plans", "purchase", "booking", "checkout", "submit_application",
    )
    for path in (HERE / "comparison").glob("*.py"):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")
        code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for word in forbidden:
            assert word not in code, f"comparison/{path.name} touches {word}"

    loop = (HERE / "conversation_engine" / "ai_core" / "loop.py").read_text(encoding="utf-8")
    branch = loop[loop.index('if mode == "compare":'):loop.index('if mode == "research":')]
    assert '"memory_eligible": False' in branch


def test_no_alternative_is_favoured_for_any_reason_but_the_person(monkeypatch):
    """
    §23. Commercial neutrality. There is no sponsorship, partner, affiliate or
    provider preference anywhere — and the code has no way to express one,
    because it never orders anything.
    """
    for path in (HERE / "comparison").glob("*.py"):
        code = path.read_text(encoding="utf-8").lower()
        for word in ("sponsor", "affiliate", "commission", "partner_", "promoted", "featured"):
            assert word not in code, f"{path.name} mentions {word}"

    from conversation_engine.ai_core.prompt import COGNITIVE_SYSTEM_PROMPT

    assert "nothing is being sold" in COGNITIVE_SYSTEM_PROMPT.lower()

    import comparison.reasoning as reasoning

    assert "Nobody is paying you" in reasoning._DISCIPLINE


def test_the_public_payload_shows_nothing_internal(monkeypatch):
    """§26 and §27: no weights, no confidence value, no provider, no run ids."""
    async def body():
        client, db = await _db()
        user = f"u_pub_{uuid.uuid4().hex[:8]}"
        try:
            _install(monkeypatch, FakeModel([_framing(), _assessment(["a"]), _recommendation()]))
            a, b = _alt("A", costo=(1.0, "")), _alt("B", costo=(2.0, ""))
            a.id, b.id = "a", "b"
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)

            from comparison.service import public_comparison_payload

            payload = public_comparison_payload(run)
            flat = str(payload).lower()
            for leak in ("confidence", "importance", "verdict", "run_id", "gemini",
                         "groq", "mistral", "criterion", "score"):
                assert leak not in flat, f"leaked {leak}"
            assert payload["message"]
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# The decision to compare, and who makes it
# ---------------------------------------------------------------------------

def test_the_decision_to_compare_lives_in_the_model_contract():
    """§3. Declared by the reasoning, never inferred from how many results there are."""
    models = (HERE / "conversation_engine" / "ai_core" / "models.py").read_text(encoding="utf-8")
    assert "comparison_need: Optional[ComparisonNeed]" in models
    assert '"compare"' in models

    loop = (HERE / "conversation_engine" / "ai_core" / "loop.py").read_text(encoding="utf-8")
    branch = loop[loop.index('if mode == "compare":'):loop.index('if mode == "research":')]
    assert "decision.comparison_need" in branch
    for inferred in ("len(alternatives) >", "count >", "keyword", "domain"):
        assert inferred not in branch, f"the loop infers comparison from {inferred}"


def test_governance_refuses_a_comparison_with_nothing_to_compare():
    from conversation_engine.ai_core.governance import validate_decision
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    tools = ToolRegistry()
    one = validate_decision(
        {"response_mode": "compare",
         "comparison_need": {"decision": "x", "alternatives": [{"name": "A"}]}},
        tools=tools,
    )
    assert one.decision.response_mode == "answer"
    assert "comparison_without_alternatives" in one.errors

    two = validate_decision(
        {"response_mode": "compare",
         "comparison_need": {"decision": "x", "alternatives": [{"name": "A"}, {"name": "B"}]}},
        tools=tools,
    )
    assert two.ok and two.decision.response_mode == "compare"


def test_the_contracts_belong_to_ora_and_not_to_a_provider():
    """§20. Nothing in comparison knows who answered."""
    for path in (HERE / "comparison").glob("*.py"):
        code = path.read_text(encoding="utf-8").lower()
        for provider in ("gemini", "groq", "mistral", "openai", "ollama"):
            assert provider not in code, f"{path.name} names {provider}"

    import comparison.reasoning as reasoning

    assert "_ask_model" in dir(reasoning)


def test_something_ruled_out_cannot_then_be_recommended(monkeypatch):
    """
    The two halves have to agree. An option excluded for breaching a hard
    requirement, and then chosen anyway, would be ORA contradicting itself
    inside one answer — and the person would see only the second half.
    """
    async def body():
        client, db = await _db()
        user = f"u_contra_{uuid.uuid4().hex[:8]}"
        try:
            over = _alt("Fuori budget", rata=(1180.0, "EUR/mese"))
            under = _alt("Nel budget", rata=(940.0, "EUR/mese"))
            over.id, under.id = "over", "under"
            _install(monkeypatch, FakeModel([
                _framing(constraints=[{
                    "name": "tetto mensile", "attribute_id": "attr:rata", "operator": "<=",
                    "number": 1100.0, "unit": "EUR/mese", "why": "oltre non ce la fa",
                }]),
                _assessment(["over", "under"], assessments=[
                    {"alternative_id": "over", "strengths": [], "weaknesses": [],
                     "excluded": True, "excluded_because": "supera il tetto", "missing": []},
                    {"alternative_id": "under", "strengths": ["rientra"], "weaknesses": [],
                     "excluded": False, "missing": []},
                ]),
                # And then it picks the one it just ruled out.
                _recommendation(chosen_alternative_id="over"),
            ]))
            run = await (await _service(db)).run(user, _need(), [over, under], allow_research=False)

            excluded = next(x for x in run.assessments if x.alternative_id == "over")
            assert excluded.excluded, "the breach was real and should have stood"
            assert run.recommendation.chosen_alternative_id != "over"
            assert run.recommendation.verdict != "clear_choice"
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


# ---------------------------------------------------------------------------
# Stable references: a label is for reading, an id is what resolves
# ---------------------------------------------------------------------------

def test_the_bug_that_was_found_live_cannot_happen_again(monkeypatch):
    """
    The exact shape of it. The model wrote an attribute called "Costo mensile"
    and then, describing the calculation it wanted, called it "costo mensile
    (39€)" — the same thing to a reader, a different string to a lookup, and
    the figure was simply never worked out.

    Now the calculation quotes the id it was given. The label can be rewritten
    between one step and the next, and the arithmetic still happens.
    """
    async def body():
        client, db = await _db()
        user = f"u_ref_{uuid.uuid4().hex[:8]}"
        try:
            from comparison.models import Alternative, Attribute

            a = Alternative(name="A", attributes=[
                Attribute(id="attr:mensile", name="Costo mensile", value="39",
                          number=39.0, unit="EUR/mese", stated_by_user=True)
            ])
            b = Alternative(name="B", attributes=[
                Attribute(id="attr:mensile", name="Costo mensile", value="29",
                          number=29.0, unit="EUR/mese", stated_by_user=True)
            ])
            _install(monkeypatch, FakeModel([
                _framing(criteria=[], computations=[{
                    "name": "costo in 12 mesi", "operation": "product",
                    # Quoted back, not retyped. The model may call it whatever
                    # it likes in prose; this is the handle.
                    "operands": ["attr:mensile", "12"], "unit": "EUR",
                    "why": "per confrontarle sullo stesso periodo",
                }]),
                _assessment([a.id, b.id]),
                _recommendation(chosen_alternative_id=b.id),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)

            results = {c.alternative_id: c.result for c in run.computations}
            assert results[a.id] == 468.0
            assert results[b.id] == 348.0
            assert all(not c.failed_reason for c in run.computations)
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_a_rewritten_label_breaks_nothing():
    """
    The property, stated directly: change every label, keep the ids, and both
    the calculation and the constraint behave identically.
    """
    from comparison.arithmetic import compute
    from comparison.constraints import check
    from comparison.models import Alternative, Attribute, Computation, Constraint

    def build(label):
        return Alternative(name="A", attributes=[
            Attribute(id="attr:x", name=label, value="850", number=850.0, unit="EUR/mese")
        ])

    computation = Computation(name="annuo", operation="product",
                              operands=["attr:x", "12"], unit="EUR/anno")
    limit = Constraint(name="tetto", attribute_id="attr:x", operator="<=",
                       number=900.0, unit="EUR/mese")

    for label in ("Costo mensile", "costo mensile (850€)", "Monthly cost", "canone"):
        alternative = build(label)
        assert compute(computation.model_copy(deep=True), alternative).result == 10200.0
        assert check(limit, alternative).satisfied is True


def test_the_same_field_across_alternatives_gets_one_identity():
    """
    Shared identity is what makes two options comparable at all — and what
    lets one requirement be checked against both.
    """
    from comparison.models import Alternative, Attribute, ComparisonNeed, ComparisonRun

    run = ComparisonRun(
        user_id="u", need=ComparisonNeed(decision="d"),
        alternatives=[
            Alternative(name="A", attributes=[
                Attribute(name="canone", number=780.0),
                Attribute(name="distanza", number=10.0),
            ]),
            Alternative(name="B", attributes=[
                Attribute(name="canone", number=590.0),
                Attribute(name="superficie", number=80.0),
            ]),
        ],
    )
    run.assign_attribute_identity()
    a_canone = run.alternatives[0].attributes[0].id
    b_canone = run.alternatives[1].attributes[0].id
    assert a_canone == b_canone, "the same field ended up with two identities"
    # And a field only one of them has stays its own.
    assert run.alternatives[0].attributes[1].id != run.alternatives[1].attributes[1].id


def test_a_reference_that_does_not_resolve_is_never_guessed_at():
    """
    §5. Fail closed. The alternative is that the code picks the nearest field,
    and a figure produced from the wrong field is worse than no figure.
    """
    from comparison.arithmetic import compute
    from comparison.constraints import check
    from comparison.models import Computation, Constraint

    alternative = _alt("A", rata=(850.0, "EUR/mese"))

    ghost = compute(
        Computation(name="x", operation="product", operands=["attr:inesistente", "12"]),
        alternative,
    )
    assert ghost.result is None and ghost.failed_reason

    # And not by label either — that is the whole point.
    by_label = compute(
        Computation(name="x", operation="product", operands=["rata", "12"]), alternative
    )
    assert by_label.result is None

    wrong = check(
        Constraint(name="t", attribute_id="attr:inesistente", operator="<=", number=1.0),
        alternative,
    )
    assert wrong.satisfied is None and wrong.reason


def test_an_id_belonging_to_another_alternative_resolves_to_nothing():
    """Identity is per field, and a field one option does not have is unknown."""
    from comparison.constraints import check
    from comparison.models import Constraint

    has_it = _alt("A", rata=(850.0, "EUR/mese"))
    lacks_it = _alt("B", canone=(700.0, "EUR/mese"))

    limit = Constraint(name="tetto", attribute_id="attr:rata", operator="<=", number=900.0)
    assert check(limit, has_it).satisfied is True
    missing = check(limit, lacks_it)
    assert missing.satisfied is None, "a field it does not have was treated as a value"
    assert missing.reason


def test_nothing_resolves_a_reference_by_reading_a_label():
    """
    Structurally, not by reading the code and hoping.

    Three things are checked: identity comparison never looks at a label; every
    lookup in the package is made with an id rather than a name; and no fuzzy
    matcher is imported anywhere near it. All three are the ways this would be
    "fixed" badly — each of them would turn a broken contract into a figure
    computed from the wrong field, which is the one outcome worse than none.
    """
    models = ast.parse((HERE / "comparison" / "models.py").read_text(encoding="utf-8"))
    lookup = next(
        n for n in ast.walk(models)
        if isinstance(n, ast.FunctionDef) and n.name == "attribute"
    )
    body = " ; ".join(
        ast.unparse(stmt) for stmt in lookup.body
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
    )
    assert "item.id == attribute_id" in body
    assert ".name" not in body, "identity is decided by reading a label"
    for cheat in (".lower()", "startswith", "endswith", " in item"):
        assert cheat not in body, f"the lookup is not exact: {cheat}"

    # Every lookup in the package asks for an id. Nothing hands it a label.
    allowed = {"ref", "attribute_id", "constraint.attribute_id"}
    for name in ("arithmetic.py", "constraints.py", "service.py"):
        tree = ast.parse((HERE / "comparison" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "attribute" and node.args):
                asked = ast.unparse(node.args[0])
                assert asked in allowed, f"{name} looks an attribute up by {asked}"

    # And no fuzzy matcher is anywhere in the package.
    for path in sorted((HERE / "comparison").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        for cheat in ("difflib", "rapidfuzz", "Levenshtein", "fuzz", "get_close_matches"):
            assert cheat not in source, f"{path.name} imports a way to guess: {cheat}"


def test_a_constraint_pointing_nowhere_is_dropped_rather_than_run(monkeypatch):
    """A requirement about a field nobody has cannot be checked, so it is not kept."""
    async def body():
        client, db = await _db()
        user = f"u_drop_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            _install(monkeypatch, FakeModel([
                _framing(constraints=[{
                    "name": "tetto", "attribute_id": "attr:non_esiste",
                    "operator": "<=", "number": 50.0,
                }]),
                _assessment([a.id, b.id]),
                _recommendation(chosen_alternative_id=a.id),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.constraints == []
            assert "constraint_unresolved_reference" in run.failures
            assert run.checks == []
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_a_computation_with_an_unresolvable_operand_is_dropped(monkeypatch):
    async def body():
        client, db = await _db()
        user = f"u_dropc_{uuid.uuid4().hex[:8]}"
        try:
            a, b = _alt("A", costo=(100.0, "EUR")), _alt("B", costo=(120.0, "EUR"))
            _install(monkeypatch, FakeModel([
                _framing(computations=[{
                    "name": "x", "operation": "product",
                    # The live failure, verbatim: a label with the value glued on.
                    "operands": ["costo mensile (39€)", "12"],
                }]),
                _assessment([a.id, b.id]),
                _recommendation(chosen_alternative_id=a.id),
            ]))
            run = await (await _service(db)).run(user, _need(), [a, b], allow_research=False)
            assert run.computations == []
            assert "computation_unresolved_reference" in run.failures
        finally:
            await db.comparison_runs.delete_many({"user_id": user})
            client.close()
    _run(body())


def test_a_result_can_say_which_numbers_went_into_it_and_where_they_came_from():
    """§9. Provenance without duplicating evidence: refs, values, origins."""
    from comparison.arithmetic import compute
    from comparison.models import Alternative, Attribute, Computation

    alternative = Alternative(name="A", attributes=[
        Attribute(id="attr:rata", name="rata", number=850.0, unit="EUR/mese",
                  source_ids=["rs_7"])
    ])
    done = compute(
        Computation(name="annuo", operation="product", operands=["attr:rata", "12"]),
        alternative,
    )
    assert done.result == 10200.0
    assert done.alternative_id == alternative.id
    first = done.inputs[0]
    assert first["ref"] == "attr:rata" and first["resolved"] is True
    assert first["value"] == 850.0 and first["source_ids"] == ["rs_7"]
    assert done.inputs[1]["literal"] == 12.0


def test_a_constraint_result_carries_where_the_figure_came_from():
    from comparison.constraints import check
    from comparison.models import Alternative, Attribute, Constraint

    alternative = Alternative(name="A", attributes=[
        Attribute(id="attr:rata", name="rata", number=940.0, unit="EUR/mese",
                  stated_by_user=True)
    ])
    result = check(
        Constraint(name="tetto", attribute_id="attr:rata", operator="<=",
                   number=1100.0, unit="EUR/mese"),
        alternative,
    )
    assert result.satisfied is True
    assert result.attribute_id == "attr:rata"
    assert result.stated_by_user is True


def test_the_model_is_shown_the_ids_and_told_to_quote_them():
    """
    §6. It keeps choosing what to calculate and what is absolute; what it stops
    doing is retyping labels as if they were keys.
    """
    source = (HERE / "comparison" / "reasoning.py").read_text(encoding="utf-8")
    assert '"attribute_id": at.id' in source
    assert '"operands": ["attribute_ids, or literal numbers"]' in source
    assert "quote it back exactly" in source
    assert "retype the label" in source


def test_the_second_account_is_the_same_adapter_with_its_own_limits():
    """
    A second Gemini account is a second set of quotas, not a second way of
    reasoning: the same class, a different key, one step below the first so an
    exhausted account does not immediately change model family.
    """
    from llm.manager import DEFAULT_PRIORITY
    from llm.providers import GeminiProvider, GeminiSecondaryProvider

    assert DEFAULT_PRIORITY[:4] == ("gemini", "gemini2", "groq", "mistral")
    assert issubclass(GeminiSecondaryProvider, GeminiProvider)
    assert GeminiSecondaryProvider.key_env == "GEMINI2_API_KEY"
    assert GeminiProvider.key_env == "GEMINI_API_KEY"

    # And nothing about how it talks to the provider is duplicated.
    extra = set(vars(GeminiSecondaryProvider)) - set(vars(GeminiProvider))
    assert extra <= {"name", "key_env", "model_name", "__doc__", "__module__"}
