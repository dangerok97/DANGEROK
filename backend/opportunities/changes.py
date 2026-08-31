"""
What the domains are allowed to say when something moves.

    A CHANGE EARNS A REVIEW, NOT ATTENTION.

A domain knows that a calendar event was edited, that a document arrived,
that someone walked through their own front door. What none of them knows is
whether any of it means anything, and the moment a domain is allowed to guess
— `if calendar_changed: create_opportunity()` — proactivity stops being a
judgement and becomes a rule nobody can argue with.

So the envelope carries facts and nothing else: what moved, when, which
thing it was about. There is no field for urgency, no field for relevance,
no way to mark something important. A domain that wants to say "this one
matters" has no vocabulary here to say it in, which is the point.

What this module does own is cost. A judgement is expensive and a life
changes constantly, so admission is deterministic and mechanical: the same
change twice is one change, eight edits to one thing in two seconds are one
review, a change that arrives after the review that would have consumed it
is not a reason to run another. None of those decisions look at meaning.
They look at whether the model would be asked the same question twice.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

COLLECTION = "meaningful_changes"

# How long a consumed change is kept. Long enough to explain a scan that
# already happened, short enough that this never becomes a permanent record of
# somebody's movements.
RETENTION_DAYS = 14

# Changes arriving inside this window are one review, not several.
COALESCE_SECONDS = 90

# The most a single review is told about. Beyond this the oldest are still
# consumed — they are not lost, they are simply not all narrated.
MAX_PER_BATCH = 12

# A change older than this on arrival is describing a world that has already
# been reviewed.
STALE_AFTER_SECONDS = 900

# The domains allowed to speak, and the vocabulary each one has. Membership is
# the whole check: a domain cannot invent a kind that means something special,
# because the set of kinds is fixed here and every one of them is a fact.
KNOWN_SOURCES: Dict[str, tuple] = {
    "calendar": ("event.added", "event.updated", "event.removed"),
    "places": ("presence.changed", "place.added", "place.updated"),
    "documents": ("document.added", "document.facts_changed"),
    "conversation": (
        "open_question.settled",
        "intent.changed",
        "constraint.changed",
        "decision.changed",
    ),
    "comparison": ("comparison.updated", "comparison.decided"),
    "research": ("evidence.added", "research.finished"),
    "work": ("work.resolved", "work.blocked"),
}

AdmissionOutcome = Literal["accepted", "duplicate", "coalesced", "stale", "rejected"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


class MeaningfulChange(BaseModel):
    """
    One fact about something that moved.

    Deliberately anaemic. It says what happened and to what; it has no way of
    saying that it matters, and reading one tells you nothing about whether
    anybody should hear about it.
    """

    id: str = Field(default_factory=lambda: f"chg_{uuid.uuid4().hex[:16]}")
    owner_id: str

    source: str = Field(min_length=1, max_length=40)
    kind: str = Field(min_length=1, max_length=60)

    # The thing that moved, by the handle its own domain already uses. A ref,
    # never a copy: the document itself, the coordinates, the message text and
    # the API payload all stay where they live.
    entity_ref: str = Field(default="", max_length=120)
    entity_kind: str = Field(default="", max_length=40)

    # Human words, when the domain has them and they are short. "annullato",
    # "spostato a giovedì" — a phrase, not a document.
    before: str = Field(default="", max_length=160)
    after: str = Field(default="", max_length=160)

    # When the thing itself happened, if that differs from when we heard.
    occurred_at: str = Field(default_factory=_now_iso)
    recorded_at: str = Field(default_factory=_now_iso)

    # pending until a review consumes it.
    status: Literal["pending", "consumed", "skipped"] = "pending"
    consumed_by: str = Field(default="", max_length=64)
    # Set by Mongo's TTL index; this is a working note, not a diary.
    expires_at: Optional[datetime] = None

    @property
    def identity(self) -> str:
        """Two changes with the same identity are the same news twice."""
        raw = "|".join(
            [self.owner_id, self.source, self.kind, self.entity_ref, self.after]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def for_ai(self) -> Dict[str, Any]:
        """What a scan is told moved. Still no judgement anywhere in it."""
        out: Dict[str, Any] = {
            "what_moved": f"{self.source}:{self.kind}",
            "ref": self.entity_ref or None,
            "when": self.occurred_at,
        }
        if self.before or self.after:
            out["from_to"] = {"before": self.before or None, "after": self.after or None}
        return out


class AdmissionResult(BaseModel):
    """Whether a change is worth the cost of looking again. Not whether it means anything."""

    outcome: AdmissionOutcome
    change: Optional[MeaningfulChange] = None
    reason: str = ""

    @property
    def admitted(self) -> bool:
        return self.outcome == "accepted"


class ChangeLog:
    """The pending changes for one person, and the rules for not re-reading them."""

    def __init__(self, db):
        self.db = db
        self.col = db[COLLECTION]

    async def ensure_indexes(self) -> None:
        try:
            await self.col.create_index("id", unique=True)
            await self.col.create_index([("owner_id", 1), ("status", 1)])
            await self.col.create_index([("owner_id", 1), ("identity", 1)])
            # Retention, enforced by the database rather than by remembering.
            await self.col.create_index("expires_at", expireAfterSeconds=0)
        except Exception:
            logger.exception("indici meaningful_changes non creati (non fatale)")

    async def record(
        self,
        owner_id: str,
        *,
        source: str,
        kind: str,
        entity_ref: str = "",
        entity_kind: str = "",
        before: str = "",
        after: str = "",
        occurred_at: Optional[str] = None,
    ) -> AdmissionResult:
        """
        Take note that something moved, if it is worth taking note.

        Every refusal here is mechanical — the same news twice, news about a
        world that has already been reviewed, a domain saying something it has
        no vocabulary for. None of them is a judgement about importance, and
        none of them can be: this function never sees enough to make one.
        """
        if not owner_id:
            return AdmissionResult(outcome="rejected", reason="nessun proprietario")

        allowed = KNOWN_SOURCES.get(source)
        if allowed is None:
            return AdmissionResult(outcome="rejected", reason=f"dominio sconosciuto: {source}")
        if kind not in allowed:
            return AdmissionResult(
                outcome="rejected", reason=f"{source} non dice {kind}"
            )

        change = MeaningfulChange(
            owner_id=owner_id,
            source=source,
            kind=kind,
            entity_ref=entity_ref[:120],
            entity_kind=entity_kind[:40],
            before=before[:160],
            after=after[:160],
            occurred_at=occurred_at or _now_iso(),
        )

        age = _age_seconds(change.occurred_at)
        if age is not None and age > STALE_AFTER_SECONDS:
            return AdmissionResult(
                outcome="stale", change=change, reason="arrivato dopo la sua revisione"
            )

        identity = change.identity
        try:
            twin = await self.col.find_one(
                {"owner_id": owner_id, "identity": identity, "status": "pending"},
                {"_id": 0, "id": 1, "recorded_at": 1},
            )
        except Exception as e:
            logger.info("change log read soft-fail: %s", type(e).__name__)
            twin = None

        if twin is not None:
            # Identical and still unread: the second copy adds nothing.
            return AdmissionResult(
                outcome="duplicate", change=change, reason="identico a uno già in attesa"
            )

        try:
            recent = await self.col.count_documents(
                {
                    "owner_id": owner_id,
                    "entity_ref": change.entity_ref,
                    "status": "pending",
                }
            ) if change.entity_ref else 0
        except Exception:
            recent = 0

        doc = change.model_dump()
        doc["identity"] = identity
        doc["expires_at"] = _now() + timedelta(days=RETENTION_DAYS)
        try:
            await self.col.insert_one(doc)
        except Exception as e:
            logger.info("change log write soft-fail: %s", type(e).__name__)
            return AdmissionResult(outcome="rejected", reason="non registrabile")

        if recent:
            # Recorded, but the review it joins is already coming: the same
            # thing edited repeatedly is one thing to look at.
            return AdmissionResult(
                outcome="coalesced",
                change=change,
                reason="si unisce a una revisione già in attesa per la stessa cosa",
            )

        return AdmissionResult(outcome="accepted", change=change)

    async def pending(self, owner_id: str, *, limit: int = MAX_PER_BATCH) -> List[MeaningfulChange]:
        docs = await self.col.find(
            {"owner_id": owner_id, "status": "pending"}, {"_id": 0}
        ).sort("recorded_at", 1).to_list(limit)
        return [MeaningfulChange.model_validate(d) for d in docs]

    async def claim(self, owner_id: str, scan_id: str) -> List[MeaningfulChange]:
        """
        Take everything waiting, as one batch.

        Three things moving within a minute of each other are one question
        about a life, not three questions asked separately — which is both
        cheaper and more accurate, because the answer often lives in how they
        relate.
        """
        batch = await self.pending(owner_id)
        if not batch:
            return []
        await self.col.update_many(
            {"owner_id": owner_id, "id": {"$in": [c.id for c in batch]}},
            {"$set": {"status": "consumed", "consumed_by": scan_id}},
        )
        for c in batch:
            c.status = "consumed"
            c.consumed_by = scan_id
        return batch

    async def release(self, owner_id: str, changes: List[MeaningfulChange]) -> None:
        """
        Put a batch back.

        A scan that could not reach the model has not read these, and marking
        them consumed would quietly lose the only record that anything moved.
        """
        if not changes:
            return
        try:
            await self.col.update_many(
                {"owner_id": owner_id, "id": {"$in": [c.id for c in changes]}},
                {"$set": {"status": "pending", "consumed_by": ""}},
            )
        except Exception as e:
            logger.info("change release soft-fail: %s", type(e).__name__)

    async def forget_all(self, owner_id: str) -> int:
        result = await self.col.delete_many({"owner_id": owner_id})
        return result.deleted_count


def _age_seconds(when: str) -> Optional[float]:
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (_now() - moment).total_seconds()


def fingerprint(snapshot: Dict[str, Any]) -> str:
    """
    A hash of the facts a scan would be shown.

    Purely a way of noticing that the model would be handed the same question
    it was handed last time. It says nothing about whether those facts matter
    — a fingerprint cannot rank a life — and the moment anything real moves,
    it changes and the question gets asked again.

    Everything that moves on its own is left out: the clock, the weekday, how
    long a horizon is. Otherwise every snapshot differs from every other one
    and this saves nothing.
    """
    import json

    material = {
        key: snapshot.get(key)
        for key in (
            "open_questions",
            "recently_settled",
            "places",
            "presence",
            "routines",
            "open_comparisons",
            "calendar",
            "existing_work",
        )
    }
    raw = json.dumps(material, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
