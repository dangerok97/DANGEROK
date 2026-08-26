"""
WAITING_USER — what ORA is waiting for a person to answer, and where to resume.

The distinction this module exists to hold is one the product did not have.
`ConversationSession.status == "waiting_user"` is set after *every* turn: it
means "the session is idle, your move". It says nothing about whether a piece
of work is blocked, what is blocking it, or where to continue from.

An OpenQuestion is the other thing: a named blocker on a named piece of work,
with a server-owned pointer back to the exact point the reasoning stopped. It
outlives the conversation UI on purpose — a person can answer it from Home two
days later and the work continues from where it was, not from the beginning.

Domain-neutral by construction. There is no mortgage question and no travel
question; there is a question, what it is blocking, and why it is needed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# Lifecycle:
#
#     open ──answer────▶ answered
#      │
#      ├───cancel──────▶ cancelled     the work it blocked is gone
#      └───supersede───▶ superseded    ORA no longer needs the answer
#
# `answered` is terminal for the *question*. Whether the work resumed is a
# separate axis — see `ContinuationState` — because losing someone's answer
# because a continuation crashed is the one failure this design refuses to
# allow.
QuestionStatus = Literal["open", "answered", "cancelled", "superseded"]

ContinuationStatus = Literal["pending", "running", "done", "failed"]

# What kind of answer would unblock this. The reasoning picks it; nothing
# downstream parses the answer *by* it — it is a hint for the interface and for
# the model, never a validator. "bundle" is several tightly-related variables
# that all serve the same next step, asked once instead of five times.
AnswerKind = Literal["free_text", "choice", "decision", "quantity", "date", "bundle"]

# Where the answer arrived from. Presentation provenance, not routing.
AnswerSource = Literal["ora", "home", "activity", "unknown"]

MAX_ATTEMPTS = 5


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_question_id() -> str:
    return f"q_{uuid.uuid4().hex[:16]}"


class WorkRefs(BaseModel):
    """
    The work this question is blocking, in the product's own identifiers.

    Every one of these is optional because not every question blocks a plan —
    a clarification inside a conversation blocks the conversation, and that is
    a legitimate, resumable thing to block. What is never optional is that they
    are written by the server from the reasoning state at the moment the
    question was asked, and never accepted from a client.
    """

    session_id: Optional[str] = Field(default=None, max_length=64)
    plan_id: Optional[str] = Field(default=None, max_length=64)
    plan_item_id: Optional[str] = Field(default=None, max_length=64)
    object_id: Optional[str] = Field(default=None, max_length=64)
    situation_id: Optional[str] = Field(default=None, max_length=64)


class ResumePointer(BaseModel):
    """
    Where the reasoning was when it stopped, in structure rather than prose.

    This is the part that makes a resume a resume. Replaying the transcript and
    asking the model to work out what it had been doing is not continuity: it
    is a second interpretation of the same words, free to reach a different
    conclusion, and it loses the plan item and the object entirely. The model
    still reasons — but over a state it was handed, not one it reconstructed.

    `kind` says what sort of thread this is, so a continuation strategy can
    branch on it without inspecting refs:
      - "plan_work"    a plan (and usually an item) is blocked
      - "object_work"  a generative object is being worked on
      - "conversation" the thread itself is what continues
    """

    kind: Literal["plan_work", "object_work", "conversation"] = "conversation"
    target_id: Optional[str] = Field(default=None, max_length=64)
    reasoning_epoch: Optional[str] = Field(default=None, max_length=64)
    goal_summary: str = Field(default="", max_length=400)
    # The information needs the reasoning said it was asking about. Refs are
    # the AI's own opaque handles (`MissingInformation.ref`), never slot names.
    asked_refs: List[str] = Field(default_factory=list, max_length=8)
    # A bounded snapshot of the conversational focus at the moment of asking,
    # so the refs can be put back even if the session has drifted since.
    focus: Dict[str, Any] = Field(default_factory=dict)


class ContinuationState(BaseModel):
    """
    Answer acceptance and work continuation are two different transactions.

    If the continuation fails — a provider timeout, a tool error, a restart —
    the answer stays answered and this stays retryable. Asking someone to type
    "mutuo" a second time because ORA's own pipeline fell over is the failure
    mode this exists to prevent.
    """

    status: ContinuationStatus = "pending"
    attempts: int = 0
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    # A code, never a stack or a provider message.
    last_error: Optional[str] = Field(default=None, max_length=120)

    def exhausted(self) -> bool:
        return self.attempts >= MAX_ATTEMPTS


class OpenQuestion(BaseModel):
    id: str = Field(default_factory=new_question_id)
    user_id: str

    status: QuestionStatus = "open"

    # What a person reads.
    question: str = Field(min_length=1, max_length=600)
    why_needed: str = Field(default="", max_length=400)
    # Human words for the work this belongs to — "Comprare casa", never an id.
    context_label: str = Field(default="", max_length=160)
    expected_answer_kind: AnswerKind = "free_text"

    refs: WorkRefs = Field(default_factory=WorkRefs)
    resume: ResumePointer = Field(default_factory=ResumePointer)

    # Storage-level idempotency. A retried reasoning cycle asks the same thing
    # again; this is what makes the second attempt find the first question
    # instead of creating a third one.
    dedupe_key: str = Field(default="", max_length=200)

    # The answer, kept exactly as it was given. Whatever the reasoning later
    # makes of it lives beside it and never replaces it: "circa 100 mila" is
    # what the person said, and structure derived from it is an interpretation.
    answer_raw: Optional[str] = Field(default=None, max_length=4000)
    answer_source: AnswerSource = "unknown"
    answered_at: Optional[str] = None

    continuation: ContinuationState = Field(default_factory=ContinuationState)

    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    # Why it left `open`, when it did not leave by being answered.
    resolved_reason: Optional[str] = Field(default=None, max_length=120)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def public(self) -> Dict[str, Any]:
        """
        What an interface is allowed to see.

        The resume pointer is deliberately absent. It is the server's answer to
        "where do I continue", and a client that could read it is a client that
        could be persuaded to suggest a different one.
        """
        return {
            "id": self.id,
            "question": self.question,
            "why_needed": self.why_needed or None,
            "context_label": self.context_label or None,
            "expected_answer_kind": self.expected_answer_kind,
            "created_at": self.created_at,
            # Opaque handles, so an interface can route to the right thread
            # without learning anything about how the work is modelled.
            "session_id": self.refs.session_id,
            "work_kind": self.resume.kind,
        }
