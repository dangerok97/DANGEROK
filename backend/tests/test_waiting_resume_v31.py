"""
V3.1 — WAITING_USER: a blocker that survives, and a resume that happens once.

The scenarios here are the ones the design exists for, and each of them is a
way the naive version breaks:

  A  ORA asks, the process restarts, the person answers from Home two days
     later, and the *same* plan / item / object continues. The naive version
     reads the transcript back and starts a second interpretation.
  B  The answer is accepted and the continuation then fails. The naive version
     loses the answer and asks again; here the answer stays answered and the
     work stays retryable.
  C  Two devices answer at the same instant. The naive version runs the work
     twice.
  D  ORA works the answer out from somewhere else. The naive version keeps
     asking a question it no longer needs.

Everything is exercised through the service, against a real Mongo, because the
guarantees being tested are storage guarantees — a unique index and two
conditional updates. A mocked repository would assert that the code calls
itself.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")

from waiting.models import OpenQuestion, ResumePointer, WorkRefs  # noqa: E402
from waiting.service import WaitingService  # noqa: E402


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, user_id: str):
    await db["open_questions"].delete_many({"user_id": user_id})


def _uid() -> str:
    return f"u_wait_{uuid.uuid4().hex[:10]}"


def _refs(*, session="s_1", plan="p_1", item="i_1", obj="o_1") -> WorkRefs:
    return WorkRefs(session_id=session, plan_id=plan, plan_item_id=item, object_id=obj)


def _resume(**kw) -> ResumePointer:
    base = dict(kind="plan_work", target_id="i_1", goal_summary="Comprare casa",
                asked_refs=["financing_source"])
    base.update(kw)
    return ResumePointer(**base)


# The product example, used as a fixture only. Nothing below knows what a
# mortgage is: these are strings that could have been anything.
QUESTION = "L'acquisto sarà finanziato con mutuo o con risparmi personali?"


@pytest.fixture()
def env():
    client, db = _run(_db())
    svc = WaitingService(db)
    _run(svc.ensure_indexes())
    uid = _uid()
    _run(_clean(db, uid))
    yield svc, db, uid
    _run(_clean(db, uid))
    client.close()


# ---------------------------------------------------------------------------
# The record itself
# ---------------------------------------------------------------------------

def test_blocker_is_persisted_with_its_work(env):
    svc, db, uid = env
    out = _run(svc.record_blocking_question(
        uid, question=QUESTION, why_needed="Serve per scegliere come procedere.",
        context_label="Valutare il finanziamento", refs=_refs(), resume=_resume(),
    ))
    assert out and out["question"] == QUESTION
    assert out["work_kind"] == "plan_work"

    stored = _run(db["open_questions"].find_one({"user_id": uid}, {"_id": 0}))
    q = OpenQuestion.model_validate(stored)
    assert q.status == "open"
    # The refs are what make a resume exact rather than approximate.
    assert (q.refs.plan_id, q.refs.plan_item_id, q.refs.object_id) == ("p_1", "i_1", "o_1")
    assert q.resume.asked_refs == ["financing_source"]


def test_public_view_never_exposes_the_resume_pointer(env):
    """A client that could read where to resume could be talked into changing it."""
    svc, db, uid = env
    out = _run(svc.record_blocking_question(
        uid, question=QUESTION, refs=_refs(), resume=_resume(),
    ))
    assert "resume" not in out
    assert "plan_id" not in out and "plan_item_id" not in out
    assert "dedupe_key" not in out and "answer_raw" not in out
    # It does carry the opaque handles an interface legitimately needs.
    assert out["id"] and out["session_id"] == "s_1"


def test_a_retried_cycle_does_not_ask_twice(env):
    """Idempotency: the same blocker recorded three times is one open question."""
    svc, db, uid = env
    ids = {
        _run(svc.record_blocking_question(
            uid, question=QUESTION, refs=_refs(), resume=_resume(),
        ))["id"]
        for _ in range(3)
    }
    assert len(ids) == 1
    assert _run(db["open_questions"].count_documents({"user_id": uid, "status": "open"})) == 1


def test_a_newer_blocker_supersedes_the_older_one_on_the_same_item(env):
    """One blocker per branch: nobody is asked about a decision ORA moved past."""
    svc, db, uid = env
    first = _run(svc.record_blocking_question(
        uid, question=QUESTION, refs=_refs(), resume=_resume(),
    ))
    second = _run(svc.record_blocking_question(
        uid, question="Di quanto avresti bisogno?", refs=_refs(),
        resume=_resume(asked_refs=["amount"]),
    ))
    assert first["id"] != second["id"]
    open_now = _run(svc.list_open(uid))
    assert [q["id"] for q in open_now] == [second["id"]]
    old = _run(db["open_questions"].find_one({"id": first["id"]}, {"_id": 0}))
    assert old["status"] == "superseded"
    assert old["resolved_reason"] == "replaced_by_newer_blocker"


# ---------------------------------------------------------------------------
# A — answer from anywhere, resume the same work
# ---------------------------------------------------------------------------

def test_answer_is_atomic_and_keeps_the_words_the_person_used(env, monkeypatch):
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))

    seen = {}

    async def fake_turn(self, user_id, question):  # noqa: ANN001
        seen["user_id"] = user_id
        seen["session"] = question.refs.session_id
        seen["plan"] = question.refs.plan_id
        seen["item"] = question.refs.plan_item_id
        seen["object"] = question.refs.object_id
        seen["answer"] = question.answer_raw
        return {"ok": True}

    async def no_focus(self, user_id, question):  # noqa: ANN001
        return None

    monkeypatch.setattr(WaitingService, "_run_turn", fake_turn, raising=True)
    monkeypatch.setattr(WaitingService, "_restore_focus", no_focus, raising=True)

    out = _run(svc.answer(uid, q["id"], answer="Mutuo", source="home"))
    assert out["ok"] and out["resumed"] is True

    # Exactly the work it was blocking — not a new plan, not a new object.
    assert (seen["plan"], seen["item"], seen["object"]) == ("p_1", "i_1", "o_1")
    assert seen["session"] == "s_1"
    assert seen["answer"] == "Mutuo"

    stored = _run(db["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
    assert stored["status"] == "answered"
    assert stored["answer_raw"] == "Mutuo"          # raw stays the source
    assert stored["answer_source"] == "home"
    assert stored["continuation"]["status"] == "done"
    # ...and it is gone from every surface that reads open questions.
    assert _run(svc.list_open(uid)) == []


def test_an_answer_that_declines_is_still_an_answer(env, monkeypatch):
    """"Non lo so" is information. It must not be rejected as an error."""
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))
    monkeypatch.setattr(WaitingService, "_run_turn",
                        lambda self, u, question: _ok(), raising=True)
    monkeypatch.setattr(WaitingService, "_restore_focus",
                        lambda self, u, question: _none(), raising=True)

    out = _run(svc.answer(uid, q["id"], answer="Non lo so", source="ora"))
    assert out["ok"] and out["resumed"] is True
    stored = _run(db["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
    assert stored["status"] == "answered" and stored["answer_raw"] == "Non lo so"


def test_a_question_without_a_thread_still_keeps_the_answer(env):
    """No session to continue into is not a reason to discard what was said."""
    svc, db, uid = env
    q = _run(svc.record_blocking_question(
        uid, question=QUESTION, refs=WorkRefs(), resume=ResumePointer(kind="conversation"),
    ))
    out = _run(svc.answer(uid, q["id"], answer="Mutuo", source="activity"))
    assert out["ok"] and out["resumed"] is False and out["reason"] == "no_thread"
    stored = _run(db["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
    assert stored["status"] == "answered" and stored["answer_raw"] == "Mutuo"


def test_ownership_is_enforced(env):
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))
    other = _uid()
    out = _run(svc.answer(other, q["id"], answer="Mutuo"))
    assert out == {"ok": False, "error": "not_found"}
    assert _run(svc.list_open(other)) == []
    # Untouched for its actual owner.
    assert len(_run(svc.list_open(uid))) == 1


# ---------------------------------------------------------------------------
# B — the continuation fails, the answer does not
# ---------------------------------------------------------------------------

def test_a_failed_continuation_never_costs_the_answer(env, monkeypatch):
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))

    async def boom(self, user_id, question):  # noqa: ANN001
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(WaitingService, "_run_turn", boom, raising=True)
    monkeypatch.setattr(WaitingService, "_restore_focus",
                        lambda self, u, question: _none(), raising=True)

    out = _run(svc.answer(uid, q["id"], answer="Mutuo", source="home"))
    assert out["ok"] and out["resumed"] is False and out["retryable"] is True

    stored = _run(db["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
    # The question does NOT go back to open: nobody is asked to type it again.
    assert stored["status"] == "answered"
    assert stored["answer_raw"] == "Mutuo"
    assert stored["continuation"]["status"] == "failed"
    assert stored["continuation"]["attempts"] == 1
    assert _run(svc.list_open(uid)) == []

    # ...and the work is still retryable, without the person doing anything.
    calls = {"n": 0}

    async def ok(self, user_id, question):  # noqa: ANN001
        calls["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(WaitingService, "_run_turn", ok, raising=True)
    again = _run(svc.retry_continuation(uid, q["id"]))
    assert again["ok"] and again["resumed"] is True and calls["n"] == 1
    stored = _run(db["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
    assert stored["continuation"]["status"] == "done"
    assert stored["continuation"]["attempts"] == 2


def test_a_finished_continuation_is_not_run_again(env, monkeypatch):
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))
    calls = {"n": 0}

    async def ok(self, user_id, question):  # noqa: ANN001
        calls["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(WaitingService, "_run_turn", ok, raising=True)
    monkeypatch.setattr(WaitingService, "_restore_focus",
                        lambda self, u, question: _none(), raising=True)

    _run(svc.answer(uid, q["id"], answer="Mutuo"))
    _run(svc.retry_continuation(uid, q["id"]))
    _run(svc.retry_continuation(uid, q["id"]))
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# C — two surfaces answering at once
# ---------------------------------------------------------------------------

def test_two_simultaneous_answers_continue_the_work_once(env, monkeypatch):
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))
    calls = {"n": 0}

    async def slow_ok(self, user_id, question):  # noqa: ANN001
        calls["n"] += 1
        await asyncio.sleep(0.05)
        return {"ok": True}

    monkeypatch.setattr(WaitingService, "_run_turn", slow_ok, raising=True)
    monkeypatch.setattr(WaitingService, "_restore_focus",
                        lambda self, u, question: _none(), raising=True)

    async def both():
        return await asyncio.gather(
            svc.answer(uid, q["id"], answer="Mutuo", source="home"),
            svc.answer(uid, q["id"], answer="Risparmi", source="ora"),
        )

    a, b = _run(both())
    # Both callers are told there is nothing left to do; only one did anything.
    assert a["ok"] and b["ok"]
    assert calls["n"] == 1
    assert [r.get("already") for r in (a, b)].count(True) == 1

    stored = _run(db["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
    assert stored["status"] == "answered"
    # The winner's words are the ones kept — not a merge of the two.
    assert stored["answer_raw"] in ("Mutuo", "Risparmi")
    assert stored["continuation"]["attempts"] == 1


# ---------------------------------------------------------------------------
# D — ORA finds out by itself
# ---------------------------------------------------------------------------

def test_a_superseded_question_disappears_and_cannot_be_answered(env, monkeypatch):
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))

    assert _run(svc.supersede(uid, q["id"], reason="answered_by_document")) is True
    assert _run(svc.list_open(uid)) == []

    calls = {"n": 0}

    async def ok(self, user_id, question):  # noqa: ANN001
        calls["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(WaitingService, "_run_turn", ok, raising=True)
    late = _run(svc.answer(uid, q["id"], answer="Mutuo"))
    # A late answer is not an error, and it does not restart anything.
    assert late["ok"] and late["already"] is True and late["status"] == "superseded"
    assert calls["n"] == 0


def test_closing_the_work_closes_its_questions(env):
    """A completed plan cannot still be waiting for a decision."""
    svc, db, uid = env
    _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))
    _run(svc.record_blocking_question(
        uid, question="Quando vuoi il rogito?", refs=_refs(item="i_2"),
        resume=_resume(target_id="i_2", asked_refs=["deed_date"]),
    ))
    assert len(_run(svc.list_open(uid))) == 2

    n = _run(svc.close_for_work(uid, plan_id="p_1", reason="plan_completed"))
    assert n == 2
    assert _run(svc.list_open(uid)) == []
    rows = _run(db["open_questions"].find({"user_id": uid}, {"_id": 0}).to_list(10))
    assert all(r["status"] == "cancelled" for r in rows)
    assert all(r["resolved_reason"] == "plan_completed" for r in rows)


# ---------------------------------------------------------------------------
# Durability
# ---------------------------------------------------------------------------

def test_an_open_question_survives_a_new_process(env):
    """Nothing about a blocker lives in memory: a fresh service finds it."""
    svc, db, uid = env
    q = _run(svc.record_blocking_question(uid, question=QUESTION, refs=_refs(), resume=_resume()))

    client2, db2 = _run(_db())
    try:
        fresh = WaitingService(db2)
        rows = _run(fresh.list_open(uid))
        assert [r["id"] for r in rows] == [q["id"]]
        # ...including the pointer it will resume from.
        stored = _run(db2["open_questions"].find_one({"id": q["id"]}, {"_id": 0}))
        assert stored["refs"]["plan_item_id"] == "i_1"
        assert stored["resume"]["kind"] == "plan_work"
    finally:
        client2.close()


# ---------------------------------------------------------------------------
# Domain neutrality
# ---------------------------------------------------------------------------

def test_the_module_knows_nothing_about_any_domain():
    """The scenario is mortgages; the code must not be.

    Checked against names rather than against text: a docstring may explain the
    example the design was reasoned through, but nothing in the module may be
    *called* after a domain. `MortgageQuestion` is the failure this forbids,
    and a comment mentioning a mortgage is not.
    """
    import ast

    banned = (
        "mutuo", "mortgage", "house", "casa", "travel", "viaggio",
        "study", "esame", "exam", "insurance", "assicurazione",
    )
    for rel in ("waiting/models.py", "waiting/repository.py", "waiting/service.py",
                "waiting/router.py"):
        tree = ast.parse((Path(_BACKEND) / rel).read_text(encoding="utf-8"))
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.add(node.name)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(node.name)
                names.update(a.arg for a in node.args.args)
                names.update(a.arg for a in node.args.kwonlyargs)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
        lowered = " ".join(n.lower() for n in names)
        for word in banned:
            assert word not in lowered, f"{rel}: {word!r} appears in a name"

        # And no domain word may reach a person through a literal the module
        # itself writes — a hardcoded question, a hardcoded label.
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if len(node.value) > 200:
                    continue  # prose, not a label
                    continue  # a docstring
                for word in banned:
                    assert word not in node.value.lower(), (
                        f"{rel}: domain word {word!r} in a string literal"
                    )


def test_the_resume_path_can_actually_reach_the_reasoning():
    """The continuation imports its orchestrator lazily, so nothing type-checks it.

    The first live run of this failed on a capitalised letter — `AiCore` where
    the class is `AICore` — and the design worked exactly as intended: the
    answer survived, the continuation was marked retryable, and nobody was
    asked to type "Mutuo" again. That is the right failure, and it is still a
    failure. This makes it a test failure instead of a production one.
    """
    import inspect

    import waiting.service as s

    src = inspect.getsource(s.WaitingService._run_turn)
    module, _, name = (
        [line for line in src.splitlines() if "import" in line][0]
        .strip()
        .partition(" import ")
    )
    module = module.replace("from ", "").strip()
    imported = __import__(module, fromlist=[name.strip()])
    assert hasattr(imported, name.strip()), f"{module} has no {name.strip()!r}"

    # And it takes the answer through the ordinary message path, so the turn
    # lands in the transcript and the message id makes a retry reuse it.
    assert "client_message_id=f\"ans_{q.id}\"" in src
    assert "orch.message(" in src


# ---------------------------------------------------------------------------
# The durability invariant
#
#   VISIBLE BLOCKING QUESTION  =>  DURABLE QUESTION EXISTS
#
# The failure this forbids is the quiet one. A blocking question that reached
# the screen but never reached the database looks exactly like a question ORA
# is waiting on — and it is on no list, it is in no read model, and it is gone
# the moment the page reloads. Persisting it "best effort" beside the turn is
# what produces that state, so the turn now fails with it.
# ---------------------------------------------------------------------------

class _FakeRepo:
    """A conversation repository that records what was made durable."""

    def __init__(self):
        self.replaced = []
        self.inserted = []
        self.sessions = {}

    async def insert(self, sess):
        self.inserted.append(sess.id)
        self.sessions[sess.id] = sess

    async def replace(self, sess):
        self.replaced.append(sess.id)
        self.sessions[sess.id] = sess

    async def get(self, user_id, session_id):
        return self.sessions.get(session_id)


def _blocking_result(question: str = QUESTION):
    from conversation_engine.ai_core.models import ActiveGoal, CognitiveTurnResult

    return CognitiveTurnResult(
        ok=True,
        mode="ask",
        ora_text=question,
        question=question,
        session_id="",
        active_goal=ActiveGoal(),
        blocking_ask={
            "question": question,
            "why_needed": "Serve per procedere.",
            "asked_refs": ["financing_source"],
            "answer_kind": "free_text",
            "sensitive": False,
        },
    )


def _session(user_id: str):
    from conversation_engine.models import ConversationSession, new_session_id

    return ConversationSession(
        id=new_session_id(),
        user_id=user_id,
        origin="text",
        input="...",
        status="waiting_user",
        engine_version="ai-core-1.0",
        meta={"ui_mode": "ai_core", "ai_core": {}},
    )


def _orch_with_fake_repo(db, uid):
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

    orch = AICoreOrchestrator(db)
    repo = _FakeRepo()
    orch.repo = repo
    sess = _session(uid)
    _run(repo.insert(sess))
    return orch, repo, sess


def test_a_question_that_cannot_be_stored_is_never_shown(env, monkeypatch):
    """B/C — persistence fails: the turn fails, and no ghost question exists."""
    svc, db, uid = env
    orch, repo, sess = _orch_with_fake_repo(db, uid)

    async def dead_store(self, user_id, **kwargs):
        raise RuntimeError("the store is unavailable")

    monkeypatch.setattr(WaitingService, "record_blocking_question", dead_store, raising=True)

    async def fake_loop(**kwargs):
        return _blocking_result()

    monkeypatch.setattr(
        "conversation_engine.ai_core.orchestrator.run_cognitive_loop", fake_loop, raising=True
    )

    out = _run(orch.message(uid, sess.id, text="Vado avanti?"))

    # The turn did not succeed, and it says so in a way the caller can retry.
    assert out["ok"] is False
    assert out["error"] == "blocking_question_not_durable"

    # Nothing was made durable: the assistant turn never reached the store, so
    # there is no question on screen that the database does not know about.
    assert repo.replaced == [], "a non-durable blocking turn must not be persisted"
    assert _run(svc.list_open(uid)) == []
    assert _run(db["open_questions"].count_documents({"user_id": uid})) == 0


def test_a_question_the_store_silently_refuses_is_also_a_failure(env, monkeypatch):
    """`None` back from the service means no open question — which is a failure."""
    svc, db, uid = env
    orch, repo, sess = _orch_with_fake_repo(db, uid)

    async def returns_nothing(self, user_id, **kwargs):
        return None

    monkeypatch.setattr(WaitingService, "record_blocking_question", returns_nothing, raising=True)

    async def fake_loop(**kwargs):
        return _blocking_result()

    monkeypatch.setattr(
        "conversation_engine.ai_core.orchestrator.run_cognitive_loop", fake_loop, raising=True
    )

    out = _run(orch.message(uid, sess.id, text="Vado avanti?"))
    assert out["ok"] is False and out["error"] == "blocking_question_not_durable"
    assert repo.replaced == []


def test_retrying_after_a_storage_failure_creates_exactly_one_question(env, monkeypatch):
    """D/E/F/G — the retry succeeds, once, and survives a new process."""
    svc, db, uid = env
    orch, repo, sess = _orch_with_fake_repo(db, uid)

    async def fake_loop(**kwargs):
        return _blocking_result()

    monkeypatch.setattr(
        "conversation_engine.ai_core.orchestrator.run_cognitive_loop", fake_loop, raising=True
    )

    calls = {"n": 0}
    real = WaitingService.record_blocking_question

    async def flaky(self, user_id, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the store is unavailable")
        return await real(self, user_id, **kwargs)

    monkeypatch.setattr(WaitingService, "record_blocking_question", flaky, raising=True)

    first = _run(orch.message(uid, sess.id, text="Vado avanti?", client_message_id="m_1"))
    assert first["ok"] is False
    assert _run(db["open_questions"].count_documents({"user_id": uid})) == 0

    # The client retries the same message. The reasoning runs again and the
    # store is back.
    second = _run(orch.message(uid, sess.id, text="Vado avanti?", client_message_id="m_1"))
    assert second.get("ok") is not False
    assert repo.replaced == [sess.id], "only the durable turn is persisted"

    # Exactly one question, and exactly one user turn — the retry reused both.
    assert _run(db["open_questions"].count_documents({"user_id": uid, "status": "open"})) == 1
    stored = _run(db["open_questions"].find_one({"user_id": uid}, {"_id": 0}))
    assert stored["refs"]["session_id"] == sess.id
    assert stored["resume"]["asked_refs"] == ["financing_source"]
    user_turns = [h for h in (repo.sessions[sess.id].history or []) if h.role == "user"]
    assert len(user_turns) == 1, "a retried message must not produce a second user turn"

    # A third identical cycle must still not create a second question.
    _run(orch.message(uid, sess.id, text="Vado avanti?", client_message_id="m_2"))
    assert _run(db["open_questions"].count_documents({"user_id": uid, "status": "open"})) == 1

    # G — a fresh process finds it exactly as it was.
    client2, db2 = _run(_db())
    try:
        rows = _run(WaitingService(db2).list_open(uid))
        assert len(rows) == 1 and rows[0]["question"] == QUESTION
    finally:
        client2.close()


def test_a_turn_that_is_not_a_blocker_is_unaffected(env, monkeypatch):
    """The invariant must not make ordinary conversation fragile."""
    svc, db, uid = env
    from conversation_engine.ai_core.models import ActiveGoal, CognitiveTurnResult

    orch, repo, sess = _orch_with_fake_repo(db, uid)

    async def dead_store(self, user_id, **kwargs):
        raise RuntimeError("the store is unavailable")

    monkeypatch.setattr(WaitingService, "record_blocking_question", dead_store, raising=True)

    async def plain_answer(**kwargs):
        return CognitiveTurnResult(
            ok=True, mode="answer", ora_text="Ecco.", session_id="", active_goal=ActiveGoal(),
        )

    monkeypatch.setattr(
        "conversation_engine.ai_core.orchestrator.run_cognitive_loop", plain_answer, raising=True
    )

    out = _run(orch.message(uid, sess.id, text="Ciao"))
    assert out.get("ok") is not False
    assert repo.replaced == [sess.id]
    assert _run(db["open_questions"].count_documents({"user_id": uid})) == 0


# --- small awaitable helpers used by monkeypatched lambdas -----------------

async def _ok():
    return {"ok": True}


async def _none():
    return None
