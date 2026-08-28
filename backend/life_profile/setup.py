"""
The guided first setup: which question is on screen, and what an answer does.

The interface renders; it decides nothing. It receives one area, one objective,
the control to draw it with and the options that exist, and sends back what the
person chose. Everything else — which question comes next, what an answer
implies, when an area is done, when to move on — is here, because a branch
implemented in a component is a branch nobody can test.

Two invariants hold the shape of it:

**One area at a time.** The visible current area is the area the current
question came from. Somebody answering about their home is never handed a
question about their studies; moving on is an explicit step they take.

**Cross-area learning, never cross-area jumping.** "Vivo con il partner" is
recorded for Famiglia as well as Casa — knowledge belongs wherever it is true —
but the next question stays where the person is.

Nothing here stores a question number. What comes next is derived from what is
known, so closing the app halfway and returning tomorrow resumes from the real
state rather than from a counter that may no longer mean anything.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from life_profile.areas import LifeArea, all_areas, area as find_area
from life_profile.guided import (
    IDENTITY_OBJECTIVE,
    GuidedObjective,
    for_area,
    objective,
    option_of,
)
from life_profile.service import LifeProfileService

logger = logging.getLogger("ora.life_profile.setup")

# Where the setup's own state lives. Not the facts — those go where facts go —
# only what the person chose to do with the setup itself.
_META_CURRENT = "guided_current_area"
_META_SKIPPED = "guided_skipped_areas"
_META_ANSWERED = "guided_answered"
_META_NA = "not_applicable_keys"
_META_DECLINED = "guided_declined"
_META_FINISHED = "first_run_finished"


class GuidedSetupService:
    """One question at a time, derived from what ORA already knows."""

    def __init__(self, db):
        self.db = db
        self.profile = LifeProfileService(db)

    # -- state -----------------------------------------------------------

    async def _load(
        self, user_id: str, *, create: bool = False
    ) -> Tuple[Any, Any, Dict[str, Any]]:
        """
        The setup's own record, created on demand.

        Found live: the guided setup stored its state on the session the *old*
        conversational start used to create, so answering the first question on
        a fresh account failed with "no_session" — and the QA that did not hit
        it had bootstrapped one by hand. The guided path owns its own record
        now, which also means Home stops offering to resume a conversation
        nobody had.
        """
        from life_setup.repository import LifeSetupRepository

        repo = LifeSetupRepository(self.db)
        sess = await repo.latest_session(user_id)
        if sess is None and create:
            from life_setup.models import LifeSetupSession

            sess = LifeSetupSession(user_id=user_id, status="active", phase="guided")
            await repo.insert_session(sess)
        meta = dict((getattr(sess, "meta", None) or {})) if sess else {}
        return repo, sess, meta

    async def _has_name(self, user_id: str) -> bool:
        """
        Does the account already carry a usable name?

        `/auth/me` is the canonical identity — it is what Home greets with —
        so anything already there makes the question unnecessary.
        """
        try:
            doc = await self.db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1})
        except Exception:
            return False
        name = str((doc or {}).get("name") or "").strip()
        # A placeholder is not a name. "Test" and an email local-part are what
        # accounts are created with, and greeting somebody by one is the bug
        # this exists to avoid.
        return bool(name) and name.lower() not in {"test", "qa", "utente", "user", "qa gate"}

    async def _facts(self, user_id: str) -> Dict[str, Any]:
        facts, _prov, _inf = await self.profile._profile_facts(user_id)
        return facts

    # -- the question on screen ------------------------------------------

    def _next_objective(
        self,
        area_id: str,
        *,
        facts: Dict[str, Any],
        answered: List[str],
        declined: List[str],
        not_applicable: List[str],
    ) -> Optional[GuidedObjective]:
        """
        The first thing in this area still worth asking.

        Worth asking means: nobody has answered it, it has not been declined,
        it has not been ruled out, ORA does not already know it, and whatever
        it depends on has been settled. Everything else waits — which is how
        the same area produces different questions for two different lives.
        """
        seen = set(answered) | set(declined) | set(not_applicable)
        for obj in for_area(area_id):
            if obj.id in seen:
                continue
            if obj.id in facts and facts.get(obj.id) not in (None, ""):
                # V3.2's rule, applied to the setup: never ask what is known.
                continue
            if not obj.relevant(facts):
                continue
            return obj
        return None

    def _area_order(self) -> List[LifeArea]:
        return all_areas()

    def _pick_area(
        self,
        *,
        current: Optional[str],
        facts: Dict[str, Any],
        answered: List[str],
        declined: List[str],
        not_applicable: List[str],
        skipped: List[str],
    ) -> Optional[str]:
        """Where the person is, or the first area that still has something to ask."""
        if current and current not in skipped:
            if self._next_objective(
                current,
                facts=facts,
                answered=answered,
                declined=declined,
                not_applicable=not_applicable,
            ):
                return current
        for a in self._area_order():
            if a.id in skipped:
                continue
            if self._next_objective(
                a.id,
                facts=facts,
                answered=answered,
                declined=declined,
                not_applicable=not_applicable,
            ):
                return a.id
        return None

    async def state(self, user_id: str) -> Dict[str, Any]:
        """Everything the interface needs to draw the screen. It adds nothing."""
        _repo, sess, meta = await self._load(user_id)
        facts = await self._facts(user_id)
        answered = list(meta.get(_META_ANSWERED) or [])
        declined = list(meta.get(_META_DECLINED) or [])
        not_applicable = list(meta.get(_META_NA) or [])
        skipped = list(meta.get(_META_SKIPPED) or [])
        current = meta.get(_META_CURRENT)

        area_id = self._pick_area(
            current=current,
            facts=facts,
            answered=answered,
            declined=declined,
            not_applicable=not_applicable,
            skipped=skipped,
        )

        comp = await self.profile.completeness(user_id)
        areas = [a.model_dump() for a in comp.areas]
        for a in areas:
            a["current"] = a["area_id"] == area_id
            a["skipped"] = a["area_id"] in skipped

        # An explicit transition: the area the person was in has nothing left,
        # so they are told where ORA is going next and choose to go.
        transition = None
        if current and area_id and current != area_id and current not in skipped:
            done = find_area(current)
            nxt = find_area(area_id)
            done_state = next((a for a in areas if a["area_id"] == current), None)
            if done and nxt:
                transition = {
                    "from_area_id": done.id,
                    "from_title": done.title,
                    "from_percent": (done_state or {}).get("percent", 0),
                    "from_state_label": (done_state or {}).get("state_label", ""),
                    "to_area_id": nxt.id,
                    "to_title": nxt.title,
                }

        # Before any area: what to call this person. Only when nobody has said
        # and the account has nothing usable — ORA does not ask for something
        # it already has.
        if (
            IDENTITY_OBJECTIVE.id not in answered
            and IDENTITY_OBJECTIVE.id not in declined
            and not await self._has_name(user_id)
        ):
            return {
                "ok": True,
                "percent": comp.percent,
                "areas": areas,
                "current_area_id": None,
                "objective": {
                    **self._public_objective(
                        IDENTITY_OBJECTIVE, "", answered, declined, not_applicable, facts
                    ),
                    "step": 1,
                    "of": 1,
                },
                "transition": None,
                "finished": False,
            }

        step = None
        if area_id:
            obj = self._next_objective(
                area_id,
                facts=facts,
                answered=answered,
                declined=declined,
                not_applicable=not_applicable,
            )
            if obj:
                step = self._public_objective(obj, area_id, answered, declined, not_applicable, facts)

        return {
            "ok": True,
            "percent": comp.percent,
            "areas": areas,
            "current_area_id": area_id,
            "objective": step,
            "transition": transition,
            "finished": bool(meta.get(_META_FINISHED)) or area_id is None,
        }

    def _public_objective(
        self,
        obj: GuidedObjective,
        area_id: str,
        answered: List[str],
        declined: List[str],
        not_applicable: List[str],
        facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        items = for_area(area_id)
        relevant = [
            o for o in items
            if o.relevant(facts) or o.id in answered or o.id in facts
        ]
        done = sum(
            1 for o in relevant
            if o.id in answered or o.id in declined or o.id in not_applicable or o.id in facts
        )
        return {
            "id": obj.id,
            "area_id": obj.area_id,
            "question": obj.question,
            "hint": obj.hint,
            "control": obj.control,
            "unit": obj.unit,
            "sensitivity": obj.sensitivity,
            "allow_other": obj.allow_other,
            "allow_skip": obj.allow_skip,
            "allow_decline": obj.allow_decline,
            "document_type": obj.document_type,
            "options": [
                {"id": o.id, "label": o.label, "description": o.description}
                for o in obj.options
            ],
            # "Passaggio 3 di 8" — honest about this area only, and it moves as
            # the shape of the area changes.
            "step": min(done + 1, max(len(relevant), 1)),
            "of": max(len(relevant), 1),
        }

    # -- answering -------------------------------------------------------

    async def answer(
        self,
        user_id: str,
        *,
        objective_id: str,
        option_ids: Optional[List[str]] = None,
        value: Any = None,
        other_text: Optional[str] = None,
        action: str = "answer",
    ) -> Dict[str, Any]:
        """
        Record what somebody chose, then work out what comes next.

        `action` is what they did: answered, skipped ("più tardi"), declined
        ("preferisco non indicarlo"). Three different things, and only the
        first one teaches ORA anything.
        """
        obj = objective(objective_id)
        if not obj:
            return {"ok": False, "error": "unknown_objective"}

        repo, sess, meta = await self._load(user_id, create=True)
        if not sess:
            return {"ok": False, "error": "no_session"}

        answered = list(meta.get(_META_ANSWERED) or [])
        declined = list(meta.get(_META_DECLINED) or [])
        not_applicable = list(meta.get(_META_NA) or [])

        if action == "decline":
            if obj.id not in declined:
                declined.append(obj.id)
        elif action == "skip":
            # Deliberately recorded nowhere: skipping leaves the objective
            # exactly where it was, which is the whole difference between
            # postponing and answering. It is simply not asked again this pass.
            answered.append(obj.id)
        else:
            facts_to_write: Dict[str, Any] = {}
            chosen = [o for o in (option_ids or []) if o]
            for option_id in chosen:
                opt = option_of(obj.id, option_id)
                if not opt:
                    continue
                if opt.declines:
                    if obj.id not in declined:
                        declined.append(obj.id)
                    continue
                facts_to_write.update(opt.sets)
                for ref in opt.not_applicable:
                    if ref not in not_applicable:
                        not_applicable.append(ref)

            # The objective's own answer, in the person's terms.
            if chosen:
                stored: Any = chosen if obj.control == "multi" else chosen[0]
                facts_to_write[obj.id] = stored
            elif value not in (None, ""):
                facts_to_write[obj.id] = value
            if other_text:
                # Kept raw and kept whole. "Altro" is where somebody's actual
                # situation lives when none of the options is it, and throwing
                # away their words to store a category would lose the point.
                facts_to_write[f"{obj.id}.altro"] = str(other_text)[:500]
                facts_to_write.setdefault(obj.id, "altro")

            await self._write_facts(user_id, facts_to_write)
            if obj.id == IDENTITY_OBJECTIVE.id:
                await self._set_canonical_name(user_id, value or other_text)
            if obj.id not in answered:
                answered.append(obj.id)

        meta[_META_ANSWERED] = answered[:200]
        meta[_META_DECLINED] = declined[:80]
        meta[_META_NA] = not_applicable[:120]
        meta[_META_CURRENT] = obj.area_id
        sess.meta = meta
        sess.touch()
        await repo.save_session(sess)

        logger.info(
            "life_setup_question_%s user=%s area=%s objective=%s",
            action, user_id, obj.area_id, obj.id,
        )
        return await self.state(user_id)

    async def _write_facts(self, user_id: str, facts: Dict[str, Any]) -> None:
        """
        Into the profile everything else writes into.

        A fact's domain is the first part of its key, which is how a fact
        learned in one area — "vivo con il partner" — lands in the area it is
        actually about. Cross-area learning; never a cross-area question.
        """
        for key, value in (facts or {}).items():
            domain = str(key).split(".", 1)[0] or "generale"
            try:
                from life_setup.profile_service import LifeProfileService as Profiles

                await Profiles(self.db).upsert_fact(
                    user_id,
                    domain=domain,
                    key=str(key),
                    value=value,
                    source="user_said",
                    confidence=0.9,
                    confirmed=True,
                )
            except Exception:
                logger.exception("setup fact write failed key=%s", key)

    async def _set_canonical_name(self, user_id: str, name: Any) -> None:
        """
        One name, everywhere.

        Found live: somebody said their name during the setup and Home went on
        greeting them as "Test", because the setup's copy lived in its own
        session while every surface reads the account. There is one identity;
        this writes to it.
        """
        clean = str(name or "").strip()[:60]
        if not clean:
            return
        try:
            await self.db.users.update_one(
                {"user_id": user_id}, {"$set": {"name": clean}}
            )
            logger.info("life_setup_display_name_set user=%s", user_id)
        except Exception:
            logger.exception("canonical name write failed user=%s", user_id)

    # -- the person's other choices --------------------------------------

    async def skip_area(self, user_id: str, area_id: str) -> Dict[str, Any]:
        repo, sess, meta = await self._load(user_id, create=True)
        if not sess:
            return {"ok": False, "error": "no_session"}
        skipped = list(meta.get(_META_SKIPPED) or [])
        if area_id and area_id not in skipped:
            skipped.append(area_id)
        meta[_META_SKIPPED] = skipped[:20]
        meta[_META_CURRENT] = None
        sess.meta = meta
        sess.touch()
        await repo.save_session(sess)
        logger.info("life_setup_area_skipped user=%s area=%s", user_id, area_id)
        return await self.state(user_id)

    async def go_to_area(self, user_id: str, area_id: str) -> Dict[str, Any]:
        """An explicit move — the person chose to go on."""
        repo, sess, meta = await self._load(user_id, create=True)
        if not sess:
            return {"ok": False, "error": "no_session"}
        if not find_area(area_id):
            return {"ok": False, "error": "unknown_area"}
        meta[_META_CURRENT] = area_id
        skipped = [s for s in (meta.get(_META_SKIPPED) or []) if s != area_id]
        meta[_META_SKIPPED] = skipped
        sess.meta = meta
        sess.touch()
        await repo.save_session(sess)
        logger.info("life_setup_area_opened user=%s area=%s", user_id, area_id)
        return await self.state(user_id)

    async def finish(self, user_id: str) -> Dict[str, Any]:
        """
        The first run is over because the person says so.

        Not because a profile reached a number: someone who told ORA three
        things has finished their first conversation, and the completeness
        figure is a separate fact about how much ORA knows.
        """
        # Created if it does not exist: somebody who opens the setup and
        # leaves straight away has still finished their first run, and must
        # not be handed back to this screen tomorrow.
        repo, sess, meta = await self._load(user_id, create=True)
        if sess:
            meta[_META_FINISHED] = True
            sess.meta = meta
            # The gate reads the session's own status, so ending the first run
            # has to say so there too — otherwise the person is handed back to
            # this screen on their next launch, which is the onboarding loop
            # V3.3 exists to remove. It says nothing about how much ORA knows.
            if str(getattr(sess, "status", "")) in ("not_started", "active"):
                sess.status = "completed"
            sess.touch()
            await repo.save_session(sess)
        logger.info("life_setup_first_run_finished user=%s", user_id)
        out = await self.state(user_id)
        out["finished"] = True
        return out


def get_guided_setup_service(db) -> GuidedSetupService:
    return GuidedSetupService(db)
