"""Home V2 service — aggregate, rank, persist, act."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from home.adapters import gather_all
from home.models import (
    RANKING_VERSION,
    ConnectionWarning,
    CurrentSituation,
    ExplanationBlock,
    HomeItem,
    HomeResponse,
    InsightItem,
    PriorityGroup,
    SituationIndicator,
    now_iso,
)
from home.ranking import dedupe_items, persist_payload, rank_items

logger = logging.getLogger("ora.home")

PRIORITY_LABELS = {
    "critical": "Critico",
    "today": "Oggi",
    "this_week": "Questa settimana",
    "waiting": "In attesa",
    "later": "Più avanti",
}
PRIORITY_ORDER = ["critical", "today", "this_week", "waiting", "later"]


class HomeService:
    def __init__(self, db):
        self.db = db

    @property
    def state_col(self):
        return self.db.home_item_state

    @property
    def snap_col(self):
        return self.db.home_snapshots

    @property
    def insight_col(self):
        return self.db.home_insights

    async def ensure_indexes(self) -> None:
        await self.state_col.create_index([("user_id", 1), ("item_id", 1)], unique=True)
        await self.snap_col.create_index([("user_id", 1), ("generated_at", -1)])
        await self.insight_col.create_index([("user_id", 1), ("dedupe_key", 1)], unique=True)
        await self.insight_col.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])

    async def _load_state_map(self, user_id: str) -> Dict[str, dict]:
        cur = self.state_col.find({"user_id": user_id}, {"_id": 0})
        rows = await cur.to_list(500)
        return {r["item_id"]: r for r in rows}

    def _apply_state(self, items: List[HomeItem], state: Dict[str, dict], now: datetime) -> List[HomeItem]:
        out: List[HomeItem] = []
        for it in items:
            st = state.get(it.id) or {}
            if st.get("status") in ("ignored", "completed"):
                continue
            snooze_until = st.get("snooze_until")
            if snooze_until:
                try:
                    su = datetime.fromisoformat(str(snooze_until).replace("Z", "+00:00"))
                    if su.tzinfo is None:
                        su = su.replace(tzinfo=timezone.utc)
                    if su > now:
                        it = it.model_copy(deep=True)
                        it.status = "waiting"
                        it.meta = {**it.meta, "snoozed_until": snooze_until}
                except Exception:
                    pass
            if st.get("priority_override"):
                it = it.model_copy(deep=True)
                it.priority = st["priority_override"]
                it.meta = {**it.meta, "priority_corrected": True}
            out.append(it)
        return out

    async def build_home(self, user_id: str) -> HomeResponse:
        now = datetime.now(timezone.utc)
        raw_items, warnings, gcal = await gather_all(self.db, user_id)
        state = await self._load_state_map(user_id)
        filtered = self._apply_state(raw_items, state, now)
        ranked = rank_items(filtered, now=now)
        ranked = dedupe_items(ranked)

        # Persist snapshot (including scores)
        snap = {
            "user_id": user_id,
            "generated_at": now.isoformat(),
            "ranking_version": RANKING_VERSION,
            "items": persist_payload(ranked),
        }
        try:
            await self.snap_col.insert_one(snap)
        except Exception as e:
            logger.warning("home snapshot persist failed: %s", type(e).__name__)

        # Split resume vs focus candidates
        resume_candidates = [i for i in ranked if i.type == "resume"]
        focus_pool = [i for i in ranked if i.type != "resume" and i.status != "waiting"]
        # waiting snoozed items still appear in priorities under waiting
        primary = focus_pool[0] if focus_pool else None

        explanation = None
        if primary:
            missing = list(primary.meta.get("missing_fields") or [])
            if primary.confidence is not None and primary.confidence < 0.55:
                missing.append("confidenza_bassa")
            explanation = ExplanationBlock(
                summary=primary.reason_summary or "Priorità determinata da regole ORA",
                factors=primary.reason_factors,
                sources=[{
                    "type": primary.source_type,
                    "id": primary.source_id,
                    "title": primary.title,
                }],
                confidence=primary.confidence,
                missing_data=missing,
                ranking_version=RANKING_VERSION,
                item_id=primary.id,
            )

        situation = await self._build_situation(user_id, ranked, now)
        priorities = self._group_priorities(ranked, primary.id if primary else None)
        insights = await self._build_insights(user_id, ranked, gcal, now)
        resume = None
        if resume_candidates:
            # pick most recently updated
            resume_candidates.sort(key=lambda x: x.updated_at or "", reverse=True)
            resume = resume_candidates[0].to_public()

        # Google: connected → no promo; disconnected → compact banner flag
        google_block = {
            "connected": bool(gcal.get("connected")),
            "show_banner": not bool(gcal.get("connected")),
            "last_sync_at": gcal.get("last_sync_at"),
            "instance_id": (gcal.get("instance") or {}).get("id"),
        }
        # Dismissed banner?
        banner_state = state.get("__google_banner__") or {}
        if banner_state.get("status") == "dismissed":
            google_block["show_banner"] = False

        partial = any(w.code.startswith("source_error_") for w in warnings)

        return HomeResponse(
            primary_focus=primary.to_public() if primary else None,
            explanation=explanation,
            current_situation=situation,
            priorities=priorities,
            insights=insights,
            resume_item=resume,
            connection_warnings=warnings,
            google_calendar=google_block,
            generated_at=now.isoformat(),
            ranking_version=RANKING_VERSION,
            partial=partial,
        )

    async def _build_situation(self, user_id: str, items: List[HomeItem], now: datetime) -> CurrentSituation:
        indicators: List[SituationIndicator] = []
        open_actions = sum(1 for i in items if i.type != "resume" and i.status == "open")
        needs_review = sum(1 for i in items if i.type in ("needs_review", "verify"))
        overdue = sum(1 for i in items if i.urgency == "overdue")
        today_n = sum(1 for i in items if i.priority in ("critical", "today"))

        free_window = None
        next_commitment = None
        try:
            from deps import get_daily_summary_service
            daily = await get_daily_summary_service().today(user_id, tz_name="Europe/Rome")
            d = daily.to_dict() if hasattr(daily, "to_dict") else daily
            slots = d.get("free_slots") or []
            for s in slots:
                if (s.get("duration_min") or 0) >= 30:
                    free_window = f"{s.get('start', '')}–{s.get('end', '')}"
                    break
            events = d.get("events") or []
            if events:
                next_commitment = events[0].get("title") or events[0].get("label")
            if d.get("total_events") is not None:
                indicators.append(SituationIndicator(
                    id="events_today",
                    label="Impegni oggi",
                    value=str(d.get("total_events")),
                    tone="info",
                ))
        except Exception:
            pass

        indicators.append(SituationIndicator(
            id="open_actions", label="Azioni aperte", value=str(open_actions),
            tone="warning" if open_actions > 5 else "default",
        ))
        if needs_review:
            indicators.append(SituationIndicator(
                id="needs_review", label="Da verificare", value=str(needs_review), tone="warning",
            ))
        if overdue:
            indicators.append(SituationIndicator(
                id="overdue", label="In ritardo", value=str(overdue), tone="warning",
            ))
        if today_n and len(indicators) < 4:
            indicators.append(SituationIndicator(
                id="today", label="Priorità oggi", value=str(today_n), tone="info",
            ))
        if free_window and len(indicators) < 4:
            indicators.append(SituationIndicator(
                id="free", label="Finestra libera", value=free_window, tone="success",
            ))

        return CurrentSituation(
            indicators=indicators[:4],
            free_window=free_window,
            next_commitment=next_commitment,
            open_actions_count=open_actions,
            needs_review_count=needs_review,
        )

    def _group_priorities(self, items: List[HomeItem], primary_id: Optional[str]) -> List[PriorityGroup]:
        groups: Dict[str, List[Dict[str, Any]]] = {k: [] for k in PRIORITY_ORDER}
        for it in items:
            if it.type == "resume":
                continue
            if primary_id and it.id == primary_id:
                continue
            groups[it.priority].append(it.to_public())
        out: List[PriorityGroup] = []
        for key in PRIORITY_ORDER:
            if groups[key]:
                out.append(PriorityGroup(key=key, label=PRIORITY_LABELS[key], items=groups[key]))  # type: ignore[arg-type]
        return out

    async def _build_insights(
        self,
        user_id: str,
        items: List[HomeItem],
        gcal: dict,
        now: datetime,
    ) -> List[InsightItem]:
        candidates: List[InsightItem] = []

        overdue_bills = [i for i in items if i.type in ("bill", "payment") and i.urgency == "overdue"]
        if overdue_bills:
            b = overdue_bills[0]
            candidates.append(InsightItem(
                id=f"ins_overdue_{b.source_id}",
                text=f"Hai una scadenza in ritardo: {b.title}",
                source=b.source_type,
                action=b.actions[0] if b.actions else None,
                status="active",
                created_at=now.isoformat(),
                valid_until=(now + timedelta(days=2)).isoformat(),
                dedupe_key=f"overdue_bill:{b.source_id}",
            ))

        reviews = [i for i in items if i.type == "needs_review"]
        if reviews and len(candidates) < 2:
            r = reviews[0]
            candidates.append(InsightItem(
                id=f"ins_review_{r.source_id}",
                text=f"Documento da verificare: {r.title}",
                source=r.source_type,
                action=r.actions[0] if r.actions else None,
                status="active",
                created_at=now.isoformat(),
                valid_until=(now + timedelta(days=3)).isoformat(),
                dedupe_key=f"review:{r.source_id}",
            ))

        free_study = [i for i in items if i.type == "study" and i.meta.get("incomplete_study")]
        if free_study and len(candidates) < 2:
            s = free_study[0]
            candidates.append(InsightItem(
                id=f"ins_study_{s.source_id}",
                text=f"Puoi riprendere lo studio: {s.title}",
                source="study",
                action=s.actions[0] if s.actions else None,
                status="active",
                created_at=now.isoformat(),
                valid_until=(now + timedelta(days=1)).isoformat(),
                dedupe_key=f"study_nudge:{s.source_id}",
            ))

        # Persist + filter ignored/read
        out: List[InsightItem] = []
        for c in candidates[:2]:
            existing = await self.insight_col.find_one(
                {"user_id": user_id, "dedupe_key": c.dedupe_key}, {"_id": 0},
            )
            if existing and existing.get("status") in ("ignored", "read"):
                continue
            if not existing:
                try:
                    await self.insight_col.update_one(
                        {"user_id": user_id, "dedupe_key": c.dedupe_key},
                        {"$setOnInsert": {**c.model_dump(), "user_id": user_id}},
                        upsert=True,
                    )
                except Exception:
                    pass
            else:
                c.status = existing.get("status") or "active"
                c.id = existing.get("id") or c.id
            if c.status == "active":
                out.append(c)
        return out[:2]

    async def apply_action(
        self,
        user_id: str,
        *,
        item_id: str,
        action: str,
        until: Optional[str] = None,
        reason: Optional[str] = None,
        priority: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        if action == "dismiss_banner":
            await self.state_col.update_one(
                {"user_id": user_id, "item_id": "__google_banner__"},
                {"$set": {"status": "dismissed", "updated_at": now.isoformat()}},
                upsert=True,
            )
            return {"ok": True, "action": action}

        if action == "mark_insight_read":
            await self.insight_col.update_one(
                {"user_id": user_id, "$or": [{"id": item_id}, {"dedupe_key": item_id}]},
                {"$set": {"status": "read", "updated_at": now.isoformat()}},
            )
            return {"ok": True, "action": action}

        if action == "ignore" and item_id.startswith("ins_"):
            await self.insight_col.update_one(
                {"user_id": user_id, "$or": [{"id": item_id}, {"dedupe_key": item_id}]},
                {"$set": {"status": "ignored", "updated_at": now.isoformat(), "reason": reason}},
            )
            return {"ok": True, "action": action}

        patch: Dict[str, Any] = {"updated_at": now.isoformat(), "last_action": action}
        if reason:
            patch["reason"] = reason
        if note:
            patch["note"] = note

        if action == "complete":
            patch["status"] = "completed"
            await self._mirror_complete(user_id, item_id)
        elif action == "ignore":
            patch["status"] = "ignored"
        elif action == "snooze":
            if until:
                patch["snooze_until"] = until
            else:
                patch["snooze_until"] = (now + timedelta(hours=4)).isoformat()
            patch["status"] = "snoozed"
        elif action == "correct":
            if priority:
                patch["priority_override"] = priority
            patch["status"] = "active"
        elif action in ("open", "resume"):
            patch["status"] = "active"
            patch["last_opened_at"] = now.isoformat()
        else:
            patch["status"] = "active"

        await self.state_col.update_one(
            {"user_id": user_id, "item_id": item_id},
            {"$set": patch, "$setOnInsert": {"created_at": now.isoformat()}},
            upsert=True,
        )
        return {"ok": True, "action": action, "item_id": item_id}

    async def _mirror_complete(self, user_id: str, item_id: str) -> None:
        """Best-effort sync completion to source documents/decisions/tasks."""
        # Find last snapshot item
        snap = await self.snap_col.find_one({"user_id": user_id}, sort=[("generated_at", -1)])
        if not snap:
            return
        item = next((i for i in (snap.get("items") or []) if i.get("id") == item_id), None)
        if not item:
            return
        st = item.get("source_type")
        sid = item.get("source_id")
        try:
            if st == "decision" and sid:
                await self.db.decisions.update_one(
                    {"user_id": user_id, "id": sid},
                    {"$set": {"status": "completed", "updated_at": now_iso()}},
                )
            elif st == "task" and sid:
                await self.db.tasks.update_one(
                    {"user_id": user_id, "id": sid},
                    {"$set": {"status": "completed", "updated_at": now_iso()}},
                )
            elif st in ("document", "document_action", "study", "admin", "event_candidate") and sid:
                # Mark admin completed when bill/payment
                if item.get("type") in ("bill", "payment"):
                    await self.db.documents.update_one(
                        {"user_id": user_id, "id": sid},
                        {"$set": {"admin_analysis.completed": True, "updated_at": now_iso()}},
                    )
                action_id = (item.get("meta") or {}).get("action_id")
                if action_id:
                    doc = await self.db.documents.find_one({"user_id": user_id, "id": sid})
                    if doc:
                        actions = list(doc.get("generic_actions") or [])
                        for a in actions:
                            if a.get("id") == action_id:
                                a["completed"] = True
                        await self.db.documents.update_one(
                            {"user_id": user_id, "id": sid},
                            {"$set": {"generic_actions": actions, "updated_at": now_iso()}},
                        )
        except Exception as e:
            logger.warning("mirror complete failed: %s", type(e).__name__)

    async def full_situation(self, user_id: str) -> Dict[str, Any]:
        home = await self.build_home(user_id)
        return {
            "generated_at": home.generated_at,
            "ranking_version": home.ranking_version,
            "current_situation": home.current_situation.model_dump(),
            "priorities": [p.model_dump() for p in home.priorities],
            "primary_focus": home.primary_focus,
            "connection_warnings": [w.model_dump() for w in home.connection_warnings],
            "google_calendar": home.google_calendar,
        }
