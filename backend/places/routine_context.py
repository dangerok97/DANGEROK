"""Live route evidence for a learned routine, without pretending it will happen.

A routine is a model-observed pattern. It can justify looking at fresh context;
it cannot justify claiming that the person will travel. This module therefore
answers one narrower question:

    IF THE OBSERVED PATTERN REPEATED NOW, WHAT WOULD THE ROUTE LOOK LIKE?

That conditional wording is preserved in the evidence and later grounding.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from places.models import ObservedRoutine

COLLECTION = "routine_route_context"
LABELS = {
    "drive": "in auto",
    "walk": "a piedi",
    "bicycle": "in bici",
    "transit": "con i mezzi",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:20]


class RoutineRouteContextService:
    def __init__(self, db):
        self.db = db

    async def refresh(
        self, owner_id: str, routine_id: str, *, now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Refresh one route hypothesis from current known-place context."""
        from places.service import PlacesService
        from places import routing, briefing

        now = now or _now()
        doc = await self.db.observed_routines.find_one(
            {"user_id": owner_id, "id": routine_id}, {"_id": 0}
        )
        if not doc:
            return {"status": "routine_gone"}
        try:
            routine = ObservedRoutine.model_validate(doc)
        except Exception:
            return {"status": "routine_invalid"}

        record = await self.db.users.find_one(
            {"user_id": owner_id}, {"preferences.place_monitoring_enabled": 1}
        )
        if (record or {}).get("preferences", {}).get("place_monitoring_enabled") is not True:
            return {"status": "monitoring_off"}

        places = PlacesService(self.db)
        here = await places.where_now(owner_id)
        current_id = str(here.get("place_id") or "")
        if not current_id:
            return {"status": "no_current_known_place"}

        sequence = list(routine.place_sequence)
        try:
            index = sequence.index(current_id)
        except ValueError:
            return {"status": "current_place_outside_routine"}
        if index + 1 >= len(sequence):
            return {"status": "no_next_place"}

        origin_place = await places.get_place(owner_id, current_id)
        target_place = await places.get_place(owner_id, sequence[index + 1])
        if (
            origin_place is None
            or target_place is None
            or origin_place.coordinates is None
            or target_place.coordinates is None
        ):
            return {"status": "place_coordinates_unavailable"}

        caps = routing.capabilities()
        if not caps.get("available"):
            return {"status": "routing_unavailable"}

        origin = {
            "latitude": origin_place.coordinates.latitude,
            "longitude": origin_place.coordinates.longitude,
        }
        destination = {
            "latitude": target_place.coordinates.latitude,
            "longitude": target_place.coordinates.longitude,
        }
        modes = [m for m in LABELS if m in (caps.get("modes") or [])]
        routes = await asyncio.gather(
            *[
                routing.get_route(
                    origin=origin,
                    destination=destination,
                    travel_mode=mode,
                    alternatives=mode == "drive",
                )
                for mode in modes
            ],
            return_exceptions=True,
        )

        options = []
        roads = []
        weather = []
        for mode, route in zip(modes, routes):
            if not isinstance(route, dict) or not route.get("available"):
                continue
            duration = route.get("duration_seconds")
            if (
                not isinstance(duration, (int, float))
                or not math.isfinite(duration)
                or duration <= 0
            ):
                continue
            options.append(
                {
                    "mode": mode,
                    "label": LABELS[mode],
                    "duration_minutes": math.ceil(duration / 60),
                    "distance_meters": route.get("distance_meters"),
                    "reflects_current_traffic": bool(
                        route.get("reflects_current_traffic")
                    ),
                    "provider": route.get("provider"),
                }
            )
            if mode == "drive":
                alternatives = route.get("alternatives") or []
                roads = briefing.route_choices(alternatives)
                best = min(
                    alternatives,
                    key=lambda r: r.get("duration_seconds", math.inf),
                    default={},
                )
                if best.get("polyline"):
                    weather = await briefing.weather_along_route(
                        best["polyline"], int(duration)
                    )

        if not options:
            return {"status": "routing_unavailable"}

        evidence = {
            "status": "ready",
            "routine_ref": routine.id,
            "hypothesis_only": True,
            "from_place_ref": origin_place.id,
            "from_place": origin_place.label,
            "to_place_ref": target_place.id,
            "to_place": target_place.label,
            "typical_start": routine.typical_start or None,
            "interpretation": routine.interpretation or None,
            "options": options,
            "road_choices": roads,
            "route_weather": weather,
            "observed_at": now.isoformat(),
            "valid_until": (now + timedelta(minutes=5)).isoformat(),
        }
        evidence["ref"] = "routine_route:" + _digest(evidence)

        await self.db[COLLECTION].update_one(
            {"owner_id": owner_id, "routine_id": routine.id},
            {
                "$set": {
                    "owner_id": owner_id,
                    "routine_id": routine.id,
                    "evidence": evidence,
                    "updated_at": now.isoformat(),
                    "expires_at": now + timedelta(hours=2),
                }
            },
            upsert=True,
        )
        return evidence

    async def current(self, owner_id: str, *, now: Optional[datetime] = None):
        now = now or _now()
        rows = await self.db[COLLECTION].find(
            {"owner_id": owner_id}, {"_id": 0, "evidence": 1}
        ).to_list(6)
        output = []
        for row in rows:
            evidence = row.get("evidence") or {}
            if evidence.get("status") != "ready":
                continue
            try:
                valid_until = datetime.fromisoformat(str(evidence["valid_until"]))
                if valid_until.tzinfo is None:
                    valid_until = valid_until.replace(tzinfo=timezone.utc)
            except (KeyError, TypeError, ValueError):
                continue
            if valid_until > now:
                output.append(evidence)
        return output


def ground_candidate(candidate, evidence: Dict[str, Any]) -> None:
    """Pin any surfaced claim to the conditional route evidence."""
    options = evidence.get("options") or []
    summary = "; ".join(
        f"{o.get('label')}: circa {o.get('duration_minutes')} min"
        for o in options
        if o.get("label") and o.get("duration_minutes")
    )
    candidate.identity_key = "routine_route:" + str(evidence.get("routine_ref") or "")
    candidate.semantic_summary = (
        f"Se la routine osservata si ripetesse ora, da "
        f"{evidence.get('from_place')} a {evidence.get('to_place')}: {summary}."
    )[:280]
    candidate.why_it_matters = (
        "È una verifica condizionale basata su una routine osservata, non la "
        "previsione che lo spostamento avverrà. I tempi sono quelli verificati "
        "nel momento indicato."
    )[:600]
    candidate.why_now = (
        f"Percorso verificato alle {str(evidence.get('observed_at') or '')[:16]}."
    )[:280]
    candidate.what_ora_can_do = (
        f"Posso ricontrollare il percorso verso {evidence.get('to_place')} "
        "e aprire la navigazione se serve."
    )[:600]
    candidate.initiative = "inform"
    candidate.valid_until = str(evidence.get("valid_until") or "")
    candidate.time_sensitivity = "perishable"
    candidate.requires_clarification = False
    candidate.clarifying_question = ""
    candidate.needs_research = False
    candidate.research_question = ""
