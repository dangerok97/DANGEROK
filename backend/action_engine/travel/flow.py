"""Conversational travel flow — Gap Analyzer driven; never re-ask known departure."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from action_engine.flows.base import opt, turn
from action_engine.models import AnswerOption, QuestionTurn
from action_engine.travel.models import DEFAULT_TZ
from action_engine.travel.period_parser import format_period_label, parse_travel_period

STEP_PERIOD = "period"
STEP_DEPARTURE_DATE = "departure_date"
STEP_RETURN_DATE = "return_date"
STEP_PERIOD_CONFIRM = "period_confirm"
STEP_DESTINATION = "destination"
STEP_DEPARTURE = "departure_place"
STEP_TRANSPORT = "transport"
STEP_BOOKINGS = "bookings"
STEP_LODGING = "lodging"
STEP_COMPANIONS = "companions"
STEP_CALENDAR_SYNC = "calendar_sync"
STEP_PREP = "prep"
STEP_PREVIEW = "preview"
STEP_CONFIRM = "confirm"


def _entities(ctx: Dict[str, Any]) -> Dict[str, Any]:
    return ctx.get("intent_entities") or {}


def _semantic_known(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten semantic known_slots / extracted entities into simple values."""
    out: Dict[str, Any] = {}
    for src in (
        ctx.get("semantic_known_slots"),
        ctx.get("known_slots"),
        (ctx.get("meta") or {}).get("semantic_known_slots"),
    ):
        if isinstance(src, dict):
            out.update({k: v for k, v in src.items() if v not in (None, "", [])})
    ents = ctx.get("semantic_entities") or (ctx.get("meta") or {}).get("semantic_entities") or {}
    if isinstance(ents, dict):
        for k, v in ents.items():
            if isinstance(v, dict) and v.get("normalized") is not None:
                conf = float(v.get("confidence") or 0)
                status = v.get("status") or ""
                if conf >= 0.60 and status not in ("ambiguous", "missing", "low_confidence"):
                    out.setdefault(k, v["normalized"])
            elif v not in (None, "", []):
                out.setdefault(k, v)
    return out


def known_departure_date(ctx: Dict[str, Any]) -> Optional[str]:
    sk = _semantic_known(ctx)
    for key in ("departure_date", "start_date"):
        v = sk.get(key) or _entities(ctx).get(key)
        if v:
            return str(v)[:10]
    return None


def known_return_date(ctx: Dict[str, Any]) -> Optional[str]:
    sk = _semantic_known(ctx)
    for key in ("return_date", "end_date"):
        v = sk.get(key) or _entities(ctx).get(key)
        if v:
            return str(v)[:10]
    return None


def known_period(ctx: Dict[str, Any]) -> Optional[Dict[str, str]]:
    ent = _entities(ctx)
    sk = _semantic_known(ctx)
    for key in ("period", "travel_period"):
        raw = sk.get(key) or ent.get(key) or ctx.get(key)
        if isinstance(raw, dict) and raw.get("start_date") and raw.get("end_date"):
            return {"start_date": raw["start_date"][:10], "end_date": raw["end_date"][:10]}
    dep = known_departure_date(ctx)
    ret = known_return_date(ctx)
    if dep and ret:
        return {"start_date": dep, "end_date": ret}
    # Both start+end on intent entities
    if ent.get("start_date") and ent.get("end_date"):
        return {"start_date": str(ent["start_date"])[:10], "end_date": str(ent["end_date"])[:10]}
    # Parse from title/description only when full range present
    blob = " ".join(
        str(x) for x in (ctx.get("original_title"), ctx.get("title"), ctx.get("description")) if x
    )
    parsed = parse_travel_period(blob, tz_name=ctx.get("timezone") or DEFAULT_TZ)
    if parsed.get("ok") and not parsed.get("assumed_end"):
        return {"start_date": parsed["start_date"], "end_date": parsed["end_date"]}
    return None


def known_destination(ctx: Dict[str, Any]) -> Optional[str]:
    sk = _semantic_known(ctx)
    for key in ("destination", "travel", "place", "location"):
        v = sk.get(key) or _entities(ctx).get(key) or ctx.get(key)
        if v and str(v).strip() and str(v).lower() not in ("from_title", "vacanza", "viaggio"):
            if isinstance(v, dict):
                v = v.get("normalized") or v.get("raw")
            if v:
                return str(v).strip()
    loc = (ctx.get("location") or "").strip()
    return loc or None


def known_departure(ctx: Dict[str, Any]) -> Optional[str]:
    for key in ("home_place", "departure_place", "brain_home"):
        v = ctx.get(key)
        if v:
            return str(v).strip()
    sk = _semantic_known(ctx)
    if sk.get("departure_place") or sk.get("departure"):
        return str(sk.get("departure_place") or sk.get("departure")).strip()
    ent = _entities(ctx)
    if ent.get("departure"):
        return str(ent["departure"]).strip()
    return None


def known_transport(ctx: Dict[str, Any]) -> Optional[str]:
    sk = _semantic_known(ctx)
    v = sk.get("transport") or _entities(ctx).get("transport")
    return str(v) if v else None


def known_lodging(ctx: Dict[str, Any]) -> Optional[str]:
    sk = _semantic_known(ctx)
    v = sk.get("lodging") or sk.get("accommodation") or sk.get("bookings")
    if v is None:
        v = _entities(ctx).get("lodging") or _entities(ctx).get("accommodation")
    return str(v) if v not in (None, "", []) else None


def _gap_next(ctx: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    gap = (
        ctx.get("gap")
        or ctx.get("semantic_gap")
        or (ctx.get("meta") or {}).get("semantic_gap")
        or (ctx.get("meta") or {}).get("gap")
        or {}
    )
    if not isinstance(gap, dict):
        return None
    return gap


def _departure_label(ctx: Dict[str, Any]) -> str:
    dep = known_departure_date(ctx)
    if not dep:
        return ""
    try:
        from datetime import date as date_cls
        d = date_cls.fromisoformat(dep[:10])
        months = [
            "", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
        ]
        return f"{d.day} {months[d.month]}"
    except Exception:
        return dep


def build_turns(ctx: Dict[str, Any]) -> List[QuestionTurn]:
    title = ctx.get("display_title") or ctx.get("title") or "vacanza"
    turns: List[QuestionTurn] = []
    period = known_period(ctx)
    dest = known_destination(ctx)
    departure = known_departure(ctx)
    dep_date = known_departure_date(ctx)
    ret_date = known_return_date(ctx)
    transport = known_transport(ctx)
    google_connected = bool(ctx.get("google_connected"))
    gap = _gap_next(ctx) or {}
    next_slot = gap.get("next_slot")
    next_q = gap.get("next_best_question")

    # --- Date / destination order (Gap-driven) ---
    # Mandatory: departure-only → ask DESTINATION first, then return — never both dates.
    if not dest:
        q = next_q if next_slot == "destination" and next_q else "Dove andrai?"
        turns.append(turn(
            STEP_DESTINATION,
            q,
            explanation=f"Parto da «{title}» — dimmi dove vai." if title else "Dimmi la destinazione.",
            input_kind="chips_or_text",
            options=[
                opt("from_title", f"Usa «{title}»", "from_title"),
            ],
            brain_key="travel_destination",
        ))

    if period:
        pass  # both dates known — skip date questions
    elif dep_date and not ret_date:
        # Only after destination is queued (or known): ask return alone
        label = _departure_label(ctx)
        q = next_q if next_slot == "return_date" and next_q else (
            f"Perfetto, partirai il {label}. Quando pensi di rientrare?"
            if label else
            "Quando pensi di rientrare?"
        )
        turns.append(turn(
            STEP_RETURN_DATE,
            q,
            explanation="La partenza è già nota — serve solo il rientro.",
            input_kind="chips_or_text",
            options=[
                opt("plus_7", "+7 giorni", "plus_7"),
                opt("plus_14", "+14 giorni", "plus_14"),
                opt("unsure", "Non ancora", "__skip__"),
            ],
            brain_key="travel_return",
        ))
    elif not dep_date:
        q = next_q if next_slot == "departure_date" and next_q else "Quando parti?"
        turns.append(turn(
            STEP_DEPARTURE_DATE,
            q,
            explanation="Es. «fra due settimane» oppure scegli un chip.",
            input_kind="chips_or_text",
            options=[
                opt("this_weekend", "Questo weekend", "this_weekend"),
                opt("next_week", "Prossima settimana", "next_week"),
                opt("in_2_weeks", "Tra 2 settimane", "in_2_weeks"),
                opt("in_1_month", "Tra 1 mese", "in_1_month"),
            ],
            brain_key="travel_departure_date",
        ))

    # When gap says lodging first (full extraction) — put bookings early
    prefer_lodging = (
        next_slot in ("lodging", "accommodation", "bookings")
        or bool(dest and period and transport)
    ) and bool(dest and (period or (dep_date and ret_date)) and transport)

    dep_opts = []
    if departure:
        dep_opts.append(opt("brain", f"Conferma {departure}", departure))
    dep_opts.extend([
        opt("tarquinia", "Tarquinia", "Tarquinia"),
        opt("roma", "Roma", "Roma"),
        opt("other", "Altro", "__other__"),
    ])

    lodging_turn = turn(
        STEP_LODGING,
        next_q if prefer_lodging and next_q else "Hai già un alloggio o prenotazioni?",
        explanation="Biglietti / hotel — utile per il progetto viaggio.",
        options=[
            opt("all", "Sì, tutto", "all"),
            opt("partial", "Parziali", "partial"),
            opt("none", "Ancora no", "none"),
            opt("booked", "Già prenotato", "booked"),
            opt("need", "Da cercare", "need"),
        ],
        brain_key="travel_lodging",
    )
    # Keep bookings as alias answer target for older clients
    bookings_turn = turn(
        STEP_BOOKINGS,
        "Hai già prenotazioni (biglietti / hotel)?",
        options=[
            opt("all", "Sì, tutto", "all"),
            opt("partial", "Parziali", "partial"),
            opt("none", "Ancora no", "none"),
        ],
        brain_key="travel_bookings",
    )

    if prefer_lodging:
        turns.append(lodging_turn)

    if not transport:
        turns.append(turn(
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
        ))

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

    if not prefer_lodging:
        turns.append(lodging_turn)
    turns.append(bookings_turn)

    turns.extend([
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

    # Re-order: if gap next is destination, ensure destination is first unanswered
    if next_slot == "destination" and not dest:
        dest_turns = [t for t in turns if t.id == STEP_DESTINATION]
        other = [t for t in turns if t.id != STEP_DESTINATION]
        turns = dest_turns + other

    return turns


def normalize_answer(
    turn_id: str, value: Any, text: Optional[str] = None,
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    if turn_id == STEP_RETURN_DATE:
        raw = text or value
        code = str(raw).lower().strip() if raw is not None else ""
        if code in ("plus_7", "plus_14", "+7", "+14"):
            days = 14 if "14" in code else 7
            return {"return_offset_days": days}, None
        if code in ("__skip__", "unsure", "skip"):
            return {"skipped": True}, None
        try:
            from semantic_engine.dates import parse_relative_single, parse_range_it
            rng = parse_range_it(str(raw))
            if rng and (rng.get("return_date") or rng.get("end_date") or rng.get("departure_date")):
                d = rng.get("return_date") or rng.get("end_date") or rng.get("departure_date")
                return {"return_date": d, "end_date": d, "label": rng.get("label")}, None
            single = parse_relative_single(str(raw))
            if single and single.get("date"):
                return {"return_date": single["date"], "end_date": single["date"], "label": single.get("label")}, None
        except Exception:
            pass
        s = str(raw).strip()
        if len(s) >= 10 and s[4] == "-":
            return {"return_date": s[:10], "end_date": s[:10]}, None
        return None, {"error": "unparsed", "message": "Indica la data di rientro (es. tra 2 settimane)."}

    if turn_id in (STEP_PERIOD, STEP_DEPARTURE_DATE):
        raw = text or value
        if turn_id == STEP_DEPARTURE_DATE:
            try:
                from semantic_engine.dates import parse_relative_single, parse_range_it
                rng = parse_range_it(str(raw))
                if rng and rng.get("departure_date"):
                    out: Dict[str, Any] = {
                        "departure_date": rng["departure_date"],
                        "start_date": rng["departure_date"],
                        "label": rng.get("label"),
                    }
                    if rng.get("return_date"):
                        out["return_date"] = rng["return_date"]
                        out["end_date"] = rng["return_date"]
                    return out, None
                parsed_rel = parse_relative_single(str(raw))
                if parsed_rel and parsed_rel.get("date"):
                    return {
                        "departure_date": parsed_rel["date"],
                        "start_date": parsed_rel["date"],
                        "label": parsed_rel.get("label"),
                        "departure_only": True,
                    }, None
            except Exception:
                pass
        parsed = parse_travel_period(raw)
        if not parsed.get("ok"):
            return None, {
                "error": parsed.get("error") or "unparsed",
                "message": parsed.get("message") or "Data non valida.",
            }
        if turn_id == STEP_DEPARTURE_DATE and parsed.get("source") == "relative":
            return {
                "departure_date": parsed["start_date"],
                "start_date": parsed["start_date"],
                "label": parsed.get("label"),
            }, None
        return {
            "start_date": parsed["start_date"],
            "end_date": parsed["end_date"],
            "departure_date": parsed["start_date"],
            "return_date": parsed["end_date"],
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
            return None, {"error": "departure_required", "message": "Indica da dove parti."}
        if not v or not str(v).strip():
            return None, {"error": "departure_required", "message": "Indica da dove parti."}
        return str(v).strip(), None

    if turn_id == STEP_LODGING:
        if value in ("__skip__",) or text == "__skip__":
            return "__skip__", None
        return value if value is not None else text, None

    if turn_id == STEP_PREP:
        if value == "__skip__" or (isinstance(value, list) and "__skip__" in value):
            return [], None
        return value if value is not None else text, None

    return value if value is not None else text, None


def jump_target(option_id: str) -> Optional[str]:
    return {
        "edit_dest": STEP_DESTINATION,
        "edit_period": STEP_DEPARTURE_DATE,
        "edit_calendar": STEP_CALENDAR_SYNC,
        "back": STEP_PREVIEW,
    }.get(option_id or "")


def preview_explanation(preview_or_ctx: Any, answers: Optional[Dict[str, Any]] = None) -> str:
    """Accept preview dict (AE service) or (ctx, answers)."""
    if answers is None and isinstance(preview_or_ctx, dict):
        preview = preview_or_ctx
        dest = preview.get("destination") or "?"
        label = preview.get("period_label") or preview.get("label") or ""
        return f"{dest} · {label}".strip(" ·")
    ctx = preview_or_ctx if isinstance(preview_or_ctx, dict) else {}
    ans = answers or {}
    dest = ans.get(STEP_DESTINATION) or known_destination(ctx) or "?"
    period = ans.get(STEP_PERIOD) or known_period(ctx)
    if isinstance(period, dict):
        label = period.get("label") or f"{period.get('start_date')} – {period.get('end_date')}"
    else:
        label = str(period or "")
    return f"{dest} · {label}"
