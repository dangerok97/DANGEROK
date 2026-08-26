"""
The service that lets ORA stop, and then genuinely carry on.

Three responsibilities, kept apart on purpose:

  1. recording a blocker, once, with a server-owned pointer back to the work;
  2. accepting an answer atomically, from any surface;
  3. continuing the work — separately, retryably, and never twice.

The third is deliberately not part of the second. An answer that was given is a
fact about the person; a continuation that ran is a fact about the system. If
those share a transaction then any failure downstream costs someone their
answer, and the product asks them to repeat themselves — which is exactly the
behaviour a persistent question was supposed to end.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

from waiting.models import (
    AnswerKind,
    AnswerSource,
    OpenQuestion,
    ResumePointer,
    WorkRefs,
    now_iso,
)
from waiting.repository import DuplicateQuestion, OpenQuestionRepository

logger = logging.getLogger("ora.waiting")

# What a person is shown at once. More than a handful of open questions is a
# signal that the reasoning is asking badly, not that the list needs paging.
MAX_OPEN = 20


def _text(v: Any, limit: int = 400) -> str:
    return str(v or "").strip()[:limit]


def _dedupe_key(*, refs: WorkRefs, question: str, asked_refs: List[str]) -> str:
    """
    One blocker, one question.

    Built from what the question is *about* rather than from how it was
    phrased, so a retried cycle that rewords slightly still collides. The
    question text is included but normalised, because two genuinely different
    questions on the same item must still be able to coexist across time.
    """
    parts = [
        refs.session_id or "",
        refs.plan_id or "",
        refs.plan_item_id or "",
        refs.object_id or "",
        "|".join(sorted(asked_refs)),
        " ".join(_text(question, 600).lower().split()),
    ]
    return hashlib.sha256(" ".join(parts).encode("utf-8")).hexdigest()[:40]


class WaitingService:
    def __init__(self, db):
        self.db = db
        self.repo = OpenQuestionRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    # ------------------------------------------------------------------
    # 1. Recording a blocker
    # ------------------------------------------------------------------

    async def record_blocking_question(
        self,
        user_id: str,
        *,
        question: str,
        why_needed: str = "",
        context_label: str = "",
        expected_answer_kind: AnswerKind = "free_text",
        refs: WorkRefs,
        resume: ResumePointer,
    ) -> Optional[Dict[str, Any]]:
        """
        Persist what ORA is waiting for. Returns the public view, or None when
        there was nothing worth persisting.

        Idempotent in two layers: the dedupe key is checked first because that
        is cheap and answers the common case, and the unique index catches the
        race where two cycles reach the insert together. Either way exactly one
        open question exists afterwards.
        """
        q_text = _text(question, 600)
        if not q_text:
            return None

        key = _dedupe_key(refs=refs, question=q_text, asked_refs=list(resume.asked_refs or []))
        existing = await self.repo.find_open_by_dedupe(user_id, key)
        if existing:
            logger.info("question_created dedupe_hit id=%s", existing.get("id"))
            return OpenQuestion.model_validate(existing).public()

        q = OpenQuestion(
            user_id=user_id,
            question=q_text,
            why_needed=_text(why_needed),
            context_label=_text(context_label, 160),
            expected_answer_kind=expected_answer_kind,
            refs=refs,
            resume=resume,
            dedupe_key=key,
        )
        try:
            await self.repo.insert(q)
        except DuplicateQuestion:
            again = await self.repo.find_open_by_dedupe(user_id, key)
            return OpenQuestion.model_validate(again).public() if again else None

        # One blocker at a time per branch. A newer question on the same item
        # means the reasoning moved on; leaving the older one open would ask
        # someone for something ORA has stopped waiting for.
        await self._supersede_siblings(user_id, q)

        logger.info(
            "question_created id=%s kind=%s plan=%s item=%s session=%s",
            q.id, q.resume.kind, refs.plan_id, refs.plan_item_id, refs.session_id,
        )
        return q.public()

    async def _supersede_siblings(self, user_id: str, q: OpenQuestion) -> None:
        match: Dict[str, Any] = {}
        if q.refs.plan_item_id:
            match = {"refs.plan_item_id": q.refs.plan_item_id}
        elif q.refs.plan_id:
            match = {"refs.plan_id": q.refs.plan_id}
        elif q.refs.session_id:
            match = {"refs.session_id": q.refs.session_id}
        if not match:
            return
        n = await self.repo.resolve_where(
            user_id, match=match, status="superseded",
            reason="replaced_by_newer_blocker", exclude_id=q.id,
        )
        if n:
            logger.info("question_superseded count=%d by=%s", n, q.id)

    # ------------------------------------------------------------------
    # 2. Reading
    # ------------------------------------------------------------------

    async def list_open(self, user_id: str, *, limit: int = MAX_OPEN) -> List[Dict[str, Any]]:
        rows = await self.repo.list_open(user_id, limit=limit)
        return [OpenQuestion.model_validate(r).public() for r in rows]

    async def open_for_session(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        rows = await self.repo.list_open_for_session(user_id, session_id)
        return [OpenQuestion.model_validate(r).public() for r in rows]

    # ------------------------------------------------------------------
    # 3. Answering, and continuing
    # ------------------------------------------------------------------

    async def answer(
        self,
        user_id: str,
        question_id: str,
        *,
        answer: str,
        source: AnswerSource = "unknown",
    ) -> Dict[str, Any]:
        """
        Accept an answer from wherever it came, then continue the work.

        The client says what the person typed and nothing else. Where to resume
        is read from the stored pointer — a client that could name its own
        continuation target would be a client that could be talked into naming
        someone else's.
        """
        raw = (answer or "").strip()
        if not raw:
            return {"ok": False, "error": "answer_required"}

        doc = await self.repo.answer(user_id, question_id, answer_raw=raw, source=source)
        if not doc:
            # Either it does not exist, or somebody already answered it. Both
            # are the same answer to the caller: there is nothing left to do.
            current = await self.repo.get(user_id, question_id)
            if not current:
                return {"ok": False, "error": "not_found"}
            return {
                "ok": True,
                "already": True,
                "status": current.get("status"),
                "question_id": question_id,
            }

        logger.info("question_answered id=%s source=%s", question_id, source)
        continuation = await self._continue(user_id, doc)
        return {"ok": True, "question_id": question_id, "status": "answered", **continuation}

    async def retry_continuation(self, user_id: str, question_id: str) -> Dict[str, Any]:
        """Run the work again for an answer that was accepted but never continued."""
        doc = await self.repo.get(user_id, question_id)
        if not doc:
            return {"ok": False, "error": "not_found"}
        if doc.get("status") != "answered":
            return {"ok": False, "error": "not_answered"}
        return {"ok": True, **(await self._continue(user_id, doc))}

    async def _continue(self, user_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Put the reasoning back where it was, then let it think.

        The claim is what makes this run once: two callers reaching here
        together — a retry racing the original, say — will find that only one
        of them owns a `running` continuation, and the other returns without
        touching the work.
        """
        question_id = str(doc.get("id"))
        claimed = await self.repo.claim_continuation(user_id, question_id)
        if not claimed:
            return {"resumed": False, "reason": "already_running_or_done"}

        q = OpenQuestion.model_validate(claimed)
        if q.continuation.exhausted():
            await self.repo.finish_continuation(
                user_id, question_id, ok=False, error="attempts_exhausted"
            )
            logger.warning("resume_failed id=%s reason=attempts_exhausted", question_id)
            return {"resumed": False, "reason": "attempts_exhausted"}

        session_id = q.refs.session_id
        if not session_id:
            # Nothing to continue into. The answer is still recorded, which is
            # what matters; the reasoning will find it as context next time.
            await self.repo.finish_continuation(user_id, question_id, ok=True)
            return {"resumed": False, "reason": "no_thread"}

        logger.info("resume_started id=%s session=%s attempt=%d",
                    question_id, session_id, q.continuation.attempts)
        try:
            await self._restore_focus(user_id, q)
            out = await self._run_turn(user_id, q)
        except Exception as e:  # noqa: BLE001 - the answer must survive anything
            code = type(e).__name__[:120]
            await self.repo.finish_continuation(user_id, question_id, ok=False, error=code)
            logger.exception("resume_failed id=%s", question_id)
            return {"resumed": False, "retryable": True, "reason": code}

        if not out.get("ok"):
            code = _text(out.get("error"), 120) or "turn_failed"
            await self.repo.finish_continuation(user_id, question_id, ok=False, error=code)
            logger.warning("resume_failed id=%s reason=%s", question_id, code)
            return {"resumed": False, "retryable": True, "reason": code}

        await self.repo.finish_continuation(user_id, question_id, ok=True)
        logger.info("resume_completed id=%s session=%s", question_id, session_id)
        return {"resumed": True, "session_id": session_id}

    async def _restore_focus(self, user_id: str, q: OpenQuestion) -> None:
        """
        Hand the reasoning back the work it was on.

        This is the difference between resuming and re-reading. The session may
        have drifted — another conversation, another object — so the plan, the
        item and the object recorded when the question was asked are written
        back onto the session's own focus before the turn runs. The existing
        Life OS binding does it, so ownership is checked the same way it always
        is and no second write path appears.
        """
        if not (q.refs.plan_id or q.refs.object_id or q.refs.plan_item_id):
            return
        try:
            from life_os.service import LifeOsService

            await LifeOsService(self.db).bind_session_object_focus(
                user_id,
                session_id=q.refs.session_id or "",
                object_id=q.refs.object_id,
                plan_id=q.refs.plan_id,
                plan_item_id=q.refs.plan_item_id,
                event_type="question_resume",
            )
        except Exception:
            # A focus that could not be re-bound is worth continuing without:
            # the answer is still delivered into the right session.
            logger.info("resume focus rebind soft-fail id=%s", q.id, exc_info=True)

    async def _run_turn(self, user_id: str, q: OpenQuestion) -> Dict[str, Any]:
        """
        Deliver the answer into the thread that asked for it.

        Reusing the ordinary message path is the point: the answer lands in the
        conversation as a real turn, the transcript stays honest after a
        reload, and the message id makes a retried continuation reuse that turn
        instead of writing a second one.
        """
        from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

        orch = AICoreOrchestrator(self.db)
        return await orch.message(
            user_id,
            str(q.refs.session_id),
            text=q.answer_raw or "",
            client_message_id=f"ans_{q.id}",
        )

    # ------------------------------------------------------------------
    # Lifecycle from the outside
    # ------------------------------------------------------------------

    async def cancel(self, user_id: str, question_id: str, *, reason: str = "user_cancelled") -> bool:
        doc = await self.repo.resolve(user_id, question_id, status="cancelled", reason=reason)
        if doc:
            logger.info("question_cancelled id=%s reason=%s", question_id, reason)
        return bool(doc)

    async def supersede(self, user_id: str, question_id: str, *, reason: str) -> bool:
        """ORA worked the answer out elsewhere; stop asking."""
        doc = await self.repo.resolve(user_id, question_id, status="superseded", reason=reason)
        if doc:
            logger.info("question_superseded id=%s reason=%s", question_id, reason)
        return bool(doc)

    async def close_for_work(
        self,
        user_id: str,
        *,
        plan_id: Optional[str] = None,
        plan_item_id: Optional[str] = None,
        session_id: Optional[str] = None,
        reason: str = "work_closed",
    ) -> int:
        """
        Work that has ended cannot still be waiting for something.

        Completing, cancelling or archiving a plan leaves its questions
        orphaned otherwise: a person keeps being asked about a decision that no
        longer has anything to decide.
        """
        match: Dict[str, Any] = {}
        if plan_item_id:
            match["refs.plan_item_id"] = plan_item_id
        elif plan_id:
            match["refs.plan_id"] = plan_id
        elif session_id:
            match["refs.session_id"] = session_id
        else:
            return 0
        n = await self.repo.resolve_where(
            user_id, match=match, status="cancelled", reason=reason
        )
        if n:
            logger.info("question_cancelled count=%d reason=%s", n, reason)
        return n


_SERVICE: Optional[WaitingService] = None


def get_waiting_service(db) -> WaitingService:
    global _SERVICE
    if _SERVICE is None or _SERVICE.db is not db:
        _SERVICE = WaitingService(db)
    return _SERVICE
