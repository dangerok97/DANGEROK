"""Study tools grounded strictly on document text / education_analysis."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from documents.intelligence.schemas import Flashcard, QuizSession, QuizTurn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build_simple_explanation(edu: dict, text: str) -> str:
    subject = edu.get("subject") or "questo argomento"
    topic = edu.get("topic")
    concepts = edu.get("key_concepts") or []
    bits = [f"In parole semplici, il documento parla di {subject}."]
    if topic:
        bits.append(f"L'argomento centrale è: {topic}.")
    if concepts:
        bits.append("Concetti tipici presenti nel testo: " + "; ".join(str(c)[:80] for c in concepts[:4]) + ".")
    snippet = " ".join((text or "").split())[:280]
    if snippet:
        bits.append(f"Dal testo: «{snippet}»")
    return " ".join(bits)


def build_outline(edu: dict, text: str) -> list[str]:
    outline = list(edu.get("outline") or [])
    if outline:
        return outline[:12]
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if re.match(r"^(capitolo|sezione|§|\d+[\.\)])\s+", s, re.I) or (
            len(s) < 80 and s[:1].isupper() and not s.endswith(".")
        ):
            lines.append(s[:120])
        if len(lines) >= 10:
            break
    if not lines and edu.get("key_concepts"):
        lines = [f"• {c}" for c in edu["key_concepts"][:8]]
    return lines


def build_flashcards(edu: dict, text: str) -> list[dict]:
    cards: list[Flashcard] = []
    defs = edu.get("definitions") or []
    for d in defs[:8]:
        if ":" in str(d):
            q, a = str(d).split(":", 1)
            cards.append(Flashcard(
                id=_new_id("fc"),
                question=f"Cos'è {q.strip()}?",
                answer=a.strip()[:400],
                source_ref="definizioni del documento",
                difficulty="medium",
            ))
        else:
            cards.append(Flashcard(
                id=_new_id("fc"),
                question="Quale definizione emerge dal testo?",
                answer=str(d)[:400],
                source_ref="definizioni del documento",
                difficulty="easy",
            ))
    for q in (edu.get("questions_for_review") or [])[:6]:
        # Answer = best matching concept/definition snippet
        ans = _grounded_snippet(text, str(q)) or (edu.get("summary_short") or "")[:240]
        if not ans:
            continue
        cards.append(Flashcard(
            id=_new_id("fc"),
            question=str(q)[:200],
            answer=ans,
            source_ref="domande di ripasso / testo",
            difficulty="medium",
        ))
    for c in (edu.get("key_concepts") or [])[:5]:
        if any(c in (x.question + x.answer) for x in cards):
            continue
        snip = _grounded_snippet(text, str(c)) or str(c)
        cards.append(Flashcard(
            id=_new_id("fc"),
            question=f"Spiega: {str(c)[:120]}",
            answer=snip[:400],
            source_ref="concetti chiave",
            difficulty="hard" if len(str(c)) > 60 else "medium",
        ))
    return [c.model_dump() for c in cards[:16]]


def build_exam_questions(edu: dict) -> list[str]:
    existing = list(edu.get("exam_questions") or [])
    if existing:
        return existing[:10]
    subject = edu.get("subject") or "l'argomento"
    qs = list(edu.get("questions_for_review") or [])
    qs.append(f"Spiega con parole tue i concetti principali di {subject} citando il documento.")
    qs.append(f"Confronta due concetti presenti nel testo su {subject}.")
    if edu.get("definitions"):
        qs.append("Elenca e spiega le definizioni presenti nel documento.")
    return qs[:8]


def start_quiz(doc_id: str, edu: dict, text: str) -> dict:
    questions = list(edu.get("questions_for_review") or []) + build_exam_questions(edu)[:3]
    # dedupe
    seen = set()
    turns: list[QuizTurn] = []
    for q in questions:
        qn = str(q).strip()
        if not qn or qn in seen:
            continue
        seen.add(qn)
        points = _expected_points(edu, text, qn)
        turns.append(QuizTurn(question=qn, expected_points=points))
        if len(turns) >= 6:
            break
    if not turns:
        turns = [QuizTurn(
            question="Quali informazioni principali contiene questo documento?",
            expected_points=[(edu.get("summary_short") or text[:160] or "contenuto del documento")[:160]],
        )]
    sess = QuizSession(
        id=_new_id("quiz"),
        document_id=doc_id,
        turns=turns,
        current_index=0,
        status="active",
        created_at=_now(),
        updated_at=_now(),
    )
    return sess.model_dump()


def answer_quiz(session: dict, user_answer: str, text: str) -> dict:
    turns = list(session.get("turns") or [])
    idx = int(session.get("current_index") or 0)
    if idx >= len(turns):
        session["status"] = "completed"
        session["updated_at"] = _now()
        return session
    turn = dict(turns[idx])
    expected = turn.get("expected_points") or []
    ans = (user_answer or "").strip()
    missing = []
    hit = 0
    ans_l = ans.lower()
    for p in expected:
        tokens = [t for t in re.split(r"\W+", str(p).lower()) if len(t) > 3]
        if tokens and sum(1 for t in tokens if t in ans_l) >= max(1, len(tokens) // 2):
            hit += 1
        else:
            missing.append(str(p)[:160])
    if not ans:
        feedback = "Non hai inserito una risposta. Riparti dagli elementi presenti nel documento."
    elif hit == 0:
        feedback = (
            "La risposta non richiama abbastanza elementi del documento. "
            + ("Manca soprattutto: " + "; ".join(missing[:3]) if missing else "Rileggi il passaggio pertinente.")
        )
    elif missing:
        feedback = (
            f"Hai coperto parte degli elementi del testo ({hit}/{len(expected)}). "
            f"Potresti aggiungere: {'; '.join(missing[:3])}."
        )
    else:
        feedback = "La risposta richiama i punti presenti nel documento."
    # Never invent grades; only grounded feedback
    if ans and text and _grounded_snippet(text, ans[:80]) is None and hit == 0:
        feedback += " Non risultano corrispondenze chiare nel testo estratto."
    turn["user_answer"] = ans
    turn["feedback"] = feedback
    turn["covered"] = hit > 0 and not missing
    turns[idx] = turn
    session["turns"] = turns
    session["current_index"] = min(idx + 1, len(turns))
    if session["current_index"] >= len(turns):
        session["status"] = "completed"
    session["updated_at"] = _now()
    return session


def _expected_points(edu: dict, text: str, question: str) -> list[str]:
    pts = []
    for d in (edu.get("definitions") or [])[:3]:
        if any(w in str(d).lower() for w in re.split(r"\W+", question.lower()) if len(w) > 4):
            pts.append(str(d)[:160])
    for c in (edu.get("key_concepts") or [])[:3]:
        if any(w in str(c).lower() for w in re.split(r"\W+", question.lower()) if len(w) > 4):
            pts.append(str(c)[:160])
    if not pts:
        snip = _grounded_snippet(text, question) or (edu.get("summary_short") or "")[:160]
        if snip:
            pts.append(snip)
    return pts[:4]


def _grounded_snippet(text: str, query: str) -> Optional[str]:
    if not text or not query:
        return None
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 3][:6]
    if not words:
        return None
    best = None
    best_score = 0
    for para in re.split(r"\n{2,}|\.\s+", text):
        p = para.strip()
        if len(p) < 20:
            continue
        pl = p.lower()
        score = sum(1 for w in words if w in pl)
        if score > best_score:
            best_score = score
            best = p
    if best_score <= 0:
        return None
    return best[:400]


def enrich_education(edu: dict, text: str) -> dict:
    """Fill missing study fields from local text only."""
    out = dict(edu or {})
    if not out.get("simple_explanation"):
        out["simple_explanation"] = build_simple_explanation(out, text)
    if not out.get("outline"):
        out["outline"] = build_outline(out, text)
    if not out.get("exam_questions"):
        out["exam_questions"] = build_exam_questions(out)
    if not out.get("estimated_read_minutes"):
        words = len((text or "").split())
        out["estimated_read_minutes"] = max(1, words // 180)
    if not out.get("difficulty"):
        out["difficulty"] = "intermedio" if (out.get("definitions") or out.get("key_concepts")) else "base"
    # people / dates from lines
    if not out.get("important_people"):
        people = []
        for m in re.finditer(r"\b([A-Z][a-zàèéìòù]+(?:\s+[A-Z][a-zàèéìòù]+)+)\b", text or ""):
            people.append(m.group(1))
            if len(people) >= 6:
                break
        out["important_people"] = people
    if not out.get("formulas"):
        out["formulas"] = [
            ln.strip() for ln in (text or "").splitlines()
            if re.search(r"[=∑√∫]|formula", ln, re.I) and len(ln.strip()) < 120
        ][:6]
    if not out.get("examples"):
        out["examples"] = [
            ln.strip() for ln in (text or "").splitlines()
            if re.search(r"esempio|ad esempio|per esempio", ln, re.I)
        ][:6]
    return out
