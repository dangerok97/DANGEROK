from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


async def load_study_state(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    items: List[HomeItem] = []
    warnings: List[ConnectionWarning] = []

    # Active / paused study plans (post-confirm Home surface)
    try:
        plans = await db.study_plans.find(
            {
                "user_id": user_id,
                "status": {"$in": ["active", "paused", "awaiting_confirmation", "draft"]},
            },
            {"_id": 0},
        ).sort("updated_at", -1).limit(20).to_list(20)
    except Exception:
        plans = []

    for p in plans:
        status = p.get("status")
        exam_name = p.get("exam_name") or "Piano di studio"
        sessions = p.get("sessions") or []
        completed = sum(1 for s in sessions if s.get("status") == "completed")
        total = len(sessions)
        next_s = None
        for s in sorted(sessions, key=lambda x: x.get("starts_at") or ""):
            if s.get("status") in ("planned", "in_progress", "snoozed"):
                next_s = s
                break
        today = datetime.now(timezone.utc).date().isoformat()
        today_count = sum(
            1 for s in sessions
            if (s.get("starts_at") or "")[:10] == today
            and s.get("status") in ("planned", "in_progress")
        )
        skipped_count = sum(1 for s in sessions if s.get("status") == "skipped")
        missed_count = sum(
            1 for s in sessions
            if s.get("status") in ("planned", "in_progress", "snoozed")
            and (s.get("starts_at") or "")[:10]
            and (s.get("starts_at") or "")[:10] < today
        )
        exam_date = p.get("exam_date") or ""
        countdown = None
        if exam_date:
            try:
                ed = datetime.fromisoformat(exam_date.replace("Z", "+00:00")).date()
                countdown = (ed - datetime.now(timezone.utc).date()).days
            except Exception:
                pass
        if status in ("draft", "awaiting_confirmation") and p.get("action_session_id"):
            items.append(HomeItem(
                id=stable_id("study_draft", user_id, p["id"]),
                type="resume",
                subtype="study_plan_draft",
                title=f"Continua piano: {exam_name}",
                description="Bozza salvata — riprendi le domande",
                source_type="action_session",
                source_id=p.get("action_session_id"),
                due_at=exam_date or None,
                status="open",
                created_at=p.get("created_at") or now_iso(),
                updated_at=p.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"study_plan_draft:{p['id']}",
                    "study_plan_id": p["id"],
                    "goal_id": p.get("goal_id"),
                    "resume_kind": "study_plan",
                    "why_now_factors": [
                        {"code": "draft_resume", "label": "Piano in bozza", "weight": 0.9},
                        {"code": "exam_countdown", "label": f"Esame tra {countdown}g", "weight": 0.7}
                        if countdown is not None else {"code": "study", "label": "Studio", "weight": 0.5},
                    ],
                },
            ))
            continue

        desc_parts = []
        if countdown is not None:
            desc_parts.append(f"Esame tra {countdown}g")
        if next_s:
            desc_parts.append(next_s.get("title") or "Prossima sessione")
        if today_count:
            desc_parts.append(f"{today_count} oggi")
        if total:
            desc_parts.append(f"{completed}/{total} sessioni")
        fc = p.get("flashcard_document_ids") or []
        iq = p.get("interrogami_document_ids") or []
        items.append(HomeItem(
            id=stable_id("study_plan", user_id, p["id"]),
            type="study",
            subtype="study_plan",
            title=f"Studio: {exam_name}",
            description=" · ".join(desc_parts) or "Piano di studio attivo",
            source_type="study_plan",
            source_id=p["id"],
            due_at=exam_date or None,
            status="open" if status == "active" else status,
            created_at=p.get("created_at") or now_iso(),
            updated_at=p.get("updated_at") or now_iso(),
            meta={
                "dedupe_key": f"study_plan:{p['id']}",
                "study_plan_id": p["id"],
                "goal_id": p.get("goal_id"),
                "intensity": p.get("intensity"),
                "progress_ratio": (completed / total) if total else 0,
                "next_session": next_s,
                "flashcard_document_ids": fc,
                "interrogami_document_ids": iq,
                "document_ids": p.get("document_ids") or [],
                "exam_countdown_days": countdown,
                "skipped_sessions": skipped_count,
                "missed_sessions": missed_count,
                "session_today": today_count > 0,
                "google_sync": p.get("google_sync") or {},
                "why_now_factors": [
                    f for f in [
                        {"code": "exam_countdown", "label": f"Esame tra {countdown} giorni", "weight": 0.95}
                        if countdown is not None and countdown <= 14 else None,
                        {"code": "session_today", "label": "Sessione oggi", "weight": 0.9}
                        if today_count else None,
                        {"code": "skipped_sessions", "label": f"{skipped_count} sessioni saltate", "weight": 0.85}
                        if skipped_count else None,
                        {"code": "flashcards", "label": "Flashcard pronte", "weight": 0.6}
                        if fc else None,
                        {"code": "plan_active", "label": "Piano attivo", "weight": 0.7},
                    ] if f
                ],
            },
        ))

    cur = db.documents.find(
        {
            "user_id": user_id,
            "deleted": {"$ne": True},
            "$or": [
                {"analysis.macro_category": "education"},
                {"education_analysis": {"$exists": True}},
                {"flashcards.0": {"$exists": True}},
                {"quiz_session": {"$exists": True}},
            ],
        },
        {
            "_id": 0, "id": 1, "display_title": 1, "filename": 1,
            "education_analysis": 1, "analysis": 1, "flashcards": 1,
            "quiz_session": 1, "created_at": 1, "updated_at": 1,
        },
    ).sort("updated_at", -1).limit(30)
    docs = await cur.to_list(30)
    for d in docs:
        edu = d.get("education_analysis") or {}
        analysis = d.get("analysis") or {}
        title = (
            edu.get("suggested_title")
            or edu.get("topic")
            or analysis.get("suggested_title")
            or d.get("display_title")
            or "Materiale di studio"
        )
        cards = d.get("flashcards") or []
        quiz = d.get("quiz_session")
        incomplete_cards = any(c.get("review_status") in ("new", "learning", None) for c in cards) if cards else False
        quiz_incomplete = bool(quiz and quiz.get("status") == "active")

        if not cards and not quiz and not edu:
            continue

        items.append(HomeItem(
            id=stable_id("study", user_id, d["id"]),
            type="study",
            subtype=edu.get("subject") or "education",
            title=title,
            description=edu.get("summary_short") or analysis.get("short_description"),
            source_type="study",
            source_id=d["id"],
            duration_minutes=edu.get("estimated_read_minutes"),
            confidence=edu.get("confidence") or analysis.get("confidence"),
            status="open",
            created_at=d.get("created_at") or now_iso(),
            updated_at=d.get("updated_at") or now_iso(),
            meta={
                "dedupe_key": f"study:{d['id']}",
                "incomplete_study": True,
                "flashcard_incomplete": incomplete_cards,
                "quiz_incomplete": quiz_incomplete,
                "document_id": d["id"],
                "flashcard_count": len(cards),
            },
        ))

        # Resume candidates from incomplete sessions
        resume: Optional[HomeItem] = None
        if quiz_incomplete:
            idx = quiz.get("current_index") or 0
            resume = HomeItem(
                id=stable_id("resume_quiz", user_id, d["id"]),
                type="resume",
                subtype="quiz",
                title=f"Continua interrogazione: {title}",
                description=f"Domanda {idx + 1}",
                source_type="quiz_session",
                source_id=d["id"],
                status="open",
                created_at=quiz.get("created_at") or now_iso(),
                updated_at=quiz.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"resume:{d['id']}:quiz",
                    "document_id": d["id"],
                    "resume_kind": "quiz",
                    "quiz_incomplete": True,
                },
            )
        elif incomplete_cards:
            unknown = sum(1 for c in cards if c.get("review_status") != "known")
            resume = HomeItem(
                id=stable_id("resume_fc", user_id, d["id"]),
                type="resume",
                subtype="flashcards",
                title=f"Continua flashcard: {title}",
                description=f"{unknown} carte da ripassare",
                source_type="study",
                source_id=d["id"],
                status="open",
                created_at=d.get("created_at") or now_iso(),
                updated_at=d.get("updated_at") or now_iso(),
                meta={
                    "dedupe_key": f"resume:{d['id']}:flashcards",
                    "document_id": d["id"],
                    "resume_kind": "flashcards",
                    "flashcard_incomplete": True,
                },
            )
        if resume:
            items.append(resume)
    return items, warnings
