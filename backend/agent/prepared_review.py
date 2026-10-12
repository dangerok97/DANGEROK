"""Bind an incomplete final review to the preparation that was actually read.

These handles do not make a draft evidence or assert a positive outcome.
Canonical source validity remains the responsibility of the existing Memory,
Opportunity and Situation fences at execution and publication boundaries.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import uuid

from agent.models import AutonomousGoal, PreparedResultReview


class PreparedReviewUnavailable(RuntimeError):
    """The current artifact could not be checked; this is not an empty review."""


# Transient status, checkpoints and progress are not part of the requested
# result. A changed source or requirement, however, invalidates the old review.
_CONTEXT_FIELDS = {
    "objective": "", "desired_outcome": "", "success_criteria": [],
    "stop_conditions": [], "clarifications": [], "origin": "agent_initiated",
    "source_kind": "", "source_refs": [], "opportunity_id": "",
    "opportunity_revision": "", "source_situation": {}, "valid_until": None,
}


def new_prepared_result_id() -> str:
    return f"prep_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class PreparedResultSnapshot:
    owner_id: str
    goal_id: str
    prepared_result_id: str
    text: str
    sources: tuple[str, ...]
    context: dict

    @property
    def digest(self) -> str:
        encoded = json.dumps({"text": self.text, "sources": self.sources,
                              "context": self.context}, ensure_ascii=False,
                             sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @property
    def ref(self) -> str:
        # Legacy content can receive an explicit negative review without
        # inventing a preparation event, let alone a successful verification.
        return f"prepared_result:{self.prepared_result_id or 'legacy'}:{self.digest}"


def capture_prepared_result(goal) -> PreparedResultSnapshot | None:
    text = getattr(goal, "prepared_text", "")
    if not text:
        return None
    return PreparedResultSnapshot(
        owner_id=goal.owner_id, goal_id=goal.id,
        prepared_result_id=getattr(goal, "prepared_result_id", "") or "",
        text=text, sources=tuple(getattr(goal, "prepared_sources", []) or []),
        context=deepcopy({key: getattr(goal, key, default)
                          for key, default in _CONTEXT_FIELDS.items()}),
    )


def prepared_result_ref(goal) -> str:
    snapshot = capture_prepared_result(goal)
    return snapshot.ref if snapshot else ""


def current_prepared_review(goal) -> dict | None:
    snapshot = capture_prepared_result(goal)
    review = getattr(goal, "prepared_review", None)
    if snapshot is None or review is None:
        return None
    if (review.prepared_result_id != snapshot.prepared_result_id
            or review.artifact_digest != snapshot.digest):
        return None
    return review.model_dump(include={"outcome", "what_is_missing", "reasoning", "reviewed_at"})


@dataclass(frozen=True)
class PreparedResultState:
    goal: AutonomousGoal
    ref: str
    review: dict | None


async def current_prepared_result(db, owner_id: str, goal_id: str) -> PreparedResultState | None:
    """Reload the exact owner's goal; unavailable never means no criticism."""
    try:
        row = await db.agent_goals.find_one({"id": goal_id, "owner_id": owner_id}, {"_id": 0})
        if row is None:
            return None
        goal = AutonomousGoal.model_validate(row)
        return PreparedResultState(goal, prepared_result_ref(goal), current_prepared_review(goal))
    except Exception as exc:
        raise PreparedReviewUnavailable(type(exc).__name__) from None


def _exact_or_legacy_default(field, value):
    if value is None or value == "" or value == [] or value == {}:
        return {"$or": [{field: value}, {field: {"$exists": False}}]}
    return {field: value}


def _snapshot_query(snapshot):
    return {
        "id": snapshot.goal_id, "owner_id": snapshot.owner_id,
        "status": {"$in": ["proposed", "active", "waiting"]},
        "prepared_text": snapshot.text,
        "$and": [
            _exact_or_legacy_default("prepared_result_id", snapshot.prepared_result_id),
            _exact_or_legacy_default("prepared_sources", list(snapshot.sources)),
            *(_exact_or_legacy_default(key, value) for key, value in snapshot.context.items()),
        ],
    }


async def persist_prepared_review(db, owner_id: str, goal, snapshot: PreparedResultSnapshot,
                                 verification) -> bool:
    """Save only a negative verdict for the unchanged owned open artifact.

    The caller captures the snapshot before awaiting the verifier and checks
    canonical sources after it. CAS also protects against a newer preparation
    or edited goal being persisted during that model call.
    """
    if (owner_id != snapshot.owner_id or goal.owner_id != owner_id
            or goal.id != snapshot.goal_id
            or verification.outcome not in ("partially_achieved", "uncertain")
            or capture_prepared_result(goal) != snapshot):
        return False
    review = PreparedResultReview(
        prepared_result_id=snapshot.prepared_result_id, artifact_digest=snapshot.digest,
        outcome="partial" if verification.outcome == "partially_achieved" else "uncertain",
        what_is_missing=verification.what_is_missing,
        reasoning=verification.reasoning, reviewed_at=verification.at,
    )
    try:
        result = await db.agent_goals.update_one(_snapshot_query(snapshot),
            {"$set": {"prepared_review": review.model_dump()}})
    except Exception as exc:
        raise PreparedReviewUnavailable(type(exc).__name__) from None
    if result.matched_count != 1:
        return False
    goal.prepared_review = review
    return True


async def complete_prepared_result(db, owner_id: str, goal, snapshot: PreparedResultSnapshot) -> bool:
    """Commit an already-authorized closure and retire its prior critique once.

    This does not authorize completion: _finish and _close still own all
    positive verification, real-evidence and source/cancellation gates. The
    single write prevents clearing a newer review or closing a newer draft.
    """
    if (owner_id != snapshot.owner_id or goal.owner_id != owner_id
            or goal.id != snapshot.goal_id or goal.status != "completed"
            or capture_prepared_result(goal) != snapshot):
        return False
    data = goal.model_dump()
    data["prepared_review"] = None
    try:
        result = await db.agent_goals.update_one(_snapshot_query(snapshot), {"$set": data})
    except Exception as exc:
        raise PreparedReviewUnavailable(type(exc).__name__) from None
    if result.matched_count != 1:
        return False
    goal.prepared_review = None
    return True
