"""
From "I need to read a calendar" to something that exists and is allowed.

    AI DECIDES WHAT SHOULD BE DONE AND HOW.
    CODE ENFORCES WHAT ORA IS ALLOWED TO EXECUTE.

The model is asked what it needs to be able to do, in ordinary terms. It is
never asked which client to call, which endpoint, or which arguments — a
model that reasons about function signatures is a model whose plans break
when the plumbing changes, and one that will confidently invent a tool that
does not exist.

So a step names a capability and this file answers three questions about it:
does it exist, is it something ORA may touch at all for this person, and does
it change anything in the world. The first two come from the permission
registry that already exists; the third is what makes the authority question
worth asking at all.

Nothing here is a plan template. It knows that `calendar.write` changes the
world and `calendar.read` does not; it has no idea what a calendar is for.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Capabilities the agent may reason about, mapped to what they mean for
# authority. `writes` is the only judgement encoded here, and it is not a
# judgement about importance — it is the difference between looking and
# touching, which is a fact about the verb.
#
# Everything a person could actually grant lives in the permission registry;
# this adds the two things that registry does not say: whether it changes the
# world, and how hard that would be to undo.
@dataclass(frozen=True)
class CapabilityFacts:
    name: str
    writes: bool
    # Default reversibility of the effect. The model may judge a particular
    # instance differently; this is the shape of the verb, not of the case.
    reversibility: str
    # Whether the effect reaches somebody other than the owner.
    reaches_third_party: bool = False
    financial: bool = False


_FACTS: Dict[str, CapabilityFacts] = {
    # Reading and thinking. Nothing here touches the world.
    "information.read": CapabilityFacts("information.read", False, "easily"),
    "web.research": CapabilityFacts("web.research", False, "easily"),
    "calendar.read": CapabilityFacts("calendar.read", False, "easily"),
    "mail.read": CapabilityFacts("mail.read", False, "easily"),
    "mail.metadata": CapabilityFacts("mail.metadata", False, "easily"),
    "document.read": CapabilityFacts("document.read", False, "easily"),
    "contacts.read": CapabilityFacts("contacts.read", False, "easily"),
    "location.read": CapabilityFacts("location.read", False, "easily"),
    # Preparing. Produces something, changes nothing outside ORA.
    "document.create": CapabilityFacts("document.create", False, "easily"),
    "comparison.run": CapabilityFacts("comparison.run", False, "easily"),
    "mail.draft": CapabilityFacts("mail.draft", False, "easily"),
    # Touching the world.
    "calendar.write": CapabilityFacts("calendar.write", True, "easily"),
    "mail.send": CapabilityFacts(
        "mail.send", True, "irreversible", reaches_third_party=True
    ),
    "navigation.open": CapabilityFacts("navigation.open", True, "easily"),
    "external.booking": CapabilityFacts(
        "external.booking", True, "with_effort", reaches_third_party=True, financial=True
    ),
    "payment.execute": CapabilityFacts(
        "payment.execute", True, "hardly", reaches_third_party=True, financial=True
    ),
}

# Which capabilities have something behind them that could actually run. In
# Sprint 1 the world-touching ones deliberately do not — the point of this
# phase is to show ORA reaching the boundary correctly, not to cross it.
_EXECUTABLE = {
    "information.read",
    "web.research",
    "calendar.read",
    "document.read",
    "document.create",
    "comparison.run",
    "mail.draft",
    # V3.9 Sprint 3 — the first real write. A personal calendar entry is
    # reversible in two taps, costs nothing, commits nobody, reaches nobody
    # else, and can be read back afterwards — which is what actually decided
    # it. A write whose only evidence is its own 200 teaches a system to
    # believe itself.
    "calendar.write",
    # One world-changing capability with a stub behind it, deliberately the
    # mildest one there is: opening a map reaches nobody, costs nothing and
    # undoes itself by being ignored. It exists so the "there is already a
    # grant, so proceed" path is something that can be demonstrated rather
    # than only described — the rest of the write side stays unwired.
    "navigation.open",
}

# Which capabilities reach something that actually exists in ORA. This is the
# set Sprint 2 is really about: everything here runs against a real engine or
# a real collection and reports what it actually found, including finding
# nothing. Everything outside it is either unwired or a declared stand-in.
#
# `calendar.read` is in the list because the read is real; whether there is a
# calendar behind it is a different question, and the capability answers that
# honestly per person rather than by being absent from this set.
_REAL = {
    "calendar.write",
    "information.read",
    "document.read",
    "calendar.read",
    "web.research",
    "comparison.run",
    "document.create",
    "mail.draft",
}

# What has a stand-in behind it, and says so. Kept to one, on purpose: the
# moment this set grows, "ORA did it" stops meaning anything.
_SIMULATED = {"navigation.open"}

# Which capability maps to which connector in the permission registry.
#
# These are the registry's own ids, not friendly names, and the difference
# was not academic: this map said `calendar` where the connector has always
# called itself `calendar_google`, so the registry was asked about something
# that does not exist and answered no. Every real person came out as "not
# permitted to write to a calendar they had connected" — invisible, because
# the only path that had ever exercised it was a test whose fixture granted
# the same wrong name.
_CONNECTOR = {
    "calendar.read": "calendar_google",
    "calendar.write": "calendar_google",
    "mail.read": "mail",
    "mail.metadata": "mail",
    "mail.send": "mail",
    "contacts.read": "contacts",
    "location.read": "location",
}

# Connectors whose consent is recorded per connected account rather than for
# the connector at large. Asking with a wildcard where the person granted one
# instance is the same shape of mistake as asking the wrong connector, and it
# fails the same silent way.
_PER_INSTANCE = {"calendar_google"}


@dataclass
class Resolution:
    """What code can say about a capability the model asked for."""

    capability: str
    known: bool
    permitted: bool
    executable: bool
    writes: bool
    reversibility: str
    reaches_third_party: bool
    financial: bool
    reason: str = ""
    # V3.9 Sprint 2 - what is actually behind it, in one word the planner can
    # act on. `available_simulated` is deliberately not `available_real`: a
    # plan built on a stand-in must know that before it leans on it.
    status: str = "unavailable"

    @property
    def usable(self) -> bool:
        return self.known and self.permitted and self.executable

    @property
    def is_real(self) -> bool:
        return self.status == "available_real"


class CapabilityResolver:
    def __init__(self, db):
        self.db = db

    async def resolve(self, owner_id: str, capability: str) -> Resolution:
        """
        Does this exist, may we touch it, and can it actually run?

        An unknown capability is reported as unknown rather than quietly
        treated as unavailable: the model asked for something that is not in
        the vocabulary, and it needs to know that so it can find another way.
        """
        facts = _FACTS.get((capability or "").strip())
        if facts is None:
            return Resolution(
                capability=capability, known=False, permitted=False, executable=False,
                writes=False, reversibility="easily", reaches_third_party=False,
                financial=False, reason="capability_unknown", status="unavailable",
            )

        permitted = await self._permitted(owner_id, facts.name)
        return Resolution(
            capability=facts.name,
            known=True,
            permitted=permitted,
            executable=facts.name in _EXECUTABLE,
            writes=facts.writes,
            reversibility=facts.reversibility,
            reaches_third_party=facts.reaches_third_party,
            financial=facts.financial,
            reason="" if permitted else "not_permitted",
            status=_status_of(facts.name, permitted),
        )

    async def _permitted(self, owner_id: str, capability: str) -> bool:
        """
        Whether ORA may touch this at all — the registry's question, not ours.

        Capabilities with no connector behind them (reading what ORA already
        holds, thinking, drafting) need no grant from anybody: they touch
        nothing that is not already ORA's to read.
        """
        connector = _CONNECTOR.get(capability)
        if connector is None:
            return True
        try:
            from permissions.service import PermissionService

            service = PermissionService(self.db)
            if connector in _PER_INSTANCE:
                instance = await self._instance_id(owner_id, connector)
                if instance:
                    return bool(
                        await service.check_access(
                            user_id=owner_id,
                            capability_id=capability,
                            connector_id=connector,
                            connector_instance_id=instance,
                        )
                    )
            return bool(
                await service.check_access(
                    user_id=owner_id,
                    capability_id=capability,
                    connector_id=connector,
                )
            )
        except Exception as e:
            logger.info("capability check soft-fail: %s", type(e).__name__)
            return False

    async def _instance_id(self, owner_id: str, connector: str) -> str:
        """Which connected account this person's consent was given about."""
        try:
            found = await self.db.connector_instances.find_one(
                {
                    "user_id": owner_id,
                    "connector_id": connector,
                    "status": {"$in": ["connected", "active", "authorized"]},
                },
                {"_id": 0, "id": 1},
                sort=[("updated_at", -1)],
            )
            return str((found or {}).get("id") or "")
        except Exception as e:
            logger.info("instance lookup soft-fail: %s", type(e).__name__)
            return ""

    async def available(self, owner_id: str) -> List[Dict[str, Any]]:
        """
        What the planner is told it can work with.

        Deliberately includes things that are known but not usable, with the
        reason: a model told only about what works will plan around a gap it
        cannot see, and one told nothing will invent.
        """
        out: List[Dict[str, Any]] = []
        grants: set = set()
        try:
            from agent.authority import AuthorityService

            grants = {
                g["capability"] for g in await AuthorityService(self.db).grants(owner_id)
            }
        except Exception as e:
            logger.info("grant read soft-fail: %s", type(e).__name__)

        for name in sorted(_FACTS):
            resolution = await self.resolve(owner_id, name)
            status = resolution.status
            # Something that changes the world and has no standing permission
            # is not unavailable - it is available and gated, and a plan is
            # entitled to include it and stop at the door.
            if status.startswith("available") and resolution.writes and name not in grants:
                status = "requires_authority"
            out.append({
                "capability": name,
                "status": status,
                "can_be_used_now": resolution.usable,
                "really_does_something": status == "available_real",
                "changes_something_in_the_world": resolution.writes,
                "why_not": resolution.reason or None,
            })
        return out


def capability_facts(capability: str) -> Optional[CapabilityFacts]:
    return _FACTS.get((capability or "").strip())


def is_world_changing(capability: str) -> bool:
    facts = _FACTS.get((capability or "").strip())
    # An unknown capability is treated as world-changing. Failing closed on
    # something nobody has described is the only safe direction.
    return True if facts is None else facts.writes


def resolution_is_stubbed(capability: str) -> bool:
    """
    Whether something world-changing has a stand-in behind it.

    True for exactly the capabilities that both change something and are in
    the executable set — which in Sprint 1 is one, on purpose.
    """
    name = (capability or "").strip()
    facts = _FACTS.get(name)
    return bool(facts and facts.writes and name in _EXECUTABLE)


def _status_of(capability: str, permitted: bool) -> str:
    """
    What is actually behind this, in one word.

    The order matters. A capability nobody has allowed reports why it cannot
    be used before anything else, because a planner told "available" about
    something it may not touch will build a route through it.
    """
    if not permitted:
        return "requires_connection" if capability in _CONNECTOR else "unavailable"
    if capability in _REAL and capability in _EXECUTABLE:
        return "available_real"
    if capability in _SIMULATED and capability in _EXECUTABLE:
        return "available_simulated"
    return "unavailable"


def capability_status(capability: str, *, permitted: bool = True) -> str:
    return _status_of((capability or "").strip(), permitted)


def is_really_wired(capability: str) -> bool:
    """Whether something real happens when this runs. Not whether it may."""
    name = (capability or "").strip()
    return name in _REAL and name in _EXECUTABLE
