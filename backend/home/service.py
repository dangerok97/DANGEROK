"""Home V2 service — aggregate, rank, persist, act."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from home.adapters import gather_all
from home.goal_context import (
    attach_goal_context,
    build_goal_insight_candidates,
    enrich_focus_with_goal,
    enrich_resume_with_goal,
    load_active_goals,
    proposal_from_idle_goals,
)
from home.models import (
    PRESENTATION_VERSION,
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
from home.presentation import (
    aggregate_presentation,
    enforce_one_card_per_goal,
)
from home.ranking import dedupe_items, persist_payload, rank_items
from home.work_admission import admit

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
        # Knowledge acquisition must not create work by itself.
        #
        # Everything ORA read is already where reading belongs: the profile,
        # Vita, Documenti, the dates it will watch. Whether any of it also
        # belongs in somebody's day is a separate question with eight possible
        # answers, and “because a document was processed” is not one of them.
        raw_items = admit(raw_items, now=now)
        # Goal context layer (flag-gated) — no Goal UX / no Goals section
        goals = await load_active_goals(self.db, user_id)
        if goals:
            raw_items = attach_goal_context(raw_items, goals, now=now)
        state = await self._load_state_map(user_id)
        filtered = self._apply_state(raw_items, state, now)
        ranked = rank_items(filtered, now=now)
        ranked = dedupe_items(ranked)

        # Load proactive suggestions early so presentation can incorporate them
        ora_raw = await self._load_ora_ti_consiglia(user_id)

        # Presentation Aggregation Layer — ONE card per Goal (non-destructive)
        ranked, ora_ti_consiglia, pres_stats = aggregate_presentation(
            ranked, now=now, suggestions=ora_raw,
        )
        ranked = enforce_one_card_per_goal(ranked)

        # Persist snapshot (including scores + presentation meta)
        snap = {
            "user_id": user_id,
            "generated_at": now.isoformat(),
            "ranking_version": RANKING_VERSION,
            "presentation_version": PRESENTATION_VERSION,
            "presentation_stats": pres_stats,
            "items": persist_payload(ranked),
        }
        try:
            await self.snap_col.insert_one(snap)
        except Exception as e:
            logger.warning("home snapshot persist failed: %s", type(e).__name__)

        # Split resume vs focus — presentation cards are never type=resume
        # (conversation resumes are folded into Goal card actions)
        resume_candidates = [i for i in ranked if i.type == "resume"]
        focus_pool = [i for i in ranked if i.type != "resume" and i.status != "waiting"]
        # Expired/superseded plan shells cannot be Daily Focus when any active
        # actionable item exists (generic temporal ownership).
        from home.temporal import (
            TEMPORAL_EXPIRED_RECOVERABLE,
            TEMPORAL_EXPIRED_STALE,
            TEMPORAL_SUPERSEDED,
            public_rank_trace_row,
        )

        has_canonical_actionable = any(
            (i.meta or {}).get("canonical_execution")
            and (i.meta or {}).get("actionable_now")
            for i in focus_pool
        )

        def _focus_eligible(it) -> bool:
            st = (it.meta or {}).get("temporal_state")
            if st in (TEMPORAL_EXPIRED_STALE, TEMPORAL_SUPERSEDED):
                return False
            # Knowing something is not a reason to open the day with it.
            #
            # An item that only reports what ORA has become able to do answers
            # “what can I accomplish by tapping this right now?” with nothing.
            # It can live further down the page; the top of Home is for what
            # matters now, and a quiet Home is a legitimate answer.
            if (it.meta or {}).get("knowledge_only"):
                return False
            # Recovery leftovers must not displace a current canonical plan
            if has_canonical_actionable and st == TEMPORAL_EXPIRED_RECOVERABLE:
                return False
            return True

        eligible = [i for i in focus_pool if _focus_eligible(i)]
        # The fallback exists so a stale-but-real item can still open the day
        # rather than leaving it empty. It must not resurrect something that was
        # excluded for *not being about anything to do*: a quiet Home is a
        # legitimate answer, and inventing a hero out of "here is what I can now
        # do" is the thing this rule removes.
        fallback_pool = [i for i in focus_pool if not (i.meta or {}).get("knowledge_only")]
        primary = (eligible[0] if eligible else None) or (
            fallback_pool[0] if fallback_pool else None
        )
        # Prefer canonical actionable when top eligible is still a weak stale leftover
        if primary and (primary.meta or {}).get("temporal_state") in (
            TEMPORAL_EXPIRED_STALE,
            TEMPORAL_SUPERSEDED,
            TEMPORAL_EXPIRED_RECOVERABLE,
        ):
            for cand in eligible:
                if (cand.meta or {}).get("canonical_execution") and (
                    cand.meta or {}
                ).get("actionable_now"):
                    primary = cand
                    break
        def _pick_canonical_focus(cands: List[HomeItem]) -> Optional[HomeItem]:
            """Prefer Life OS plan shells over plan-item decisions; then freshest."""
            actionable = [
                c
                for c in cands
                if (c.meta or {}).get("canonical_execution")
                and (c.meta or {}).get("actionable_now")
                and (c.meta or {}).get("temporal_state")
                not in (TEMPORAL_EXPIRED_STALE, TEMPORAL_SUPERSEDED)
            ]
            if not actionable:
                return None
            shells = [
                c
                for c in actionable
                if c.source_type == "life_os_plan"
                and c.type != "resume"
                and not (c.meta or {}).get("plan_item_id")
            ]
            pool = shells or [c for c in actionable if c.type != "resume"] or actionable
            top = max((c.score or 0) for c in pool)
            near = [c for c in pool if abs((c.score or 0) - top) <= 2.0]
            near.sort(
                key=lambda c: (
                    c.updated_at or (c.meta or {}).get("freshness") or ""
                ),
                reverse=True,
            )
            return near[0] if near else pool[0]

        if primary and has_canonical_actionable and not (primary.meta or {}).get(
            "canonical_execution"
        ):
            # Do not let legacy/recovery/reminders outrank current canonical work
            # unless primary is a true overdue debt (bill/payment).
            if primary.type not in ("bill", "payment"):
                picked = _pick_canonical_focus(eligible)
                if picked:
                    primary = picked
        elif (
            primary
            and (primary.meta or {}).get("canonical_execution")
            and has_canonical_actionable
        ):
            picked = _pick_canonical_focus(eligible)
            if picked:
                primary = picked

        # Draft-only: promote resume into Adesso so Home is not empty
        promoted_resume_id: Optional[str] = None
        if primary is None and resume_candidates:
            resume_candidates.sort(key=lambda x: x.updated_at or "", reverse=True)
            promoted = resume_candidates[0]
            primary = enrich_focus_with_goal(enrich_resume_with_goal(promoted)) or promoted
            promoted_resume_id = promoted.id

        # Goals exist but no actionable artifact / resume → useful proposal
        if primary is None and goals:
            covered = {r.goal_id for r in resume_candidates if r.goal_id}
            covered |= {i.goal_id for i in ranked if i.goal_id}
            idle = proposal_from_idle_goals(goals, now=now)
            if idle and idle.goal_id and idle.goal_id in covered:
                idle = None
            if idle:
                idle_ranked = rank_items([idle], now=now)
                primary = idle_ranked[0] if idle_ranked else idle
                ranked = enforce_one_card_per_goal(dedupe_items(ranked + [primary]))

        if primary and not promoted_resume_id:
            primary = enrich_focus_with_goal(primary) or primary

        explanation = None
        if primary:
            missing = list(primary.meta.get("missing_fields") or [])
            if primary.confidence is not None and primary.confidence < 0.55:
                missing.append("confidenza_bassa")
            sources = list(primary.meta.get("source_refs") or [])
            if not sources:
                sources = [{
                    "type": primary.source_type,
                    "id": primary.source_id,
                    "title": primary.title,
                }]
            explanation = ExplanationBlock(
                summary=primary.reason_summary or "Priorità determinata da regole ORA",
                factors=primary.reason_factors,
                sources=[{
                    "type": s.get("type") or "",
                    "id": s.get("id") or "",
                    "title": s.get("title") or "",
                } for s in sources[:6]],
                confidence=primary.confidence,
                missing_data=missing,
                ranking_version=RANKING_VERSION,
                item_id=primary.id,
            )

        situation = await self._build_situation(user_id, ranked, now)
        priorities = self._group_priorities(ranked, primary.id if primary else None, primary_goal_id=primary.goal_id if primary else None)
        insights = await self._build_insights(user_id, ranked, gcal, now, goals=goals)

        # Filter ORA TI CONSIGLIA: drop anything that duplicates primary Goal card
        primary_gid = primary.goal_id if primary else None
        if primary_gid:
            ora_ti_consiglia = [
                s for s in ora_ti_consiglia
                if s.get("goal_id") != primary_gid
            ]
        # Also drop suggestions whose study_plan/travel already is the primary source
        if primary:
            plan_id = (primary.meta or {}).get("study_plan_id")
            travel_id = (primary.meta or {}).get("travel_project_id")
            ora_ti_consiglia = [
                s for s in ora_ti_consiglia
                if not (
                    (plan_id and s.get("study_plan_id") == plan_id)
                    or (travel_id and s.get("travel_project_id") == travel_id)
                )
            ]

        resume = None
        if resume_candidates:
            # Prefer Life OS plan resumes (durable goal) over bare conversation_session.
            def _resume_rank(r) -> tuple:
                life = 1 if (
                    r.source_type == "life_os_plan"
                    or (r.meta or {}).get("resume_kind") == "life_os_plan"
                ) else 0
                return (life, r.updated_at or "")

            resume_candidates.sort(key=_resume_rank, reverse=True)
            primary_gid = primary.goal_id if primary else None
            resume_pick = next(
                (
                    r for r in resume_candidates
                    if r.id != (primary.id if primary else None)
                    and r.id != promoted_resume_id
                    and (not primary_gid or r.goal_id != primary_gid)
                ),
                None,
            )
            if resume_pick:
                resume_item = enrich_resume_with_goal(resume_pick)
                resume = resume_item.to_public() if resume_item else None

        # Google: connected → no promo; disconnected → compact banner flag
        google_block = {
            "connected": bool(gcal.get("connected")),
            "show_banner": not bool(gcal.get("connected")),
            "last_sync_at": gcal.get("last_sync_at"),
            "instance_id": (gcal.get("instance") or {}).get("id"),
        }
        banner_state = state.get("__google_banner__") or {}
        if banner_state.get("status") == "dismissed":
            google_block["show_banner"] = False

        partial = any(w.code.startswith("source_error_") for w in warnings)

        # DEV ranking trace (no PII dumps) — HOME_RANK_TRACE=1 or DEV=1
        import os as _os

        rank_trace = None
        if (_os.environ.get("HOME_RANK_TRACE") or _os.environ.get("DEV") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        ):
            rank_trace = []
            for it in ranked[:24]:
                row = public_rank_trace_row(it)
                row["selected"] = bool(primary and it.id == primary.id)
                rank_trace.append(row)

        # Contextual visual for the hero. Costs one indexed lookup and never
        # waits on a provider: `attach_visuals` schedules generation in the
        # background and returns whatever state exists right now, so Home
        # renders at the same speed whether or not a picture exists yet.
        # What ORA is waiting for. Read straight from the questions themselves
        # rather than inferred from a suggestion's delivery mode: a blocker is
        # a fact about the work, not a judgement about what to surface. Soft:
        # Home must still render if this read fails.
        open_questions: List[Dict[str, Any]] = []
        try:
            from waiting.service import get_waiting_service

            open_questions = await get_waiting_service(self.db).list_open(user_id, limit=5)
        except Exception as e:
            logger.info("open questions read soft-fail: %s", type(e).__name__)

        # V3.7 — whatever the surfacing decision already settled. Read only:
        # Home never decides what to show and never asks a model to decide,
        # so a slow provider can no more delay this page than an empty result
        # can break it.
        opportunities: List[Dict[str, Any]] = []
        try:
            from opportunities.surfacing import SurfacingService

            opportunities = await SurfacingService(self.db).for_home(user_id)
        except Exception as e:
            logger.info("opportunity surfacing read soft-fail: %s", type(e).__name__)

        primary_public = primary.to_public() if primary else None
        if primary_public:
            try:
                primary_public = await attach_visual(self.db, user_id, primary_public)
            except Exception as e:
                logger.info("hero visual attach soft-fail: %s", type(e).__name__)

        return HomeResponse(
            primary_focus=primary_public,
            explanation=explanation,
            current_situation=situation,
            priorities=priorities,
            insights=insights,
            opportunities=opportunities,
            resume_item=resume,
            ora_ti_consiglia=ora_ti_consiglia[:3],
            open_questions=open_questions,
            connection_warnings=warnings,
            google_calendar=google_block,
            generated_at=now.isoformat(),
            ranking_version=RANKING_VERSION,
            partial=partial,
            dev_rank_trace=rank_trace,
        )

    async def _load_ora_ti_consiglia(self, user_id: str) -> List[Dict[str, Any]]:
        """Proactive suggestions for Home — max 3, fail-soft, hidden when empty."""
        try:
            from proactive_engine.service import ProactiveEngineService, proactive_engine_enabled
            if not proactive_engine_enabled():
                return []
            return await ProactiveEngineService(self.db).home_suggestions(user_id, limit=3)
        except Exception as e:
            logger.warning("ora_ti_consiglia load failed: %s", type(e).__name__)
            return []

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

    def _group_priorities(
        self,
        items: List[HomeItem],
        primary_id: Optional[str],
        *,
        primary_goal_id: Optional[str] = None,
    ) -> List[PriorityGroup]:
        """Priorities: max one card per Goal; never re-list primary Goal."""
        groups: Dict[str, List[Dict[str, Any]]] = {k: [] for k in PRIORITY_ORDER}
        seen_goals: set = set()
        if primary_goal_id:
            seen_goals.add(primary_goal_id)
        for it in items:
            if it.type == "resume":
                continue
            if primary_id and it.id == primary_id:
                continue
            # Horizon/priority: suppress expired/superseded plan shells from
            # competing as "future" priorities (still available via Contesti/legacy).
            tstate = (it.meta or {}).get("temporal_state")
            if tstate in ("EXPIRED_STALE", "SUPERSEDED") and (it.meta or {}).get("plan_shell"):
                continue
            if it.goal_id:
                if it.goal_id in seen_goals:
                    continue
                seen_goals.add(it.goal_id)
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
        *,
        goals: Optional[list] = None,
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

        # Goal progress insights (honest, deduped) — fill remaining slots up to 2
        if goals and len(candidates) < 2:
            for gi in build_goal_insight_candidates(items, goals, now=now):
                if len(candidates) >= 2:
                    break
                if any(c.dedupe_key == gi.dedupe_key for c in candidates):
                    continue
                candidates.append(gi)

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


async def attach_visual(db, user_id: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Give one Home item its contextual visual state.

    The image belongs to the *entity*, not to this position on the page: a
    situation already carrying a ready visual reuses it here rather than
    generating a second copy for Home, which is what keeps one meaning to one
    picture across every surface that shows it.
    """
    from visuals.service import VisualService

    ref = None
    if item.get("source_type") and item.get("source_id"):
        ref = f"{item['source_type']}:{item['source_id']}"
    elif item.get("goal_id"):
        ref = f"goal:{item['goal_id']}"
    if not ref:
        return item

    svc = VisualService(db)
    existing = await svc.for_entity(user_id=user_id, entity_ref=ref)
    if existing:
        return {**item, "visual": existing}

    state = await svc.ensure(
        user_id=user_id,
        entity_ref=ref,
        title=item.get("title"),
        summary=item.get("subtitle") or item.get("description"),
    )
    return {**item, "visual": state}
