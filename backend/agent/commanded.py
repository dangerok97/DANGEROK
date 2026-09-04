"""
When the person has already said what they want.

    AN EXPLICIT USER COMMAND CAN ITSELF BE THE ONE-TIME AUTHORITY
    FOR THE SPECIFIC ACTION REQUESTED.

    ONE HUMAN DECISION SHOULD NOT REQUIRE TWO HUMAN CONFIRMATIONS
    UNLESS THE SECOND PROTECTS AGAINST A MATERIALLY DIFFERENT EFFECT.

The situation this file exists for is one exchange long. Somebody writes
«segnami un evento di prova domani alle 10» and is asked «vuoi che lo
inserisca?». The only honest answer to that question is the sentence they
have just typed, and being asked it teaches them that saying what they want
does not count. Two turns for one decision, and the second one carries no
information.

The fix is not to stop asking. It is to notice that the asking was already
answered — and to do that in a way an audit can check afterwards, which is
why nothing here is a copy change. A commanded act produces exactly what an
approved one produces: an `ActionIntent` with an `effect_hash`, an
`AuthorityConsent` bound to that hash, an atomic claim, a provider call, an
`ExecutionReceipt` and a read-back. The only field that differs is where the
yes came from, and it is written down rather than smoothed over.

What deliberately does not change:

  - Nothing standing is created. A command is spent on one act and gone.
  - The act is bound by hash. Move the time after the words were said and the
    words no longer cover it.
  - The ceiling holds. Anything that reaches somebody else, costs money,
    commits anybody, is public or destroys something still asks — a command
    is an important authority fact, not a reason to skip a safeguard.
  - ORA's own ideas still ask. This is about a request somebody made, and
    `origin` on a goal is not that: "sort out my residency certificate" is a
    request for an outcome, not permission for any particular act inside it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from agent.authority import AuthorityService, UserCommand
from agent.models import (
    ActionEffect,
    ActionIntent,
    AuthorityAssessment,
    EffectiveAuthority,
    ExecutionReceipt,
    ResultProvenance,
)

logger = logging.getLogger(__name__)

# Argument names that mean somebody other than the owner is on this. Read
# rather than trusted: the schema has no field for a guest today, and the day
# it grows one this must already be looking.
_GUEST_KEYS = ("attendees", "guests", "invitees", "participants", "emails")


# Ways of saying no, flattened. Short on purpose: this is not sentiment
# analysis, it is the handful of words somebody types when they mean stop, and
# a list that tried to be clever would start guessing about people's moods.
_REFUSALS = {
    "no", "no grazie", "meglio di no", "lascia stare", "lascia perdere",
    "annulla", "aspetta", "non ancora", "non farlo", "fermati",
    "stop", "niente", "nah",
}


def reads_as_a_refusal(reply: str) -> bool:
    """
    Whether a reply to a proposal is plainly a no.

    Used only to *withhold* authority, never to grant it. A sentence this
    does not recognise is not thereby a yes — it just leaves the decision
    where it was, which for an unanswered proposal is "still ask".
    """
    from agent.authority import _flatten

    said = _flatten(reply)
    if not said:
        return True
    if said in _REFUSALS:
        return True
    return said.split(" ")[0] in ("no", "non", "annulla", "aspetta", "fermati")


@dataclass
class CommandedAct:
    """One act somebody asked for, and what code decided about it."""

    intent: ActionIntent
    authority: EffectiveAuthority
    command: UserCommand
    # Why it may not go ahead, in a word the caller can act on. Empty when it
    # may.
    blocked_by: str = ""
    missing: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def may_execute(self) -> bool:
        return not self.blocked_by and self.authority.may_execute

    @property
    def basis(self) -> str:
        return self.authority.reason_code


def calendar_effect(arguments: Dict[str, Any]) -> ActionEffect:
    """
    What a calendar request would actually do, derived from the request.

    Derived by code, never declared by the model. The model says what the
    person asked for; whether that act lands on somebody else is a fact about
    the arguments, and a model allowed to answer it could be talked into
    answering no.
    """
    guests = any(arguments.get(key) for key in _GUEST_KEYS)
    modifying = bool(arguments.get("calendar_ref"))
    return ActionEffect(
        effect_type="modify" if modifying else "create",
        target="il calendario personale",
        effect_summary=str(arguments.get("title") or "")[:300],
        # An event with a guest on it is a different act from the same event
        # alone, and it is the difference this whole sprint is about.
        external_party=guests,
        financial_effect=False,
        legal_effect=False,
        privacy_effect=False,
        public_visibility=False,
        destructive=False,
        reversibility="easily",
        expected_outcome=str(arguments.get("title") or "")[:300],
    )


def intent_for_request(
    owner_id: str, *, capability: str, effect: ActionEffect,
    parameters: Dict[str, Any], summary: str, expected: str = "",
) -> ActionIntent:
    """
    An act somebody asked for, as something authority can be about.

    There is no goal and no plan behind this one, and pretending otherwise —
    minting a goal so the shape matches — would put a fiction in the journal.
    So `goal_id` is empty and the step is the act itself: `step_id` carries
    the effect's own hash, which makes the idempotency key a function of what
    is about to happen rather than of when it was asked for. Send the same
    message twice and it is the same key, and therefore one event.
    """
    intent = ActionIntent(
        owner_id=owner_id,
        goal_id="",
        step_id="",
        capability=capability,
        effect_summary=summary[:300],
        target_ref=effect.target[:120],
        parameters=dict(parameters or {}),
        authority_required=capability,
        expected_effect=(expected or summary)[:300],
        reversibility=effect.reversibility,
        external_effect=True,
        status="planned",
        effect=effect,
    )
    # Computed after the intent exists, because the hash is a function of the
    # cleaned parameters and the validator is what cleans them.
    intent.step_id = f"cmd:{intent.effect_hash}"
    return intent


async def assess(
    db, owner_id: str, *, capability: str, effect: ActionEffect,
    parameters: Dict[str, Any], summary: str, command: UserCommand,
    expected: str = "", answered_proposal: bool = False,
) -> CommandedAct:
    """
    Whether this can go ahead now, and on what basis.

    The order inside `effective_authority` is the point and it is not this
    file's to change: a refusal already recorded wins, then a standing
    permission, then a yes already given, and only then the instruction. An
    instruction fills the one gap where ORA would otherwise ask a question
    with a single possible answer.
    """
    intent = intent_for_request(
        owner_id, capability=capability, effect=effect,
        parameters=parameters, summary=summary, expected=expected,
    )
    authority = AuthorityService(db)

    # The other way a person authorises something: ORA asked, and they
    # answered. Until now that lived only in the model's memory of its own
    # last turn, which is not a thing anybody can audit — «the user
    # confirmed» was a sentence in a prompt, not a record. Here it becomes
    # an ordinary consent row, bound to the same hash as any other, created
    # only when code can see that a question was actually asked.
    #
    # A reply that plainly says no withholds it. Nothing else about the
    # sentence is interpreted: not recognising a no is not the same as
    # hearing a yes, and an unrecognised reply simply leaves the act where a
    # proposal leaves it.
    if answered_proposal and not reads_as_a_refusal(command.spoken):
        await authority.consent(
            owner_id, intent, decision="approved",
            shown=(command.asked_for or summary)[:300],
        )

    # The model is not asked to recommend autonomy here, and is given none:
    # the conversation already contains its judgement — it chose to act, and
    # said what the person asked for. Starting from the cautious end means
    # everything that follows is code lifting a floor for a stated reason,
    # never a model talking its way up a ladder.
    assessment = AuthorityAssessment(
        capability=capability,
        model_outcome="prepare_then_confirm",
        reasoning=(command.asked_for or summary)[:400],
        reversibility=effect.reversibility,
        third_party_impact=effect.external_party,
    )
    effective = await authority.effective_authority(
        owner_id, intent, assessment, command=command
    )
    return CommandedAct(intent=intent, authority=effective, command=command)


async def begin(db, act: CommandedAct) -> str:
    """
    Take the act, atomically, or say why not.

    Returns `already_done` when this exact effect has been through before —
    which is what makes a re-sent message, a double tap and a client retry
    produce one calendar entry rather than three.
    """
    from agent.execution import StepExecutor

    return await StepExecutor(db).begin_declared(act.intent)


async def settle(
    db, act: CommandedAct, *, provider: str, external_ref: str,
    accepted: bool, observed: bool, error_type: str = "",
) -> ExecutionReceipt:
    """
    Write down what the provider said and whether anybody looked afterwards.

        PROVIDER ACCEPTED IS NOT OUTCOME ACHIEVED.

    `accepted` and `observed` are two arguments because they are two facts.
    A receipt that collapsed them would be the exact mistake this phase spent
    a sprint refusing: the request went out, therefore it is done.
    """
    from agent.execution import StepExecutor

    receipt = ExecutionReceipt(
        owner_id=act.intent.owner_id,
        goal_id="",
        action_intent_id=act.intent.id,
        idempotency_key=act.intent.idempotency_key,
        capability=act.intent.capability,
        provider=provider,
        external_ref=str(external_ref or "")[:200],
        provider_status=(
            "succeeded" if accepted and observed
            else "accepted" if accepted
            else "failed"
        ),
        error_type=error_type[:80],
        retryable=not accepted,
        authority_basis=act.authority.reason_code,
    )
    receipt.answered_at = receipt.requested_at
    if observed and external_ref:
        receipt.result_refs = [str(external_ref)[:120]]

    executor = StepExecutor(db)
    await executor.settle_declared(
        act.intent, receipt, executed=accepted,
    )
    if act.authority.consent_id:
        # Spent. A one-time yes that stayed unspent would be a yes lying
        # around for the next thing that happened to hash the same way.
        await AuthorityService(db).spend_consent(
            act.intent.owner_id, act.authority.consent_id
        )
    return receipt


def provenance_for(observed: bool, capability: str, provider: str, ref: str) -> ResultProvenance:
    """Where a commanded result came from, and how sure anybody is of it."""
    return ResultProvenance(
        source_class="connected_provider",
        capability=capability,
        provider=provider,
        source_refs=[ref] if ref else [],
        freshness="fresh" if observed else "unknown",
        certainty_note=(
            "riletto dal calendario dopo averlo scritto" if observed
            else "accettato, non ancora osservato"
        ),
    )


async def already_done_ref(db, owner_id: str, intent: ActionIntent) -> Optional[str]:
    """The handle from the time this was already done, if there was one."""
    from agent.execution import StepExecutor

    found = await StepExecutor(db).receipt_for(owner_id, intent.idempotency_key)
    return str((found or {}).get("external_ref") or "") or None
