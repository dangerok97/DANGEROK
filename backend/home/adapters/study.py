from __future__ import annotations

from typing import List, Optional, Tuple

from home.models import ConnectionWarning, HomeItem

from ._util import now_iso, stable_id


async def load_study_state(
    db, user_id: str,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
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
    items: List[HomeItem] = []
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
    return items, []
