"""
Whether to say it now, which is not the same as whether it is true.

    SURFACE != NOTIFY.
    OPPORTUNITY ACTIVE != CARD ALWAYS VISIBLE.

An opportunity that survives a scan is something ORA believes. That belief
earns it a place in the system, not a place on somebody's screen: the second
question — is this the moment, next to everything else already there, for the
fourth time this week? — has a different answer, and giving it the same answer
by default is how a quiet home turns into a feed.

So the model is asked again, and told what it needs to answer honestly: what
is on the screen already, how often this has been shown, what was refused.
Code holds only the things code can hold — how many fit, in what order, and
the timestamps that make "already seen" a fact rather than a guess.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from opportunities.models import Opportunity
from opportunities.repository import OpportunityRepository

logger = logging.getLogger(__name__)

# How many may be visible at once. A limit, not a ranking: the model says
# which matter, this says how many fit on a home that is meant to stay quiet.
MAX_VISIBLE = 2

# How many are put to the model at all. Past this the tail is held without
# asking — deciding about twelve things is not a decision worth paying for.
MAX_CONSIDERED = 6

# What to do when the model cannot be reached at the moment somebody taps
# "più tardi". Not a guess at the right time — there is no judgement in it at
# all. It exists so the card does not reappear in the same breath, and it is
# recorded as `technical_retry_hold` precisely so nobody later mistakes it for
# an opinion about when this should come back.
RETRY_HOLD_MINUTES = 45

# The bounds a judgement has to land inside. Not a preference about timing:
# an hour is the shortest hold that means anything at all, and past a
# fortnight the facts underneath will have moved enough that the decision was
# about a different situation.
MIN_REVISIT_HOURS = 1
MAX_REVISIT_HOURS = 24 * 14

_VALID = {"surface", "hold", "retire"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SurfacingService:
    def __init__(self, db):
        self.db = db
        self.repo = OpportunityRepository(db)

    # --- what home should show -------------------------------------------

    async def visible(self, user_id: str) -> List[Opportunity]:
        """
        What is currently on this person's home. No model, no cost.

        Home renders often and asking a model on every render would be both
        expensive and wrong — the decision was already made, and re-deciding
        it every few seconds would make cards flicker in and out of somebody's
        morning.
        """
        now = _now().isoformat()
        out: List[Opportunity] = []
        for opportunity in await self.repo.list(user_id, statuses=["active"]):
            if opportunity.surface_state != "surfaced":
                continue
            if opportunity.deferred_until and opportunity.deferred_until > now:
                continue
            out.append(opportunity)
        # The model chose which. This only decides how many fit, in a fixed
        # order so the same two do not swap places between two renders.
        return sorted(out, key=lambda o: o.order_key)[:MAX_VISIBLE]

    async def for_home(self, user_id: str) -> List[Dict[str, Any]]:
        """Human words only — never the words the system thinks in."""
        return [o.for_home() for o in await self.visible(user_id)]

    # --- deciding ---------------------------------------------------------

    async def decide(
        self,
        user_id: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        language: str = "it",
    ) -> Dict[str, Any]:
        """
        Ask whether any of what we believe belongs on screen right now.

        Returns what was decided. An unreachable model changes nothing: what
        was already visible stays visible, and nothing new appears — a network
        error is not a reason to put something in front of somebody, and not a
        reason to take away what is already there either.
        """
        from opportunities.reasoning import decide_surfacing

        candidates = await self._considerable(user_id)
        if not candidates:
            return {"decided": 0, "surfaced": 0, "unavailable": False, "decisions": []}

        answer = await decide_surfacing(
            [self._for_ai(o) for o in candidates],
            context=await self._context(user_id, extra=context),
            language=language,
        )
        if answer is None:
            logger.info("surfacing unavailable for %s", user_id[:8])
            return {
                "decided": 0,
                "surfaced": len(await self.visible(user_id)),
                "unavailable": True,
                "decisions": [],
            }

        by_id = {o.id: o for o in candidates}
        applied: List[Dict[str, str]] = []
        now = _now().isoformat()

        for row in answer.get("decisions") or []:
            if not isinstance(row, dict):
                continue
            opportunity = by_id.get(str(row.get("id") or ""))
            decision = str(row.get("decision") or "").strip().lower()
            if opportunity is None or decision not in _VALID:
                continue

            rationale = str(row.get("rationale") or "")[:300]
            opportunity.surface_rationale = rationale

            if decision == "surface":
                # Only count an appearance the first time it appears. A card
                # that stays put across a morning has been shown once.
                if opportunity.surface_state != "surfaced":
                    opportunity.surfaced_count += 1
                    opportunity.last_surfaced_at = now
                opportunity.surface_state = "surfaced"
                opportunity.deferred_until = None
            elif decision == "hold":
                opportunity.surface_state = "held"
            else:
                opportunity.surface_state = "hidden"

            await self.repo.save(opportunity)
            applied.append({"id": opportunity.id, "decision": decision, "why": rationale})

        return {
            "decided": len(applied),
            "surfaced": len(await self.visible(user_id)),
            "unavailable": False,
            "decisions": applied,
        }

    # --- what a person does about it --------------------------------------

    async def mark_seen(self, user_id: str, opportunity_id: str) -> Dict[str, Any]:
        """
        It has been in front of them. Not that they did anything about it.

        Without this the same card is new every morning, and a system that
        cannot tell "shown once" from "shown eleven times" has no way to stop
        being tiresome.
        """
        opportunity = await self.repo.get(user_id, opportunity_id)
        if opportunity is None:
            return {"ok": False, "reason": "unknown_opportunity"}
        if not opportunity.seen_at:
            opportunity.seen_at = _now().isoformat()
            await self.repo.save(opportunity)
        return {"ok": True, "seen_at": opportunity.seen_at}

    async def defer(
        self, user_id: str, opportunity_id: str, *, language: str = "it"
    ) -> Dict[str, Any]:
        """
        "Più tardi" — off the screen, still true, for as long as it deserves.

        How long is a judgement, not a constant. The same two words mean this
        evening about tomorrow morning's appointment and next week about a
        dentist somebody has been avoiding since spring, and the difference is
        entirely in what the thing is. So the model is asked, and what it says
        is recorded with its reason.

        Nothing is scheduled by any of this. `deferred_until` is the earliest
        moment the surfacing decision may look at this again — and that
        decision is still free to hold it a second time.
        """
        from opportunities.reasoning import decide_revisit

        opportunity = await self.repo.get(user_id, opportunity_id)
        if opportunity is None:
            return {"ok": False, "reason": "unknown_opportunity"}
        if opportunity.status != "active":
            return {"ok": False, "reason": "not_active"}

        answer = await decide_revisit(
            self._for_ai(opportunity),
            context=await self._context(user_id),
            language=language,
        )

        if answer is None:
            # No judgement was available, so none is recorded. The card is held
            # only long enough not to reappear immediately, and the hold says
            # so in its own name — the next surfacing pass, with the model
            # back, is free to reconsider the timing properly.
            until = _now() + timedelta(minutes=RETRY_HOLD_MINUTES)
            source = "technical_retry_hold"
            rationale = ""
        else:
            hours = min(
                MAX_REVISIT_HOURS, max(MIN_REVISIT_HOURS, int(answer["revisit_in_hours"]))
            )
            until = _now() + timedelta(hours=hours)
            source = "model"
            rationale = str(answer.get("rationale") or "")[:300]

        opportunity.surface_state = "deferred"
        opportunity.deferred_until = until.isoformat()
        opportunity.revisit_source = source
        opportunity.revisit_rationale = rationale
        await self.repo.save(opportunity)
        return {
            "ok": True,
            "deferred_until": opportunity.deferred_until,
            "decided_by": source,
        }

    # --- what the model is told -------------------------------------------

    async def _considerable(self, user_id: str) -> List[Opportunity]:
        now = _now().isoformat()
        out = []
        for opportunity in await self.repo.list(user_id, statuses=["active"]):
            if opportunity.deferred_until and opportunity.deferred_until > now:
                continue
            out.append(opportunity)
        return sorted(out, key=lambda o: o.order_key)[:MAX_CONSIDERED]

    @staticmethod
    def _for_ai(opportunity: Opportunity) -> Dict[str, Any]:
        return {
            "id": opportunity.id,
            "what": opportunity.semantic_summary,
            "why_now": opportunity.why_now or opportunity.why_it_matters,
            "relevance": opportunity.relevance,
            "urgency": opportunity.urgency,
            "currently": opportunity.surface_state,
            "times_shown": opportunity.surfaced_count,
            "already_seen": bool(opportunity.seen_at),
            "raised_at": opportunity.created_at,
            # What it is waiting on, when it is waiting on something. Deciding
            # how long "later" lasts without this would be deciding blind.
            "valid_until": opportunity.valid_until,
            "waiting_on_an_answer": opportunity.requires_clarification,
            "how_time_sensitive": opportunity.time_sensitivity,
        }

    async def _context(
        self, user_id: str, *, extra: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        What else is on that screen, and what this person is doing.

        Enough to judge crowding, and no more: counts and short labels. The
        model deciding whether a card fits does not need to read anybody's
        calendar to know that four things are already there.
        """
        context: Dict[str, Any] = {"now": _now().isoformat()}

        try:
            from waiting.service import get_waiting_service

            open_questions = await get_waiting_service(self.db).list_open(user_id, limit=5)
            context["questions_waiting_for_them"] = len(open_questions)
        except Exception:
            pass

        try:
            rows = await self.db.home_snapshots.find(
                {"user_id": user_id}, {"_id": 0, "items": 1}
            ).sort("generated_at", -1).to_list(1)
            items = (rows[0].get("items") if rows else None) or []
            context["already_on_their_home"] = len(items)
            context["what_is_already_there"] = [
                str((i.get("title") or ""))[:80] for i in items[:4]
            ]
        except Exception:
            pass

        try:
            from places.service import PlacesService

            here = await PlacesService(self.db).where_now(user_id)
            if here.get("at_a_known_place"):
                # A label, never coordinates. Where somebody is may change what
                # is worth interrupting them about; it is never a reason on its own.
                context["where_they_are"] = here.get("place")
        except Exception:
            pass

        recent = []
        for opportunity in await self.repo.list(
            user_id, statuses=["dismissed", "suppressed"], limit=10
        ):
            recent.append(
                {"what": opportunity.semantic_summary, "status": opportunity.status}
            )
        if recent:
            context["they_already_refused"] = recent[:4]

        if extra:
            context.update({k: v for k, v in extra.items() if k not in context})
        return context
