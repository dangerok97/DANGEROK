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
    state_pub = {
        k: v for k, v in (obj.state or {}).items()
        if v not in (None, "", [], {}) and not str(k).startswith("_")
    }
    return {
        "id": obj.id,
        "type": obj.type,
        "title": obj.title,
        "status": obj.status,
        "identity": {k: v for k, v in (obj.identity or {}).items() if v not in (None, "", [], {})},
        "state": state_pub,
        "identity_keys": dict(obj.identity_keys or {}),
        "documents_count": len(obj.documents or []),
        "goals_count": len(obj.goals or []),
        "relationships_count": len(obj.relationships or []),
        "history_tail": hist_summaries,
        "document_sources": list(getattr(obj, "document_sources", None) or obj.documents or []),
        "total_sources": int(getattr(obj, "total_sources", None) or obj.source_count or 0),
        "assimilated_kinds": list(getattr(obj, "assimilated_kinds", None) or []),
        "role": "Gemini=consultant; backend=authority on type/title/merge/fields",
    }


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


# ---------------------------------------------------------------------------
# Deterministic Italian fallbacks
# ---------------------------------------------------------------------------

def deterministic_narrative(obj: LifeObject) -> NarrativeAIResult:
    """Personal-consultant narrative: what it is, what ORA knows, gaps, help, risks, next doc.

    Never invent / never dump raw field lists.
    """
    t = obj.type
    identity = obj.identity or {}
    state = obj.state or {}
    parts: List[str] = []

    if t == "HOME":
        addr = _safe_str(
            identity.get("address")
            or identity.get("property_address")
            or (obj.identity_keys or {}).get("address_norm")
        )
        parts.append(
            f"Questa è la tua casa{(' a ' + addr) if addr else ''}."
            if addr else
            "Questa è una casa in ORA, ancora senza indirizzo stabile."
        )
        known: List[str] = []
        if identity.get("cadastral_data") or identity.get("cadastral") or (obj.identity_keys or {}).get("cadastral"):
            known.append("dati catastali")
        lender = _safe_str(state.get("lender"))
        installment = _safe_str(state.get("monthly_installment"))
        if lender and installment:
            known.append(f"mutuo con {lender} (rata ~{installment})")
        elif lender:
            known.append(f"mutuo con {lender}")
        supplier = _safe_str(state.get("utility_supplier") or state.get("supplier"))
        amount = _safe_str(state.get("utility_amount") or state.get("amount_total") or state.get("amount"))
        if supplier and amount:
            known.append(f"utenze con {supplier} (ultima bolletta {amount})")
        elif supplier:
            known.append(f"fornitore utenze {supplier}")
        if known:
            parts.append("ORA sa già: " + "; ".join(known) + ".")
        missing: List[str] = []
        if not addr:
            missing.append("indirizzo completo")
        if not (identity.get("cadastral_data") or (obj.identity_keys or {}).get("cadastral")):
            missing.append("riferimento catastale")
        if missing:
            parts.append("Manca ancora: " + ", ".join(missing) + ".")
        parts.append("ORA può aiutarti a tenere insieme mutuo, utenze e documenti senza duplicare la casa.")
        if not lender and not state.get("mortgage_assimilated"):
            parts.append("Un prossimo documento utile sarebbe il contratto di mutuo, se presente.")
        elif not supplier:
            parts.append("Un prossimo documento utile sarebbe l'ultima bolletta utenze.")
        else:
            parts.append("Se cambi fornitore o rata, carica il nuovo documento: aggiorno lo stato della stessa casa.")
    elif t == "VEHICLE":
        plate = _safe_str(identity.get("plate") or (obj.identity_keys or {}).get("plate"))
        brand = _safe_str(identity.get("brand"))
        model = _safe_str(identity.get("model"))
        label = " ".join(x for x in (brand, model) if x).strip() or "veicolo"
        parts.append(
            f"Questo è il tuo {label}" + (f" (targa {plate})." if plate else ", ancora senza targa primaria.")
        )
        company = _safe_str(state.get("insurance_company") or state.get("company"))
        if company:
            parts.append(f"ORA conosce l'assicurazione con {company}.")
        if not plate:
            parts.append("Manca la targa per unificare libretto e polizza.")
        parts.append("Carica polizza o libretto per rafforzare identità e scadenze.")
    elif t in ("UNIVERSITY", "COURSE"):
        inst = _safe_str(identity.get("institution") or identity.get("university") or (obj.identity_keys or {}).get("institution"))
        course = _safe_str(state.get("course_name") or state.get("subject") or identity.get("course_name"))
        if inst and course:
            parts.append(f"Il tuo percorso riguarda {course} presso {inst}.")
        elif inst:
            parts.append(f"Hai un legame universitario con {inst}.")
        else:
            parts.append("Hai un oggetto di studio, ma mancano ateneo o corso.")
        parts.append("ORA può collegare esami, dispense e scadenze allo stesso percorso.")
    elif t == "JOB":
        emp = _safe_str(identity.get("employer") or state.get("employer") or (obj.identity_keys or {}).get("employer"))
        if emp:
            parts.append(f"Il tuo lavoro è collegato a {emp}.")
        else:
            parts.append("Hai un oggetto Lavoro, ma manca il datore di lavoro.")
        parts.append("Una busta paga o un contratto rafforza affidabilità senza inventare dati.")
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
        parts.append("Prenotazioni e documenti di viaggio aggiornano questo stesso oggetto.")
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
    """Concept-based gap questions (Knowledge Gap Engine)."""
    from life_objects.knowledge_gaps import build_gap_questions

    return QuestionsAIResult(
        questions=build_gap_questions(obj),
        invented_facts=False,
        ai_used=False,
    )


def deterministic_insights(obj: LifeObject) -> InsightsAIResult:
    """Observations, not descriptions — never «hai una casa»."""
    items: List[InsightItemAI] = []
    state = obj.state or {}
    changes = detect_state_changes(obj)
    series = utility_amount_series(obj)
    trend = basic_utility_trend(obj)

    supplier_changes = [
        ch for ch in changes
        if ch.get("field") in ("supplier", "utility_supplier")
    ]
    if len(supplier_changes) >= 2:
        items.append(InsightItemAI(
            kind="observation",
            title="Cambi fornitore ripetuti",
            detail=(
                f"Hai cambiato fornitore energia/utenze {len(supplier_changes)} volte "
                "nelle fonti osservate."
            ),
            evidence=[str(ch.get("at") or "") for ch in supplier_changes[:4]],
            confidence=0.85,
        ))
    elif len(supplier_changes) == 1:
        ch = supplier_changes[0]
        items.append(InsightItemAI(
            kind="change",
            title="Cambio fornitore",
            detail=f"Fornitore passato da «{ch.get('from')}» a «{ch.get('to')}».",
            evidence=[str(ch.get("at") or "")],
            confidence=0.8,
        ))

    for ch in changes[:5]:
        field = ch.get("field")
        if field in ("supplier", "utility_supplier"):
            continue  # handled above
        if field in ("amount_total", "amount", "utility_amount"):
            items.append(InsightItemAI(
                kind="trend",
                title="Importo bolletta aggiornato",
                detail=f"Ultimo importo osservato: {ch.get('to')} (prima {ch.get('from')}).",
                evidence=[str(ch.get("at") or "")],
                confidence=0.7,
            ))
        elif field in ("company", "insurance_company"):
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
            title="Documentazione casa in crescita",
            detail="Rogito/mutuo/bolletta (o equivalenti) stanno consolidando lo stesso oggetto Casa.",
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

    # Drop descriptive fluff
    filtered = []
    for it in items:
        blob = f"{it.title} {it.detail}".lower()
        if "hai una casa" in blob or blob.strip() in ("hai una casa", "hai un lavoro"):
            continue
        filtered.append(it)

    return InsightsAIResult(insights=filtered[:8], invented_facts=False, ai_used=False)


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
    """Health 2.0 — explainable dimensions. Never 100% if open merges / unassimilated mutuo / dup Q."""
    from life_objects.assimilation import mortgage_assimilated, open_real_conflicts, utility_assimilated
    from life_objects.knowledge_gaps import concept_satisfied
    from life_objects.link_states import summarize_pending_links

    missing: List[str] = []
    opportunities: List[str] = []
    risks: List[str] = []
    reasons: List[str] = []
    t = obj.type
    identity = obj.identity or {}
    state = obj.state or {}
    ik = obj.identity_keys or {}

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
    identity_completeness = present / max(1, len(needed_identity)) if needed_identity else (
        0.6 if (identity or ik) else 0.35
    )
    if t == "HOME" and concept_satisfied(obj, "cadastral"):
        identity_completeness = min(1.0, identity_completeness + 0.15)
        reasons.append("Catastale presente rafforza identity_completeness.")
    elif t == "HOME" and "cadastral" not in missing and not concept_satisfied(obj, "cadastral"):
        missing.append("cadastral")

    # State completeness by type
    state_needed = {
        "HOME": ["lender_or_utility"],
        "VEHICLE": ["insurance_company"],
        "JOB": [],
        "TRAVEL": ["start_date"],
    }.get(t, [])
    state_hits = 0
    state_total = max(1, len(state_needed)) if state_needed else 1
    if t == "HOME":
        state_total = 2
        if mortgage_assimilated(obj) or state.get("lender"):
            state_hits += 1
        else:
            missing.append("mortgage_state")
        if utility_assimilated(obj) or state.get("utility_supplier") or state.get("supplier"):
            state_hits += 1
        else:
            missing.append("utility_state")
    else:
        for key in state_needed:
            if key == "insurance_company" and (
                state.get("insurance_company") or state.get("company")
            ):
                state_hits += 1
            elif state.get(key):
                state_hits += 1
            else:
                missing.append(key)
    state_completeness = state_hits / max(1, state_total) if state_needed or t == "HOME" else 0.5

    # Reliability
    reliability = 0.45
    n_docs = len(obj.documents or [])
    if n_docs:
        reliability += min(0.3, 0.08 * n_docs)
        reasons.append(f"{n_docs} documenti collegati migliorano reliability.")
    if obj.confidence:
        reliability = (reliability + float(obj.confidence)) / 2
    if obj.status == "uncertain":
        reliability = min(reliability, 0.35)
        risks.append("Identità uncertain")
        reasons.append("Stato uncertain riduce reliability.")

    # Source consistency
    source_consistency = 0.7
    if n_docs >= 2:
        source_consistency = min(1.0, 0.7 + 0.05 * n_docs)
        reasons.append("Più fonti documentali migliorano source_consistency.")
    if obj.status == "uncertain":
        source_consistency = min(source_consistency, 0.4)

    # Temporal confidence
    series = utility_amount_series(obj)
    temporal_confidence = 0.3
    if len(series) >= 2:
        temporal_confidence = 0.75
        reasons.append("Serie temporale utenze ≥2 punti.")
    elif len(series) == 1:
        temporal_confidence = 0.45
    elif len(obj.history or []) >= 3:
        temporal_confidence = 0.5

    # Pending conflicts / links
    conflicts = open_real_conflicts(obj)
    link_counts = summarize_pending_links(obj.public() if hasattr(obj, "public") else {})
    pending_conflict_score = min(1.0, conflicts * 0.5)
    quiet_links = link_counts.get("LINK_PROBABLE", 0) + link_counts.get("LINK_UNCERTAIN", 0)
    pending_links_score = min(1.0, quiet_links * 0.25 + conflicts * 0.5)
    if conflicts:
        reliability -= 0.15
        risks.append("Conflitto reale in sospeso")
        reasons.append("REAL_CONFLICT aperti: score abbassato.")
    # Quiet LINK_PROBABLE must NOT tank health like conflicts
    if link_counts.get("LINK_PROBABLE", 0) and not conflicts:
        reasons.append("LINK_PROBABLE silenziosi: non disturbano l'utente.")

    # Duplicate / stale questions penalty
    qtexts = [(q.question or "").strip().lower() for q in (obj.pending_questions or [])]
    dup_q = len(qtexts) - len(set(qtexts))
    if dup_q > 0:
        reliability -= 0.05 * dup_q
        reasons.append("Domande duplicate: reliability ridotta.")

    # Never claim full health if mortgage docs exist but not assimilated
    hist_blob = " ".join(
        (h.summary or "") + str((h.delta or {}).get("properties", {}))
        for h in (obj.history or [])
    ).lower()
    docs_blob = " ".join(obj.documents or []).lower()
    mutuo_seen = "mutuo" in hist_blob or "doc_mutuo" in docs_blob or any(
        "mutuo" in str((h.delta or {}).get("properties", {}).get("document_type") or "")
        for h in (obj.history or [])
    )
    if t == "HOME" and mutuo_seen and not mortgage_assimilated(obj):
        risks.append("Mutuo non assimilato")
        reasons.append("Mutuo visto ma non assimilato nello state: no 100% healthy.")
        state_completeness = min(state_completeness, 0.4)
        reliability = min(reliability, 0.55)

    if obj.merge_proposals and conflicts:
        opportunities.append("Risolvere il conflitto reale per ripristinare coerenza")
    if t == "HOME" and (state.get("utility_supplier") or state.get("supplier")) and len(series) >= 2:
        opportunities.append("Confrontare andamento bollette nel tempo")
    if t == "HOME" and not mortgage_assimilated(obj) and not state.get("lender"):
        opportunities.append("Collegare il mutuo se presente")
    if t == "VEHICLE" and not (state.get("insurance_company") or state.get("company")):
        opportunities.append("Aggiungere polizza per scadenze")

    for w in (obj.last_reasoning or {}).get("worsens") or []:
        risks.append(str(w))

    reliability = max(0.0, min(1.0, reliability))
    ai_conf = float(obj.ai_confidence or 0.0)

    # Weighted score — conflicts / unassimilated hard-cap below 1.0
    overall = (
        identity_completeness * 0.22
        + state_completeness * 0.18
        + reliability * 0.18
        + source_consistency * 0.12
        + temporal_confidence * 0.10
        + (1.0 - pending_conflict_score) * 0.10
        + (1.0 - pending_links_score) * 0.05
        + ai_conf * 0.05
    )
    overall = max(0.0, min(1.0, round(overall, 3)))
    if conflicts or (t == "HOME" and mutuo_seen and not mortgage_assimilated(obj)) or dup_q > 0:
        overall = min(overall, 0.92)
        reasons.append("Cap <1.0: conflitti / mutuo non assimilato / domande duplicate.")

    if identity or ik:
        reasons.append("Chiavi di identità presenti.")
    if missing:
        reasons.append("Mancano: " + ", ".join(missing[:6]))

    return HealthAIResult(
        completeness=round(identity_completeness, 3),
        reliability=round(reliability, 3),
        identity_completeness=round(identity_completeness, 3),
        state_completeness=round(state_completeness, 3),
        source_consistency=round(source_consistency, 3),
        temporal_confidence=round(temporal_confidence, 3),
        pending_conflicts=round(pending_conflict_score, 3),
        pending_links=round(pending_links_score, 3),
        ai_confidence=round(ai_conf, 3),
        missing_info=missing[:10],
        opportunities=opportunities[:6],
        risks=risks[:6],
        reasons=reasons[:10],
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
            "Sei il consulente personale Life Object di ORA (Gemini=consultant). "
            "Scrivi in italiano: cos'è l'oggetto, cosa ORA sa, cosa manca, come ORA può aiutare, "
            "rischi, prossimo documento utile, relazioni note. "
            "Separa mentalmente Facts (confermati) da Hypotheses (supposizioni) — non mischiarli. "
            "NON elencare campi. NON inventare. NON ripetere campi grezzi. "
            "NON promuovere ipotesi a fatti. Il backend resta autorità. invented_facts=false. "
            "JSON NarrativeAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "narrative_consultant",
                "object": _minimal_context(obj),
                "style": "consulente personale, frasi brevi, zero invenzioni",
            },
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
    from life_objects.knowledge_gaps import filter_ai_questions

    fallback = deterministic_questions(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei il question planner Life Object di ORA (consultant). "
            "Domande su CONCETTI mancanti (non nomi campo grezzi). "
            "Separa Questions da Facts/Hypotheses/Recommendations/Decisions — non mischiare. "
            "Se catastale/mutuo già presenti sotto qualsiasi alias, NON chiederli. "
            "Mai «Hai un mutuo?» se il mutuo è già assimilato. "
            "Rispetta never_ask_again (non ripropporre). "
            "No password/PIN/OTP/IBAN/CVV. invented_facts=false. JSON QuestionsAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "questions_concepts",
                "object": _minimal_context(obj),
                "known_concepts_hint": "use only canonical concepts; backend filters aliases",
                "existing_questions": [q.question for q in (obj.pending_questions or [])[:8]],
            },
            QuestionsAIResult,
            f"ora-lo-questions-{obj.id}",
        )
        if not parsed or not parsed.questions:
            return fallback
        for dq in fallback.questions:
            if dq.priority == "high" and dq.question not in {x.question for x in parsed.questions}:
                parsed.questions.insert(0, dq)
        parsed.questions = [
            q for q in filter_ai_questions(obj, parsed.questions)
            if (q.question or "").strip()
        ][:6]
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
            "Sei l'insight engine Life Object di ORA. Produci OSSERVAZIONI, non descrizioni. "
            "Esempio buono: «hai cambiato fornitore energia due volte in 18 mesi». "
            "Esempio vietato: «hai una casa». "
            "Solo fatti da storia. Mai inventare. invented_facts=false. JSON InsightsAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "insights_observations",
                "object": _minimal_context(obj),
                "deterministic_hints": [i.model_dump() for i in fallback.insights[:6]],
            },
            InsightsAIResult,
            f"ora-lo-insights-{obj.id}",
        )
        if not parsed or not parsed.insights:
            return fallback
        # Drop descriptive fluff from AI
        cleaned = []
        for ii in parsed.insights:
            blob = f"{ii.title} {ii.detail}".lower()
            if "hai una casa" in blob or blob.strip() == "hai un lavoro":
                continue
            cleaned.append(ii)
        parsed.insights = cleaned or fallback.insights
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
    """Health 2.0: backend dimensions are authoritative; Gemini may only suggest reasons."""
    fallback = deterministic_health(obj)
    if not life_object_gemini_enabled():
        return fallback
    try:
        system = (
            "Sei il life-health evaluator di ORA (consultant). "
            "Puoi suggerire reasons/opportunities/risks. "
            "NON dichiarare 100% healthy se ci sono merge aperti, mutuo non assimilato "
            "o domande duplicate. invented_facts=false. JSON HealthAIResult."
        )
        parsed = await _chat_enrich(
            system,
            {
                "task": "health_2",
                "object": _minimal_context(obj),
                "deterministic": fallback.model_dump(),
            },
            HealthAIResult,
            f"ora-lo-health-{obj.id}",
        )
        if not parsed:
            return fallback
        # Backend dimensions win
        parsed.identity_completeness = fallback.identity_completeness
        parsed.state_completeness = fallback.state_completeness
        parsed.source_consistency = fallback.source_consistency
        parsed.temporal_confidence = fallback.temporal_confidence
        parsed.pending_conflicts = fallback.pending_conflicts
        parsed.pending_links = fallback.pending_links
        parsed.ai_confidence = fallback.ai_confidence
        parsed.completeness = fallback.completeness
        parsed.reliability = fallback.reliability
        parsed.overall_score = fallback.overall_score
        miss = list(dict.fromkeys((parsed.missing_info or []) + (fallback.missing_info or [])))
        parsed.missing_info = miss[:10]
        if not parsed.reasons:
            parsed.reasons = fallback.reasons
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
        id_c = float(hres.identity_completeness if hres.identity_completeness is not None else hres.completeness or 0.5)
        st_c = float(hres.state_completeness if hres.state_completeness is not None else 0.5)
        obj.health = LifeObjectHealth(
            score=score,
            label=_health_label(score),
            issues=issues[:12],
            completeness=id_c,
            reliability=float(hres.reliability or 0.5),
            identity_completeness=id_c,
            state_completeness=st_c,
            source_consistency=float(hres.source_consistency if hres.source_consistency is not None else 0.5),
            temporal_confidence=float(hres.temporal_confidence if hres.temporal_confidence is not None else 0.5),
            pending_conflicts=float(hres.pending_conflicts or 0.0),
            pending_links=float(hres.pending_links or 0.0),
            ai_confidence=float(hres.ai_confidence if hres.ai_confidence is not None else obj.ai_confidence or 0.0),
            missing_info=list(hres.missing_info or []),
            opportunities=list(hres.opportunities or []),
            risks=list(hres.risks or []),
            reasons=list(hres.reasons or []),
            dimensions={
                "identity_completeness": id_c,
                "state_completeness": st_c,
                "reliability": float(hres.reliability or 0.5),
                "source_consistency": float(hres.source_consistency or 0.5),
                "temporal_confidence": float(hres.temporal_confidence or 0.5),
                "pending_conflicts": float(hres.pending_conflicts or 0.0),
                "pending_links": float(hres.pending_links or 0.0),
                "ai_confidence": float(hres.ai_confidence or 0.0),
                "score": score,
            },
            updated_at=now_iso(),
            source="gemini" if hres.ai_used else "deterministic",
        )

    obj.ai_enrichment_version = AI_ENRICHMENT_VERSION
    # Quietly suppress questions/suggestions blocked by never_ask_again Decisions
    try:
        from life_objects.knowledge_model.integration import apply_never_ask_filters
        apply_never_ask_filters(obj)
    except Exception:
        pass
    obj.touch()
    return obj
