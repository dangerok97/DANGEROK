"""AI enrichment for Life Objects — narrative, questions, insights, temporal, health.

Gemini via Provider Manager (structured Pydantic). Deterministic Italian fallback
when Gemini absent/invalid. Never invents facts — only uses object fields/history.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from life_objects.identity_state import apply_identity_state_migration
from life_objects.memory import basic_utility_trend, detect_state_changes, utility_amount_series
from life_objects.models import (
    AI_ENRICHMENT_VERSION,
    AIInsight,
    AINarrative,
    HealthAIResult,
    InsightItemAI,
    InsightsAIResult,
    LifeObject,
    LifeObjectHealth,
    NarrativeAIResult,
    PendingQuestion,
    QuestionItemAI,
    QuestionsAIResult,
    TemporalAIResult,
    TemporalComparison,
    now_iso,
)
from life_objects.reasoner import life_object_gemini_enabled

logger = logging.getLogger("ora.life_objects.enrichment")


def _minimal_context(obj: LifeObject) -> Dict[str, Any]:
    """Privacy-minimized payload for Gemini — no secrets, no full history dumps."""
    hist_summaries = []
    for h in (obj.history or [])[-12:]:
        hist_summaries.append({
            "at": h.at,
            "event": h.event,
            "source": h.source,
            "summary": (h.summary or "")[:160],
            "improves": (h.improves or [])[:4],
            "worsens": (h.worsens or [])[:4],
            "delta_keys": list((h.delta or {}).keys())[:8],
        })
    return {
        "id": obj.id,
        "type": obj.type,
        "title": obj.title,
        "status": obj.status,
        "identity": {k: v for k, v in (obj.identity or {}).items() if v not in (None, "", [], {})},
        "state": {k: v for k, v in (obj.state or {}).items() if v not in (None, "", [], {})},
        "identity_keys": dict(obj.identity_keys or {}),
        "documents_count": len(obj.documents or []),
        "goals_count": len(obj.goals or []),
        "relationships_count": len(obj.relationships or []),
        "history_tail": hist_summaries,
        "source_count": obj.source_count or len(obj.documents or []),
    }


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


# ---------------------------------------------------------------------------
# Deterministic Italian fallbacks
# ---------------------------------------------------------------------------

def deterministic_narrative(obj: LifeObject) -> NarrativeAIResult:
    """Natural Italian situation description from known facts only."""
    t = obj.type
    identity = obj.identity or {}
    state = obj.state or {}
    parts: List[str] = []

    if t == "HOME":
        addr = _safe_str(identity.get("address") or identity.get("property_address") or (obj.identity_keys or {}).get("address_norm"))
        if addr:
            parts.append(f"Hai una casa collegata a {addr}.")
        else:
            parts.append("Hai una casa in ORA, ma manca ancora un indirizzo stabile.")
        lender = _safe_str(state.get("lender"))
        installment = _safe_str(state.get("monthly_installment"))
        if lender and installment:
            parts.append(f"Risulta un mutuo con {lender} (rata circa {installment}).")
        elif lender:
            parts.append(f"Risulta un mutuo collegato con {lender}.")
        supplier = _safe_str(state.get("supplier"))
        utility = _safe_str(state.get("utility_type")) or "utenze"
        amount = _safe_str(state.get("amount_total") or state.get("amount"))
        if supplier and amount:
            parts.append(f"Per le utenze ({utility}) il fornitore noto è {supplier}, ultima bolletta {amount}.")
        elif supplier:
            parts.append(f"Fornitore utenze noto: {supplier}.")
        cadastral = _safe_str(identity.get("cadastral_data") or identity.get("cadastral"))
        if cadastral:
            parts.append("I dati catastali sono presenti.")
    elif t == "VEHICLE":
        plate = _safe_str(identity.get("plate") or (obj.identity_keys or {}).get("plate"))
        brand = _safe_str(identity.get("brand"))
        model = _safe_str(identity.get("model"))
        label = " ".join(x for x in (brand, model) if x).strip() or "veicolo"
        if plate:
            parts.append(f"Hai un {label} con targa {plate}.")
        else:
            parts.append(f"Hai un {label}, ma manca la targa come chiave primaria.")
        company = _safe_str(state.get("company"))
        if company:
            parts.append(f"Assicurazione nota: {company}.")
        if identity.get("vin"):
            parts.append("Il telaio (VIN) è registrato.")
    elif t in ("UNIVERSITY", "COURSE"):
        inst = _safe_str(identity.get("institution") or identity.get("university") or (obj.identity_keys or {}).get("institution"))
        course = _safe_str(state.get("course_name") or state.get("subject") or identity.get("course_name"))
        if inst and course:
            parts.append(f"Il tuo percorso di studi riguarda {course} presso {inst}.")
        elif inst:
            parts.append(f"Hai un legame universitario con {inst}.")
        elif course:
            parts.append(f"Stai seguendo il corso {course}.")
        else:
            parts.append("Hai un oggetto di studio, ma mancano ateneo o corso.")
    elif t == "JOB":
        emp = _safe_str(identity.get("employer") or state.get("employer") or (obj.identity_keys or {}).get("employer"))
        if emp:
            parts.append(f"Il tuo lavoro è collegato a {emp}.")
        else:
            parts.append("Hai un oggetto Lavoro, ma manca il datore di lavoro.")
    elif t == "TRAVEL":
        dest = _safe_str(state.get("destination") or identity.get("destination"))
        start = _safe_str(state.get("start_date"))
        end = _safe_str(state.get("end_date"))
        if dest and start and end:
            parts.append(f"Hai un viaggio verso {dest} dal {start} al {end}.")
        elif dest:
            parts.append(f"Hai un viaggio verso {dest}.")
        else:
            parts.append("Hai un progetto di viaggio in ORA.")
    else:
        title = _safe_str(obj.title) or t
        parts.append(f"Oggetto «{title}» con {len(obj.documents or [])} documenti collegati.")

    n_docs = len(obj.documents or [])
    if n_docs:
        parts.append(f"Fonti documentali collegate: {n_docs}.")

    text = " ".join(parts).strip()
    conf = 0.55 + (0.1 if obj.identity_keys else 0) + min(0.2, 0.05 * n_docs)
    return NarrativeAIResult(
        narrative=text[:1200],
        invented_facts=False,
        confidence=min(0.95, conf),
        ai_used=False,
    )


def deterministic_questions(obj: LifeObject) -> QuestionsAIResult:
    """Intelligent pending questions that increase ORA's ability to help."""
    qs: List[QuestionItemAI] = []

    identity = obj.identity or {}
    state = obj.state or {}
    ik = obj.identity_keys or {}
    t = obj.type

    def add(q: str, why: str, priority: str = "medium", category: str = "missing_info"):
        qs.append(QuestionItemAI(question=q, why=why, priority=priority, category=category))  # type: ignore[arg-type]

    if t == "HOME":
        if not (identity.get("address") or ik.get("address_norm")):
            add(
                "Qual è l'indirizzo completo di questa casa?",
                "Senza indirizzo ORA non può unificare rogito, mutuo e bollette sulla stessa casa.",
                "high",
            )
        if not (identity.get("cadastral_data") or ik.get("cadastral")):
            add(
                "Hai il riferimento catastale (foglio/particella/sub)?",
                "Il catastale rafforza l'identità e evita una seconda Casa.",
                "medium",
            )
        if not state.get("lender") and not any(
            (h.delta or {}).get("properties", {}).get("lender") for h in (obj.history or [])
        ):
            # Only ask if mortgage-like docs not already linking lender
            if not any("mutuo" in str((h.delta or {}).get("properties", {}).get("document_type") or "") for h in (obj.history or [])):
                add(
                    "Hai un mutuo su questa casa? Se sì, con quale banca?",
                    "Sapere banca e rata aiuta ORA a monitorare impegno finanziario e scadenze.",
                    "medium",
                    "help_ability",
                )
        if not (ik.get("pod") or identity.get("pod")):
            add(
                "Conosci il codice POD della fornitura elettrica?",
                "Il POD collega bollette luce alla stessa casa in modo stabile.",
                "low",
                "help_ability",
            )
        if state.get("supplier") and not state.get("amount_total"):
            add(
                "Puoi caricare l'ultima bolletta con l'importo?",
                "Serve a leggere andamento consumi/spesa nel tempo.",
                "medium",
                "help_ability",
            )
    elif t == "VEHICLE":
        if not (identity.get("plate") or ik.get("plate")):
            add(
                "Qual è la targa del veicolo?",
                "La targa è la chiave primaria per unificare libretto e polizza.",
                "high",
            )
        if not state.get("company"):
            add(
                "Con quale compagnia è assicurata l'auto?",
                "Serve per scadenze e confronti di copertura.",
                "medium",
                "help_ability",
            )
        if not (identity.get("vin") or ik.get("vin")):
            add(
                "Hai il numero di telaio (VIN)?",
                "Il VIN rafforza l'identità se la targa cambia o manca.",
                "low",
            )
    elif t in ("UNIVERSITY", "COURSE"):
        if not (identity.get("institution") or ik.get("institution")):
            add(
                "Presso quale università o istituto studi?",
                "L'ateneo è la chiave per non duplicare percorsi di studio.",
                "high",
            )
        if not (state.get("course_name") or state.get("subject")):
            add(
                "Qual è il corso di laurea o la materia principale?",
                "Serve a collegare esami, dispense e scadenze al percorso giusto.",
                "medium",
                "help_ability",
            )
    elif t == "JOB":
        if not (identity.get("employer") or ik.get("employer")):
            add(
                "Qual è il nome del datore di lavoro?",
                "Il datore di lavoro identifica in modo stabile l'oggetto Lavoro.",
                "high",
            )
        add(
            "Puoi caricare l'ultima busta paga o il contratto?",
            "Documenti reali riducono domande e migliorano affidabilità.",
            "medium",
            "help_ability",
        )
    elif t == "TRAVEL":
        if not state.get("destination"):
            add(
                "Qual è la destinazione del viaggio?",
                "La destinazione definisce l'oggetto viaggio e collega prenotazioni.",
                "high",
            )
        if not state.get("start_date"):
            add(
                "Quando parti?",
                "Le date consentono scadenze e priorità nel tempo.",
                "medium",
                "help_ability",
            )
    else:
        if not obj.documents:
            add(
                "Hai un documento che descrive meglio questo oggetto?",
                "Una fonte documentale aumenta affidabilità e riduce ambiguità.",
                "medium",
                "help_ability",
            )

    if obj.status == "uncertain":
        add(
            "Queste informazioni appartengono allo stesso oggetto di vita?",
            "Lo stato è incerto: una conferma evita duplicati.",
            "high",
            "clarify",
        )
    if obj.merge_proposals:
        add(
            "Vuoi unire le informazioni in conflitto in un unico oggetto?",
            "Ci sono proposte di merge in sospeso.",
            "high",
            "clarify",
        )

    # Cap + dedupe
    seen = set()
    unique: List[QuestionItemAI] = []
    for q in qs:
        key = q.question.strip().lower()
        if key in seen or not q.question.strip():
            continue
        seen.add(key)
        unique.append(q)
    return QuestionsAIResult(questions=unique[:6], invented_facts=False, ai_used=False)


def deterministic_insights(obj: LifeObject) -> InsightsAIResult:
    items: List[InsightItemAI] = []
    state = obj.state or {}
    changes = detect_state_changes(obj)
    series = utility_amount_series(obj)
    trend = basic_utility_trend(obj)

    for ch in changes[:5]:
        field = ch.get("field")
        if field == "supplier":
            items.append(InsightItemAI(
                kind="change",
                title="Cambio fornitore",
                detail=f"Fornitore passato da «{ch.get('from')}» a «{ch.get('to')}».",
                evidence=[str(ch.get("at") or "")],
                confidence=0.8,
            ))
        elif field in ("amount_total", "amount"):
            items.append(InsightItemAI(
                kind="trend",
                title="Importo bolletta aggiornato",
                detail=f"Ultimo importo osservato: {ch.get('to')} (prima {ch.get('from')}).",
                evidence=[str(ch.get("at") or "")],
                confidence=0.7,
            ))
        elif field == "company":
            items.append(InsightItemAI(
                kind="change",
                title="Cambio compagnia",
                detail=f"Compagnia da «{ch.get('from')}» a «{ch.get('to')}».",
                evidence=[str(ch.get("at") or "")],
                confidence=0.75,
            ))
        elif field == "monthly_installment":
            items.append(InsightItemAI(
                kind="observation",
                title="Rata mutuo aggiornata",
                detail=f"Rata osservata: {ch.get('to')}.",
                evidence=[str(ch.get("at") or "")],
                confidence=0.7,
            ))
        else:
            items.append(InsightItemAI(
                kind="change",
                title=f"Variazione {field}",
                detail=f"{field}: {ch.get('from')} → {ch.get('to')}",
                evidence=[str(ch.get("at") or "")],
                confidence=0.6,
            ))

    if trend.get("trend") in ("rising", "falling") and trend.get("points", 0) >= 2:
        label = "in aumento" if trend["trend"] == "rising" else "in calo"
        items.append(InsightItemAI(
            kind="trend",
            title=f"Andamento utenze {label}",
            detail=(
                f"Confronto ultime bollette: {trend.get('previous')} → {trend.get('latest')} "
                f"(Δ {trend.get('delta')})."
            ),
            evidence=[f"points={trend.get('points')}"],
            confidence=0.75,
        ))

    # Mortgage years left — only if both term and years_elapsed present (never invent)
    years_left = state.get("mortgage_years_left") or state.get("years_remaining")
    if years_left not in (None, ""):
        items.append(InsightItemAI(
            kind="observation",
            title="Anni residui mutuo",
            detail=f"Secondo i dati presenti restano circa {years_left} anni di mutuo.",
            evidence=["state.mortgage_years_left"],
            confidence=0.65,
        ))

    if len(obj.documents or []) >= 3 and obj.type == "HOME":
        items.append(InsightItemAI(
            kind="opportunity",
            title="Casa ben documentata",
            detail="Più fonti (es. rogito/mutuo/bolletta) aumentano l'affidabilità dell'oggetto Casa.",
            evidence=[f"documents={len(obj.documents or [])}"],
            confidence=0.7,
        ))

    if obj.status == "uncertain":
        items.append(InsightItemAI(
            kind="risk",
            title="Identità non certa",
            detail="L'oggetto è in stato uncertain: ORA evita di trattarlo come verità piena.",
            evidence=["status=uncertain"],
            confidence=0.9,
        ))

    if not items and series:
        items.append(InsightItemAI(
            kind="observation",
            title="Storico utenze presente",
            detail=f"Ci sono {len(series)} punti di spesa/utenze nella storia dell'oggetto.",
            evidence=[f"series={len(series)}"],
            confidence=0.55,
        ))

    return InsightsAIResult(insights=items[:8], invented_facts=False, ai_used=False)


def deterministic_temporal(obj: LifeObject) -> TemporalAIResult:
    changes = detect_state_changes(obj)
    trend = basic_utility_trend(obj)
    observations: List[str] = []
    if trend.get("points", 0) >= 2:
        observations.append(
            f"Confronto bollette: trend={trend.get('trend')}, "
            f"ultimo={trend.get('latest')}, precedente={trend.get('previous')}."
        )
    elif trend.get("points", 0) == 1:
        observations.append(f"Una sola bolletta nota (importo {trend.get('latest')}); serve almeno un altro periodo per il trend.")
    for ch in changes[:6]:
        observations.append(
            f"Cambio {ch.get('field')}: {ch.get('from')} → {ch.get('to')} ({ch.get('at') or 'n/d'})."
        )
    if not observations:
        observations.append("Non ci sono ancora confronti temporali sufficienti su questo oggetto.")
    return TemporalAIResult(
        observations=observations[:10],
        changes=changes[:10],
        invented_facts=False,
        ai_used=False,
    )


def deterministic_health(obj: LifeObject) -> HealthAIResult:
    missing: List[str] = []
    opportunities: List[str] = []
    risks: List[str] = []
    reasons: List[str] = []
    t = obj.type
    identity = obj.identity or {}
    state = obj.state or {}
    ik = obj.identity_keys or {}

    # Completeness by type
    needed_identity = {
        "HOME": ["address"],
        "VEHICLE": ["plate"],
        "UNIVERSITY": ["institution"],
        "COURSE": ["institution"],
        "JOB": ["employer"],
        "TRAVEL": ["destination"],
    }.get(t, [])
    present = 0
    for key in needed_identity:
        val = identity.get(key) or ik.get(key) or ik.get(f"{key}_norm") or state.get(key)
        if val:
            present += 1
        else:
            missing.append(key)
    completeness = 0.4
    if needed_identity:
        completeness = present / max(1, len(needed_identity))
    else:
        completeness = 0.6 if (identity or ik) else 0.35
    if obj.documents:
        completeness = min(1.0, completeness + min(0.25, 0.05 * len(obj.documents)))
        reasons.append(f"{len(obj.documents)} documenti collegati migliorano la completezza.")
    if identity or ik:
        reasons.append("Chiavi di identità presenti.")
    else:
        reasons.append("Poche chiavi di identità: completezza limitata.")

    reliability = 0.45
    if obj.documents:
        reliability += min(0.3, 0.08 * len(obj.documents))
    if obj.confidence:
        reliability = (reliability + float(obj.confidence)) / 2
    if obj.status == "uncertain":
        reliability = min(reliability, 0.35)
        risks.append("Identità uncertain")
        reasons.append("Stato uncertain riduce l'affidabilità.")
    if obj.merge_proposals:
        reliability -= 0.1
        risks.append("Merge in sospeso")
        reasons.append("Ci sono proposte di merge non risolte.")
    reliability = max(0.0, min(1.0, reliability))

    # Opportunities / risks from facts
    if t == "HOME" and state.get("supplier") and len(utility_amount_series(obj)) >= 2:
        opportunities.append("Confrontare andamento bollette nel tempo")
    if t == "HOME" and not state.get("lender"):
        opportunities.append("Collegare il mutuo se presente")
    if t == "VEHICLE" and not state.get("company"):
        opportunities.append("Aggiungere polizza per scadenze")
    if t in ("UNIVERSITY", "COURSE") and not state.get("course_name"):
        opportunities.append("Specificare corso/materia")
    for w in (obj.last_reasoning or {}).get("worsens") or []:
        risks.append(str(w))

    if not missing and completeness >= 0.7:
        reasons.append("Informazioni essenziali presenti.")
    if missing:
        reasons.append("Mancano: " + ", ".join(missing))

    overall = round((completeness * 0.45 + reliability * 0.55), 3)
    overall = max(0.0, min(1.0, overall))
    return HealthAIResult(
        completeness=round(completeness, 3),
        reliability=round(reliability, 3),
        missing_info=missing,
        opportunities=opportunities[:6],
        risks=risks[:6],
        reasons=reasons[:8],
        overall_score=overall,
        invented_facts=False,
        ai_used=False,
    )


# ---------------------------------------------------------------------------
# Gemini paths
# ---------------------------------------------------------------------------

async def _chat_enrich(system: str, payload: Dict[str, Any], model_cls, session_id: str):
    from llm.structured import chat_json
    from llm import llm_status

    status = llm_status()
    if not status.get("configured"):
        return None
    parsed, meta = await chat_json(
        system=system,
        user=json.dumps(payload, ensure_ascii=False)[:10000],
        model_cls=model_cls,
        session_id=session_id,
        user_preference="gemini",
    )
    if getattr(parsed, "invented_facts", False):
        return None
    parsed.ai_used = True
    parsed.provider = str(meta.get("provider") or "gemini")
    parsed.model = str(meta.get("model") or "")
    return parsed


async def enrich_narrative(obj: LifeObject) -> NarrativeAIResult:
    fallback = deterministic_narrative(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei il narratore Life Object di ORA. Scrivi UNA descrizione naturale in italiano "
            "della situazione attuale dell'oggetto, NON un elenco di campi. "
            "Usa SOLO i fatti nel JSON. Non inventare. invented_facts=false sempre. "
            "Rispondi SOLO JSON schema NarrativeAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {"task": "narrative", "object": _minimal_context(obj), "style": "Casa naturale, frasi brevi"},
            NarrativeAIResult,
            f"ora-lo-narrative-{obj.id}",
        )
        if not parsed or not (parsed.narrative or "").strip():
            return fallback
        return parsed
    except Exception as e:
        logger.info("narrative Gemini soft-fail: %s", type(e).__name__)
        return fallback


async def enrich_questions(obj: LifeObject) -> QuestionsAIResult:
    fallback = deterministic_questions(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei il question planner Life Object di ORA. Proponi fino a 5 domande in italiano "
            "che aumentano la capacità di ORA di aiutare (non casuali). "
            "Non chiedere password, PIN, OTP, IBAN completi, CVV. "
            "Non inventare fatti. invented_facts=false. JSON QuestionsAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "questions",
                "object": _minimal_context(obj),
                "existing_questions": [q.question for q in (obj.pending_questions or [])[:8]],
            },
            QuestionsAIResult,
            f"ora-lo-questions-{obj.id}",
        )
        if not parsed or not parsed.questions:
            return fallback
        # Merge with deterministic must-haves (identity gaps)
        det_qs = {q.question for q in fallback.questions}
        for dq in fallback.questions:
            if dq.priority == "high" and dq.question not in {x.question for x in parsed.questions}:
                parsed.questions.insert(0, dq)
        # Drop empties
        parsed.questions = [q for q in parsed.questions if (q.question or "").strip()][:6]
        # Keep det_qs unused warning quiet
        _ = det_qs
        return parsed
    except Exception as e:
        logger.info("questions Gemini soft-fail: %s", type(e).__name__)
        return fallback


async def enrich_insights(obj: LifeObject) -> InsightsAIResult:
    fallback = deterministic_insights(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei l'insight engine Life Object di ORA. Osservazioni (NON notificazioni) "
            "da storia + fatti noti: cambi fornitore, trend consumi, rata mutuo, ecc. "
            "Mai inventare. invented_facts=false. JSON InsightsAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "insights",
                "object": _minimal_context(obj),
                "deterministic_hints": [i.model_dump() for i in fallback.insights[:6]],
            },
            InsightsAIResult,
            f"ora-lo-insights-{obj.id}",
        )
        if not parsed or not parsed.insights:
            return fallback
        return parsed
    except Exception as e:
        logger.info("insights Gemini soft-fail: %s", type(e).__name__)
        return fallback


async def enrich_temporal(obj: LifeObject) -> TemporalAIResult:
    fallback = deterministic_temporal(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei il temporal reasoner Life Object di ORA. Confronta presente vs storia "
            "dello STESSO oggetto (bollette, fornitori). Solo fatti presenti. "
            "invented_facts=false. JSON TemporalAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "temporal",
                "object": _minimal_context(obj),
                "deterministic": fallback.model_dump(),
            },
            TemporalAIResult,
            f"ora-lo-temporal-{obj.id}",
        )
        if not parsed:
            return fallback
        # Keep deterministic changes if AI omitted them
        if not parsed.changes:
            parsed.changes = fallback.changes
        if not parsed.observations:
            parsed.observations = fallback.observations
        return parsed
    except Exception as e:
        logger.info("temporal Gemini soft-fail: %s", type(e).__name__)
        return fallback


async def enrich_health(obj: LifeObject) -> HealthAIResult:
    fallback = deterministic_health(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei il life-health evaluator di ORA. Valuta completeness, reliability, "
            "missing_info, opportunities, risks con reasons. Score overall derivato. "
            "Mai inventare. invented_facts=false. JSON HealthAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "health",
                "object": _minimal_context(obj),
                "deterministic": fallback.model_dump(),
            },
            HealthAIResult,
            f"ora-lo-health-{obj.id}",
        )
        if not parsed:
            return fallback
        # Prefer AI scores but keep missing_info union
        miss = list(dict.fromkeys((parsed.missing_info or []) + (fallback.missing_info or [])))
        parsed.missing_info = miss[:10]
        if parsed.overall_score is None:
            parsed.overall_score = fallback.overall_score
        return parsed
    except Exception as e:
        logger.info("health Gemini soft-fail: %s", type(e).__name__)
        return fallback


# ---------------------------------------------------------------------------
# Apply to object
# ---------------------------------------------------------------------------

def _health_label(score: float) -> str:
    if score >= 0.75:
        return "healthy"
    if score >= 0.5:
        return "ok"
    if score >= 0.3:
        return "attention"
    return "critical"


async def refresh_enrichment(
    obj: LifeObject,
    *,
    sections: Optional[List[str]] = None,
) -> LifeObject:
    """Refresh narrative / questions / insights / temporal / health on object (in-memory)."""
    apply_identity_state_migration(obj)
    wanted = set(sections or ["narrative", "questions", "insights", "temporal", "health"])

    if "narrative" in wanted:
        nar = await enrich_narrative(obj)
        prev_ver = int(obj.narrative.version or 1) if obj.narrative and obj.narrative.text else 0
        new_text = (nar.narrative or "").strip()
        bump = 1 if new_text and new_text != (obj.narrative.text or "").strip() else 0
        obj.narrative = AINarrative(
            text=new_text or (obj.narrative.text if obj.narrative else ""),
            version=max(1, prev_ver + bump) if prev_ver else 1,
            updated_at=now_iso(),
            source="gemini" if nar.ai_used else "deterministic",
            provider=nar.provider,
            model=nar.model,
            confidence=float(nar.confidence or 0.5),
            enrichment_version=AI_ENRICHMENT_VERSION,
        )
        if obj.narrative.text:
            obj.ai_summary = obj.narrative.text[:500]

    if "questions" in wanted:
        qres = await enrich_questions(obj)
        source = "gemini" if qres.ai_used else "deterministic"
        new_qs: List[PendingQuestion] = []
        for qi in qres.questions:
            if not (qi.question or "").strip():
                continue
            new_qs.append(PendingQuestion(
                question=qi.question.strip(),
                why=qi.why or "",
                priority=qi.priority,  # type: ignore[arg-type]
                category=qi.category or "missing_info",
                source=source,
            ))
        obj.pending_questions = new_qs
        if new_qs:
            obj.next_reasoning = new_qs[0].question

    if "insights" in wanted:
        ires = await enrich_insights(obj)
        source = "gemini" if ires.ai_used else "deterministic"
        obj.insights = [
            AIInsight(
                kind=ii.kind or "observation",
                title=ii.title or "Osservazione",
                detail=ii.detail or "",
                evidence=list(ii.evidence or []),
                confidence=float(ii.confidence or 0.5),
                source=source,
            )
            for ii in ires.insights
            if (ii.title or ii.detail)
        ]

    if "temporal" in wanted:
        tres = await enrich_temporal(obj)
        obj.temporal = TemporalComparison(
            observations=list(tres.observations or []),
            changes=list(tres.changes or []),
            utility_trend=basic_utility_trend(obj),
            compared_at=now_iso(),
            source="gemini" if tres.ai_used else "deterministic",
            provider=tres.provider,
            model=tres.model,
        )

    if "health" in wanted:
        hres = await enrich_health(obj)
        score = float(hres.overall_score if hres.overall_score is not None else 0.5)
        issues = list(hres.risks or []) + list(hres.missing_info or [])
        obj.health = LifeObjectHealth(
            score=score,
            label=_health_label(score),
            issues=issues[:12],
            completeness=float(hres.completeness or 0.5),
            reliability=float(hres.reliability or 0.5),
            missing_info=list(hres.missing_info or []),
            opportunities=list(hres.opportunities or []),
            risks=list(hres.risks or []),
            reasons=list(hres.reasons or []),
            updated_at=now_iso(),
            source="gemini" if hres.ai_used else "deterministic",
        )

    obj.ai_enrichment_version = AI_ENRICHMENT_VERSION
    obj.touch()
    return obj
