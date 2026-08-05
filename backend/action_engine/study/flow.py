"""Conversational study flow — one question at a time, skip known, stable step ids."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from action_engine.flows.base import opt, turn
from action_engine.models import AnswerOption, QuestionTurn
from action_engine.study.date_parser import format_local, parse_exam_date
from action_engine.study.models import DEFAULT_TZ, TimeRange

# Stable step ids (product contract)
STEP_CONFIRM_SUBJECT = "confirm_subject"
STEP_EXAM_DATE = "exam_date"
STEP_EXAM_DATE_CONFIRM = "exam_date_confirm"
STEP_SELECT_MATERIALS = "select_materials"
STEP_DAILY_TIME = "daily_time"
STEP_AVAILABLE_DAYS = "available_days"
STEP_PREFERRED_RANGES = "preferred_time_ranges"
STEP_INTENSITY = "intensity"
STEP_TOOLS = "tools"
STEP_CALENDAR_SYNC = "calendar_sync"
STEP_PREVIEW = "preview"
STEP_CONFIRM = "confirm"
STEP_DUPLICATE = "duplicate_resolution"
STEP_UPLOAD_RESUME = "upload_resume"

DAY_OPTS = [
    opt("mon", "Lun", 0),
    opt("tue", "Mar", 1),
    opt("wed", "Mer", 2),
    opt("thu", "Gio", 3),
    opt("fri", "Ven", 4),
    opt("sat", "Sab", 5),
    opt("sun", "Dom", 6),
]


def _subject_from_ctx(ctx: Dict[str, Any]) -> Optional[str]:
    entities = ctx.get("intent_entities") or {}
    return (
        entities.get("subject")
        or entities.get("exam")
        or ctx.get("display_title")
        or None
    )


def _known_exam_date(ctx: Dict[str, Any]) -> Optional[str]:
    entities = ctx.get("intent_entities") or {}
    for key in ("deadline", "date", "exam_date"):
        if entities.get(key):
            parsed = parse_exam_date(entities[key], tz_name=ctx.get("timezone") or DEFAULT_TZ)
            if parsed.get("ok"):
                return parsed["date_iso"]
    due = ctx.get("due_at")
    if due:
        parsed = parse_exam_date(due, tz_name=ctx.get("timezone") or DEFAULT_TZ)
        if parsed.get("ok"):
            return parsed["date_iso"]
    return None


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    """Initial turn list — subject skipped when Intent already has it."""
    subject = _subject_from_ctx(ctx)
    title = subject or ctx.get("title") or "esame"
    turns: List[QuestionTurn] = []

    if not subject or ctx.get("force_confirm_subject"):
        turns.append(turn(
            STEP_CONFIRM_SUBJECT,
            f"Confermi che l'esame è «{title}»?",
            explanation="Puoi correggere la materia se ho capito male.",
            input_kind="chips_or_text",
            options=[
                opt("yes", f"Sì, {title}", title),
                opt("other", "No, correggi", "__other__"),
            ],
            brain_key="study_subject",
        ))
    else:
        # Pre-seed answer later in service; still expose for transparency if needed
        pass

    known_date = _known_exam_date(ctx)
    date_opts = [
        opt("in_1_week", "Tra 1 settimana", "in_1_week"),
        opt("in_2_weeks", "Tra 2 settimane", "in_2_weeks"),
        opt("in_1_month", "Tra 1 mese", "in_1_month"),
        opt("picker", "Scegli data", "__picker__"),
    ]
    explanation = "Scrivi una data (es. 15/09/2026 o «tra 10 giorni») oppure usa un chip."
    if known_date:
        label = format_local(known_date, ctx.get("timezone") or DEFAULT_TZ)
        date_opts.insert(0, opt("known", f"Conferma {label}", known_date))
        explanation = f"Ho trovato {label} dal contesto — conferma o cambia."

    turns.append(turn(
        STEP_EXAM_DATE,
        f"Quando è l'esame «{title}»?",
        explanation=explanation,
        input_kind="chips_or_text",
        options=date_opts,
        brain_key="exam_date",
    ))

    # Remaining steps — always present; materials options filled dynamically
    turns.extend(_tail_turns(ctx, material_options=None))
    return turns


def _tail_turns(
    ctx: Dict[str, Any],
    *,
    material_options: Optional[List[AnswerOption]] = None,
) -> List[QuestionTurn]:
    mat_opts = material_options or [
        opt("none", "Nessun materiale ancora", []),
        opt("upload", "Carica documento", "__upload__"),
        opt("skip_docs", "Continua senza", []),
    ]
    google_connected = bool(ctx.get("google_connected"))
    return [
        turn(
            STEP_SELECT_MATERIALS,
            "Quali materiali vuoi usare?",
            explanation="Ho cercato in Documents V2. Seleziona uno o più, oppure carica.",
            input_kind="multi_chips",
            options=mat_opts,
            brain_key="study_materials",
        ),
        turn(
            STEP_DAILY_TIME,
            "Quanto tempo al giorno puoi studiare?",
            explanation="Adatto il carico delle sessioni.",
            options=[
                opt("15m", "15 minuti", 15),
                opt("30m", "30 minuti", 30),
                opt("1h", "1 ora", 60),
                opt("90m", "1 ora e mezza", 90),
                opt("2h", "2 ore", 120),
                opt("3h", "3 ore", 180),
            ],
            brain_key="study_daily_minutes",
        ),
        turn(
            STEP_AVAILABLE_DAYS,
            "In quali giorni puoi studiare?",
            explanation="Puoi selezionarne più di uno.",
            input_kind="multi_chips",
            options=DAY_OPTS,
            brain_key="study_available_days",
        ),
        turn(
            STEP_PREFERRED_RANGES,
            "In quale fascia oraria preferisci?",
            explanation=(
                "Finestre libere da Google se collegato."
                if google_connected else
                "Google non collegato — uso le fasce che indichi tu."
            ),
            options=[
                opt("morning", "Mattina 9–12", {"start": "09:00", "end": "12:00"}),
                opt("afternoon", "Pomeriggio 14–17", {"start": "14:00", "end": "17:00"}),
                opt("evening", "Sera 18–21", {"start": "18:00", "end": "21:00"}),
                opt("night", "Tarda sera 21–23", {"start": "21:00", "end": "23:00"}),
            ],
            brain_key="study_time_range",
        ),
        turn(
            STEP_INTENSITY,
            "Che intensità vuoi?",
            explanation="Light = poche sessioni. Intensive = più sessioni vicine all'esame.",
            options=[
                opt("light", "Light", "light"),
                opt("distributed", "Distribuito", "distributed"),
                opt("intensive", "Intensivo", "intensive"),
                opt("custom", "Personalizzato", "custom"),
            ],
            brain_key="study_intensity",
        ),
        turn(
            STEP_TOOLS,
            "Quali strumenti preparo?",
            explanation="Solo strumenti reali supportati da ORA — niente fake.",
            input_kind="multi_chips",
            options=[
                opt("study", "Sessioni di studio", "study"),
                opt("review", "Ripasso", "review"),
                opt("flashcards", "Flashcard", "flashcards"),
                opt("interrogami", "Interrogami", "interrogami"),
                opt("exam_questions", "Domande d'esame", "exam_questions"),
            ],
            brain_key="study_tools",
        ),
        turn(
            STEP_CALENDAR_SYNC,
            "Vuoi sincronizzare le sessioni su Google Calendar?",
            explanation=(
                "Creerò eventi reali se Google è collegato."
                if google_connected else
                "Google non collegato — puoi attivarlo dopo; il piano resta su ORA."
            ),
            options=[
                opt("yes", "Sì, sincronizza", True) if google_connected else opt("connect_later", "Più tardi", False),
                opt("no", "No, solo ORA", False),
            ],
            brain_key="study_calendar_sync",
        ),
        turn(
            STEP_PREVIEW,
            "Ecco il piano proposto — va bene?",
            explanation="Puoi modificare tempo, giorni, intensità, materiali o calendario.",
            input_kind="preview",
            options=[
                opt("accept", "Continua a conferma", "accept"),
                opt("edit_time", "Cambia tempo/giorni", "edit_time"),
                opt("edit_intensity", "Cambia intensità", "edit_intensity"),
                opt("edit_materials", "Cambia materiali", "edit_materials"),
                opt("edit_calendar", "Cambia sync calendario", "edit_calendar"),
            ],
            brain_key="study_preview",
        ),
        turn(
            STEP_CONFIRM,
            "Confermi e creo il piano di studio?",
            explanation="Solo dopo la conferma creo sessioni, flashcard e sync.",
            options=[
                opt("confirm", "Conferma e crea", "confirm"),
                opt("back", "Torna al riepilogo", "back"),
            ],
            brain_key="study_confirm",
        ),
    ]


def rebuild_material_turn(turns: List[QuestionTurn], docs: List[dict]) -> List[QuestionTurn]:
    """Inject document chips into select_materials turn."""
    opts: List[AnswerOption] = []
    for d in docs[:12]:
        opts.append(opt(
            f"doc_{d['id']}",
            (d.get("title") or "Documento")[:48],
            d["id"],
        ))
    opts.append(opt("upload", "Carica documento", "__upload__"))
    opts.append(opt("none", "Nessuno / continua", []))
    out = []
    for t in turns:
        if t.id == STEP_SELECT_MATERIALS:
            out.append(turn(
                STEP_SELECT_MATERIALS,
                t.question,
                explanation=t.explanation if docs else "Nessun documento trovato — carica o continua senza.",
                input_kind="multi_chips",
                options=opts,
                brain_key=t.brain_key,
            ))
        else:
            out.append(t)
    return out


def inject_ambiguous_date_turn(
    turns: List[QuestionTurn],
    candidates: List[dict],
) -> List[QuestionTurn]:
    opts = [
        opt(f"c_{i}", c.get("label") or c.get("local_date"), c.get("date_iso") or c.get("local_date"))
        for i, c in enumerate(candidates)
    ]
    confirm_turn = turn(
        STEP_EXAM_DATE_CONFIRM,
        "Quale data intendi?",
        explanation="La data era ambigua — scegli esplicitamente.",
        options=opts,
        brain_key="exam_date_confirm",
    )
    out: List[QuestionTurn] = []
    inserted = False
    for t in turns:
        out.append(t)
        if t.id == STEP_EXAM_DATE and not inserted:
            out.append(confirm_turn)
            inserted = True
    if not inserted:
        out.insert(0, confirm_turn)
    return out


def inject_duplicate_turn(turns: List[QuestionTurn], existing: dict) -> List[QuestionTurn]:
    title = existing.get("exam_name") or existing.get("title") or "piano esistente"
    dup = turn(
        STEP_DUPLICATE,
        f"Esiste già un piano simile: «{title}». Cosa vuoi fare?",
        explanation="Evito duplicati silenziosi.",
        options=[
            opt("open", "Apri esistente", "open"),
            opt("update", "Aggiorna", "update"),
            opt("merge", "Unisci", "merge"),
            opt("replace", "Sostituisci", "replace"),
            opt("create_anyway", "Crea comunque", "create_anyway"),
        ],
        brain_key="study_duplicate",
    )
    # Insert before preview
    out: List[QuestionTurn] = []
    for t in turns:
        if t.id == STEP_PREVIEW:
            out.append(dup)
        out.append(t)
    if dup not in out and all(t.id != STEP_DUPLICATE for t in out):
        out.append(dup)
    return out


def normalize_answer(turn_id: str, value: Any, text: Optional[str] = None) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """Validate/normalize a turn answer. Returns (value, error_dict|None)."""
    if turn_id == STEP_CONFIRM_SUBJECT:
        if value == "__other__" or (isinstance(value, str) and value == "__other__"):
            if not text or not text.strip():
                return None, {"error": "subject_required", "message": "Scrivi il nome della materia."}
            return text.strip()[:80], None
        if text and str(value) in ("__other__", "other"):
            return text.strip()[:80], None
        return (text or value or "").strip()[:80] or None, None

    if turn_id in (STEP_EXAM_DATE, STEP_EXAM_DATE_CONFIRM):
        raw = text or value
        if value == "__picker__" and text:
            raw = text
        parsed = parse_exam_date(raw)
        if parsed.get("ambiguous"):
            return None, {
                "error": "ambiguous",
                "message": parsed.get("message"),
                "candidates": parsed.get("candidates") or [],
            }
        if not parsed.get("ok"):
            return None, {
                "error": parsed.get("error") or "invalid_date",
                "message": parsed.get("message") or "Data non valida.",
            }
        return parsed["date_iso"], None

    if turn_id == STEP_SELECT_MATERIALS:
        if value == "__upload__":
            return {"action": "upload"}, None
        if isinstance(value, list):
            ids = [v for v in value if v and v not in ("__upload__", "none", "skip_docs")]
            return ids, None
        if isinstance(value, str) and value.startswith("doc_"):
            return [value.replace("doc_", "", 1)], None
        if isinstance(value, str) and value not in ("none", "skip_docs", []):
            return [value], None
        return [], None

    if turn_id == STEP_DAILY_TIME:
        try:
            mins = int(float(value))
            if mins < 15:
                return None, {"error": "too_short", "message": "Minimo 15 minuti."}
            return mins, None
        except Exception:
            return None, {"error": "invalid", "message": "Scegli una durata."}

    if turn_id == STEP_AVAILABLE_DAYS:
        if isinstance(value, list):
            days = sorted({int(v) for v in value if str(v).lstrip("-").isdigit() or isinstance(v, int)})
            days = [d for d in days if 0 <= d <= 6]
            if not days:
                return None, {"error": "no_days", "message": "Seleziona almeno un giorno."}
            return days, None
        try:
            d = int(value)
            if 0 <= d <= 6:
                return [d], None
        except Exception:
            pass
        return None, {"error": "no_days", "message": "Seleziona almeno un giorno."}

    if turn_id == STEP_PREFERRED_RANGES:
        if isinstance(value, dict) and value.get("start"):
            return [TimeRange(start=value["start"], end=value.get("end") or "20:00").model_dump()], None
        if isinstance(value, list):
            return value, None
        return [TimeRange(start="18:00", end="20:00").model_dump()], None

    if turn_id == STEP_INTENSITY:
        if value in ("light", "distributed", "intensive", "custom"):
            return value, None
        return "distributed", None

    if turn_id == STEP_TOOLS:
        allowed = {"study", "review", "flashcards", "interrogami", "exam_questions"}
        if isinstance(value, list):
            tools = [v for v in value if v in allowed]
            return tools or ["study", "review"], None
        if value in allowed:
            return [value], None
        return ["study", "review"], None

    if turn_id == STEP_CALENDAR_SYNC:
        return bool(value), None

    if turn_id == STEP_PREVIEW:
        return value or "accept", None

    if turn_id == STEP_CONFIRM:
        return value or "confirm", None

    if turn_id == STEP_DUPLICATE:
        if value in ("open", "update", "merge", "replace", "create_anyway"):
            return value, None
        return None, {"error": "invalid", "message": "Scegli un'opzione."}

    return value, None


def jump_target(edit_code: str) -> Optional[str]:
    return {
        "edit_time": STEP_DAILY_TIME,
        "edit_intensity": STEP_INTENSITY,
        "edit_materials": STEP_SELECT_MATERIALS,
        "edit_calendar": STEP_CALENDAR_SYNC,
        "back": STEP_PREVIEW,
    }.get(str(edit_code))
