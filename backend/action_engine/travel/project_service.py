"""Travel Project persistence — draft / preview / confirm (no silent calendar create)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from action_engine.models import ProposedAction, now_iso
from action_engine.travel.brain_links import link_project_to_brain
from action_engine.travel.documents import search_travel_documents
from action_engine.travel.flow import (
    STEP_BOOKINGS,
    STEP_CALENDAR_SYNC,
    STEP_COMPANIONS,
    STEP_DEPARTURE,
    STEP_DESTINATION,
    STEP_PERIOD,
    STEP_PREP,
    STEP_TRANSPORT,
)
from action_engine.travel.google_sync import (
    delete_travel_google_events,
    is_google_connected,
    sync_travel_events,
)
from action_engine.travel.maps import build_maps_info, departure_time_advice
from action_engine.travel.models import (
    DEFAULT_TZ,
    TravelCalendarEvent,
    TravelModifyBody,
    TravelProject,
    make_idempotency_key,
)
from action_engine.travel.period_parser import format_period_label, parse_travel_period
from action_engine.travel.prep import build_prep_items

logger = logging.getLogger("ora.action_engine.travel.project")


def _tz(name: str = DEFAULT_TZ) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo(DEFAULT_TZ)


def _local_dt(d: str, hour: int, minute: int = 0, tz_name: str = DEFAULT_TZ) -> str:
    from datetime import date as date_cls

    day = date_cls.fromisoformat(d[:10])
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=_tz(tz_name))
    return local.astimezone(timezone.utc).isoformat()


class TravelProjectService:
    def __init__(self, db, *, life_graph=None, knowledge=None, decisions=None):
        self.db = db
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.decisions = decisions

    @property
    def projects(self):
        return self.db.travel_projects

    async def ensure_indexes(self) -> None:
        await self.projects.create_index("id", unique=True)
        await self.projects.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.projects.create_index([("user_id", 1), ("idempotency_key", 1)])
        await self.projects.create_index([("user_id", 1), ("action_session_id", 1)])
        await self.projects.create_index([("user_id", 1), ("source_priority_id", 1)])

    async def find_similar(
        self,
        user_id: str,
        *,
        destination: str,
        start_date: Optional[str],
        end_date: Optional[str],
        source_priority_id: Optional[str] = None,
    ) -> Optional[dict]:
        key = make_idempotency_key(
            user_id, source_priority_id, destination, start_date or "", end_date or "",
        )
        found = await self.projects.find_one(
            {
                "user_id": user_id,
                "idempotency_key": key,
                "status": {"$in": ["draft", "awaiting_confirmation", "active", "paused"]},
            },
            {"_id": 0},
        )
        if found:
            return found
        q: Dict[str, Any] = {
            "user_id": user_id,
            "status": {"$in": ["active", "paused", "awaiting_confirmation"]},
            "destination": {"$regex": f"^{destination.strip()}$", "$options": "i"},
        }
        if start_date:
            q["start_date"] = {"$regex": f"^{start_date[:10]}"}
        return await self.projects.find_one(q, {"_id": 0})

    def build_draft_from_answers(
        self,
        *,
        user_id: str,
        answers: Dict[str, Any],
        session: dict,
        meta: Optional[dict] = None,
    ) -> TravelProject:
        meta = meta or {}
        entities = (session.get("meta") or {}).get("intent_entities") or {}
        period = answers.get(STEP_PERIOD) or {}
        if isinstance(period, str):
            parsed = parse_travel_period(period, tz_name=meta.get("timezone") or DEFAULT_TZ)
            period = {
                "start_date": parsed.get("start_date"),
                "end_date": parsed.get("end_date"),
            } if parsed.get("ok") else {}
        dep_ans = answers.get("departure_date") or {}
        ret_ans = answers.get("return_date") or {}
        start = period.get("start_date") or entities.get("start_date") or entities.get("departure_date")
        end = period.get("end_date") or entities.get("end_date") or entities.get("return_date")
        if isinstance(dep_ans, dict):
            start = start or dep_ans.get("departure_date") or dep_ans.get("start_date")
            end = end or dep_ans.get("return_date") or dep_ans.get("end_date")
        elif dep_ans:
            start = start or str(dep_ans)[:10]
        if isinstance(ret_ans, dict):
            end = end or ret_ans.get("return_date") or ret_ans.get("end_date")
        elif ret_ans:
            end = end or str(ret_ans)[:10]

        dest = answers.get(STEP_DESTINATION) or entities.get("travel") or entities.get("place") or entities.get("destination")
        if dest == "from_title":
            dest = session.get("title")
        departure = answers.get(STEP_DEPARTURE) or meta.get("home_place")
        transport = answers.get(STEP_TRANSPORT) or entities.get("transport") or "car"
        if isinstance(transport, dict):
            transport = transport.get("normalized") or transport.get("raw") or "car"
        bookings = answers.get(STEP_BOOKINGS) or "none"
        companions = answers.get(STEP_COMPANIONS) or 1
        try:
            companions = int(companions)
        except Exception:
            companions = 1
        cal = bool(answers.get(STEP_CALENDAR_SYNC))
        prep = answers.get(STEP_PREP) or []
        if isinstance(prep, str):
            prep = [prep]
        title = f"Vacanza: {dest}" if dest else (session.get("title") or "Vacanza")
        source_priority_id = session.get("home_item_id")
        key = make_idempotency_key(
            user_id, source_priority_id, str(dest or ""), str(start or ""), str(end or ""),
        )
        return TravelProject(
            user_id=user_id,
            status="draft",
            title=title,
            destination=str(dest) if dest else None,
            departure_place=str(departure) if departure else None,
            start_date=str(start)[:10] if start else None,
            end_date=str(end)[:10] if end else None,
            timezone=meta.get("timezone") or DEFAULT_TZ,
            transport=transport,  # type: ignore[arg-type]
            bookings=bookings,  # type: ignore[arg-type]
            companions=companions,
            calendar_sync=cal,
            prep_items=build_prep_items(list(prep)),
            document_ids=list(answers.get("document_ids") or meta.get("travel_document_ids") or []),
            source_priority_id=source_priority_id,
            source_type=session.get("source_type"),
            source_id=session.get("source_id"),
            action_session_id=session.get("id"),
            project_id=(session.get("project") or {}).get("project_id"),
            brain_node_id=session.get("brain_node_id"),
            idempotency_key=key,
            answers=dict(answers),
            email_search={"status": "not_implemented", "hook": "email_auto_find"},
            weather={"status": "unavailable", "reason": "no_weather_api_configured"},
        )

    async def upsert_draft(self, plan: TravelProject) -> TravelProject:
        plan.updated_at = now_iso()
        existing = None
        if plan.action_session_id:
            existing = await self.projects.find_one(
                {"user_id": plan.user_id, "action_session_id": plan.action_session_id},
                {"_id": 0},
            )
        if existing:
            plan.id = existing["id"]
            plan.created_at = existing.get("created_at") or plan.created_at
        await self.projects.update_one(
            {"id": plan.id, "user_id": plan.user_id},
            {"$set": plan.model_dump()},
            upsert=True,
        )
        return plan

    def _propose_calendar_events(self, plan: TravelProject) -> List[TravelCalendarEvent]:
        if not plan.start_date or not plan.end_date:
            return []
        dest = plan.destination or "viaggio"
        events = [
            TravelCalendarEvent(
                kind="vacation_block",
                title=f"Vacanza: {dest}",
                starts_at=plan.start_date[:10],
                ends_at=plan.end_date[:10],
                all_day=True,
            ),
            TravelCalendarEvent(
                kind="outbound",
                title=f"Andata → {dest}",
                starts_at=_local_dt(plan.start_date, 8, 0, plan.timezone),
                ends_at=_local_dt(plan.start_date, 12, 0, plan.timezone),
                all_day=False,
            ),
            TravelCalendarEvent(
                kind="return",
                title=f"Ritorno ← {dest}",
                starts_at=_local_dt(plan.end_date, 14, 0, plan.timezone),
                ends_at=_local_dt(plan.end_date, 18, 0, plan.timezone),
                all_day=False,
            ),
        ]
        return events

    async def build_preview(
        self, plan: TravelProject, *, allow_network_maps: bool = True,
    ) -> Dict[str, Any]:
        if not plan.start_date or not plan.end_date:
            return {
                "ok": False,
                "error": "missing_period",
                "message": "Mancano le date del viaggio.",
            }
        if not plan.destination:
            return {
                "ok": False,
                "error": "missing_destination",
                "message": "Manca la destinazione.",
            }

        try:
            from datetime import date as date_cls
            sd = date_cls.fromisoformat(plan.start_date[:10])
            ed = date_cls.fromisoformat(plan.end_date[:10])
            period_label = format_period_label(sd, ed)
            nights = (ed - sd).days
        except Exception:
            period_label = f"{plan.start_date} – {plan.end_date}"
            nights = None

        plan.calendar_events = self._propose_calendar_events(plan)
        maps = await build_maps_info(
            origin=plan.departure_place,
            destination=plan.destination,
            transport=plan.transport or "car",
            allow_network=allow_network_maps,
        )
        plan.maps = maps
        busy = []
        try:
            from action_engine.study.google_sync import free_windows_hint
            hints = await free_windows_hint(self.db, plan.user_id, days=21)
            if hints:
                busy = (hints[0].get("events") or [])[:10]
        except Exception:
            pass
        plan.departure_advice = departure_time_advice(
            transport=plan.transport or "car",
            duration_minutes=maps.duration_minutes,
            calendar_busy=busy,
        )

        docs_res = await search_travel_documents(
            self.db, user_id=plan.user_id, destination=plan.destination,
        )
        if docs_res.get("items") and not plan.document_ids:
            plan.document_ids = [d["id"] for d in docs_res["items"][:5]]

        transport_labels = {
            "train": "Treno", "plane": "Aereo", "car": "Auto", "other": "Altro",
        }
        preview = {
            "destination": plan.destination,
            "departure_place": plan.departure_place,
            "period_label": period_label,
            "start_date": plan.start_date,
            "end_date": plan.end_date,
            "nights": nights,
            "transport": plan.transport,
            "transport_label": transport_labels.get(plan.transport or "", plan.transport),
            "bookings": plan.bookings,
            "companions": plan.companions,
            "calendar_sync": plan.calendar_sync,
            "calendar_proposed": bool(plan.calendar_events),
            "calendar_event_count": len(plan.calendar_events),
            "calendar_events_summary": [
                {"kind": e.kind, "title": e.title, "all_day": e.all_day}
                for e in plan.calendar_events
            ],
            "maps": maps.model_dump(),
            "departure_advice": plan.departure_advice,
            "prep_items": [p.model_dump() for p in plan.prep_items],
            "documents": docs_res.get("items") or [],
            "documents_message": docs_res.get("message"),
            "weather": plan.weather,
            "email_search": plan.email_search,
            "honesty": {
                "weather": "Meteo non disponibile — nessuna API configurata.",
                "maps": maps.honesty,
                "tolls": maps.tolls_note,
                "email": "Ricerca email automatica non implementata.",
                "calendar": (
                    "Eventi Google creati solo dopo conferma."
                    if plan.calendar_sync else
                    "Nessuna sync Google richiesta."
                ),
            },
        }
        plan.preview = preview
        plan.status = "awaiting_confirmation"
        plan.phase = plan.compute_phase()
        plan.updated_at = now_iso()
        await self.projects.update_one(
            {"id": plan.id, "user_id": plan.user_id},
            {"$set": plan.model_dump()},
            upsert=True,
        )
        return {"ok": True, "plan": plan.public(), "preview": preview}

    async def modify_draft(
        self, user_id: str, plan_id: str, body: TravelModifyBody,
    ) -> Dict[str, Any]:
        doc = await self.projects.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        plan = TravelProject(**doc)
        if body.destination is not None:
            plan.destination = body.destination
        if body.departure_place is not None:
            plan.departure_place = body.departure_place
        if body.start_date is not None:
            plan.start_date = body.start_date
        if body.end_date is not None:
            plan.end_date = body.end_date
        if body.transport is not None:
            plan.transport = body.transport
        if body.bookings is not None:
            plan.bookings = body.bookings
        if body.companions is not None:
            plan.companions = body.companions
        if body.calendar_sync is not None:
            plan.calendar_sync = body.calendar_sync
        if body.document_ids is not None:
            plan.document_ids = body.document_ids
        return await self.build_preview(plan)

    async def confirm(self, user_id: str, plan_id: str, *, force: bool = False) -> Dict[str, Any]:
        doc = await self.projects.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        plan = TravelProject(**doc)

        if plan.status == "active" and plan.confirmed_at:
            return {
                "ok": True,
                "already_confirmed": True,
                "plan": plan.public(),
                "actions": [],
                "effects": {"travel_project_id": plan.id},
            }

        similar = await self.find_similar(
            user_id,
            destination=plan.destination or "",
            start_date=plan.start_date,
            end_date=plan.end_date,
            source_priority_id=plan.source_priority_id,
        )
        if similar and similar.get("id") != plan.id and similar.get("status") == "active" and not force:
            return {
                "ok": False,
                "error": "duplicate",
                "message": "Esiste già un viaggio simile.",
                "duplicate": {
                    "id": similar.get("id"),
                    "destination": similar.get("destination"),
                    "status": similar.get("status"),
                },
            }

        if not plan.calendar_events:
            plan.calendar_events = self._propose_calendar_events(plan)

        # Life Graph calendar nodes (internal) — always when we have events
        calendar_ids: List[str] = []
        if self.life_graph:
            for ev in plan.calendar_events:
                try:
                    starts = ev.starts_at
                    if ev.all_day:
                        starts = _local_dt(ev.starts_at, 9, 0, plan.timezone)
                    node = await self.life_graph.create_node(
                        user_id,
                        type="event",
                        label=ev.title[:120],
                        description="Travel Project ORA",
                        attributes={
                            "kind": f"travel_{ev.kind}",
                            "starts_at": starts,
                            "start_at": starts,
                            "travel_project_id": plan.id,
                            "all_day": ev.all_day,
                        },
                        origin="action_engine_travel",
                    )
                    ev.life_node_id = node["id"]
                    calendar_ids.append(node["id"])
                except Exception as e:
                    logger.info("life event soft-fail: %s", type(e).__name__)

        brain = await link_project_to_brain(
            life_graph=self.life_graph,
            knowledge=self.knowledge,
            db=self.db,
            user_id=user_id,
            project=plan.model_dump(),
            existing_brain_node_id=plan.brain_node_id,
        )
        if brain.get("brain_node_id"):
            plan.brain_node_id = brain["brain_node_id"]

        # Prefer latest answer over stale draft field (never silent create)
        if "calendar_sync" in (plan.answers or {}):
            plan.calendar_sync = bool(plan.answers.get("calendar_sync"))

        # Google sync ONLY if user opted in — never silent
        google_res: Dict[str, Any] = {"skipped": ["not_requested"]}
        if plan.calendar_sync:
            google_res = await sync_travel_events(
                db=self.db, user_id=user_id, project=plan.model_dump(),
            )
            # Reload events with google ids (sync persists full array)
            refreshed = await self.projects.find_one(
                {"id": plan.id, "user_id": user_id},
                {"_id": 0, "calendar_events": 1, "google_sync": 1},
            )
            if refreshed and refreshed.get("calendar_events"):
                plan.calendar_events = [
                    TravelCalendarEvent(**e) for e in refreshed["calendar_events"]
                ]
            # Mirror ids from sync result if array fields still empty
            by_local = {
                s.get("event_local_id"): s
                for s in (google_res.get("synced") or [])
                if s.get("event_local_id") and s.get("event_id")
            }
            for ev in plan.calendar_events:
                hit = by_local.get(ev.id)
                if hit and not ev.google_event_id:
                    ev.google_event_id = hit["event_id"]
                    ev.google_calendar_id = hit.get("calendar_id")
                    ev.google_sync_status = "synced"
        plan.google_sync = google_res

        # Optional prep decisions
        decision_ids: List[str] = []
        actions: List[ProposedAction] = []
        if plan.prep_items and self.decisions:
            try:
                dec = await self.decisions.create(
                    user_id,
                    {
                        "title": f"Prep viaggio: {plan.destination}",
                        "category": "travel",
                        "urgency": 3,
                        "importance": 3,
                        "deadline": plan.start_date,
                        "metadata": {
                            "travel_project_id": plan.id,
                            "checklist": [p.label for p in plan.prep_items],
                            "action_session_id": plan.action_session_id,
                        },
                    },
                    origin="action_engine_travel",
                )
                if isinstance(dec, dict) and dec.get("id"):
                    decision_ids.append(dec.get("id"))
                    actions.append(ProposedAction(
                        id=f"prep_{dec.get('id')}",
                        kind="decision",
                        label="Lista preparazione",
                        status="done",
                    ))
            except Exception:
                actions.append(ProposedAction(
                    id="prep_local",
                    kind="decision",
                    label="Suggerimenti prep sul progetto",
                    status="proposed",
                    meta={"items": [p.model_dump() for p in plan.prep_items]},
                ))

        if plan.maps.deep_link:
            actions.append(ProposedAction(
                id="maps",
                kind="maps",
                label="Apri percorso Maps",
                detail=plan.maps.duration_label or plan.maps.honesty,
                status="proposed",
                meta={"url": plan.maps.deep_link, "distance_km": plan.maps.distance_km},
            ))

        actions.append(ProposedAction(
            id="weather",
            kind="blocked",
            label="Meteo destinazione",
            detail="Nessuna API meteo configurata — non invento previsioni.",
            status="blocked",
        ))
        actions.append(ProposedAction(
            id="email_find",
            kind="blocked",
            label="Cerca prenotazioni nelle email",
            detail="Modulo futuro — hook non implementato.",
            status="blocked",
        ))

        for ev in plan.calendar_events:
            actions.append(ProposedAction(
                id=f"cal_{ev.kind}",
                kind="calendar",
                label=ev.title,
                status="done" if (ev.google_event_id or ev.life_node_id) else "proposed",
                meta={
                    "kind": ev.kind,
                    "google_event_id": ev.google_event_id,
                    "life_node_id": ev.life_node_id,
                },
            ))

        plan.status = "active"
        plan.confirmed_at = now_iso()
        plan.phase = plan.compute_phase()
        plan.updated_at = plan.confirmed_at
        await self.projects.update_one(
            {"id": plan.id, "user_id": user_id},
            {"$set": plan.model_dump()},
            upsert=True,
        )

        days = plan.public().get("days_until")
        if plan.phase == "departure_day":
            hint = f"Partenza oggi verso {plan.destination}"
        elif plan.phase == "during":
            hint = f"In vacanza a {plan.destination}"
        elif days is not None and days >= 0:
            hint = f"Vacanza {plan.destination} tra {days} giorni"
        else:
            hint = f"Vacanza: {plan.destination}"

        effects = {
            "travel_project_id": plan.id,
            "calendar_ids": calendar_ids,
            "decision_ids": decision_ids,
            "google_sync": google_res,
            "maps": plan.maps.model_dump(),
            "brain": brain,
            "next_focus_hint": hint,
            "home_invalidate": True,
        }
        if google_res.get("banner"):
            effects["google_banner"] = google_res["banner"]

        # Goal Engine shadow upsert (no UX) — Action Engine does not invent Goals ad-hoc
        try:
            from goal_engine import get_goal_service
            goal_res = await get_goal_service(
                self.db, life_graph=self.life_graph, knowledge=self.knowledge,
            ).upsert_from_travel_confirm(plan.model_dump(), effects=effects)
            effects["goal"] = {
                "goal_id": goal_res.get("goal_id"),
                "created": goal_res.get("created"),
                "skipped": goal_res.get("skipped"),
            }
            if goal_res.get("goal_id"):
                try:
                    await self.projects.update_one(
                        {"id": plan.id, "user_id": user_id},
                        {"$set": {"goal_id": goal_res["goal_id"]}},
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.info("goal shadow travel soft-fail: %s", type(e).__name__)
            effects["goal"] = {"error": type(e).__name__, "soft_fail": True}

        # Life Object Engine shadow — TRAVEL object alongside Travel Project
        try:
            from life_objects.shadow import shadow_upsert_from_travel
            lo_res = await shadow_upsert_from_travel(
                self.db,
                user_id=user_id,
                project=plan.model_dump(),
                life_graph=self.life_graph,
            )
            effects["life_object"] = {
                "life_object_id": (lo_res.get("object") or {}).get("id"),
                "created": lo_res.get("created"),
                "skipped": lo_res.get("skipped"),
            }
        except Exception as e:
            logger.info("life_object travel shadow soft-fail: %s", type(e).__name__)
            effects["life_object"] = {"error": type(e).__name__, "soft_fail": True}

        return {
            "ok": True,
            "plan": plan.public(),
            "actions": [a.model_dump() for a in actions],
            "effects": effects,
            "next_focus_hint": hint,
        }

    async def get_project(self, user_id: str, plan_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.projects.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return None
        plan = TravelProject(**doc)
        plan.phase = plan.compute_phase()
        return plan.public()

    async def list_projects(
        self, user_id: str, status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {"user_id": user_id}
        if status:
            q["status"] = status
        else:
            q["status"] = {"$in": ["draft", "awaiting_confirmation", "active", "paused"]}
        docs = await self.projects.find(q, {"_id": 0}).sort("updated_at", -1).to_list(50)
        out = []
        for d in docs:
            p = TravelProject(**d)
            p.phase = p.compute_phase()
            out.append(p.public())
        return out

    async def delete_project(
        self, user_id: str, plan_id: str, *, soft: bool = True, cleanup_google: bool = False,
    ) -> Dict[str, Any]:
        doc = await self.projects.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        gdel = {}
        if cleanup_google:
            gdel = await delete_travel_google_events(self.db, user_id, doc)
        if soft:
            await self.projects.update_one(
                {"id": plan_id, "user_id": user_id},
                {"$set": {
                    "status": "cancelled",
                    "cancelled_at": now_iso(),
                    "updated_at": now_iso(),
                }},
            )
        else:
            await self.projects.delete_one({"id": plan_id, "user_id": user_id})
        return {"ok": True, "google_cleanup": gdel}
