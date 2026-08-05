"""Conversational travel flow — ask only missing pieces; preview/confirm gated."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from action_engine.flows.base import opt, turn
from action_engine.models import AnswerOption, QuestionTurn
from action_engine.travel.models import DEFAULT_TZ
from action_engine.travel.period_parser import format_period_label, parse_travel_period

STEP_PERIOD = "period"
STEP_PERIOD_CONFIRM = "period_confirm"
STEP_DESTINATION = "destination"
STEP_DEPARTURE = "departure_place"
STEP_TRANSPORT = "transport"
STEP_BOOKINGS = "bookings"
STEP_COMPANIONS = "companions"
STEP_CALENDAR_SYNC = "calendar_sync"
STEP_PREP = "prep"
STEP_PREVIEW = "preview"
STEP_CONFIRM = "confirm"


def _entities(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return ctx.get("intent_entities") or {}


def known_period(ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    ent = _entities(ctx)
    for key in ("period", "start_date", "travel_period"):
        raw = ent.get(key) or ctx.get(key)
        if isinstance(raw, dict) and raw.get("start_date") and raw.get("end_date"):
            return {"start_date": raw["start_date"][:10], "end_date": raw["end_date"][:10]}
    if ent.get("start_date") and ent.get("end_date"):
        return {"start_date": str(ent["start_date"])[:10], "end_date": str(ent["end_date"])[:10]}
    # Parse from title/description
    blob = " ".join(
        str(x) for x in (ctx.get("original_title"), ctx.get("title"), ctx.get("description")) if x
    )
    parsed = parse_travel_period(blob, tz_name=ctx.get("timezone") or DEFAULT_TZ)
    if parsed.get("ok"):
        return {"start_date": parsed["start_date"], "end_date": parsed["end_date"]}
    return None


def known_destination(ctx: Dict[str, Any]) -> Optional[str]:
    ent = _entities(ctx)
    for key in ("travel", "place", "destination", "location"):
        v = ent.get(key) or ctx.get(key)
        if v and str(v).strip() and str(v).lower() not in ("from_title", "vacanza", "viaggio"):
            return str(v).strip()
    loc = (ctx.get("location") or "").strip()
    return loc or None


def known_departure(ctx: Dict[str, Any]) -> Optional[str]:
    """Brain / profile home place if available."""
    for key in ("home_place", "departure_place", "brain_home"):
        v = ctx.get(key)
        if v:
            return str(v).strip()
    ent = _entities(ctx)
    if ent.get("departure"):
        return str(ent["departure"]).strip()
    return None


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("display_title") or ctx.get("title") or "vacanza"
    turns: List[QuestionTurn] = []
    period = known_period(ctx)
    dest = known_destination(ctx)
    departure = known_departure(ctx)
    google_connected = bool(ctx.get("google_connected"))

    if not period:
        turns.append(turn(
            STEP_PERIOD,
            "Quando parti e quando torni?",
            explanation="Es. «dal 9 al 24 agosto» oppure scegli un chip.",
            input_kind="chips_or_text",
            options=[
                opt("this_weekend", "Questo weekend", "this_weekend"),
                opt("next_week", "Prossima settimana", "next_week"),
                opt("in_2_weeks", "Tra 2 settimane", "in_2_weeks"),
                opt("in_1_month", "Tra 1 mese", "in_1_month"),
            ],
            brain_key="travel_period",
        ))
    else:
        # Pre-seed later; optional confirm chip only if from fuzzy text
        pass

    if not dest:
        turns.append(turn(
            STEP_DESTINATION,
            "Qual è la destinazione?",
            explanation=f"Parto da «{title}» — dimmi dove vai.",
            input_kind="chips_or_text",
            options=[
                opt("from_title", f"Usa «{title}»", "from_title"),
            ],
            brain_key="travel_destination",
        ))

    dep_opts = []
    if departure:
        dep_opts.append(opt("brain", f"Conferma {departure}", departure))
    dep_opts.extend([
        opt("tarquinia", "Tarquinia", "Tarquinia"),
        opt("roma", "Roma", "Roma"),
        opt("other", "Altro", "__other__"),
    ])
    turns.append(turn(
        STEP_DEPARTURE,
        "Da dove parti?",
        explanation=(
            f"Ho in memoria «{departure}» — conferma o cambia."
            if departure else
            "Serve per Maps e orario di partenza (stimato)."
        ),
        input_kind="chips_or_text",
        options=dep_opts,
        brain_key="travel_departure",
    ))

    turns.extend([
        turn(
            STEP_TRANSPORT,
            "Come ti sposti?",
            explanation="Adatto Maps, soste e consigli di partenza.",
            options=[
                opt("train", "Treno", "train"),
                opt("plane", "Aereo", "plane"),
                opt("car", "Auto", "car"),
                opt("other", "Altro", "other"),
            ],
            brain_key="travel_transport",
        ),
        turn(
            STEP_BOOKINGS,
            "Hai già prenotazioni (biglietti / hotel)?",
            options=[
                opt("all", "Sì, tutto", "all"),
                opt("partial", "Parziali", "partial"),
                opt("none", "Ancora no", "none"),
            ],
            brain_key="travel_bookings",
        ),
        turn(
            STEP_COMPANIONS,
            "Con chi viaggi?",
            options=[
                opt("solo", "Solo io", 1),
                opt("2", "In 2", 2),
                opt("family", "3+", 3),
            ],
            brain_key="travel_companions",
        ),
        turn(
            STEP_CALENDAR_SYNC,
            "Vuoi proporre eventi su Google Calendar?",
            explanation=(
                "Blocchi vacanza, andata e ritorno — li creo solo dopo la tua conferma."
                if google_connected else
                "Google non collegato: il progetto resta su ORA. Puoi collegare Google dopo."
            ),
            options=[
                opt("yes", "Sì, proponi eventi", True),
                opt("no", "No, solo su ORA", False),
            ],
            brain_key="travel_calendar_sync",
        ),
        turn(
            STEP_PREP,
            "Suggerimenti di preparazione? (opzionale)",
            explanation="Valigia, documenti, auto, carburante, animali, farmaci, caricatore — solo se ti servono.",
            input_kind="multi_chips",
            allow_skip=True,
            options=[
                opt("luggage", "Valigia", "luggage"),
                opt("docs", "Documenti", "docs"),
                opt("car", "Auto", "car"),
                opt("fuel", "Carburante", "fuel"),
                opt("pets", "Animali", "pets"),
                opt("medicine", "Farmaci", "medicine"),
                opt("charger", "Caricatore", "charger"),
                opt("skip", "Nessuno / salta", "__skip__"),
            ],
            brain_key="travel_prep",
        ),
        turn(
            STEP_PREVIEW,
            "Ecco il progetto viaggio — va bene?",
            explanation="Controlla periodo, destinazione, calendario proposto e Maps.",
            input_kind="preview",
            options=[
                opt("accept", "Sì, continua", "accept"),
                opt("edit_dest", "Cambia destinazione", "edit_dest"),
                opt("edit_period", "Cambia date", "edit_period"),
                opt("edit_calendar", "Cambia sync calendario", "edit_calendar"),
            ],
            brain_key="travel_preview",
        ),
        turn(
            STEP_CONFIRM,
            "Confermi e creo il Travel Project?",
            explanation=(
                "Solo ora creo eventi Google (se li hai chiesti). Niente sync silenziosa."
            ),
            options=[
                opt("confirm", "Conferma", "confirm"),
                opt("back", "Indietro", "back"),
            ],
            brain_key="travel_confirm",
        ),
    ])
    return turns


def normalize_answer(
    turn_id: str, value: Any, text: Optional[str] = None,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    if turn_id == STEP_PERIOD:
        raw = text or value
        parsed = parse_travel_period(raw)
        if not parsed.get("ok"):
            return None, {
                "error": parsed.get("error") or "unparsed",
                "message": parsed.get("message") or "Periodo non valido.",
            }
        return {
            "start_date": parsed["start_date"],
            "end_date": parsed["end_date"],
            "label": parsed.get("label"),
        }, None

    if turn_id == STEP_DESTINATION:
        v = text or value
        if v == "from_title" or v == "__other__":
            if text and text.strip() and text.strip() != "from_title":
                return text.strip(), None
            if v == "__other__":
                return None, {"error": "destination_required", "message": "Scrivi la destinazione."}
        if not v or not str(v).strip():
            return None, {"error": "destination_required", "message": "Indica la destinazione."}
        return str(v).strip(), None

    if turn_id == STEP_DEPARTURE:
        v = text or value
        if v == "__other__":
            if text and text.strip():
                return text.strip(), None
            return None, {"error": "departure_required", "message": "Scrivi il luogo di partenza."}
        if not v:
            return None, {"error": "departure_required", "message": "Indica da dove parti."}
        return str(v).strip(), None

    if turn_id == STEP_TRANSPORT:
        if value not in ("train", "plane", "car", "other"):
            return None, {"error": "validation", "message": "Scegli un mezzo di trasporto."}
        return value, None

    if turn_id == STEP_BOOKINGS:
        if value not in ("all", "partial", "none"):
            return None, {"error": "validation", "message": "Scegli lo stato prenotazioni."}
        return value, None

    if turn_id == STEP_COMPANIONS:
        try:
            n = int(value)
        except Exception:
            return None, {"error": "validation", "message": "Indica il numero di persone."}
        return max(1, min(n, 20)), None

    if turn_id == STEP_CALENDAR_SYNC:
        if value in (True, "yes", "true", "1"):
            return True, None
        return False, None

    if turn_id == STEP_PREP:
        if value in (None, "__skip__", "skip") or value == []:
            return [], None
        if isinstance(value, str):
            return [value] if value != "__skip__" else [], None
        if isinstance(value, list):
            return [x for x in value if x and x not in ("__skip__", "skip")], None
        return [], None

    if turn_id == STEP_PREVIEW:
        return value or "accept", None

    if turn_id == STEP_CONFIRM:
        return value, None

    return value, None


def jump_target(edit_code: str) -> Optional[str]:
    return {
        "edit_dest": STEP_DESTINATION,
        "edit_period": STEP_PERIOD,
        "edit_calendar": STEP_CALENDAR_SYNC,
    }.get(edit_code)


def preview_explanation(preview: dict) -> str:
    if not preview:
        return "Riepilogo viaggio."
    parts = [
        preview.get("destination") or "?",
        preview.get("period_label") or "",
        preview.get("transport_label") or "",
    ]
    if preview.get("calendar_proposed"):
        parts.append(f"{preview.get('calendar_event_count', 0)} eventi calendario")
    if preview.get("maps", {}).get("duration_label"):
        parts.append(preview["maps"]["duration_label"])
    return " · ".join(p for p in parts if p)
