"""
Mongo persistence for open questions.

Two properties matter more than anything else here and both are enforced by
the storage rather than by application code:

  * a retried reasoning cycle cannot leave two identical open questions —
    the partial unique index on (user_id, dedupe_key) refuses the second;
  * two devices answering the same question at the same moment cannot both
    win — `answer` is a single conditional update, and the loser is told the
    question was already answered rather than starting a second continuation.

Nothing here is in memory. A backend restart finds every open question exactly
where it was, which is the whole point of persisting the blocker instead of
leaving it in a chat transcript.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from waiting.models import (
    AnswerSource,
    ContinuationState,
    OpenQuestion,
    QuestionStatus,
    now_iso,
)


class DuplicateQuestion(Exception):
    """The same blocker was already recorded (idempotent replay)."""


def _is_duplicate_key(exc: Exception) -> bool:
    return "E11000" in str(exc) or getattr(exc, "code", None) == 11000


class OpenQuestionRepository:
    COLLECTION = "open_questions"

    def __init__(self, db):
        self.db = db
        self.col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        await self.col.create_index([("user_id", 1), ("id", 1)], unique=True)
        # One open question per blocker. Partial, so answering does not stop
        # the same question being asked again later if it genuinely recurs.
        await self.col.create_index(
            [("user_id", 1), ("dedupe_key", 1)],
            unique=True,
            partialFilterExpression={"status": "open", "dedupe_key": {"$gt": ""}},
        )
        # The read model: everything a person is currently being asked.
        await self.col.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
        # Cancelling or superseding everything attached to a piece of work.
        await self.col.create_index([("user_id", 1), ("refs.plan_id", 1), ("status", 1)])
        await self.col.create_index([("user_id", 1), ("refs.session_id", 1), ("status", 1)])
        # Continuations that still owe someone an answer.
        await self.col.create_index([("status", 1), ("continuation.status", 1)])

    # --- writes ------------------------------------------------------------

    async def insert(self, q: OpenQuestion) -> None:
        try:
            await self.col.insert_one(q.model_dump())
        except Exception as e:  # pragma: no cover - driver-specific type
            if _is_duplicate_key(e):
                raise DuplicateQuestion(q.dedupe_key) from e
            raise

    async def answer(
        self,
        user_id: str,
        question_id: str,
        *,
        answer_raw: str,
        source: AnswerSource,
    ) -> Optional[Dict[str, Any]]:
        """
        Accept an answer, once.

        The `status: "open"` in the filter is the whole concurrency story: two
        simultaneous requests both reach the database, one matches, the other
        matches nothing and gets `None`. There is no read-then-write window for
        them to race inside, so there can be no second continuation.
        """
        now = now_iso()
        return await self.col.find_one_and_update(
            {"user_id": user_id, "id": question_id, "status": "open"},
            {
                "$set": {
                    "status": "answered",
                    "answer_raw": (answer_raw or "")[:4000],
                    "answer_source": source,
                    "answered_at": now,
                    "updated_at": now,
                    "continuation.status": "pending",
                }
            },
            projection={"_id": 0},
            return_document=True,
        )

    async def claim_continuation(self, user_id: str, question_id: str) -> Optional[Dict[str, Any]]:
        """
        Take ownership of running the continuation, once.

        Same shape as `answer`: only a continuation that is pending or has
        failed can be claimed, so a retry that overlaps with a still-running
        attempt gets nothing rather than running the work twice.
        """
        now = now_iso()
        return await self.col.find_one_and_update(
            {
                "user_id": user_id,
                "id": question_id,
                "status": "answered",
                "continuation.status": {"$in": ["pending", "failed"]},
            },
            {
                "$set": {
                    "continuation.status": "running",
                    "continuation.started_at": now,
                    "updated_at": now,
                },
                "$inc": {"continuation.attempts": 1},
            },
            projection={"_id": 0},
            return_document=True,
        )

    async def finish_continuation(
        self,
        user_id: str,
        question_id: str,
        *,
        ok: bool,
        error: Optional[str] = None,
    ) -> None:
        now = now_iso()
        await self.col.update_one(
            {"user_id": user_id, "id": question_id},
            {
                "$set": {
                    "continuation.status": "done" if ok else "failed",
                    "continuation.completed_at": now if ok else None,
                    "continuation.last_error": None if ok else (error or "unknown")[:120],
                    "updated_at": now,
                }
            },
        )

    async def resolve(
        self,
        user_id: str,
        question_id: str,
        *,
        status: QuestionStatus,
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        """Close an open question without an answer: cancelled or superseded."""
        now = now_iso()
        return await self.col.find_one_and_update(
            {"user_id": user_id, "id": question_id, "status": "open"},
            {"$set": {"status": status, "resolved_reason": reason[:120], "updated_at": now}},
            projection={"_id": 0},
            return_document=True,
        )

    async def resolve_where(
        self,
        user_id: str,
        *,
        match: Dict[str, Any],
        status: QuestionStatus,
        reason: str,
        exclude_id: Optional[str] = None,
    ) -> int:
        """Close every open question matching a work reference. Returns the count."""
        now = now_iso()
        query: Dict[str, Any] = {"user_id": user_id, "status": "open", **match}
        if exclude_id:
            query["id"] = {"$ne": exclude_id}
        res = await self.col.update_many(
            query,
            {"$set": {"status": status, "resolved_reason": reason[:120], "updated_at": now}},
        )
        return int(getattr(res, "modified_count", 0) or 0)

    # --- reads -------------------------------------------------------------

    async def get(self, user_id: str, question_id: str) -> Optional[Dict[str, Any]]:
        return await self.col.find_one({"user_id": user_id, "id": question_id}, {"_id": 0})

    async def find_open_by_dedupe(self, user_id: str, dedupe_key: str) -> Optional[Dict[str, Any]]:
        if not dedupe_key:
            return None
        return await self.col.find_one(
            {"user_id": user_id, "dedupe_key": dedupe_key, "status": "open"}, {"_id": 0}
        )

    async def list_open(self, user_id: str, *, limit: int = 20) -> List[Dict[str, Any]]:
        cur = (
            self.col.find({"user_id": user_id, "status": "open"}, {"_id": 0})
            .sort("created_at", -1)
            .limit(max(1, min(limit, 50)))
        )
        return await cur.to_list(length=limit)

    async def list_open_for_session(self, user_id: str, session_id: str) -> List[Dict[str, Any]]:
        cur = self.col.find(
            {"user_id": user_id, "status": "open", "refs.session_id": session_id}, {"_id": 0}
        ).sort("created_at", -1)
        return await cur.to_list(length=10)

    async def list_stalled_continuations(self, *, limit: int = 20) -> List[Dict[str, Any]]:
        """Answers that were accepted and whose work never continued."""
        cur = self.col.find(
            {"status": "answered", "continuation.status": {"$in": ["pending", "failed"]}},
            {"_id": 0},
        ).limit(max(1, min(limit, 100)))
        return await cur.to_list(length=limit)

    @staticmethod
    def hydrate(doc: Dict[str, Any]) -> OpenQuestion:
        return OpenQuestion.model_validate(doc)

    @staticmethod
    def continuation_of(doc: Dict[str, Any]) -> ContinuationState:
        return ContinuationState.model_validate(doc.get("continuation") or {})
