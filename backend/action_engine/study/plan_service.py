"""Study plan persistence, preview, confirm, session actions, idempotency."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from action_engine.models import ProposedAction, now_iso
from action_engine.study.brain_links import link_plan_to_brain
from action_engine.study.generator import generate_plan_sessions, maybe_split_topics
from action_engine.study.google_sync import (
    delete_plan_google_events,
    is_google_connected,
    sync_plan_sessions,
    update_session_google_event,
)
from action_engine.study.models import (
    DEFAULT_TZ,
    PlanModifyBody,
    StudyPlan,
    StudySessionItem,
    TimeRange,
    make_idempotency_key,
)
from action_engine.study.tools import prepare_study_tools

logger = logging.getLogger("ora.action_engine.study.plan")


class StudyPlanService:
    def __init__(self, db, *, life_graph=None, knowledge=None, decisions=None):
        self.db = db
        self.life_graph = life_graph
        self.knowledge = knowledge
        self.decisions = decisions

    @property
    def plans(self):
        return self.db.study_plans

    @property
    def sessions(self):
        return self.db.study_sessions

    async def ensure_indexes(self) -> None:
        await self.plans.create_index("id", unique=True)
        await self.plans.create_index([("user_id", 1), ("status", 1), ("updated_at", -1)])
        await self.plans.create_index([("user_id", 1), ("idempotency_key", 1)])
        await self.plans.create_index([("user_id", 1), ("source_priority_id", 1)])
        await self.plans.create_index([("user_id", 1), ("action_session_id", 1)])
        await self.sessions.create_index("id", unique=True)
        await self.sessions.create_index([("user_id", 1), ("plan_id", 1), ("starts_at", 1)])
        await self.sessions.create_index([("user_id", 1), ("status", 1), ("starts_at", 1)])

    async def find_similar(
        self,
        user_id: str,
        *,
        exam_name: str,
        exam_date: Optional[str],
        source_priority_id: Optional[str] = None,
    ) -> Optional[dict]:
        key = make_idempotency_key(user_id, source_priority_id, exam_name, exam_date or "")
        found = await self.plans.find_one(
            {
                "user_id": user_id,
                "idempotency_key": key,
                "status": {"$in": ["draft", "awaiting_confirmation", "active", "paused"]},
            },
            {"_id": 0},
        )
        if found:
            return found
        # Fuzzy: same exam name + date day
        day = (exam_date or "")[:10]
        q: Dict[str, Any] = {
            "user_id": user_id,
            "status": {"$in": ["active", "paused", "awaiting_confirmation"]},
            "exam_name": {"$regex": f"^{exam_name.strip()}$", "$options": "i"},
        }
        if day:
            q["exam_date"] = {"$regex": f"^{day}"}
        return await self.plans.find_one(q, {"_id": 0})

    def build_draft_from_answers(
        self,
        *,
        user_id: str,
        answers: Dict[str, Any],
        session: dict,
        meta: Optional[dict] = None,
    ) -> StudyPlan:
        meta = meta or {}
        entities = (session.get("meta") or {}).get("intent_entities") or {}
        subject = (
            answers.get("confirm_subject")
            or entities.get("subject")
            or session.get("title")
        )
        exam_name = str(subject or session.get("title") or "Esame")
        exam_date = answers.get("exam_date_confirm") or answers.get("exam_date")
        daily = int(answers.get("daily_time") or 60)
        days = answers.get("available_days") or [0, 1, 2, 3, 4]
        if isinstance(days, int):
            days = [days]
        ranges_raw = answers.get("preferred_time_ranges") or [{"start": "18:00", "end": "20:00"}]
        ranges = []
        for r in ranges_raw if isinstance(ranges_raw, list) else [ranges_raw]:
            if isinstance(r, dict):
                ranges.append(TimeRange(start=r.get("start", "18:00"), end=r.get("end", "20:00")))
        intensity = answers.get("intensity") or "distributed"
        tools = answers.get("tools") or ["study", "review"]
        if isinstance(tools, str):
            tools = [tools]
        docs = answers.get("select_materials") or []
        if isinstance(docs, dict):
            docs = []
        if isinstance(docs, str):
            docs = [docs] if docs else []
        cal = bool(answers.get("calendar_sync"))
        source_priority_id = session.get("home_item_id")
        key = make_idempotency_key(user_id, source_priority_id, exam_name, str(exam_date or ""))
        return StudyPlan(
            user_id=user_id,
            status="draft",
            exam_name=exam_name,
            subject=str(subject) if subject else None,
            exam_date=str(exam_date) if exam_date else None,
            timezone=meta.get("timezone") or DEFAULT_TZ,
            intensity=intensity,  # type: ignore[arg-type]
            daily_minutes=daily,
            available_days=list(days),
            preferred_ranges=ranges,
            tools=tools,  # type: ignore[arg-type]
            document_ids=list(docs),
            calendar_sync=cal,
            source_priority_id=source_priority_id,
            source_type=session.get("source_type"),
            source_id=session.get("source_id"),
            action_session_id=session.get("id"),
            project_id=(session.get("project") or {}).get("project_id"),
            brain_node_id=session.get("brain_node_id"),
            idempotency_key=key,
            answers=dict(answers),
        )

    async def upsert_draft(self, plan: StudyPlan) -> StudyPlan:
        plan.updated_at = now_iso()
        existing = None
        if plan.action_session_id:
            existing = await self.plans.find_one(
                {"user_id": plan.user_id, "action_session_id": plan.action_session_id},
                {"_id": 0},
            )
        if existing:
            plan.id = existing["id"]
            plan.created_at = existing.get("created_at") or plan.created_at
        await self.plans.update_one(
            {"id": plan.id, "user_id": plan.user_id},
            {"$set": plan.model_dump()},
            upsert=True,
        )
        return plan

    async def build_preview(self, plan: StudyPlan, *, doc_titles: Optional[List[str]] = None) -> Dict[str, Any]:
        if not plan.exam_date:
            return {"ok": False, "error": "missing_exam_date", "message": "Manca la data dell'esame."}
        topics = await maybe_split_topics(
            subject=plan.subject or plan.exam_name,
            exam_name=plan.exam_name,
            document_titles=doc_titles,
        )
        gen = generate_plan_sessions(
            user_id=plan.user_id,
            plan_id=plan.id,
            exam_name=plan.exam_name,
            subject=plan.subject,
            exam_date_iso=plan.exam_date,
            daily_minutes=plan.daily_minutes,
            available_days=plan.available_days,
            preferred_ranges=plan.preferred_ranges,
            intensity=plan.intensity,
            tools=list(plan.tools),
            document_ids=plan.document_ids,
            topics=topics,
            tz_name=plan.timezone,
        )
        if not gen.get("ok"):
            return gen
        plan.sessions = gen["sessions"]
        plan.topics = gen.get("topics") or topics
        plan.preview = gen["preview"]
        plan.status = "awaiting_confirmation"
        plan.updated_at = now_iso()
        await self.plans.update_one(
            {"id": plan.id, "user_id": plan.user_id},
            {"$set": plan.model_dump()},
            upsert=True,
        )
        return {"ok": True, "plan": plan.public(), "preview": plan.preview}

    async def modify_draft(self, user_id: str, plan_id: str, body: PlanModifyBody) -> Dict[str, Any]:
        doc = await self.plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        plan = StudyPlan(**doc)
        if body.daily_minutes is not None:
            plan.daily_minutes = body.daily_minutes
        if body.available_days is not None:
            plan.available_days = body.available_days
        if body.preferred_ranges is not None:
            plan.preferred_ranges = body.preferred_ranges
        if body.intensity is not None:
            plan.intensity = body.intensity
        if body.document_ids is not None:
            plan.document_ids = body.document_ids
        if body.calendar_sync is not None:
            plan.calendar_sync = body.calendar_sync
        if body.tools is not None:
            plan.tools = body.tools
        if body.exam_date is not None:
            plan.exam_date = body.exam_date
        return await self.build_preview(plan)

    async def confirm(
        self,
        user_id: str,
        plan_id: str,
        *,
        duplicate_action: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        doc = await self.plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        plan = StudyPlan(**doc)

        # Idempotent re-confirm
        if plan.status == "active" and plan.confirmed_at:
            return {
                "ok": True,
                "already_confirmed": True,
                "plan": plan.public(),
                "actions": [],
                "effects": {"study_plan_id": plan.id},
            }

        similar = await self.find_similar(
            user_id,
            exam_name=plan.exam_name,
            exam_date=plan.exam_date,
            source_priority_id=plan.source_priority_id,
        )
        if similar and similar.get("id") != plan.id and similar.get("status") == "active" and not force:
            if not duplicate_action or duplicate_action == "open":
                return {
                    "ok": False,
                    "error": "duplicate",
                    "duplicate": similar,
                    "options": ["open", "update", "merge", "replace", "create_anyway"],
                }
            if duplicate_action == "open":
                return {"ok": True, "plan": StudyPlan(**similar).public(), "opened_existing": True}
            if duplicate_action == "replace":
                await self.delete_plan(user_id, similar["id"], soft=True)
            elif duplicate_action == "update":
                plan.id = similar["id"]
            elif duplicate_action == "merge":
                # Keep existing sessions + append new non-overlapping
                existing_starts = {
                    (s.get("starts_at") or "")[:16]
                    for s in (similar.get("sessions") or [])
                }
                merged_sessions = list(similar.get("sessions") or [])
                for s in plan.sessions:
                    if (s.starts_at or "")[:16] not in existing_starts:
                        merged_sessions.append(s.model_dump())
                plan.id = similar["id"]
                plan.sessions = [StudySessionItem(**s) if isinstance(s, dict) else s for s in merged_sessions]
            # create_anyway continues with current plan id

        if not plan.sessions or not plan.preview:
            prev = await self.build_preview(plan)
            if not prev.get("ok"):
                return prev
            plan = StudyPlan(**(await self.plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})))

        actions: List[ProposedAction] = []
        effects: Dict[str, Any] = {
            "study_plan_id": plan.id,
            "calendar_ids": [],
            "reminder_ids": [],
            "session_ids": [],
            "study": {},
            "home_invalidate": True,
        }

        # Persist sessions
        for s in plan.sessions:
            s.plan_id = plan.id
            s.user_id = user_id
            s.status = "planned"
            await self.sessions.update_one(
                {"id": s.id, "user_id": user_id},
                {"$set": s.model_dump()},
                upsert=True,
            )
            effects["session_ids"].append(s.id)

            # Life Graph calendar event
            if self.life_graph:
                try:
                    start = datetime.fromisoformat(s.starts_at.replace("Z", "+00:00"))
                    node = await self.life_graph.create_node(
                        user_id,
                        type="event",
                        label=s.title[:120],
                        description="Sessione piano di studio",
                        attributes={
                            "starts_at": s.starts_at,
                            "start_at": s.starts_at,
                            "ends_at": s.ends_at,
                            "duration_minutes": s.duration_minutes,
                            "kind": "study_session",
                            "session_type": s.session_type,
                            "study_plan_id": plan.id,
                            "study_session_id": s.id,
                            "action_session_id": plan.action_session_id,
                        },
                        origin="action_engine_study",
                    )
                    s.calendar_node_id = node["id"]
                    effects["calendar_ids"].append(node["id"])
                    await self.sessions.update_one(
                        {"id": s.id}, {"$set": {"calendar_node_id": node["id"]}},
                    )
                    actions.append(ProposedAction(
                        id=f"cal_{node['id']}",
                        kind="calendar",
                        label=s.title,
                        detail=s.starts_at,
                        status="done",
                        meta={"node_id": node["id"], "session_id": s.id},
                    ))
                except Exception as e:
                    logger.info("life event skip: %s", type(e).__name__)

        # Reminder day before exam
        if plan.exam_date:
            try:
                exam_at = datetime.fromisoformat(plan.exam_date.replace("Z", "+00:00"))
                rem = {
                    "id": f"rem_{plan.id[:12]}",
                    "user_id": user_id,
                    "title": f"Ripasso: {plan.exam_name}",
                    "status": "open",
                    "due_at": (exam_at - timedelta(days=1)).isoformat(),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "origin": "action_engine_study",
                    "meta": {"kind": "study_review", "study_plan_id": plan.id},
                }
                await self.db.reminders.update_one(
                    {"id": rem["id"], "user_id": user_id},
                    {"$set": rem},
                    upsert=True,
                )
                effects["reminder_ids"].append(rem["id"])
                actions.append(ProposedAction(
                    id=f"rem_{rem['id']}", kind="reminder", label="Promemoria ripasso",
                    status="done", meta={"reminder_id": rem["id"]},
                ))
            except Exception:
                pass

        # Tools
        tools_res = await prepare_study_tools(
            user_id=user_id,
            document_ids=plan.document_ids,
            tools=list(plan.tools),
            db=self.db,
        )
        plan.flashcard_document_ids = tools_res.get("flashcard_document_ids") or []
        plan.interrogami_document_ids = tools_res.get("interrogami_document_ids") or []
        effects["study"] = tools_res
        for a in tools_res.get("actions") or []:
            actions.append(ProposedAction(
                id=f"tool_{a.get('kind')}_{a.get('document_id')}",
                kind="study",
                label=f"{a.get('kind')} ({a.get('status')})",
                status="done" if a.get("status") in ("linked", "generated") else "blocked",
                meta=a,
            ))

        # Brain
        brain = await link_plan_to_brain(
            life_graph=self.life_graph,
            knowledge=self.knowledge,
            db=self.db,
            user_id=user_id,
            plan=plan.model_dump(),
            existing_brain_node_id=plan.brain_node_id,
        )
        plan.brain_node_id = brain.get("brain_node_id") or plan.brain_node_id
        effects["brain"] = brain

        # Google sync
        sync = await sync_plan_sessions(
            db=self.db,
            user_id=user_id,
            plan=plan.model_dump(),
            sessions=[s.model_dump() for s in plan.sessions],
        )
        plan.google_sync = sync
        effects["google_sync"] = sync
        if sync.get("banner"):
            actions.append(ProposedAction(
                id="google_banner",
                kind="calendar",
                label=sync["banner"]["message"],
                status="blocked" if sync["banner"].get("level") == "warning" else "done",
                meta=sync["banner"],
            ))

        # Decision / home hint
        next_hint = f"Piano studio: {plan.exam_name}"
        if plan.sessions:
            try:
                st = datetime.fromisoformat(plan.sessions[0].starts_at.replace("Z", "+00:00"))
                today = datetime.now(timezone.utc).date()
                if st.date() == today:
                    next_hint = f"Sessione oggi {st.strftime('%H:%M')} · {plan.exam_name}"
                else:
                    days = (st.date() - today).days
                    exam_days = 0
                    if plan.exam_date:
                        ed = datetime.fromisoformat(plan.exam_date.replace("Z", "+00:00")).date()
                        exam_days = (ed - today).days
                    next_hint = f"Prossima sessione tra {days}g · esame tra {exam_days}g"
            except Exception:
                pass
        effects["next_focus_hint"] = next_hint

        if self.decisions:
            try:
                dec = await self.decisions.create(
                    user_id,
                    {
                        "title": f"Studio: {plan.exam_name}",
                        "category": "study",
                        "urgency": 4,
                        "importance": 5,
                        "deadline": plan.exam_date,
                        "metadata": {
                            "study_plan_id": plan.id,
                            "action_session_id": plan.action_session_id,
                        },
                    },
                    origin="action_engine_study",
                )
                if dec:
                    effects.setdefault("decision_ids", []).append(dec.get("id"))
            except Exception:
                pass

        plan.status = "active"
        plan.confirmed_at = now_iso()
        plan.updated_at = plan.confirmed_at
        plan.sessions = [
            StudySessionItem(**{
                **s.model_dump(),
                "calendar_node_id": s.calendar_node_id,
            })
            for s in plan.sessions
        ]
        await self.plans.update_one(
            {"id": plan.id, "user_id": user_id},
            {"$set": plan.model_dump()},
            upsert=True,
        )

        # Update action project hint
        if plan.project_id:
            try:
                await self.db.action_projects.update_one(
                    {"id": plan.project_id, "user_id": user_id},
                    {"$set": {
                        "next_focus_hint": next_hint,
                        "study_plan_id": plan.id,
                        "updated_at": now_iso(),
                        "status": "active",
                    }},
                )
            except Exception:
                pass

        return {
            "ok": True,
            "plan": plan.public(),
            "actions": [a.model_dump() for a in actions],
            "effects": effects,
            "next_focus_hint": next_hint,
        }

    async def get_plan(self, user_id: str, plan_id: str) -> Optional[Dict[str, Any]]:
        doc = await self.plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return None
        return StudyPlan(**doc).public()

    async def list_plans(self, user_id: str, *, status: Optional[str] = None) -> List[dict]:
        q: Dict[str, Any] = {"user_id": user_id}
        if status:
            q["status"] = status
        cur = self.plans.find(q, {"_id": 0}).sort("updated_at", -1).limit(50)
        items = await cur.to_list(50)
        return [StudyPlan(**d).public() for d in items]

    async def session_action(
        self, user_id: str, session_id: str, action: str, *, snooze_minutes: int = 60,
    ) -> Dict[str, Any]:
        doc = await self.sessions.find_one({"id": session_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        s = StudySessionItem(**doc)
        if action == "start":
            s.status = "in_progress"
        elif action == "complete":
            s.status = "completed"
            s.completed_at = now_iso()
        elif action == "snooze":
            s.status = "snoozed"
            start = datetime.fromisoformat(s.starts_at.replace("Z", "+00:00"))
            new_start = start + timedelta(minutes=snooze_minutes)
            dur = s.duration_minutes or 60
            s.starts_at = new_start.isoformat()
            s.ends_at = (new_start + timedelta(minutes=dur)).isoformat()
            s.snoozed_until = s.starts_at
        elif action == "skip":
            s.status = "skipped"
        else:
            return {"ok": False, "error": "invalid_action"}
        s.updated_at = now_iso()
        await self.sessions.update_one({"id": session_id}, {"$set": s.model_dump()})
        # Update plan progress
        await self._refresh_progress(user_id, s.plan_id)
        google_result = None
        if action == "snooze" and s.google_event_id:
            google_result = await update_session_google_event(
                self.db, user_id, s.model_dump(),
            )
        out: Dict[str, Any] = {"ok": True, "session": s.model_dump()}
        if google_result is not None:
            out["google_sync"] = google_result
        return out

    async def _refresh_progress(self, user_id: str, plan_id: str) -> None:
        sessions = await self.sessions.find(
            {"plan_id": plan_id, "user_id": user_id}, {"_id": 0},
        ).to_list(100)
        completed = sum(1 for s in sessions if s.get("status") == "completed")
        total = len(sessions)
        status = "completed" if total and completed == total else None
        patch: Dict[str, Any] = {
            "sessions": sessions,
            "progress": {"completed_sessions": completed, "total_sessions": total},
            "updated_at": now_iso(),
        }
        if status:
            patch["status"] = status
        await self.plans.update_one({"id": plan_id, "user_id": user_id}, {"$set": patch})

    async def update_plan(self, user_id: str, plan_id: str, patch: dict) -> Dict[str, Any]:
        doc = await self.plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        allowed = {
            "daily_minutes", "available_days", "preferred_ranges", "intensity",
            "document_ids", "calendar_sync", "tools", "status", "exam_date", "exam_name",
        }
        clean = {k: v for k, v in patch.items() if k in allowed}
        if clean.get("status") == "paused" and doc.get("status") == "active":
            pass
        # Regenerate future sessions only (not past/completed)
        regenerate = bool(patch.get("regenerate_future"))
        clean["updated_at"] = now_iso()
        await self.plans.update_one({"id": plan_id, "user_id": user_id}, {"$set": clean})
        if regenerate:
            plan = StudyPlan(**{**doc, **clean})
            # Keep completed sessions
            kept = [
                StudySessionItem(**s) if isinstance(s, dict) else s
                for s in plan.sessions
                if (isinstance(s, dict) and s.get("status") in ("completed", "skipped"))
                or (not isinstance(s, dict) and s.status in ("completed", "skipped"))
            ]
            prev = await self.build_preview(plan)
            if prev.get("ok"):
                plan = StudyPlan(**(await self.plans.find_one({"id": plan_id}, {"_id": 0})))
                future = [s for s in plan.sessions if s.status == "planned"]
                plan.sessions = kept + future
                await self.plans.update_one({"id": plan_id}, {"$set": {"sessions": [s.model_dump() for s in plan.sessions]}})
                # Replace planned DB sessions
                await self.sessions.delete_many({
                    "plan_id": plan_id, "user_id": user_id, "status": "planned",
                })
                for s in future:
                    await self.sessions.update_one(
                        {"id": s.id}, {"$set": s.model_dump()}, upsert=True,
                    )
        return {"ok": True, "plan": await self.get_plan(user_id, plan_id)}

    async def delete_plan(self, user_id: str, plan_id: str, *, soft: bool = True) -> Dict[str, Any]:
        doc = await self.plans.find_one({"id": plan_id, "user_id": user_id}, {"_id": 0})
        if not doc:
            return {"ok": False, "error": "not_found"}
        google_cleanup = await delete_plan_google_events(self.db, user_id, plan_id)
        if soft:
            await self.plans.update_one(
                {"id": plan_id},
                {"$set": {"status": "cancelled", "cancelled_at": now_iso(), "updated_at": now_iso()}},
            )
            await self.sessions.update_many(
                {"plan_id": plan_id, "user_id": user_id, "status": {"$in": ["planned", "in_progress", "snoozed"]}},
                {"$set": {"status": "cancelled", "updated_at": now_iso()}},
            )
        else:
            await self.plans.delete_one({"id": plan_id, "user_id": user_id})
            await self.sessions.delete_many({"plan_id": plan_id, "user_id": user_id})
        return {"ok": True, "google_sync": google_cleanup}

    async def google_status(self, user_id: str) -> Dict[str, Any]:
        connected = await is_google_connected(self.db, user_id)
        return {
            "connected": connected,
            "banner": None if connected else {
                "level": "info",
                "message": "Google Calendar non collegato",
            },
        }
