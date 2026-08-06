"""ProactiveEngineService — observe → candidates → score → gate → persist."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from proactive_engine.accept import handle_accept
from proactive_engine.decision_engine import (
    build_gate_context_from_evidence,
    would_assistant_speak,
)
from proactive_engine.dedupe import collapse_home_list, filter_duplicate_candidates, is_snoozed
from proactive_engine.explainability import build_explain
from proactive_engine.generators import gather_candidates
from proactive_engine.learning import LearningStore
from proactive_engine.lifecycle import apply_lifecycle
from proactive_engine.models import Suggestion
from proactive_engine.notification_policy import evaluate_notification, snooze_until_iso
from proactive_engine.repository import SuggestionRepository
from proactive_engine.scoring import priority_from_score, score_candidate

logger = logging.getLogger("ora.proactive_engine")


def proactive_engine_enabled() -> bool:
    raw = (os.environ.get("PROACTIVE_ENGINE_ENABLED") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


class ProactiveEngineService:
    def __init__(self, db):
        self.db = db
        self.repo = SuggestionRepository(db)
        self.learning = LearningStore(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()
        await self.learning.ensure_indexes()

    async def regenerate(self, user_id: str) -> Dict[str, Any]:
        if not proactive_engine_enabled():
            return {
                "ok": True,
                "enabled": False,
                "created": 0,
                "rejected": 0,
                "suggestions": [],
            }
        now = datetime.now(timezone.utc)
        await apply_lifecycle(self.repo, user_id, now=now)

        candidates = await gather_candidates(self.db, user_id, now=now)
        existing_keys = await self.repo.active_dedupe_keys(user_id)
        candidates = filter_duplicate_candidates(candidates, existing_keys)

        # Observation context for gate
        study_sessions = await self.db.study_sessions.find(
            {"user_id": user_id, "status": {"$in": ["planned", "in_progress"]}},
            {"_id": 0},
        ).to_list(80)
        cal_events = []
        try:
            nodes = await self.db.life_nodes.find(
                {
                    "user_id": user_id,
                    "type": "event",
                    "status": "active",
                    "attributes.starts_at": {
                        "$gte": (now - timedelta(hours=2)).isoformat(),
                        "$lte": (now + timedelta(days=2)).isoformat(),
                    },
                },
                {"_id": 0},
            ).to_list(40)
            for n in nodes:
                attrs = n.get("attributes") or {}
                cal_events.append({
                    "id": n.get("id"),
                    "title": n.get("label"),
                    "starts_at": attrs.get("starts_at"),
                    "ends_at": attrs.get("ends_at"),
                })
        except Exception:
            pass

        since_1h = (now - timedelta(hours=1)).isoformat()
        recent_1h = await self.repo.count_recent(user_id, since_iso=since_1h)
        active = await self.repo.list_for_user(user_id, statuses=["active", "snoozed"], limit=100)

        goals = await self.db.goals.find(
            {"user_id": user_id, "status": {"$nin": ["cancelled", "archived", "merged"]}},
            {"_id": 0},
        ).to_list(80)
        goal_map = {g["id"]: g for g in goals if g.get("id")}

        created: List[Suggestion] = []
        rejected: List[Dict[str, Any]] = []

        for cand in candidates:
            mult = await self.learning.multiplier(user_id, cand.type, cand.source)
            dismiss_rate = await self.learning.dismiss_rate(user_id, cand.type, cand.source)
            goal = goal_map.get(cand.goal_id) if cand.goal_id else None
            brain_ctx = None
            if goal and goal.get("brain_node_id"):
                brain_ctx = {"node_id": goal.get("brain_node_id")}

            score, importance, urgency, factors = score_candidate(
                cand,
                now=now,
                goal=goal,
                brain_ctx=brain_ctx,
                calendar_busy=len(cal_events) >= 4,
                learning_multiplier=mult,
            )

            since_day = (now - timedelta(hours=20)).isoformat()
            recent_dedupe = 1 if await self.repo.has_dedupe_recent(
                user_id, cand.dedupe_key, since_iso=since_day,
            ) else 0

            ctx = build_gate_context_from_evidence(
                now=now,
                active_count=len(active) + len(created),
                recent_same_dedupe=recent_dedupe,
                recent_emitted_1h=recent_1h + len(created),
                calendar_events=cal_events,
                study_sessions=study_sessions,
                learning_dismiss_rate=dismiss_rate,
            )
            gate = would_assistant_speak(
                cand, score=score, confidence=cand.confidence, ctx=ctx,
            )
            if not gate.accept:
                rejected.append({
                    "title": cand.title,
                    "type": cand.type,
                    "reasons": gate.reasons,
                    "notes": gate.notes,
                    "score": score,
                })
                continue

            priority = priority_from_score(score, urgency)
            explain = build_explain(
                reason=cand.reason,
                factors=factors,
                gate_notes=gate.notes,
                would_speak=True,
            )
            sug = Suggestion(
                user_id=user_id,
                title=cand.title,
                description=cand.description,
                reason=cand.reason,
                type=cand.type,
                priority=priority,  # type: ignore[arg-type]
                importance=importance,
                urgency=urgency,
                confidence=cand.confidence,
                score=score,
                source=cand.source,
                goal_id=cand.goal_id,
                project_id=cand.project_id,
                calendar_event=cand.calendar_event,
                document_id=cand.document_id,
                study_plan_id=cand.study_plan_id,
                travel_project_id=cand.travel_project_id,
                action=cand.action,
                status="active",
                factors=factors,
                explain=explain,
                dedupe_key=cand.dedupe_key,
                expires_at=cand.expires_at,
                meta={**(cand.meta or {}), "evidence": cand.evidence},
            )
            # Notification policy — never push now
            note = evaluate_notification(
                sug.model_dump(),
                now=now,
                in_study=ctx.in_study_session,
                in_event=ctx.in_calendar_event,
                driving=ctx.likely_driving,
            )
            sug.meta["notification_policy"] = {
                "send_now": note.send_now,
                "batch": note.batch,
                "reason": note.reason,
                "channel": note.channel,
                "earliest_at": note.earliest_at,
            }
            await self.repo.insert(sug)
            created.append(sug)
            active.append(sug)

        return {
            "ok": True,
            "enabled": True,
            "created": len(created),
            "rejected": len(rejected),
            "rejected_samples": rejected[:12],
            "suggestions": [s.public() for s in created],
        }

    async def list_suggestions(
        self,
        user_id: str,
        *,
        status: Optional[str] = None,
        suggestion_type: Optional[str] = None,
        limit: int = 40,
        regenerate_if_empty: bool = False,
    ) -> Dict[str, Any]:
        if not proactive_engine_enabled():
            return {"suggestions": [], "enabled": False, "count": 0}
        await apply_lifecycle(self.repo, user_id)
        statuses = [status] if status else ["active", "snoozed"]
        items = await self.repo.list_for_user(
            user_id, statuses=statuses, suggestion_type=suggestion_type, limit=limit,
        )
        if regenerate_if_empty and not items:
            await self.regenerate(user_id)
            items = await self.repo.list_for_user(
                user_id, statuses=statuses, suggestion_type=suggestion_type, limit=limit,
            )
        # Filter still-snoozed from "active" listing for home
        now = datetime.now(timezone.utc)
        visible = []
        for s in items:
            if s.status == "snoozed" and is_snoozed(s, now):
                continue
            if s.status == "active" or (s.status == "snoozed" and not is_snoozed(s, now)):
                visible.append(s)
        return {
            "suggestions": [s.public() for s in visible],
            "enabled": True,
            "count": len(visible),
        }

    async def home_suggestions(self, user_id: str, *, limit: int = 3) -> List[Dict[str, Any]]:
        if not proactive_engine_enabled():
            return []
        await apply_lifecycle(self.repo, user_id)
        items = await self.repo.list_for_user(user_id, statuses=["active"], limit=40)
        if not items:
            # Soft regenerate once when Home asks and store empty
            try:
                await self.regenerate(user_id)
                items = await self.repo.list_for_user(user_id, statuses=["active"], limit=40)
            except Exception as e:
                logger.warning("home regenerate failed: %s", type(e).__name__)
                items = []
        top = collapse_home_list(items, limit=limit)
        return [s.public() for s in top]

    async def dismiss(self, user_id: str, suggestion_id: str) -> Dict[str, Any]:
        s = await self.repo.get(user_id, suggestion_id)
        if not s:
            return {"ok": False, "error": "not_found"}
        await self.repo.update_fields(user_id, suggestion_id, {
            "status": "dismissed",
            "dismissed": True,
        })
        await self.learning.record(user_id, s.type, s.source, event="dismissed")
        return {"ok": True, "id": suggestion_id, "status": "dismissed"}

    async def accept(self, user_id: str, suggestion_id: str) -> Dict[str, Any]:
        s = await self.repo.get(user_id, suggestion_id)
        if not s:
            return {"ok": False, "error": "not_found"}
        result = await handle_accept(self.db, user_id, s)
        await self.repo.update_fields(user_id, suggestion_id, {
            "status": "accepted",
            "accepted": True,
            "accept_result": result,
        })
        await self.learning.record(user_id, s.type, s.source, event="accepted")
        return {"ok": True, "id": suggestion_id, "status": "accepted", "result": result}

    async def complete(self, user_id: str, suggestion_id: str) -> Dict[str, Any]:
        s = await self.repo.get(user_id, suggestion_id)
        if not s:
            return {"ok": False, "error": "not_found"}
        await self.repo.update_fields(user_id, suggestion_id, {
            "status": "completed",
            "completed": True,
            "accepted": True,
        })
        await self.learning.record(user_id, s.type, s.source, event="completed")
        return {"ok": True, "id": suggestion_id, "status": "completed"}

    async def snooze(
        self,
        user_id: str,
        suggestion_id: str,
        *,
        preset: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        s = await self.repo.get(user_id, suggestion_id)
        if not s:
            return {"ok": False, "error": "not_found"}
        try:
            when = snooze_until_iso(preset or "1h", custom_until=until)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        await self.repo.update_fields(user_id, suggestion_id, {
            "status": "snoozed",
            "snooze_until": when,
        })
        return {"ok": True, "id": suggestion_id, "status": "snoozed", "snooze_until": when}

    async def explain(self, user_id: str, suggestion_id: str) -> Dict[str, Any]:
        s = await self.repo.get(user_id, suggestion_id)
        if not s:
            return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "id": s.id,
            "reason": s.reason,
            "explain": s.explain.model_dump() if s.explain else None,
            "factors": [f.model_dump() for f in s.factors],
            "priority": s.priority,
            "importance": s.importance,
            "urgency": s.urgency,
            "confidence": s.confidence,
            "notification_policy": (s.meta or {}).get("notification_policy"),
        }

    async def search(
        self,
        user_id: str,
        *,
        q: Optional[str] = None,
        suggestion_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 40,
    ) -> Dict[str, Any]:
        if not proactive_engine_enabled():
            return {"suggestions": [], "enabled": False, "count": 0}
        items = await self.repo.search(
            user_id, q=q, suggestion_type=suggestion_type, status=status, limit=limit,
        )
        return {
            "suggestions": [s.public() for s in items],
            "enabled": True,
            "count": len(items),
        }

    async def notification_preview(self, user_id: str, suggestion_id: str) -> Dict[str, Any]:
        s = await self.repo.get(user_id, suggestion_id)
        if not s:
            return {"ok": False, "error": "not_found"}
        decision = evaluate_notification(s.model_dump())
        return {
            "ok": True,
            "decision": {
                "send_now": decision.send_now,
                "batch": decision.batch,
                "reason": decision.reason,
                "channel": decision.channel,
                "earliest_at": decision.earliest_at,
            },
        }
