"""
Deciding is one job; sending is another, later, and only if it is still true.

    OPPORTUNITY != NOTIFICATION.
    NOTIFICATION != ACTION.
    CODE ORCHESTRATES. AI REASONS.

The dangerous thing about a scheduled notification is the gap between the
decision and the moment. Everything can change in it: the document arrives,
the meeting is cancelled, the person deals with it themselves and would be
puzzled to be told about it at eight the next morning. So a plan is an
intention, `deliver_due` re-examines it before anything leaves, and an
opportunity that closes takes every open plan with it.

The split is strict. The model chooses the mode, the timing, the words and
what a lock screen may carry. This file persists that, enforces bounds it can
enforce without an opinion — no push without permission, no push after the
moment has passed, no second plan for a concern that already has one, a
technical ceiling on how many interruptions can arrive in an hour — and calls
a provider that knows nothing about any of it.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from agent.memory_fence import (
    MemorySourcesUnavailable, memory_result_current, opportunity_memories_current,
)
from delivery import context as delivery_context
from delivery.models import (
    DeliverySubject,
    source_of,
    AmbientActivity,
    DeliveryDecision,
    DeliveryPlan,
    DeliveryResult,
    PushCopy,
)
from delivery.repository import DeliveryRepository

logger = logging.getLogger(__name__)

# The furthest ahead an intention is worth holding. Past this the life it was
# about has moved, and the right thing is to decide again rather than to fire
# a judgement made in a different week.
MAX_PLAN_HORIZON_HOURS = 72

# A technical ceiling, not a view about relevance: however good each one is,
# this many uninvited interruptions in an hour is a malfunction. The model is
# shown the same history and usually stops long before here.
MAX_PUSHES_PER_HOUR = 2

# The shortest gap between two pushes that is not effectively one burst.
MIN_MINUTES_BETWEEN_PUSHES = 10

# How often the ambient line is rewritten. A sentence that changes every few
# minutes reads as fidgeting rather than as presence, and each rewrite costs
# a model call for something nobody asked to be updated.
AMBIENT_REFRESH_HOURS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lockscreen_copy_for(plan: DeliveryPlan) -> Dict[str, str]:
    """Never fall back to expanded copy on a personal/private lock screen.

    PushCopy.public() retains a legacy fallback needed by ordinary messages.
    That fallback is inappropriate when sensitivity was explicitly elevated.
    """
    if plan.sensitivity == "ordinary":
        return plan.words.public()
    return {
        "title": (plan.words.public_title or "").strip() or "Avviso riservato di ORA",
        "body": (plan.words.public_body or "").strip() or "Apri ORA per i dettagli.",
    }


class DeliveryService:
    def __init__(self, db):
        self.db = db
        self.repo = DeliveryRepository(db)

    # --- deciding ---------------------------------------------------------

    async def evaluate(
        self,
        user_id: str,
        opportunity_id: str,
        *,
        app_state: str = "unknown",
        language: str = "it",
    ) -> DeliveryResult:
        """
        How should this reach them, if at all?

        Most of the time the answer is `silence` or `in_app`, and neither
        writes a plan. A plan is only for something that intends to arrive.
        """
        from opportunities.repository import OpportunityRepository

        opportunity = await OpportunityRepository(self.db).get(user_id, opportunity_id)
        if opportunity is None:
            return DeliveryResult(blocked_by="unknown_opportunity")
        if opportunity.status != "active":
            # A concern that is settled has nothing to announce, and any
            # intention left standing for it is now wrong.
            await self.cancel_for_opportunity(
                user_id, opportunity_id, reason="la questione non è più aperta"
            )
            return DeliveryResult(blocked_by="opportunity_not_active")

        return await self.evaluate_subject(
            user_id, opportunity, app_state=app_state, language=language
        )

    async def evaluate_subject(
        self,
        user_id: str,
        subject: Any,
        *,
        app_state: str = "unknown",
        language: str = "it",
    ) -> DeliveryResult:
        """
        The same judgement, for anything that might need saying.

            DELIVERY DECIDES WHETHER, WHEN AND HOW. NOBODY ELSE.

        This is the whole bridge. V3.8 was written when only an opportunity
        could reach somebody, and an agent that gets stuck is not an
        opportunity — inventing one so it could get through would have been
        three lines and a lie. So the subject became a shape rather than a
        type, and everything below is the code that was already here.

        Nothing about the source reaches the judgement as a shortcut: an
        agent need does not get a different prompt, a different mode set, or
        a lower bar for interrupting. It gets the same question asked about
        different facts.
        """
        from delivery.reasoning import decide_delivery

        kind = source_of(subject)
        subject_id = getattr(subject, "id", "")
        if kind == "source_result":
            from delivery.source_results import current_subject, existing_plan, settled_or_inflight
            try:
                subject = await current_subject(self.db, user_id, subject_id)
            except MemorySourcesUnavailable:
                return await self._source_check_unavailable(user_id, kind, subject_id)
            if subject is None:
                await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                             reason="il risultato verificato non è più attuale")
                return DeliveryResult(blocked_by="source_result_changed")
            previous = await existing_plan(self.db, user_id, subject_id)
            if settled_or_inflight(previous):
                return DeliveryResult(mode="in_app", blocked_by="source_result_already_handled",
                                      plan=DeliveryPlan.model_validate(previous))
            import os
            if not os.environ.get("ORA_SOURCE_MODEL_CONTRACT"):
                return DeliveryResult(unavailable=True, blocked_by="source_model_contract_required")
        if kind == "agent_need":
            try:
                current = await self._current_agent_need(user_id, subject_id)
            except MemorySourcesUnavailable:
                return await self._source_check_unavailable(user_id, kind, subject_id)
            if current is None:
                await self.cancel_for_source(
                    user_id, subject_id, source_type=kind,
                    reason="la richiesta o il suo esito non sono più attuali",
                )
                return DeliveryResult(blocked_by="agent_need_source_changed")
            # Re-judgement sees the validated current need, not caller-held
            # wording or a result from an older Situation attention cycle.
            subject = current
        if (kind in ("agent_need", "opportunity")
                and getattr(subject, "source_context", "") != "one_shot_reminder"
                and not getattr(subject, "requires_response", False)):
            # Something drying outdoors has one voice: the computed plan sends
            # its own notices. The model's watch stays in the app (27/10: a
            # second notice at 21:04, hours after dark).
            from situations.outdoor_drying import situation_of, speaks_for
            sid = await situation_of(self.db, user_id, kind, subject)
            if sid and await speaks_for(self.db, user_id, sid):
                await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                             reason="gli avvisi li manda il calcolo dal meteo")
                return DeliveryResult(mode="in_app", blocked_by="computed_plan_speaks",
                                      reason="Per questa situazione avvisa il calcolo dal meteo.")
        if (kind == "opportunity" and getattr(subject, "source_context", "") != "one_shot_reminder"
                and any(getattr(e, "kind", "") == "departure" for e in getattr(subject, "evidence", []) or [])
                and await self.db.reminders.find_one(
                    {"user_id": user_id, "origin": "leave_notice", "status": {"$ne": "cancelled"}}, {"_id": 1})):
            # The leave notice computed by code is the one voice for departures.
            await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                         reason="l'avviso di partenza lo manda il calcolo del percorso")
            return DeliveryResult(mode="in_app", blocked_by="computed_plan_speaks",
                                  reason="Per la partenza avvisa il calcolo del percorso.")
        # Do not even ask a model to notify about a provably expired event.
        # The exact source is rechecked once more just before send.
        if kind == "opportunity":
            try:
                memory_current = await opportunity_memories_current(self.db, user_id, subject)
            except MemorySourcesUnavailable:
                return await self._source_check_unavailable(user_id, kind, subject_id)
            if not memory_current:
                await self.cancel_for_source(
                    user_id, subject_id, source_type=kind,
                    reason="le memorie citate sono state aggiornate o ritirate",
                )
                return DeliveryResult(blocked_by="memory_sources_changed")
            from opportunities.source_lifecycle import (
                perishable_opportunity_expired, appointment_disagreement_unverifiable,
            )
            from agent.service import _aware_wait_until
            source_deadline = _aware_wait_until(getattr(subject, "valid_until", None))
            if (
                (source_deadline is not None and source_deadline <= datetime.now(timezone.utc))
                or await perishable_opportunity_expired(self.db, user_id, subject)
                or await appointment_disagreement_unverifiable(self.db, user_id, subject)
            ):
                await self.cancel_for_source(
                    user_id, subject_id, source_type=kind,
                    reason="l'appuntamento originario è già terminato",
                )
                return DeliveryResult(blocked_by="expired_source_event")
        if kind == "opportunity" and getattr(subject, "source_context", "") == "recurring_memo":
            from memos.delivery_guard import memo_opportunity_current

            if not await memo_opportunity_current(self.db, subject):
                await self.cancel_for_source(
                    user_id, subject_id, source_type=kind,
                    reason="il promemoria originario non è più valido",
                )
                return DeliveryResult(
                    mode="in_app", blocked_by="recurring_memo_source_changed",
                    reason="Il ricordo o il promemoria è stato modificato o revocato.",
                )

        if kind == "opportunity":
            from memos.one_shot import reminder_opportunity_current

            if not await reminder_opportunity_current(self.db, subject):
                await self.cancel_for_source(
                    user_id, subject_id, source_type=kind,
                    reason="il promemoria è stato completato o eliminato",
                )
                return DeliveryResult(
                    mode="in_app", blocked_by="reminder_source_changed",
                    reason="Il promemoria è stato completato o eliminato.",
                )

        if any(e.kind == "departure" for e in getattr(subject, "evidence", [])):
            from places.departures import DepartureService
            try:
                current = await DepartureService(self.db).evidence_is_current(user_id, subject)
            except Exception:
                current = False
            if not current:
                await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                             reason="il percorso richiede una nuova verifica")
                return DeliveryResult(blocked_by="departure_evidence_stale")

        if await self._muted(user_id, subject_id):
            # "Non notificarmi per questa cosa." Checked before anything is
            # spent: a person saying stop should not depend on a model
            # agreeing, and asking one anyway would be paying to be told
            # something already decided. Not a dismissal — the concern goes on
            # living wherever it was living, so this lands on the screen.
            await self.cancel_for_source(
                user_id, subject_id, source_type=kind,
                reason="l'utente ha chiesto di non essere avvisato",
            )
            return DeliveryResult(
                mode="in_app",
                blocked_by="muted_by_user",
                reason="l'utente ha chiesto di non essere avvisato per questa cosa",
            )

        moment = await delivery_context.build(
            self.db, user_id, subject=subject, app_state=app_state
        )
        # Source-origin work and its communication use the same configured
        # provider/model boundary; ordinary notification decisions are unchanged.
        from contextlib import nullcontext
        contract_scope = nullcontext()
        if kind == "source_result":
            from llm.model_contract import scoped_model_contract
            contract_scope = scoped_model_contract(os.environ.get("ORA_SOURCE_MODEL_CONTRACT"))
        from memos.one_shot import SOURCE_CONTEXT as ONE_SHOT, push_decision
        if kind == "opportunity" and getattr(subject, "source_context", "") == ONE_SHOT:
            # The person already decided this one: "ricordamelo alle 15".
            # Asking a model whether to interrupt would only make the reminder
            # depend on a quota. Quiet hours and devices still apply below.
            answer = push_decision(subject)
        else:
            with contract_scope:
                answer = await decide_delivery(moment, language=language)

        if answer is None:
            # No judgement was available. Nothing is sent, nothing is
            # recorded as silence, and the next pass tries again.
            logger.info("delivery judgement unavailable for %s", user_id[:8])
            return DeliveryResult(unavailable=True, reason="il giudizio non era disponibile")

        if kind == "source_result":
            try:
                subject = await current_subject(self.db, user_id, subject_id)
            except MemorySourcesUnavailable:
                return await self._source_check_unavailable(user_id, kind, subject_id)
            if subject is None:
                await self.cancel_for_source(user_id, subject_id, source_type=kind,
                                             reason="il risultato è cambiato durante la decisione")
                return DeliveryResult(blocked_by="source_result_changed")
        decision = self._read(answer)

        if decision.mode != "push":
            # Quiet, in-app or nothing: no intention to arrive anywhere, so no
            # plan — and any plan that was standing is no longer what we think.
            await self.cancel_for_source(
                user_id, subject_id, source_type=kind,
                reason="non è più il caso di interrompere",
            )
            return DeliveryResult(
                mode=decision.mode,
                reason=decision.reason_to_interrupt or "",
                what_decided_the_mode=decision.what_decided_the_mode,
            )

        allowed, why_not = await self._may_push(
            user_id, moment,
            invited=kind == "opportunity" and getattr(subject, "source_context", "") == ONE_SHOT,
        )
        if not allowed:
            # A technical refusal, named as one. The judgement stands; the
            # channel is unavailable, so it lands on the screen instead.
            plan = await self._hold(
                user_id, subject_id, decision, why_not, source_type=kind
            )
            return DeliveryResult(
                mode="in_app", blocked_by=why_not, plan=plan,
                reason="l'interruzione non era possibile adesso",
                what_decided_the_mode=decision.what_decided_the_mode,
            )

        plan = await self._plan(user_id, subject, decision)
        result = DeliveryResult(
            mode="push", plan=plan, reason=decision.reason_to_interrupt,
            what_decided_the_mode=decision.what_decided_the_mode,
        )

        if plan.not_before:
            # Somebody has to be there at that hour. Sprint 1 wrote the
            # intention and then waited for a request to come along; this is
            # the alarm that makes a future decision actually happen.
            await self._arrange_wake(plan)

        if plan.status == "pending" and self._due(plan):
            # Decided for now, so now. Everything else waits for its moment
            # and gets re-examined when it arrives.
            await self._send(user_id, plan)
        return result

    def _read(self, raw: Dict[str, Any]) -> DeliveryDecision:
        """The model's answer, trimmed to the contract and bounded in time."""
        copy = raw.get("copy") if isinstance(raw.get("copy"), dict) else {}
        decision = DeliveryDecision(
            mode=raw["mode"],
            timing=(
                str(raw.get("timing") or "now").strip().lower()
                if str(raw.get("timing") or "now").strip().lower()
                in ("now", "at", "window", "hold")
                else "now"
            ),
            not_before=_bounded(raw.get("not_before")),
            not_after=_bounded(raw.get("not_after")),
            reason_to_interrupt=str(raw.get("reason_to_interrupt") or "")[:400],
            reason_to_open=str(raw.get("reason_to_open") or "")[:400],
            what_decided_the_mode=str(raw.get("what_decided_the_mode") or "")[:300],
            copy_intent=str(raw.get("copy_intent") or "")[:300],
            confidence=(
                raw.get("confidence")
                if raw.get("confidence") in ("weak", "reasonable", "strong")
                else "reasonable"
            ),
            sensitivity=(
                raw.get("sensitivity")
                if raw.get("sensitivity") in ("ordinary", "personal", "private")
                else "ordinary"
            ),
            requires_recheck=bool(raw.get("requires_recheck", True)),
        )
        if decision.mode == "push":
            decision.words = PushCopy(
                title=str(copy.get("title") or "")[:80],
                body=str(copy.get("body") or "")[:200],
                public_title=str(copy.get("public_title") or "")[:80],
                public_body=str(copy.get("public_body") or "")[:200],
            )
        return decision

    # --- intentions -------------------------------------------------------

    async def _plan(
        self, user_id: str, subject, decision: DeliveryDecision
    ) -> DeliveryPlan:
        """
        Write down the intention — updating the one that exists, never adding.

        Three re-evaluations of the same concern are three judgements about
        one thing, and a person should hear about it once. So an open plan is
        found and rewritten with what we now think.
        """
        kind = source_of(subject)
        if kind == "source_result":
            from delivery.source_results import save_decision
            return await save_decision(self, subject, decision)
        existing = await self.repo.open_plan_for(
            user_id, subject.id, source_type=kind
        )
        plan = existing or DeliveryPlan(
            owner_id=user_id, source_type=kind, source_id=subject.id, mode="push"
        )

        plan.mode = "push"
        plan.status = "pending"
        plan.not_before = decision.not_before
        plan.not_after = decision.not_after or _default_not_after(subject)
        plan.words = decision.words or PushCopy()
        plan.reason_to_interrupt = decision.reason_to_interrupt
        plan.reason_to_open = decision.reason_to_open
        # Rewritten on every re-evaluation: the trade-off that held last night
        # is not necessarily the one that holds this morning.
        plan.what_decided_the_mode = decision.what_decided_the_mode
        plan.sensitivity = decision.sensitivity
        plan.deep_link = _deep_link_for(subject)
        plan.decision_provenance = "model"
        plan.rationale = decision.reason_to_interrupt[:300]
        return await self.repo.save_plan(plan)

    async def _hold(
        self, user_id: str, subject_id: str, decision: DeliveryDecision, why: str,
        *, source_type: str = "opportunity",
    ) -> DeliveryPlan:
        if source_type == "source_result":
            from delivery.source_results import current_subject, save_decision
            subject = await current_subject(self.db, user_id, subject_id)
            if subject is None:
                raise MemorySourcesUnavailable("source_result_changed_before_hold")
            return await save_decision(self, subject, decision, held_reason=why)
        existing = await self.repo.open_plan_for(
            user_id, subject_id, source_type=source_type
        )
        plan = existing or DeliveryPlan(
            owner_id=user_id, source_type=source_type, source_id=subject_id,
            mode="push",
        )
        plan.status = "held"
        plan.decision_provenance = "code_safety"
        plan.rationale = why
        plan.reason_to_open = decision.reason_to_open
        plan.what_decided_the_mode = decision.what_decided_the_mode
        plan.words = decision.words or plan.words
        plan.deep_link = plan.deep_link or _deep_link(
            subject_id, target="opportunity" if source_type == "opportunity" else "home"
        )
        return await self.repo.save_plan(plan)

    # --- sending, much later ----------------------------------------------

    async def _current_agent_need(self, user_id: str, need_id: str) -> Optional[Any]:
        """Bind communication to its current owned work and Situation result.

        Completing a watch can leave its useful result to communicate. It
        cannot leave a question asking for authority/information, or revive
        an outcome after the person has resolved, revoked or changed it.
        """
        from agent.needs import NeedService
        from agent.repository import AgentRepository
        from agent.service import AgentService, _aware_wait_until

        need = await NeedService(self.db).get(user_id, need_id)
        if need is None or not need.is_open:
            return None
        goal = await AgentRepository(self.db).get_goal(user_id, need.goal_id)
        if goal is None:
            return None
        if not await memory_result_current(self.db, user_id, goal, need.memory_source_snapshot):
            return None
        now = _now()
        for raw in (need.valid_until, goal.valid_until):
            due = _aware_wait_until(raw)
            if due is not None and due <= now:
                return None
        if await AgentService(self.db)._legacy_event_alert_expired(user_id, goal):
            return None

        watched = goal.source_kind in ("situation_initial_review", "situation_followup")
        if not goal.is_open and not (
            watched and goal.status == "completed" and need.kind == "important_outcome"
        ):
            return None
        outcome = None
        if watched:
            if need.kind in ("important_outcome", "useful_result"):
                from situations.outcomes import current_outcome, outcome_refs

                if await self.db.delivery_plans.find_one({
                    "owner_id": user_id, "source_type": "agent_need",
                    "source_id": need.id, "status": "delivered",
                }, {"_id": 0, "id": 1}):
                    return None  # The same immutable assessment already arrived.
                outcome = await current_outcome(
                    self.db, user_id, goal, allow_settled=goal.status == "completed", now=now,
                )
                if outcome is None or not set(outcome_refs(outcome)) <= set(need.source_refs):
                    return None
                if goal.status == "completed" and outcome["status"] != "action_now":
                    return None
            else:
                from agent.source_refresh import changed

                # A failed best-effort cancellation must not leave an old
                # question deliverable while its source is already closed.
                if await changed(self.db, goal):
                    return None
        subject = need.as_subject()
        if outcome:
            subject["semantic_summary"] = (
                f"{outcome['headline']} {outcome['action_summary']}"
            )[:400]
            if outcome["basis"] == "estimate":
                subject["why_it_matters"] = (
                    "È una stima, non una misura diretta dell'esito. " + subject["why_it_matters"]
                )[:400]
            if outcome.get("action_reason") == "early_risk":
                subject["why_now"] = "L'azione evita un rischio; non conferma che l'esito atteso sia già raggiunto."
            expiry = _aware_wait_until(outcome["valid_until"])
            original = _aware_wait_until(subject.get("valid_until"))
            subject["valid_until"] = min(expiry, original).isoformat() if original else expiry.isoformat()
        return DeliverySubject.model_validate(subject)

    async def _current_subject_for_plan(
        self, user_id: str, plan: DeliveryPlan
    ) -> Optional[Any]:
        """Reload the exact thing a pending notification is about.

        A delivery plan is only an intention. At send time the source must
        still exist *as the same kind of source* and still be open. Agent
        needs are not opportunities, so they are reloaded through their own
        repository and adapted to DeliverySubject only at this boundary.
        """
        if plan.owner_id != user_id:
            return None
        if plan.source_type == "source_result":
            from delivery.source_results import current_subject
            return await current_subject(self.db, user_id, plan.source_id)
        if plan.source_type == "opportunity":
            from opportunities.repository import OpportunityRepository

            subject = await OpportunityRepository(self.db).get(
                user_id, plan.source_id or plan.opportunity_id
            )
            if subject is None or subject.status != "active":
                return None
            if not await opportunity_memories_current(self.db, user_id, subject):
                return None
            from agent.service import _aware_wait_until
            deadline = _aware_wait_until(subject.valid_until)
            if deadline is not None and deadline <= datetime.now(timezone.utc):
                return None
            # A successful AI admission is not everlasting authorization
            # to notify: recheck the owner-owned event before every send.
            from opportunities.source_lifecycle import (
                perishable_opportunity_expired, appointment_disagreement_unverifiable,
            )
            if (
                await perishable_opportunity_expired(self.db, user_id, subject)
                or await appointment_disagreement_unverifiable(self.db, user_id, subject)
            ):
                return None
            if getattr(subject, "source_context", "") == "recurring_memo":
                from memos.delivery_guard import memo_opportunity_current

                if not await memo_opportunity_current(self.db, subject):
                    return None
            from memos.one_shot import reminder_opportunity_current

            if not await reminder_opportunity_current(self.db, subject):
                return None
            return subject

        if plan.source_type == "agent_need":
            return await self._current_agent_need(user_id, plan.source_id)

        return None

    async def deliver_due(self, user_id: str, *, language: str = "it") -> Dict[str, Any]:
        """
        Re-decide every due notification from fresh source state.

            RECHECK BEFORE DELIVERY MEANS RE-JUDGE, NOT JUST RE-PERMISSION.

        The plan records what seemed worth saying earlier. When its moment
        arrives, ORA reloads the exact source and asks Delivery again using the
        current moment. The answer may now be silence, in-app, a later push or
        a push now. This applies equally to opportunities and agent needs.
        """
        sent, cancelled, held = 0, 0, 0

        for plan in await self.repo.open_plans(user_id):
            if self._expired(plan):
                plan.status = "expired"
                plan.decision_provenance = "code_expiry"
                plan.rationale = "il momento utile è passato"
                if plan.outcome is None and plan.delivered_at:
                    plan.outcome = "expired"
                await self.repo.save_plan(plan)
                cancelled += 1
                continue

            if not self._due(plan):
                held += 1
                continue

            try:
                subject = await self._current_subject_for_plan(user_id, plan)
            except MemorySourcesUnavailable:
                await self._defer_source_check(plan)
                held += 1
                continue
            if subject is None:
                await self._cancel(
                    plan, "la sorgente non è più aperta prima dell'invio", "code_cancel"
                )
                cancelled += 1
                continue

            # Persist proof that the old intention was revisited even when the
            # model is temporarily unavailable. An outage is not silence and
            # leaves the plan open for another bounded attempt.
            plan.last_rechecked_at = _now().isoformat()
            await self.repo.save_plan(plan)

            result = await self.evaluate_subject(
                user_id, subject, app_state="unknown", language=language
            )

            current = await self.repo.get_plan(user_id, plan.id)
            if current is None:
                cancelled += 1
                continue
            if current.status == "delivered":
                sent += 1
            elif current.status in ("cancelled", "expired"):
                cancelled += 1
            else:
                # pending for a newly chosen future moment, held by a code
                # safety gate, or still pending because judgement was
                # unavailable: all mean "not sent now".
                held += 1

        return {"sent": sent, "cancelled": cancelled, "held": held}

    async def _send(self, user_id: str, plan: DeliveryPlan) -> None:
        if plan.source_type == "source_result":
            from delivery.source_results import send_guarded
            await send_guarded(self, user_id, plan)
            return
        await self._send_current(user_id, plan)

    async def _send_current(self, user_id: str, plan: DeliveryPlan):
        from delivery.provider import get_provider

        # A source can close after the re-judgement but before the provider
        # call. Re-read it at the last possible boundary; no old plan gets to
        # outlive the fact that justified it.
        try:
            subject = await self._current_subject_for_plan(user_id, plan)
        except MemorySourcesUnavailable:
            await self._defer_source_check(plan)
            return
        if subject is None:
            await self._cancel(
                plan, "la sorgente si è chiusa prima dell'invio", "code_cancel"
            )
            return

        # Route evidence has an even shorter lifetime. Revalidate it again at
        # the provider boundary so traffic advice cannot arrive stale.
        if plan.source_type == "opportunity" and any(
            e.kind == "departure" for e in getattr(subject, "evidence", [])
        ):
            from places.departures import DepartureService
            try:
                current = await DepartureService(self.db).evidence_is_current(
                    user_id, subject
                )
            except Exception:
                current = False
            if not current:
                await self._cancel(
                    plan, "il percorso richiede una nuova verifica", "code_safety"
                )
                return

        # The source was just revalidated by the canonical DeliveryService.
        # This additional channel uses that SAME judgement; it never bypasses
        # consent or performs a second AI decision. A queued WhatsApp alert
        # is independently rechecked again immediately before Meta sends it.
        try:
            from whatsapp.alerts import enqueue as enqueue_whatsapp_alert

            await enqueue_whatsapp_alert(self.db, user_id, plan)
        except Exception as exc:
            # Expo delivery must remain usable even if WhatsApp is offline.
            logger.info("WhatsApp alert admission deferred: %s", type(exc).__name__)

        public = _lockscreen_copy_for(plan)
        outcome = await get_provider().send(
            owner_id=user_id,
            plan_id=plan.id,
            title=plan.words.title,
            body=plan.words.body,
            public_title=public["title"],
            public_body=public["body"],
            deep_link=plan.deep_link,
        )
        if not outcome.get("ok"):
            plan.status = "held"
            plan.rationale = "il canale non era disponibile"
            plan.decision_provenance = "code_safety"
            plan.transport_retry_due = None
            plan.transport_retry_alarm_queued = False

            # Only an explicit proof of zero provider acceptance (Expo HTTP
            # 429) authorises a later *re-evaluation*. Unknown timeouts,
            # incomplete ticket sets and partially accepted batches must
            # never trigger a second blind send.
            if outcome.get("safe_to_retry") is True:
                from delivery.transport_retry import next_retry_time

                plan.transport_retry_attempts += 1
                plan.transport_retry_due = next_retry_time(plan)

            # Persist the intent first. If the process crashes before the
            # wake is written, the existing delivery-admission lane repairs
            # that missing alarm from this durable plan record.
            await self.repo.save_plan(plan)
            if plan.transport_retry_due:
                try:
                    from delivery.transport_retry import ensure_retry_wake

                    await ensure_retry_wake(self.db, plan)
                except Exception as exc:
                    logger.info(
                        "push retry wake deferred: %s", type(exc).__name__
                    )
            return outcome

        plan.transport_retry_due = None
        plan.transport_retry_alarm_queued = False
        plan.status = "delivered"
        plan.delivered_at = _now().isoformat()
        plan.outcome = "delivered"
        plan.last_rechecked_at = plan.last_rechecked_at or plan.delivered_at
        await self.repo.save_plan(plan)
        return outcome

    async def _defer_source_check(self, plan: DeliveryPlan) -> None:
        """Keep an unsent intention durable while source validity is unknown."""
        plan.status = "pending"
        plan.not_before = (_now() + timedelta(minutes=2)).isoformat()
        plan.decision_provenance = "code_safety"
        plan.rationale = "La verifica delle fonti non è disponibile; riprovo prima di inviare."
        await self.repo.save_plan(plan)
        await self._arrange_wake(plan)

    async def _source_check_unavailable(self, owner_id: str, kind: str, source_id: str) -> DeliveryResult:
        for plan in await self.repo.plans_for(owner_id, source_id, source_type=kind):
            if plan.is_open:
                await self._defer_source_check(plan)
        return DeliveryResult(unavailable=True, blocked_by="source_check_unavailable",
                              reason="La verifica delle fonti non è disponibile.")

    # --- what happens to it afterwards ------------------------------------

    async def record_outcome(
        self, user_id: str, plan_id: str, outcome: str
    ) -> Dict[str, Any]:
        """Record a user interaction with an existing, owned delivery plan.

        A client notification is untrusted. A tap cannot invent a delivery,
        choose its URL, approve an agent action, or cross account boundaries.
        """
        if outcome not in ("opened", "dismissed", "expired"):
            return {"ok": False, "reason": "unknown_outcome"}
        plan = await self.repo.get_plan(user_id, plan_id)
        if plan is None:
            return {"ok": False, "reason": "unknown_plan"}

        if outcome == "opened":
            # The provider must have accepted the notification first; a held
            # plan is not something that the person could have opened.
            if plan.status != "delivered" and plan.outcome != "opened":
                return {"ok": False, "reason": "not_delivered"}
            route = _notification_open_route(plan)
            if route is None:
                return {"ok": False, "reason": "invalid_notification_target"}
            if plan.outcome == "opened":
                return {
                    "ok": True, "outcome": "opened",
                    "opportunity_id": plan.opportunity_id, "route": route,
                }
            if plan.opened_at is None:
                plan.opened_at = _now().isoformat()
            plan.outcome = "opened"
            await self.repo.save_plan(plan)
            return {
                "ok": True, "outcome": "opened",
                "opportunity_id": plan.opportunity_id, "route": route,
            }

        # The original interaction policy is retained: after opening, later
        # dismiss/expire actions must not erase the fact it was opened.
        if plan.outcome == "opened":
            return {"ok": True, "outcome": "opened",
                    "opportunity_id": plan.opportunity_id}
        plan.outcome = outcome
        await self.repo.save_plan(plan)
        return {"ok": True, "outcome": outcome,
                "opportunity_id": plan.opportunity_id}

    async def cancel_for_opportunity(
        self, user_id: str, opportunity_id: str, *, reason: str
    ) -> int:
        """A concern that closed takes its intentions with it."""
        return await self.cancel_for_source(
            user_id, opportunity_id, source_type="opportunity", reason=reason
        )

    async def cancel_for_source(
        self, user_id: str, source_id: str, *, source_type: str = "opportunity",
        reason: str,
    ) -> int:
        """
        A subject that closed takes its intentions with it.

        Guaranteed by code rather than left to a judgement: a notification
        about something already dealt with is never right, so there is nothing
        to decide.

        Cancels the *intention to say*, and nothing else. Whatever raised it
        goes on existing — an agent still stuck is still stuck when the push
        is called off, and forgetting that is the failure this whole bridge
        exists to avoid.
        """
        cancelled = 0
        for plan in await self.repo.plans_for(
            user_id, source_id, source_type=source_type
        ):
            if plan.is_open:
                await self._cancel(plan, reason, "code_cancel")
                cancelled += 1
        return cancelled

    async def _cancel(self, plan: DeliveryPlan, reason: str, source: str) -> None:
        from delivery.provider import get_provider

        plan.status = "cancelled"
        plan.cancelled_at = _now().isoformat()
        plan.decision_provenance = source
        plan.rationale = reason[:300]
        await self.repo.save_plan(plan)
        # An alarm set for a notification that is no longer going to happen is
        # a process that will wake up, find nothing, and have cost something.
        await self._cancel_wakes(plan.owner_id, plan.source_id)
        try:
            await get_provider().cancel(owner_id=plan.owner_id, plan_id=plan.id)
        except Exception as e:
            logger.info("provider cancel soft-fail: %s", type(e).__name__)

    # --- arranging to be there --------------------------------------------

    async def _arrange_wake(self, plan) -> None:
        """
        Ask the runtime to be awake when this plan's moment arrives.

        Best-effort in both directions: a failure here must not fail the
        decision, and the wake it creates promises nothing — what happens at
        that hour is decided then, by asking again.
        """
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).schedule_for_plan(plan)
        except Exception as e:
            logger.info("wake schedule soft-fail: %s", type(e).__name__)

    async def _cancel_wakes(self, owner_id: str, opportunity_id: str) -> None:
        try:
            from ambient.service import AmbientService

            await AmbientService(self.db).cancel_for_opportunity(owner_id, opportunity_id)
        except Exception as e:
            logger.info("wake cancel soft-fail: %s", type(e).__name__)

    # --- the bounds code is allowed to hold -------------------------------

    async def _may_push(
        self, user_id: str, moment: Dict[str, Any], *, invited: bool = False
    ) -> tuple[bool, str]:
        """
        Whether a push is technically permissible. Never whether it is a good idea.

        Each of these is a fact about capability or a ceiling on volume. None
        of them looks at what the opportunity is about, and none can be
        reached by anything that does.
        """
        if not (moment.get("can_be_notified") or {}).get("push"):
            return False, "no_notification_permission"

        if moment.get("they_muted_this_concern"):
            # "Non notificarmi per questa cosa." Enforced here rather than
            # weighed, because somebody saying stop should not depend on a
            # model agreeing — and it is not a dismissal: the concern goes on
            # living wherever it was living.
            return False, "muted_by_user"

        if invited:
            # "Ricordamelo alle 15", the outcome of a call they asked for: the
            # person chose this interruption. The ceiling below is for the ones
            # nobody asked for; applying it here lost a reminder set two
            # minutes after another notification (audit 26/10).
            return True, ""

        recent = moment.get("recent_interruptions") or []
        within_hour = [
            r for r in recent
            if r.get("minutes_ago") is not None and r["minutes_ago"] <= 60
        ]
        if len(within_hour) >= MAX_PUSHES_PER_HOUR:
            return False, "rate_limited"
        if any(
            r.get("minutes_ago") is not None
            and r["minutes_ago"] < MIN_MINUTES_BETWEEN_PUSHES
            for r in recent
        ):
            return False, "too_soon_after_last"
        return True, ""

    async def _muted(self, user_id: str, opportunity_id: str) -> bool:
        """Whether they have asked not to be reached about this one thing."""
        try:
            from ambient.preferences import PreferenceService

            return await PreferenceService(self.db).is_suppressed(user_id, opportunity_id)
        except Exception as e:
            logger.info("suppression read soft-fail: %s", type(e).__name__)
            return False

    def _due(self, plan: DeliveryPlan) -> bool:
        moment = _now().isoformat()
        if (plan.status == "held" and plan.transport_retry_due
                and plan.transport_retry_due > moment):
            # An explicit retry backoff cannot be skipped by a foreground
            # /delivery/due request before the original scheduled moment.
            return False
        return not plan.not_before or plan.not_before <= moment

    def _expired(self, plan: DeliveryPlan) -> bool:
        now = _now()
        if plan.not_after and plan.not_after < now.isoformat():
            return True
        try:
            created = datetime.fromisoformat(plan.created_at)
        except ValueError:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return (now - created) > timedelta(hours=MAX_PLAN_HORIZON_HOURS)

    # --- proof of work ----------------------------------------------------

    async def note_activity(
        self,
        user_id: str,
        *,
        kind: str,
        summary: str = "",
        source_refs: Optional[List[str]] = None,
        provenance: Optional[Dict[str, Any]] = None,
        visible: bool = False,
        activity_id: str = "",
    ) -> AmbientActivity:
        """
        Write down something ORA actually did.

        Called by the work, never by the surface. A screen that could create
        one of these to have something to say would be manufacturing its own
        evidence, which is exactly the failure this record exists to make
        impossible.
        """
        activity = AmbientActivity(
            owner_id=user_id,
            kind=kind,
            summary=summary[:200],
            source_refs=[str(r)[:120] for r in (source_refs or [])][:8],
            cognitive_provenance=provenance or {},
            visibility="ambient" if visible else "internal",
            **({"id": activity_id} if activity_id else {}),
        )
        return await self.repo.record_activity(activity)

    async def summarise_recent(self, user_id: str, *, language: str = "it") -> Optional[Any]:
        """
        Turn work that really happened into one line a person could read.

        Called by the work, after the work. The model is shown the record and
        nothing else — it cannot reach a life, so it cannot claim anything the
        record does not contain, and a review that could not see half of
        somebody's sources produces a smaller sentence rather than a
        reassuring one.

        Rate-limited by the clock rather than by judgement: a line that
        rewrites itself every few minutes is not presence, it is fidgeting.
        """
        from delivery.reasoning import describe_ambient

        # Cosa ORA ha deciso che merita attenzione, adesso. Non e' un secondo
        # giudizio: e' esattamente lo stato che la consegna sta gia' usando
        # per decidere cosa mettere in Home.
        #
        #     LA RIGA E LA CARD DEVONO VENIRE DALLA STESSA DECISIONE.
        #
        # Su uno schermo vero si sono contraddette: «due variazioni
        # controllate oggi, tutto tranquillo» sopra, e sotto un'iniziativa che
        # diceva che c'era un conflitto in calendario da chiarire. La riga era
        # stata scritta qualche minuto prima dell'iniziativa ed era vera
        # quando e' stata scritta — il che e' il modo peggiore di essere
        # falsa, perche' nessuno l'aveva mai detta a voce alta.
        standing = await self._what_is_standing(user_id)
        fingerprint = [row["ref"] for row in standing]

        latest = await self.repo.latest_ambient(user_id)
        if (
            latest is not None
            and not _older_than(latest.occurred_at, AMBIENT_REFRESH_HOURS)
            and list(
                (latest.cognitive_provenance or {}).get("standing") or []
            ) == fingerprint
        ):
            # Stessa ora e stesso stato: la riga di prima e' ancora quella
            # giusta. Se lo stato e' cambiato, l'ora non basta piu'.
            return latest

        recent = await self.repo.recent_activity(user_id, visibility="internal", limit=6)
        if not recent:
            # Nothing was done, so there is nothing to say. This is the branch
            # that makes the whole feature honest.
            return None

        blind = sorted(
            {
                str(source)
                for activity in recent
                for source in (activity.cognitive_provenance.get("sources_unavailable") or [])
            }
        )
        answer = await describe_ambient(
            {
                "what_ora_did": [
                    {
                        "kind": a.kind,
                        "when": a.occurred_at,
                        "details": a.cognitive_provenance,
                    }
                    for a in recent
                ],
                "what_is_standing_right_now": standing,
                "sources_it_could_not_check": blind,
                "language": language,
            },
            language=language,
        )
        if answer is None or not answer.get("worth_saying"):
            # Either the model was unreachable or it judged that nothing here
            # is worth a person reading. Neither produces a line.
            return None

        return await self.note_activity(
            user_id,
            kind=recent[0].kind,
            summary=answer["line"],
            source_refs=[r for a in recent for r in a.source_refs][:8],
            provenance={
                "written_from": [a.id for a in recent][:6],
                "sources_unavailable": blind,
                # Con quale stato e' stata scritta, cosi' che quando lo stato
                # cambia si sappia che questa riga non lo racconta piu'.
                "standing": fingerprint,
            },
            visible=True,
        )

    async def _what_is_standing(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Quello che ORA ha gia' deciso di tenere davanti a questa persona.

        Letto, non deciso: la stessa lista che Home rende. Serve perche' chi
        scrive la riga sappia se in fondo alla schermata c'e' qualcosa che la
        smentisce — non perche' debba giudicare di nuovo se c'e'.
        """
        try:
            from opportunities.surfacing import SurfacingService

            return [
                {"ref": o.id, "what": o.semantic_summary[:140],
                 "waiting_on_an_answer": o.requires_clarification}
                for o in await SurfacingService(self.db).visible(user_id)
            ][:4]
        except Exception as e:
            logger.info("standing read soft-fail: %s", type(e).__name__)
            return []

    async def permission_moment(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Whether there is now a reason to ask about notifications.

            NON CHIEDERE AL PRIMO AVVIO.

        Asked at launch, the question is about a feature and the honest answer
        is no. Asked here it is about something concrete: ORA judged that a
        particular thing was worth reaching them for, and could not. That is
        the only moment the question is worth a person's time, and it arrives
        by itself — nothing schedules it and nothing nags.

        Returns nothing at all when no such judgement is waiting, which is
        almost always.
        """
        held = []
        for plan in await self.repo.open_plans(user_id):
            if plan.status != "held" or plan.rationale != "no_notification_permission":
                continue
            try:
                if await self._current_subject_for_plan(user_id, plan) is not None:
                    held.append(plan)
            except MemorySourcesUnavailable:
                continue  # A read cannot request permission using unverifiable words.
        if not held:
            return None
        return {
            "reason": "ORA può avvisarti quando cambia qualcosa che vale davvero la pena vedere.",
            # What it would have said, so the question is about something real
            # rather than about a permission dialog.
            "example": held[0].reason_to_open or None,
            "waiting": len(held),
        }

    async def ambient_line(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        The one line Home may show, or nothing.

        Reads what was already recorded — it never runs a review and never
        asks a model. If no real work is on file, there is nothing to say, and
        saying something anyway is the lie this whole layer is built to avoid.
        """
        latest = await self.repo.latest_ambient(user_id)
        if latest is None or latest.owner_id != user_id or not latest.summary:
            return None
        now = _now()
        if latest.expires_at:
            expiry = latest.expires_at
            if expiry.tzinfo is None:  # Mongo stores UTC datetimes without an offset.
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                return None

        # An accepted Home handoff is still a historical record. Reload its
        # Situation before showing the line: TTL cleanup and best-effort goal
        # cancellation can both happen later than the person's correction.
        # Also find older activities carrying only the bare goal id, so they
        # cannot present an unbound recap as a current result after upgrading.
        refs = set(latest.source_refs)
        goal_ids = set(refs)
        if isinstance(latest.cognitive_provenance.get("goal"), str):
            goal_ids.add(latest.cognitive_provenance["goal"])
        bindings = {ref for ref in refs if ref.startswith((
            "situation:", "situation_outcome:", "situation_revision:",
        ))}
        rows = await self.db.agent_goals.find({
            "owner_id": user_id, "id": {"$in": list(goal_ids)},
        }, {"_id": 0}).to_list(2) if goal_ids else []
        if not rows:
            return None if bindings or latest.cognitive_provenance.get("goal") else latest.for_home()
        if len(rows) != 1:
            return None

        from agent.models import AutonomousGoal
        from agent.source_refresh import changed
        from situations.outcomes import current_outcome, moment, situation_id

        goal = AutonomousGoal.model_validate(rows[0])
        try:
            if not await memory_result_current(
                self.db, user_id, goal,
                str(latest.cognitive_provenance.get("memory_source_snapshot") or ""),
            ):
                return None
        except MemorySourcesUnavailable:
            return None
        if goal.source_kind not in ("situation_initial_review", "situation_followup"):
            return latest.for_home() if goal.status not in ("cancelled", "abandoned") else None
        expiry = moment(goal.valid_until)
        if goal.valid_until and (expiry is None or expiry <= now):
            return None
        assessment = await current_outcome(
            self.db, user_id, goal, allow_settled=goal.status == "completed", now=now,
        )
        if assessment:
            # Activity refs are bounded more tightly than evidence refs.
            # These two identifiers and the exact validated headline bind
            # the visible words without requiring every truncated evidence id.
            expected = {f"situation:{assessment['situation_id']}",
                        f"situation_outcome:{assessment['id']}"}
            if bindings != expected or latest.summary != assessment["headline"][:200]:
                return None
        else:
            # A question can precede an estimate, but it belongs to one
            # unresolved attention revision, never to a completed old watch.
            sid = situation_id(goal)
            revision = goal.source_situation.get("situation_revision")
            expected = f"situation_revision:{sid}:{revision}"
            if (not sid or not revision or not goal.is_open
                    or not (goal.requires_user_input or goal.requires_user_authority)
                    or expected not in bindings
                    or not bindings.issubset({expected, f"situation:{sid}"})
                    or await changed(self.db, goal)):
                return None
        return latest.for_home()


def _older_than(when: str, hours: int) -> bool:
    try:
        moment = datetime.fromisoformat(str(when))
    except (TypeError, ValueError):
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (_now() - moment) > timedelta(hours=hours)


# The only places a notification may open. A model may reason about where a
# tap should land; it may never hand over a URL, because a URL from a model is
# a string somebody else's text could have influenced.
ALLOWED_TARGETS = {
    "opportunity": "/aggiornamento/{id}",
    "conversation": "/ora?sessionId={id}&entry=notification",
    # An agent need carries two handles, because a tap has to land on the
    # blocker inside the goal that raised it — not on the goal, and certainly
    # not on Home. Both are validated as opaque ids before they go anywhere.
    "agent_need": "/ora?needId={id}&goalId={goal}&entry=agent_need",
    "home": "/",
}

# Opaque ids only. Anything else is not an id we produced.
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{4,80}$")


def _deep_link(opportunity_id: str, *, target: str = "opportunity") -> str:
    """
    Where a tap lands, built here from a validated target and a validated id.

    The same handoff "Vediamo" uses, with the origin preserved so the
    conversation knows it began with an interruption. A notification that
    opens Home when we know exactly what it was about has thrown away the only
    thing it knew — and one that opens whatever a model wrote has thrown away
    rather more than that.
    """
    template = ALLOWED_TARGETS.get(target) or ALLOWED_TARGETS["home"]
    if "{id}" not in template:
        return template
    if not _OPAQUE_ID.match(str(opportunity_id or "")):
        return ALLOWED_TARGETS["home"]
    return template.format(id=opportunity_id)


def _notification_open_route(plan: DeliveryPlan) -> Optional[str]:
    """Return only a canonical route already authorised by Delivery code."""
    if plan.source_type == "opportunity":
        opaque = str(plan.source_id or plan.opportunity_id or "")
        if not _OPAQUE_ID.fullmatch(opaque):
            return None
        expected = _deep_link(opaque, target="opportunity")
        return expected if plan.deep_link == expected else None

    if plan.source_type == "source_result":
        from delivery.source_results import plan_id
        if (_OPAQUE_ID.fullmatch(plan.source_id) and plan.deep_link == "/"
                and plan.id == plan_id(plan.owner_id, plan.source_id)):
            return "/"
        return None

    if plan.source_type == "agent_need":
        match = re.fullmatch(
            r"/ora\?needId=([A-Za-z0-9_-]{4,80})"
            r"&goalId=([A-Za-z0-9_-]{4,80})&entry=agent_need",
            plan.deep_link or "",
        )
        if match and match.group(1) == plan.source_id:
            return plan.deep_link

    return None


def _default_not_after(subject) -> Optional[str]:
    """When the model did not say, the subject's own horizon does."""
    return getattr(subject, "valid_until", None)


def _deep_link_for(subject) -> str:
    """
    Where a tap on this subject lands.

    An opportunity opens the concern; a need opens the blocker inside the goal
    that raised it. Anything unrecognised opens Home, which is the honest
    answer when we do not know where to send somebody.
    """
    kind = source_of(subject)
    subject_id = str(getattr(subject, "id", "") or "")
    if kind == "opportunity":
        return _deep_link(subject_id, target="opportunity")

    goal_id = str(getattr(subject, "goal_id", "") or "")
    if not (_OPAQUE_ID.match(subject_id) and _OPAQUE_ID.match(goal_id)):
        return ALLOWED_TARGETS["home"]
    return (
        ALLOWED_TARGETS["agent_need"].replace("{id}", subject_id).replace("{goal}", goal_id)
    )


def _bounded(raw: Any) -> Optional[str]:
    """A moment the model named, kept only if it is a moment and it is near."""
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    horizon = _now() + timedelta(hours=MAX_PLAN_HORIZON_HOURS)
    if moment > horizon:
        moment = horizon
    return moment.isoformat()
