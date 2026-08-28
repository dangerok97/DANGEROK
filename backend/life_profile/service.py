"""
The Life Profile, read from what ORA already holds.

This is a projection and nothing else. Every fact it reports was written by
somebody else — the setup conversation, a document, an ordinary turn with ORA —
into the stores that already own them: `LifeProfile` for structured facts about
a life, the setup session for what a person chose to skip or not to say. There
is no `onboarding_answers` collection, and there must never be one: two copies
of where somebody lives is how a system starts contradicting itself.

Because it is a projection, it is also cheap. Opening Vita reads two documents
and does arithmetic. Nothing here calls a model; the model is for writing the
next question, not for counting what is already known.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from life_profile.areas import all_areas, area, area_for_domain
from life_profile.completeness import ProfileCompleteness, profile_completeness

logger = logging.getLogger("ora.life_profile")

# How a source is said out loud. The vocabulary is the profile's own; this only
# turns it into something a person recognises as an answer to "how do you know
# that?".
_PROVENANCE_LABEL = {
    "user_said": "Me lo hai detto",
    "user_confirmed": "Confermato da te",
    "document_extract": "Da un documento",
    "semantic_extract": "Da quello che mi hai raccontato",
    "inferred": "Dedotto da ORA",
    "system": "Dal tuo account",
}

# Sources ORA worked out rather than was told. They still count — a life
# profile that ignored what it can reasonably conclude would be useless — but
# they are marked, and the interface can say so.
_INFERRED_SOURCES = {"inferred"}


class LifeProfileService:
    """Read model over the profile, the setup state, and nothing new."""

    def __init__(self, db):
        self.db = db

    # -- gathering -------------------------------------------------------

    async def _profile_facts(
        self, user_id: str
    ) -> Tuple[Dict[str, Any], Dict[str, str], List[str]]:
        """Everything the durable profile holds, with where each piece came from."""
        facts: Dict[str, Any] = {}
        provenance: Dict[str, str] = {}
        inferred: List[str] = []
        try:
            from life_setup.profile_service import LifeProfileService as Profiles

            profile = await Profiles(self.db).get(user_id)
        except Exception:
            logger.info("life profile read soft-fail", exc_info=True)
            return facts, provenance, inferred
        if not profile:
            return facts, provenance, inferred

        for domain in (profile.domains or {}).values():
            for key, obj in (domain.objects or {}).items():
                # `False` is kept deliberately. "No, I don't own a car" is an
                # answer, and filtering falsey values is exactly what made an
                # area unfinishable for the people it did not apply to.
                facts[key] = obj.value
                source = str(getattr(obj, "source", "") or "")
                provenance[key] = _PROVENANCE_LABEL.get(source, "Dal tuo profilo")
                if source in _INFERRED_SOURCES:
                    inferred.append(key)
        return facts, provenance, inferred

    async def _setup_state(self, user_id: str) -> Dict[str, Any]:
        """What the person chose: skipped, declined, not applicable, where they were."""
        empty = {
            "declined": [],
            "postponed": [],
            "not_applicable": [],
            "touched": [],
            "known_facts": {},
            "status": "not_started",
            "first_run_finished": False,
            "last_area": None,
        }
        try:
            from life_setup.repository import LifeSetupRepository

            sess = await LifeSetupRepository(self.db).latest_session(user_id)
        except Exception:
            logger.info("setup state read soft-fail", exc_info=True)
            return empty
        if not sess:
            return empty

        meta = dict(getattr(sess, "meta", None) or {})
        touched = [
            a.id
            for d in (sess.domains_touched or [])
            if (a := area_for_domain(d)) is not None
        ]
        return {
            "declined": list(sess.refused_keys or []),
            "postponed": list(sess.postponed_keys or []),
            "not_applicable": list(meta.get("not_applicable_keys") or []),
            "touched": touched,
            "known_facts": dict(sess.known_facts or {}),
            "status": str(sess.status or "not_started"),
            "first_run_finished": bool(meta.get("first_run_finished"))
            or str(sess.status) in ("completed", "skipped", "cancelled"),
            "last_area": meta.get("last_area"),
        }

    # -- the projection --------------------------------------------------

    async def completeness(self, user_id: str) -> ProfileCompleteness:
        facts, provenance, inferred = await self._profile_facts(user_id)
        state = await self._setup_state(user_id)

        # The session's own working notes fill gaps the durable profile has not
        # caught up with yet. The profile wins where both have something: it is
        # the governed copy.
        merged: Dict[str, Any] = dict(state["known_facts"])
        merged.update(facts)

        return profile_completeness(
            facts=merged,
            provenance=provenance,
            declined_refs=state["declined"],
            not_applicable_refs=state["not_applicable"],
            inferred_refs=inferred,
            touched_area_ids=state["touched"],
        )

    async def public(self, user_id: str) -> Dict[str, Any]:
        """
        What an interface may see.

        First-run state and profile completeness are two different things and
        are reported as two different things: someone can be done with
        onboarding at 30%, and that is a finished onboarding, not a broken one.
        """
        comp = await self.completeness(user_id)
        state = await self._setup_state(user_id)
        return {
            "ok": True,
            "percent": comp.percent,
            "areas": [a.model_dump() for a in comp.areas],
            "suggested_area_id": comp.suggested_area_id,
            "first_run": {
                "finished": state["first_run_finished"],
                "status": state["status"],
                "last_area": state["last_area"],
            },
        }

    async def area_detail(self, user_id: str, area_id: str) -> Dict[str, Any]:
        found = area(area_id)
        if not found:
            return {"ok": False, "error": "unknown_area"}
        comp = await self.completeness(user_id)
        for a in comp.areas:
            if a.area_id == found.id:
                return {"ok": True, "area": a.model_dump()}
        return {"ok": False, "error": "unknown_area"}

    # -- what a person chose ---------------------------------------------

    async def mark_not_applicable(self, user_id: str, refs: List[str]) -> Dict[str, Any]:
        """
        Record that something does not apply to this life.

        The client reports the choice; it never reports a percentage. What that
        choice does to the numbers is worked out here, from the same rules as
        everything else.
        """
        clean = [str(r).strip()[:120] for r in (refs or []) if str(r).strip()]
        if not clean:
            return {"ok": False, "error": "no_refs"}
        try:
            from life_setup.repository import LifeSetupRepository

            repo = LifeSetupRepository(self.db)
            sess = await repo.latest_session(user_id)
            if not sess:
                return {"ok": False, "error": "no_session"}
            meta = dict(sess.meta or {})
            existing = list(meta.get("not_applicable_keys") or [])
            meta["not_applicable_keys"] = list(dict.fromkeys(existing + clean))[:64]
            sess.meta = meta
            sess.touch()
            await repo.save_session(sess)
        except Exception:
            logger.exception("not_applicable write failed user=%s", user_id)
            return {"ok": False, "error": "write_failed"}
        logger.info(
            "life_profile_not_applicable user=%s count=%d", user_id, len(clean)
        )
        return await self.public(user_id)


def get_life_profile_service(db) -> LifeProfileService:
    return LifeProfileService(db)
