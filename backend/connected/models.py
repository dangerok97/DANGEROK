"""
What the outside world is, to ORA.

    INTEGRATIONS ARE NOT FEATURES.
    THEY ARE SENSORS AND ACTUATORS OF THE PERSONAL LIFE MODEL.

Two nouns, and the distance between them is the whole design.

A `ConnectedSource` is a thing ORA can look at, and everything true about
*looking*: whether the connection still works, when it last worked, where the
reading got to, and how old what we know is. None of that is about a life. It
is about an instrument, and instruments lie by omission — a source that has
been failing for a day and still reports "connected" turns every downstream
conclusion into a guess nobody flagged.

A `ConnectedSignal` is one observation: something out there is now different
from how we last saw it. It is deliberately not a fact about somebody's life.
"L'appuntamento è passato dalle 10 alle 15" is an observation; whether that
matters, what it means, and whether anybody should hear about it are three
further judgements that belong to layers that already exist.

    A SIGNAL IS SOMETHING OBSERVED.
    A LIFE OBSERVATION IS SOMETHING THAT MEANS SOMETHING.

Nothing here has a way of saying that a signal is important. Reading one tells
you what moved and how sure we are that we saw it — and that is all it can
tell you, on purpose.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# What kind of instrument this is.
#
# The full list is here because a schema that has to be migrated to learn a
# new word is a schema that discourages learning one. Only two of these have
# anything behind them today, and `connected/sensors/` is the only place that
# can change — a name in this list is a shape, not a promise.
# ---------------------------------------------------------------------------
SourceType = Literal[
    "calendar",
    "documents",
    "email",
    "contacts",
    "location",
    "tasks",
    "finance",
    # Un conto bancario. Distinto da «finance», che e' la categoria larga:
    # qui serve il nome dello strumento, perche' e' su quello che il ciclo
    # automatico decide la cadenza — e una banca si legge ogni sei ore,
    # mentre una casella ogni minuto.
    "bank",
    "health",
    "travel",
    "commerce",
    "communications",
]

# How the connection itself is doing. Facts about the instrument, never about
# the life behind it.
#
#   connected     it works, and it worked recently
#   syncing       a reading is in progress
#   degraded      the last attempt failed; what we hold is still what we hold
#   auth_expired  the person's permission needs renewing
#   disconnected  they took it away, or it was never there
#   stale         it works, and what we hold is too old to lean on
SourceStatus = Literal[
    "connected", "syncing", "degraded", "auth_expired", "disconnected", "stale",
]

# How old what we know is. Four words rather than a number of seconds,
# because the question a reasoning step asks is "can I lean on this", and a
# threshold is an answer to a different question.
Freshness = Literal["fresh", "aging", "stale", "unknown"]

# What kind of change was observed.
#
#     CODE KNOWS WHAT CHANGED. THE MODEL DECIDES WHETHER IT MATTERS.
#
# Three words for a calendar, and the shape is the correction. There used to
# be five — `time_changed`, `location_changed`, `updated` — and choosing
# between them meant ranking them: a move outranked a room change, a room
# change outranked a rename, and anything else was dropped. That ranking is a
# judgement about somebody's life ("being late matters more than being in the
# wrong room"), and it was being made by an `if`.
#
# So an update is `changed`, and everything that actually differs travels in
# `changed_fields`. `created` and `cancelled` survive because they are
# structural rather than evaluative: a thing exists or it does not, and no
# opinion is needed to say which.
SignalType = Literal[
    "calendar.event.created",
    "calendar.event.changed",
    "calendar.event.cancelled",
    "document.added",
    "document.updated",
    "document.removed",
    # A message is one arrival; a thread is the conversation it belongs to.
    # Both are facts about a mailbox, and neither says what the message
    # means — "conferma", "richiesta" and "pubblicità" are judgements and
    # live nowhere in this list.
    "email.message.added",
    "email.thread.updated",
]

# Fields whose difference a person could observe. Everything a provider also
# changes on every write — an etag, a sequence number, its own idea of when
# the record was updated — is deliberately absent: those are facts about a
# record, not about a life, and filtering them is arithmetic rather than
# judgement.
#
# The set is what CODE is allowed to look at. Which of them matters is not
# decided here, is not decided anywhere in this package, and a guard walks
# the module to keep it that way.
OBSERVABLE_FIELDS = (
    "title",
    "starts_at",
    "ends_at",
    "all_day",
    "timezone",
    "location",
    "status",
    "description",
    "attendees",
    "recurrence_rule",
    "recurrence_instance_id",
    "organizer",
)

# What a provider rewrites without anything having happened. Recognised so it
# can be ignored, and named so that ignoring it is auditable.
PROVIDER_NOISE_FIELDS = (
    "etag", "sequence", "ical_uid", "updated", "created",
    "source_updated_at", "source_hash", "html_link", "reminders",
)

# Fields whose *content* is not carried, only the fact that it moved.
#
#     DATA MINIMISATION IS NOT THE SAME AS DISCARDING THE FACT.
#
# A description is somebody's private note and an attendee list is other
# people's addresses. Neither belongs in a stored signal — but "the
# description changed" is a fact the judgement is entitled to, and dropping
# the field entirely to protect the content would be protecting it by lying.
WITHHELD_CONTENT_FIELDS = ("description", "attendees", "organizer")

# Who caused what we are looking at.
#
#     ORA MUST RECOGNISE ITS OWN FOOTPRINTS.
#
# `self_originated` is the one that matters. ORA writes an event, the next
# sync sees a new event, and without this the agent would read its own work as
# news about the world and do it again. Not ignored — the observation is real
# and is exactly what verification wants — but it can never become new work.
SignalOrigin = Literal["external", "self_originated"]

SignalStatus = Literal["pending", "interpreted", "superseded", "skipped"]

# Whose commitment this is.
#
#     AN APPOINTMENT SOMEBODY WAS INVITED TO IS SOMEBODY ELSE'S DECISION.
#
# The distinction is not decoration and it is not a preference. An event this
# person arranged is theirs to rearrange; one they were invited to belongs to
# whoever called the meeting, and an assistant that moves it has reached into
# somebody else's day. So it travels as a fact the judgement weighs, and —
# separately — as a fact the authority ceiling reads: an act on a shared
# commitment is an act that reaches a third party, whatever else it looks
# like.
#
# `unknown` is a real answer and stays available. A source that cannot tell
# should say so rather than guess "own", which is the guess that would be
# convenient.
Relationship = Literal["own", "shared", "invited", "unknown"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return _now().isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


# ---------------------------------------------------------------------------
# How old is too old, per instrument.
#
# One threshold for everything would be wrong in both directions: a calendar
# read four hours ago is arguably stale because a day rearranges itself, and a
# document archive read four hours ago is perfectly current because documents
# do not move on their own. The numbers are hours, and they are here rather
# than in a settings screen because they describe the world, not a preference.
# ---------------------------------------------------------------------------
FRESHNESS_HOURS: Dict[str, tuple] = {
    # (fresh up to, aging up to) — beyond the second, stale.
    "calendar": (2, 12),
    "documents": (24, 168),
    # A mailbox goes out of date faster than a shelf and slower than a
    # calendar: what arrives in it is news for a while, and a reading from
    # this morning is still a fair picture of the day.
    "email": (4, 24),
}
DEFAULT_FRESHNESS_HOURS = (6, 48)


def freshness_of(source_type: str, last_success: Optional[str]) -> Freshness:
    """
    How much of what we hold is worth leaning on.

    `unknown` when nothing has ever succeeded — which is not the same as
    stale, and the difference matters: one means we have old news, the other
    means we have never had any.
    """
    if not last_success:
        return "unknown"
    fresh_h, aging_h = FRESHNESS_HOURS.get(source_type, DEFAULT_FRESHNESS_HOURS)
    try:
        moment = datetime.fromisoformat(str(last_success).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "unknown"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    hours = (_now() - moment).total_seconds() / 3600.0
    if hours <= fresh_h:
        return "fresh"
    if hours <= aging_h:
        return "aging"
    return "stale"


class ConnectedSource(BaseModel):
    """
    One instrument ORA can read a life through, and the truth about reading it.

        A SOURCE THAT CANNOT SAY HOW OLD IT IS CANNOT BE TRUSTED FRESH.

    Assembled from what the connector layer already knows rather than kept as
    a second copy of it: the account, the scopes and the cursor live where
    they were always kept, and this is the one place that reads them together
    and answers the question nobody could ask before — "is what I know about
    this person's calendar still true?".
    """

    id: str = Field(default_factory=lambda: _id("src"))
    owner_id: str

    source_type: SourceType
    provider: str = Field(default="", max_length=60)
    # Which account, by the handle its own connector uses. Never a token, and
    # never an address we did not already hold.
    account_ref: str = Field(default="", max_length=200)

    status: SourceStatus = "disconnected"
    read_capabilities: List[str] = Field(default_factory=list, max_length=12)
    write_capabilities: List[str] = Field(default_factory=list, max_length=12)
    granted_scopes: List[str] = Field(default_factory=list, max_length=20)

    last_successful_sync_at: Optional[str] = None
    last_attempt_at: Optional[str] = None
    # Where the reading got to, by whatever the provider calls it. Opaque
    # here: this model has no idea what a Google sync token is, and should
    # not, because the day a second provider arrives it will mean something
    # else entirely.
    sync_cursor: Dict[str, Any] = Field(default_factory=dict)

    freshness_state: Freshness = "unknown"
    health_state: str = Field(default="", max_length=80)
    # A type name or a code, safe to keep and safe to show an engineer. Never
    # a provider body, never a token.
    error_state: str = Field(default="", max_length=120)

    provenance: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    @property
    def is_readable(self) -> bool:
        """Whether asking this instrument for a reading is worth the attempt."""
        return self.status in ("connected", "syncing", "degraded", "stale")

    @property
    def can_be_leaned_on(self) -> bool:
        """Whether what it last said may be treated as how things are."""
        return self.status == "connected" and self.freshness_state in ("fresh", "aging")

    def for_human(self) -> Dict[str, Any]:
        """
        What a person may see about a connection. Deliberately three things.

        No cursor, no scopes, no error codes, no provider ids: every one of
        those is a fact about our plumbing wearing the costume of a fact about
        their life. What is left is the connection, whether it is working, and
        — only when it is genuinely useful — how recently it was read.
        """
        return {
            "what": self.provider or self.source_type,
            "state": _human_state(self.status, self.freshness_state),
            "last_read_at": self.last_successful_sync_at,
        }

    def for_ai(self) -> Dict[str, Any]:
        """
        What a judgement is told. Facts about the instrument, in words.

        `how_old` travels because a reasoning step that does not know its
        evidence is a day out of date will state a day-old thing as current.
        """
        return {
            "kind": self.source_type,
            "working": self.status == "connected",
            "how_old_is_what_we_know": self.freshness_state,
            "problem": self.health_state or None,
        }


def _human_state(status: str, freshness: str) -> str:
    """One sentence about a connection, in the words somebody would use."""
    if status == "disconnected":
        return "Non collegato"
    if status == "auth_expired":
        return "Da ricollegare"
    if status == "syncing":
        return "Sto guardando"
    if status == "degraded":
        return "Non riesco a leggerlo in questo momento"
    if status == "stale" or freshness == "stale":
        return "Collegato, ma quello che so è vecchio"
    return "Connesso"


class FieldChange(BaseModel):
    """
    One thing about a record that is now different, said in facts.

    `content_withheld` is the honest half of data minimisation: the field
    changed, and what it changed to is not ours to keep. A judgement told
    "the description changed" can still decide that matters; a judgement told
    nothing cannot decide anything.
    """

    field: str = Field(max_length=40)
    before: str = Field(default="", max_length=160)
    after: str = Field(default="", max_length=160)
    content_withheld: bool = False

    def for_ai(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"field": self.field}
        if self.content_withheld:
            # Said plainly, so a judgement knows the difference between "this
            # did not change" and "we are not carrying what it changed to".
            out["changed"] = True
            out["content_not_carried"] = True
        else:
            out["from"] = self.before or None
            out["to"] = self.after or None
        return out


class ConnectedSignal(BaseModel):
    """
    One thing that is now different out there from how we last saw it.

        CONNECTED DOES NOT MEAN INTERRUPTING.

    Anaemic on purpose, in exactly the way `MeaningfulChange` is: it says what
    moved and how confident we are that we saw it move. There is no field for
    importance, none for urgency and none for what to do, because a layer that
    could say those things would start saying them about everything.

    `payload_summary` is a phrase, never a copy. The event, the document and
    the provider's body stay where they live; what travels is enough for a
    judgement to recognise the thing and a person to recognise the sentence.
    """

    id: str = Field(default_factory=lambda: _id("sig"))
    owner_id: str
    source_id: str = Field(default="", max_length=64)
    source_type: SourceType

    signal_type: SignalType
    # When we saw it, and when the thing itself is about. They differ, and the
    # difference is what makes "spostato a domani" different from "domani".
    observed_at: str = Field(default_factory=now_iso)
    effective_at: Optional[str] = None

    # The thing that moved, by its own provider handle. A ref, never a copy.
    source_object_ref: str = Field(default="", max_length=200)
    payload_summary: str = Field(default="", max_length=300)
    # What it was before, when there was a before and it is sayable in a
    # phrase. Two short strings are enough for "spostato dalle 10 alle 15";
    # anything longer is the record itself and belongs where it lives.
    #
    # A convenience for surfaces that want one line. Never the whole story:
    # the story is `changed_fields`, and a consumer that reads only these two
    # is reading a summary somebody else chose.
    before: str = Field(default="", max_length=160)
    after: str = Field(default="", max_length=160)

    # Every human-observable difference, all of them, in a stable order.
    #
    #     NOTHING IS DROPPED BECAUSE IT SEEMED UNIMPORTANT.
    #
    # The order is alphabetical by field name and means nothing at all — it
    # exists so two readings of the same change serialise identically and
    # therefore fingerprint identically. It is deliberately not a ranking:
    # there is no first, and no code below reads position for meaning.
    changed_fields: List[FieldChange] = Field(default_factory=list, max_length=12)

    origin: SignalOrigin = "external"
    # Whose thing this is. Read by the judgement, and by the authority
    # ceiling that decides what ORA may do about it on its own.
    relationship: Relationship = "unknown"
    # How many things this one signal actually covers. One, unless a change to
    # a recurring series is being reported as itself rather than as fifty
    # identical appointments moving.
    covers: int = Field(default=1, ge=1, le=999)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    freshness: Freshness = "fresh"
    confidence: Literal["certain", "likely", "unsure"] = "certain"

    # Same news twice is one piece of news. Built from what was observed, not
    # from when — a re-read of an unchanged world produces the same
    # fingerprint and is recognised rather than recorded.
    fingerprint: str = Field(default="", max_length=64)
    supersedes: str = Field(default="", max_length=64)
    # A handle to the record this was derived from, so an audit can walk back
    # to the ingestion row and from there to the provider.
    raw_ref: str = Field(default="", max_length=120)

    status: SignalStatus = "pending"
    interpreted_at: Optional[str] = None
    # What the interpretation concluded, in one word. Kept so a second pass
    # can see that this was already looked at and what came of it.
    outcome: str = Field(default="", max_length=60)

    created_at: str = Field(default_factory=now_iso)

    def compute_fingerprint(self) -> str:
        """
        What this signal *is*, reduced to something comparable.

        Deliberately excludes anything that moves on its own — no clock, no
        ids that get regenerated. Two readings of the same moved appointment
        produce one fingerprint, which is what makes a re-sync free.
        """
        delta = ";".join(
            f"{c.field}={'?' if c.content_withheld else (c.after or '').strip().lower()}"
            for c in sorted(self.changed_fields, key=lambda c: c.field)
        )
        raw = "|".join([
            self.owner_id,
            self.source_type,
            self.signal_type,
            self.source_object_ref.strip().lower(),
            (self.after or "").strip().lower(),
            # The composite delta, so that "moved to 15:00" and "moved to
            # 15:00 and to Studio B" are two different observations rather
            # than one that silently absorbed the other.
            delta,
            # And how far it reaches: one occurrence moving and a whole series
            # moving are different news about the same object.
            str(self.covers),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def for_ai(self) -> Dict[str, Any]:
        """
        What a judgement is shown. Still no opinion anywhere in it.

        `who_caused_it` is here and not hidden because it changes the answer:
        a change ORA made itself is context for checking its own work, and
        never a reason to do more of it.
        """
        out: Dict[str, Any] = {
            "what_kind_of_change": self.signal_type,
            "in_words": self.payload_summary or None,
            # Whose commitment moved. The same appointment changing means
            # something different depending on whether they arranged it.
            "whose_it_is": {
                "own": "theirs — they arranged it",
                "shared": "shared — other people are on it",
                "invited": "somebody else's — they were invited",
            }.get(self.relationship, "not known"),
            "when_we_saw_it": self.observed_at,
            "when_it_is_about": self.effective_at,
            "who_caused_it": (
                "ORA itself" if self.origin == "self_originated" else "the outside world"
            ),
            "how_sure_we_saw_it": self.confidence,
            "how_old_is_the_reading": self.freshness,
        }
        if self.before or self.after:
            out["from_to"] = {"before": self.before or None, "after": self.after or None}
        if self.changed_fields:
            # All of them. A judgement that is shown one of three differences
            # is judging a different event from the one that happened.
            out["what_is_different"] = [c.for_ai() for c in self.changed_fields]
        if self.covers > 1:
            # Said plainly, because "a recurring thing changed" and "fifty
            # appointments changed" would be weighed very differently and only
            # one of them happened.
            out["how_many_occurrences_this_covers"] = self.covers
        return out

    def as_change(self) -> Dict[str, Any]:
        """
        The signal in the vocabulary the existing change log already speaks.

        This is the join, and it is deliberately a translation rather than a
        new pipe: V3.7 built an intake for "something moved" with dedupe,
        coalescing, staleness and a review loop behind it, and declared
        `calendar` and `documents` as sources it would accept. Nothing ever
        spoke to it. Connected Life is what speaks.
        """
        kind = {
            "calendar.event.created": "event.added",
            "calendar.event.changed": "event.updated",
            "calendar.event.cancelled": "event.removed",
            "document.added": "document.added",
            "document.updated": "document.facts_changed",
            "document.removed": "document.facts_changed",
            "email.message.added": "message.received",
            "email.thread.updated": "thread.updated",
        }.get(self.signal_type, "event.updated")
        return {
            "source": {
                "calendar": "calendar",
                "documents": "documents",
                "email": "communications",
            }.get(self.source_type, "documents"),
            "kind": kind,
            "entity_ref": self.source_object_ref,
            "entity_kind": self.source_type,
            "before": self.before,
            "after": self.after or self.payload_summary,
            "occurred_at": self.effective_at or self.observed_at,
        }
