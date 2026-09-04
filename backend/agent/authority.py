"""
What ORA is allowed to actually do, and who gets the last word.

    AI MAY RECOMMEND AUTONOMY.
    CODE MAY DENY IT.
    AI MAY NOT OVERRIDE POLICY.

The model reads the situation and says what kind of act this is: routine, or
something a person should see before it happens. That reading is worth
having — "send this email" means something different depending on who it is
to and what it says, and no table of capabilities knows that.

But the reading is a recommendation. This file takes it and narrows it,
never widens it. Four things can only make the answer more cautious: the
person's own autonomy setting, whether a grant exists for this capability,
whether anything behind it can actually run, and a hard floor for effects
that are irreversible, financial, or reach somebody else.

The asymmetry is the whole safety story. A model that has been talked into
enthusiasm can produce `proceed_autonomously` all day; it will not get past
here without a grant somebody actually made.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from agent.capabilities import CapabilityResolver, Resolution
from agent.models import (
    ActionEffect,
    ActionIntent,
    AuthorityAssessment,
    AuthorityConsent,
    AutonomyGrant,
    AutonomyPolicy,
    EffectiveAuthority,
)

logger = logging.getLogger(__name__)

GRANTS = "autonomy_grants"
POLICIES = "autonomy_policies"
DENIALS = "autonomy_denials"
CONSENTS = "autonomy_consents"

# How long a refusal is remembered. Not for ever - somebody who said no
# last month may say yes today, and a permanent no would be a decision
# nobody made. Long enough that asking again is not nagging.
DENIAL_DAYS = 30

# How long a grant lasts unless somebody says otherwise. An authority given
# once in a good mood should not still be in force a year later.
GRANT_DAYS = 180

# The order of caution, most permissive first. Narrowing means moving right.
_LADDER: List[str] = [
    "proceed_autonomously",
    "prepare_then_confirm",
    "ask_before_execution",
    "needs_user_information",
    "cannot_proceed",
]

# Effects that never proceed on a model's say-so, whatever it concluded and
# whatever grant exists. Sprint 1 does not cross these at all.
_NEVER_AUTONOMOUS = {"payment.execute", "external.booking", "mail.send"}

# ---------------------------------------------------------------------------
# An explicit command is an authority.
#
#     AN EXPLICIT USER COMMAND CAN ITSELF BE THE ONE-TIME AUTHORITY
#     FOR THE SPECIFIC ACTION REQUESTED.
#
#     DO NOT ASK FOR CONFIRMATION OF A DECISION THE USER HAS JUST MADE.
#
# The thing this fixes is small and corrosive. Somebody writes «segnami un
# evento di prova domani alle 10» and is asked «vuoi che lo inserisca?» — a
# question whose only possible answer is the sentence they just typed. Every
# such round trip teaches the person that saying what they want is not
# enough, which is the opposite of what an agent is for.
#
# What it is not: a widening of autonomy. Three things stay exactly as they
# were, and each has a test.
#
#   - It authorises one act, once. It never becomes a standing permission.
#   - It is bound to the act by `effect_hash`. Change the act after the words
#     were said and the words no longer cover it.
#   - It only reaches effects that cannot hurt anybody: nothing that lands on
#     a third party, costs money, commits anybody legally, is public, or
#     destroys something. Those still ask, command or no command.
#
# And it only applies to something a person actually asked for. ORA deciding
# by itself that an act would be useful is a different situation with a
# different answer, and it is the situation approve/deny exists for.
# ---------------------------------------------------------------------------

# Capabilities where a person's own instruction may carry the authority. One,
# and adding to it is a decision somebody has to make on purpose.
_COMMANDABLE = {"calendar.write"}

# Kinds of change an instruction may authorise. Making something and changing
# something; deliberately not un-making it.
_COMMANDABLE_EFFECTS = {"create", "modify"}

# Long enough that two common words cannot be passed off as an instruction.
_MIN_COMMAND_CHARS = 8
_MIN_COMMAND_TOKENS = 2


@dataclass
class UserCommand:
    """
    What a person said, and what the model read out of it.

    `spoken` is the message as it arrived — code's own copy, never the
    model's. `words` is the fragment the model says carries the request, and
    it is checked against `spoken` rather than believed. `asked_for` is the
    act in the model's words: kept for the audit, and used to decide nothing.
    """

    spoken: str = ""
    words: str = ""
    asked_for: str = ""


def _flatten(text: str) -> str:
    """A sentence reduced to something two spellings of it would share."""
    lowered = unicodedata.normalize("NFKD", str(text or "")).casefold()
    stripped = "".join(c for c in lowered if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def command_is_grounded(spoken: str, words: str) -> bool:
    """
    Whether those words were really said, here, in this message.

        THE AUTHORITY IS A SPAN OF THE PERSON'S OWN SENTENCE.

    The one check that cannot be delegated. A model asked "did they ask for
    this?" will say yes — not from malice but because agreeing is what it is
    for — so it is never asked. It is asked to *quote*, and code looks the
    quote up in what actually arrived.

    Deliberately strict: a contiguous span, after both sides are flattened to
    the same shape. Reordered or paraphrased fails, and failing means the
    ordinary propose-then-confirm flow — which is the thing that was already
    working. A false negative costs one question; a false positive is an act
    nobody asked for.
    """
    said = _flatten(spoken)
    claimed = _flatten(words)
    if not said or not claimed:
        return False
    if len(claimed) < _MIN_COMMAND_CHARS:
        return False
    if len([t for t in claimed.split(" ") if len(t) >= 3]) < _MIN_COMMAND_TOKENS:
        return False
    return claimed in said


def effect_is_commandable(effect: ActionEffect) -> Tuple[bool, str]:
    """
    Whether an instruction is enough for this kind of effect, or whether a
    person should still be asked in as many words.

        A COMMAND IS AN IMPORTANT AUTHORITY FACT.
        IT IS NOT A REASON TO SKIP A SAFEGUARD.

    Each of these is a separate reason, checked separately, because a single
    "risky" flag would let one hide behind another — the same discipline the
    grant matcher uses, for the same reason.
    """
    if effect.effect_type not in _COMMANDABLE_EFFECTS:
        return False, "effect_type"
    if effect.external_party:
        return False, "reaches_somebody_else"
    if effect.financial_effect:
        return False, "involves_money"
    if effect.legal_effect:
        return False, "commits_them"
    if effect.public_visibility:
        return False, "public"
    if effect.destructive:
        return False, "destroys_something"
    if effect.reversibility not in ("easily", "with_effort"):
        return False, "cannot_be_undone"
    return True, ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _at_least_as_cautious(a: str, b: str) -> str:
    """The more cautious of two outcomes. Never the more permissive."""
    try:
        return a if _LADDER.index(a) >= _LADDER.index(b) else b
    except ValueError:
        return "ask_before_execution"


class AuthorityService:
    def __init__(self, db):
        self.db = db
        self.capabilities = CapabilityResolver(db)

    async def ensure_indexes(self) -> None:
        try:
            await self.db[GRANTS].create_index([("owner_id", 1), ("capability", 1)])
            await self.db[GRANTS].create_index("expires_at", expireAfterSeconds=0)
            await self.db[POLICIES].create_index("owner_id", unique=True)
            await self.db[DENIALS].create_index([("owner_id", 1), ("capability", 1)])
            await self.db[DENIALS].create_index("expires_at", expireAfterSeconds=0)
            await self.db[CONSENTS].create_index(
                [("owner_id", 1), ("effect_hash", 1)]
            )
            await self.db[CONSENTS].create_index("action_intent_id")
        except Exception:
            logger.exception("indici authority non creati (non fatale)")

    # --- what the person has said -----------------------------------------

    async def policy(self, owner_id: str) -> AutonomyPolicy:
        doc = await self.db[POLICIES].find_one({"owner_id": owner_id}, {"_id": 0})
        return (
            AutonomyPolicy.model_validate(doc) if doc else AutonomyPolicy(owner_id=owner_id)
        )

    async def set_mode(self, owner_id: str, mode: str) -> Dict[str, Any]:
        if mode not in ("observe", "prepare", "act_within_grants"):
            return {"ok": False, "reason": "unknown_mode"}
        policy = await self.policy(owner_id)
        policy.mode = mode  # type: ignore[assignment]
        policy.chosen_by_user = True
        policy.updated_at = _now().isoformat()
        await self.db[POLICIES].update_one(
            {"owner_id": owner_id}, {"$set": policy.model_dump()}, upsert=True
        )
        return {"ok": True, "policy": {"mode": policy.mode}}

    # --- grants -----------------------------------------------------------

    async def grant(
        self, owner_id: str, capability: str, *, scope_note: str = "", by: str = "user",
        effect_scope: Optional[List[str]] = None,
        allows_external_party: bool = False,
        allows_financial: bool = False,
        allows_public: bool = False,
        allows_destructive: bool = False,
        constraints: Optional[Dict[str, Any]] = None,
        human_summary: str = "",
    ) -> Dict[str, Any]:
        """
        Give ORA permission to do one kind of thing without asking each time.

        `by` may only ever be `user` or `code`. There is no path from a model
        to this function, and a test enforces it: an agent that can widen its
        own authority has no authority boundary at all.
        """
        if by not in ("user", "code"):
            return {"ok": False, "reason": "only_a_person_or_code_may_grant"}
        if not capability:
            return {"ok": False, "reason": "missing_capability"}

        grant = AutonomyGrant(
            owner_id=owner_id,
            capability=capability,
            granted_by=by,  # type: ignore[arg-type]
            scope_note=scope_note[:200],
            # Absent scope means the narrowest useful thing, not the widest:
            # a permission given without saying what it covers covers making
            # something new, for the person alone.
            effect_scope=[e for e in (effect_scope or ["create"])][:7],
            allows_external_party=bool(allows_external_party),
            allows_financial=bool(allows_financial),
            allows_public=bool(allows_public),
            allows_destructive=bool(allows_destructive),
            constraints=dict(constraints or {}),
            human_summary=(human_summary or scope_note)[:200],
        )
        doc = grant.model_dump()
        doc["expires_at"] = _now() + timedelta(days=GRANT_DAYS)
        await self.db[GRANTS].update_one(
            {"owner_id": owner_id, "capability": capability},
            {"$set": doc},
            upsert=True,
        )
        return {"ok": True, "grant": grant.public()}

    async def revoke(self, owner_id: str, capability: str) -> Dict[str, Any]:
        result = await self.db[GRANTS].update_many(
            {"owner_id": owner_id, "capability": capability, "active": True},
            {"$set": {"active": False, "revoked_at": _now().isoformat()}},
        )
        return {"ok": True, "revoked": result.modified_count}

    async def has_grant(self, owner_id: str, capability: str) -> bool:
        found = await self.db[GRANTS].find_one(
            {"owner_id": owner_id, "capability": capability, "active": True},
            {"_id": 0, "id": 1},
        )
        return found is not None

    async def grants(self, owner_id: str) -> List[Dict[str, Any]]:
        docs = await self.db[GRANTS].find(
            {"owner_id": owner_id, "active": True}, {"_id": 0}
        ).to_list(20)
        return [AutonomyGrant.model_validate(d).public() for d in docs]


    # --- refusals ---------------------------------------------------------

    async def deny(
        self, owner_id: str, capability: str, *, reason: str = ""
    ) -> Dict[str, Any]:
        """
        Somebody said no. Remember it, so the answer is not asked for again.

            A REFUSAL IS AN ANSWER, NOT A ROUND OF NEGOTIATION.

        The failure this prevents is small and enraging: ORA prepares
        something, asks, is told no, replans, arrives at the same door and
        asks again. From the outside that is not diligence, it is pestering,
        and the fact that a fresh judgement produced it each time is no
        comfort to whoever is being asked.

        Not permanent. A month later the situation may genuinely differ, and
        a no that never expires is a decision nobody made.
        """
        if not capability:
            return {"ok": False, "reason": "missing_capability"}
        row = {
            "owner_id": owner_id,
            "capability": capability,
            "reason": (reason or "")[:200],
            "at": _now().isoformat(),
            "expires_at": _now() + timedelta(days=DENIAL_DAYS),
        }
        await self.db[DENIALS].update_one(
            {"owner_id": owner_id, "capability": capability},
            {"$set": row},
            upsert=True,
        )
        # A refusal also withdraws any standing permission for the same thing:
        # being told no now outranks having been told yes before.
        await self.revoke(owner_id, capability)
        return {"ok": True, "denied": capability}

    async def is_denied(self, owner_id: str, capability: str) -> bool:
        found = await self.db[DENIALS].find_one(
            {"owner_id": owner_id, "capability": capability}, {"_id": 0, "capability": 1}
        )
        return found is not None


    # --- what a permission actually covers --------------------------------

    async def match_grant(
        self, owner_id: str, intent: ActionIntent
    ) -> Tuple[Optional[AutonomyGrant], str]:
        """
        Does any permission this person gave actually cover this act?

            AI PROVIDES SEMANTICS. CODE CHECKS SCOPE. FAIL CLOSED IF AMBIGUOUS.

        Never asked of a model, and it would be a mistake to: "does this
        permission cover this action" reads like a judgement and is in fact
        arithmetic, and a model asked it will be helpful — which is the one
        thing it must not be here.

        Every check below is a reason to say no. There is deliberately no
        branch that widens a grant, infers one from another, or treats a
        near-miss as good enough: the failure this prevents is somebody who
        allowed personal calendar entries discovering that their colleague
        was invited to one.
        """
        if not intent.capability:
            return None, "capability_unknown"

        docs = await self.db[GRANTS].find(
            {"owner_id": owner_id, "capability": intent.capability, "active": True},
            {"_id": 0},
        ).to_list(10)
        if not docs:
            return None, "no_grant"

        effect = intent.effect
        now = _now()
        out_of_scope = False

        for doc in docs:
            try:
                grant = AutonomyGrant.model_validate(doc)
            except Exception:
                continue
            if grant.revoked_at:
                continue
            if grant.expires_at and _as_datetime(grant.expires_at) < now:
                continue

            if effect.effect_type not in grant.effect_scope:
                out_of_scope = True
                continue
            # Each of these is a different way of being bigger than what was
            # allowed, and every one of them is checked separately because a
            # single "risky" flag would let one hide behind another.
            if effect.external_party and not grant.allows_external_party:
                out_of_scope = True
                continue
            if effect.financial_effect and not grant.allows_financial:
                out_of_scope = True
                continue
            if effect.public_visibility and not grant.allows_public:
                out_of_scope = True
                continue
            if effect.destructive and not grant.allows_destructive:
                out_of_scope = True
                continue
            if not _within_constraints(grant.constraints, intent):
                out_of_scope = True
                continue

            return grant, "grant_matched"

        return None, "grant_out_of_scope" if out_of_scope else "no_grant"

    # --- a yes, bound to what it was a yes to -----------------------------

    async def consent(
        self, owner_id: str, intent: ActionIntent, *, decision: str = "approved",
        goal_id: str = "", shown: str = "",
    ) -> AuthorityConsent:
        """
        Record what a person agreed to, keyed on the act rather than its name.

        Only ever called from a place a person reached. There is no path from
        the model to this function, and a test walks for one.
        """
        record = AuthorityConsent(
            owner_id=owner_id,
            action_intent_id=intent.id,
            goal_id=goal_id,
            effect_hash=intent.effect_hash,
            decision="denied" if decision == "denied" else "approved",
            approved_what=(shown or intent.effect.for_human())[:300],
        )
        await self.db[CONSENTS].insert_one(record.model_dump())
        return record

    async def find_consent(
        self, owner_id: str, intent: ActionIntent
    ) -> Tuple[Optional[AuthorityConsent], str]:
        """
        Whether this exact act has already been agreed to.

            APPROVAL DOES NOT SURVIVE THE THING IT APPROVED CHANGING.

        Matched on `effect_hash`. A consent recorded for this intent whose
        hash no longer matches is reported as stale rather than ignored,
        because "you already said yes to something else" is a different
        situation from "you have never been asked" and the model deserves to
        know which.
        """
        # Looked up by what was agreed to, not by the row that carried it.
        # An `ActionIntent` is rebuilt every time the loop reaches its step and
        # gets a fresh id each time, so keying on the id would lose the yes
        # between asking and acting — which is precisely the window it exists
        # to cover. The hash is stable because the act is.
        wanted = intent.effect_hash
        docs = await self.db[CONSENTS].find(
            {"owner_id": owner_id, "effect_hash": wanted}, {"_id": 0}
        ).sort("approved_at", -1).to_list(5)
        if not docs:
            # Nothing for this act. Whether they were once asked about
            # something adjacent is a different question, answered below.
            asked = await self.db[CONSENTS].count_documents(
                {"owner_id": owner_id, "action_intent_id": intent.id}
            )
            return None, "consent_stale" if asked else "no_grant"

        for doc in docs:
            try:
                record = AuthorityConsent.model_validate(doc)
            except Exception:
                continue
            if record.decision == "denied":
                return record, "explicitly_denied"
            if record.used_at:
                # Spent, and therefore no longer authority.
                #
                #     A ONE-TIME YES IS ONE TIME.
                #
                # This used to return the consent as valid, on the reasoning
                # that the idempotency guard would stop the effect happening
                # twice anyway. That reasoning was wrong in the case it
                # mattered: the key is built from the goal and step, the hash
                # from the act, so the *same act inside another goal* has a
                # different key and the same hash. A yes given for Thursday's
                # entry silently authorised an identical entry a second goal
                # wanted to make, and nobody was asked.
                #
                # Pressing approve twice on one goal is still harmless: by the
                # second press the intent is already `executed` and the
                # executor recognises it before authority is consulted.
                return record, "consent_spent"
            return record, "one_time_consent"

        return None, "consent_stale"

    async def consent_from_command(
        self, owner_id: str, intent: ActionIntent, command: UserCommand, *,
        goal_id: str = "",
    ) -> Tuple[Optional[AuthorityConsent], str]:
        """
        Turn a person's own instruction into a yes for exactly this act.

        Refuses more often than it agrees, and every refusal is named. What
        comes out is an ordinary `AuthorityConsent` — same collection, same
        `effect_hash` binding, same one-shot lifetime as one produced by
        pressing a button. The only difference is where it came from, and
        that is recorded rather than smoothed over.

        What it never produces is an `AutonomyGrant`. There is no line here
        that creates one, and a test walks this function looking for it: an
        instruction about tomorrow at ten is not a decision about every
        future Thursday, and treating it as one would be inventing a
        permission the person never gave.
        """
        if intent.capability not in _COMMANDABLE:
            return None, "capability_unknown"
        if intent.capability in _NEVER_AUTONOMOUS:
            return None, "never_autonomous"

        allowed, _why = effect_is_commandable(intent.effect)
        if not allowed:
            return None, "grant_out_of_scope"

        if not command_is_grounded(command.spoken, command.words):
            # They may well have asked. What did not happen is code being
            # able to see it in what arrived — and an authority nobody can
            # check is not one.
            return None, "no_grant"

        if await self.is_denied(owner_id, intent.capability):
            return None, "explicitly_denied"

        record = AuthorityConsent(
            owner_id=owner_id,
            action_intent_id=intent.id,
            goal_id=goal_id,
            effect_hash=intent.effect_hash,
            decision="approved",
            source="explicit_user_command",
            commanded_words=command.words[:200],
            approved_what=(command.asked_for or intent.effect.for_human())[:300],
        )
        await self.db[CONSENTS].insert_one(record.model_dump())
        return record, "explicit_user_command"

    async def spend_consent(self, owner_id: str, consent_id: str) -> None:
        await self.db[CONSENTS].update_one(
            {"owner_id": owner_id, "id": consent_id, "used_at": None},
            {"$set": {"used_at": _now().isoformat()}},
        )

    # --- the answer the executor actually acts on -------------------------

    async def effective_authority(
        self, owner_id: str, intent: ActionIntent, assessment: AuthorityAssessment,
        *, command: Optional[UserCommand] = None,
    ) -> EffectiveAuthority:
        """
        What the model recommended, narrowed by everything code knows.

            CODE ENFORCES THE AUTHORITY CEILING.

        Called twice on purpose: once when the plan reaches the step, and
        again immediately before the provider is touched. The second call is
        not paranoia — a person can revoke a permission in the seconds
        between, and an answer computed ten minutes ago is a claim about ten
        minutes ago.
        """
        narrowed = await self.apply_ceiling(owner_id, assessment)
        answer = EffectiveAuthority(
            recommended_by_ai=assessment.model_outcome,
            code_ceiling=narrowed.effective_outcome,
            effective_decision=narrowed.effective_outcome,
            reason_code="no_grant",
            note=narrowed.code_reason,
        )

        if narrowed.effective_outcome == "cannot_proceed":
            # Why it cannot proceed matters more than that it cannot. "You
            # said no to this" and "nobody ever connected this" lead to
            # different next moves, and a plan told the wrong one wastes a
            # turn finding out.
            if await self.is_denied(owner_id, intent.capability):
                answer.reason_code = "explicitly_denied"
                return answer
            refused, _why = await self.find_consent(owner_id, intent)
            answer.reason_code = (
                "explicitly_denied"
                if refused is not None and refused.decision == "denied"
                else "not_permitted"
            )
            return answer

        grant, why = await self.match_grant(owner_id, intent)
        if grant is not None:
            answer.matched_grant_id = grant.id
            answer.reason_code = "grant_matched"
            # A grant removes the reason to ask. It cannot lift a ceiling code
            # put there for another reason, so this is a floor-raise bounded
            # by what `apply_ceiling` already allowed.
            if narrowed.effective_outcome != "cannot_proceed":
                answer.effective_decision = "proceed_autonomously"
            return answer

        found, consent_why = await self.find_consent(owner_id, intent)
        # The reason matters as much as the row. A consent that is denied,
        # stale or already spent is still a consent — it is just not one that
        # authorises anything, and reading only the row was how a spent yes
        # kept opening doors.
        if consent_why == "one_time_consent" and found is not None and (
            found.decision == "approved"
        ):
            answer.consent_id = found.id
            answer.reason_code = "one_time_consent"
            answer.effective_decision = "proceed_autonomously"
            return answer

        # Nobody has been asked, and nothing standing covers this. The last
        # question is whether anybody needed to be asked: a person who has
        # just said what they want has already decided, and asking them to
        # confirm it is asking them to repeat themselves.
        #
        # Tried last on purpose. A refusal recorded earlier still wins, an
        # existing yes is still the yes that gets spent, and a grant is still
        # the broader basis. An instruction only ever fills the gap where
        # otherwise ORA would have asked a question with one possible answer.
        if command is not None and consent_why != "explicitly_denied":
            minted, _why_command = await self.consent_from_command(
                owner_id, intent, command, goal_id=intent.goal_id
            )
            if minted is not None:
                answer.consent_id = minted.id
                answer.reason_code = "explicit_user_command"
                answer.effective_decision = "proceed_autonomously"
                return answer

        answer.reason_code = (
            "explicitly_denied" if consent_why == "explicitly_denied"
            else "consent_spent" if consent_why == "consent_spent"
            else "consent_stale" if consent_why == "consent_stale"
            else why
        )
        # Nothing proceeds on its own without one of the two things above.
        #
        # `apply_ceiling` knows whether a permission exists for the capability;
        # it does not know whether that permission covers *this act*, because
        # scope is checked here. So a ceiling of `proceed_autonomously` that
        # survived to this point means "nothing else objected", not "go" — and
        # letting it stand was the hole a grant for personal events could have
        # been stretched through.
        answer.effective_decision = _at_least_as_cautious(
            answer.effective_decision, "prepare_then_confirm"
        )
        return answer

    # --- the ceiling ------------------------------------------------------

    async def apply_ceiling(
        self, owner_id: str, assessment: AuthorityAssessment
    ) -> AuthorityAssessment:
        """
        Take what the model concluded and make it no more permissive.

        Every rule here can only move the answer towards caution. There is
        deliberately no branch that makes anything more permissive than what
        the model asked for — not even with a grant, which removes a reason
        to refuse rather than adding a reason to proceed.
        """
        capability = assessment.capability
        resolution: Resolution = await self.capabilities.resolve(owner_id, capability)
        effective = assessment.model_outcome
        reasons: List[str] = []

        if not resolution.known:
            effective = _at_least_as_cautious(effective, "cannot_proceed")
            reasons.append("capability sconosciuta")

        elif await self.is_denied(owner_id, capability):
            # Already asked, already answered. The model is free to have
            # concluded otherwise; it does not get to ask twice.
            effective = _at_least_as_cautious(effective, "cannot_proceed")
            reasons.append("aveva gia detto di no a questa cosa")

        elif resolution.writes:
            # Anything that touches the world starts from "ask", and only a
            # real grant moves it back.
            if capability in _NEVER_AUTONOMOUS:
                effective = _at_least_as_cautious(effective, "ask_before_execution")
                reasons.append("effetto che non parte mai da solo")
            if not await self.has_grant(owner_id, capability):
                effective = _at_least_as_cautious(effective, "prepare_then_confirm")
                reasons.append("nessuna autorizzazione per questa cosa")
            if not resolution.permitted:
                effective = _at_least_as_cautious(effective, "cannot_proceed")
                reasons.append("accesso non concesso")
            if not resolution.executable:
                # Sprint 1: the world-touching side is deliberately not wired.
                effective = _at_least_as_cautious(effective, "prepare_then_confirm")
                reasons.append("l'esecuzione reale non è ancora collegata")

        elif not resolution.permitted:
            effective = _at_least_as_cautious(effective, "cannot_proceed")
            reasons.append("accesso non concesso")

        # The general setting narrows what has not been decided. A grant is a
        # decision about this particular capability, and re-asking about
        # something somebody has explicitly allowed is how «prepare» would
        # quietly become «never».
        policy = await self.policy(owner_id)
        decided = resolution.writes and await self.has_grant(owner_id, capability)
        if policy.mode == "observe" and resolution.writes:
            effective = _at_least_as_cautious(effective, "ask_before_execution")
            reasons.append("ha chiesto che ORA osservi soltanto")
        elif policy.mode == "prepare" and resolution.writes and not decided:
            effective = _at_least_as_cautious(effective, "prepare_then_confirm")
            reasons.append("ha chiesto che ORA prepari e poi chieda")

        assessment.effective_outcome = effective  # type: ignore[assignment]
        assessment.narrowed_by_code = effective != assessment.model_outcome
        assessment.code_reason = "; ".join(reasons)[:200]
        if assessment.narrowed_by_code:
            logger.info(
                "authority narrowed capability=%s model=%s effective=%s",
                capability, assessment.model_outcome, effective,
            )
        return assessment

    async def may_execute(self, owner_id: str, assessment: AuthorityAssessment) -> bool:
        """The one question the executor asks. Nothing else may open this door."""
        return assessment.effective_outcome == "proceed_autonomously"

    async def forget_all(self, owner_id: str) -> Dict[str, int]:
        grants = await self.db[GRANTS].delete_many({"owner_id": owner_id})
        await self.db[POLICIES].delete_many({"owner_id": owner_id})
        await self.db[DENIALS].delete_many({"owner_id": owner_id})
        await self.db[CONSENTS].delete_many({"owner_id": owner_id})
        return {"grants_deleted": grants.deleted_count}


def _as_datetime(value: Any) -> datetime:
    """A moment, however it was stored. Far future when it cannot be read."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        moment = datetime.fromisoformat(str(value))
        return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.max.replace(tzinfo=timezone.utc)


def _within_constraints(constraints: Dict[str, Any], intent: ActionIntent) -> bool:
    """
    Whether the extra conditions on a permission hold.

    Small on purpose. Two conditions are enough for the shapes that exist,
    and a constraint language nobody can read is a permission nobody can
    check — which is worse than not having one.
    """
    if not constraints:
        return True

    target = (constraints.get("target_prefix") or "").strip().lower()
    if target and not intent.target_ref.strip().lower().startswith(target):
        return False

    forbidden = constraints.get("forbidden_parameters") or []
    if any(key in (intent.parameters or {}) for key in forbidden):
        return False

    return True
