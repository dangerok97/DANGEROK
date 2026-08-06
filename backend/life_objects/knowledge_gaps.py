"""Knowledge Gap Engine — questions check CONCEPTS, not raw field names.

If cadastral present under any alias → don't ask.
Never ask "Hai un mutuo?" when mortgage already assimilated.
Semantic questions only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from life_objects.assimilation import mortgage_assimilated, open_real_conflicts, utility_assimilated
from life_objects.models import LifeObject, QuestionItemAI
from life_objects.property_registry import concept_present


def _add(
    qs: List[QuestionItemAI],
    *,
    question: str,
    why: str,
    priority: str = "medium",
    category: str = "missing_info",
    concept: str = "",
) -> None:
    qs.append(
        QuestionItemAI(
            question=question,
            why=why,
            priority=priority,  # type: ignore[arg-type]
            category=category,
        )
    )
    # Attach concept via why prefix for filtering (kept in why naturally)


def concept_satisfied(obj: LifeObject, concept: str) -> bool:
    return concept_present(
        concept,
        identity=obj.identity,
        state=obj.state,
        properties=obj.properties,
        identity_keys=obj.identity_keys,
    )


def build_gap_questions(obj: LifeObject) -> List[QuestionItemAI]:
    """Build semantic gap questions. Never invent; never re-ask known concepts."""
    qs: List[QuestionItemAI] = []
    t = obj.type

    if t == "HOME":
        if not concept_satisfied(obj, "home_address"):
            _add(
                qs,
                question="Qual è l'indirizzo completo di questa casa?",
                why="Senza indirizzo ORA non può unificare rogito, mutuo e bollette sulla stessa casa.",
                priority="high",
                concept="home_address",
            )
        if not concept_satisfied(obj, "cadastral"):
            _add(
                qs,
                question="Hai il riferimento catastale (foglio/particella/sub)?",
                why="Il catastale rafforza l'identità e evita una seconda Casa.",
                priority="medium",
                concept="cadastral",
            )
        # Mortgage: only if NOT already assimilated / concept present
        if not mortgage_assimilated(obj) and not concept_satisfied(obj, "mortgage"):
            # Softer help question — still allowed only when concept absent
            # But NEVER the blunt "Hai un mutuo?" when docs already imply assimilation path
            docs = " ".join(obj.documents or []).lower()
            hist = " ".join((h.summary or "") + str((h.delta or {}).get("properties", {})) for h in (obj.history or []))
            if "mutuo" not in hist.lower() and "mutuo" not in docs:
                _add(
                    qs,
                    question="Se hai un finanziamento sull'immobile, con quale banca?",
                    why="Sapere banca e rata aiuta ORA a monitorare impegno finanziario.",
                    priority="medium",
                    category="help_ability",
                    concept="mortgage",
                )
        if not concept_satisfied(obj, "pod"):
            _add(
                qs,
                question="Conosci il codice POD della fornitura elettrica?",
                why="Il POD collega bollette luce alla stessa casa in modo stabile.",
                priority="low",
                category="help_ability",
                concept="pod",
            )
        if concept_satisfied(obj, "utility_supplier") and not concept_satisfied(obj, "utility_amount"):
            _add(
                qs,
                question="Puoi caricare l'ultima bolletta con l'importo?",
                why="Serve a leggere andamento consumi/spesa nel tempo.",
                priority="medium",
                category="help_ability",
                concept="utility_amount",
            )

    elif t == "VEHICLE":
        if not concept_satisfied(obj, "vehicle_plate"):
            _add(
                qs,
                question="Qual è la targa del veicolo?",
                why="La targa è la chiave primaria per unificare libretto e polizza.",
                priority="high",
                concept="vehicle_plate",
            )
        if not concept_satisfied(obj, "insurance"):
            _add(
                qs,
                question="Con quale compagnia è assicurata l'auto?",
                why="Serve per scadenze e confronti di copertura.",
                priority="medium",
                category="help_ability",
                concept="insurance",
            )
        if not concept_satisfied(obj, "vehicle_vin"):
            _add(
                qs,
                question="Hai il numero di telaio (VIN)?",
                why="Il VIN rafforza l'identità se la targa cambia o manca.",
                priority="low",
                concept="vehicle_vin",
            )

    elif t in ("UNIVERSITY", "COURSE"):
        if not concept_satisfied(obj, "institution"):
            _add(
                qs,
                question="Presso quale università o istituto studi?",
                why="L'ateneo è la chiave per non duplicare percorsi di studio.",
                priority="high",
                concept="institution",
            )
        if not concept_satisfied(obj, "course"):
            _add(
                qs,
                question="Qual è il corso di laurea o la materia principale?",
                why="Serve a collegare esami, dispense e scadenze al percorso giusto.",
                priority="medium",
                category="help_ability",
                concept="course",
            )

    elif t == "JOB":
        if not concept_satisfied(obj, "employer"):
            _add(
                qs,
                question="Qual è il nome del datore di lavoro?",
                why="Il datore di lavoro identifica in modo stabile l'oggetto Lavoro.",
                priority="high",
                concept="employer",
            )
        _add(
            qs,
            question="Puoi caricare l'ultima busta paga o il contratto?",
            why="Documenti reali riducono domande e migliorano affidabilità.",
            priority="medium",
            category="help_ability",
        )

    elif t == "TRAVEL":
        if not concept_satisfied(obj, "travel_destination"):
            _add(
                qs,
                question="Qual è la destinazione del viaggio?",
                why="La destinazione definisce l'oggetto viaggio e collega prenotazioni.",
                priority="high",
                concept="travel_destination",
            )
        if not (obj.state or {}).get("start_date"):
            _add(
                qs,
                question="Quando parti?",
                why="Le date consentono scadenze e priorità nel tempo.",
                priority="medium",
                category="help_ability",
            )
    else:
        if not obj.documents:
            _add(
                qs,
                question="Hai un documento che descrive meglio questo oggetto?",
                why="Una fonte documentale aumenta affidabilità e riduce ambiguità.",
                priority="medium",
                category="help_ability",
            )

    if obj.status == "uncertain":
        _add(
            qs,
            question="Queste informazioni appartengono allo stesso oggetto di vita?",
            why="Lo stato è incerto: una conferma evita duplicati.",
            priority="high",
            category="clarify",
        )

    # Only REAL_CONFLICT is user-facing
    if open_real_conflicts(obj) > 0:
        _add(
            qs,
            question="Ho trovato dati incompatibili sullo stesso oggetto. Quale versione è corretta?",
            why="Solo i conflitti reali richiedono una scelta esplicita.",
            priority="high",
            category="clarify",
        )

    # Cap + dedupe + filter forbidden re-asks
    return _finalize(qs, obj)


def _finalize(qs: List[QuestionItemAI], obj: LifeObject) -> List[QuestionItemAI]:
    seen = set()
    unique: List[QuestionItemAI] = []
    cadastral_ok = concept_satisfied(obj, "cadastral")
    mortgage_ok = mortgage_assimilated(obj) or concept_satisfied(obj, "mortgage")
    for q in qs:
        key = (q.question or "").strip().lower()
        if not key or key in seen:
            continue
        # Hard bans
        if cadastral_ok and ("catastale" in key or "catasto" in key or "foglio" in key):
            continue
        if mortgage_ok and ("hai un mutuo" in key or key.startswith("hai un finanziamento")):
            continue
        if mortgage_ok and "mutuo" in key and "rata" not in key:
            # Don't re-ask mortgage existence
            continue
        seen.add(key)
        unique.append(q)
    return unique[:6]


def filter_ai_questions(obj: LifeObject, questions: List[Any]) -> List[Any]:
    """Drop AI questions that violate concept presence / hard bans."""
    cadastral_ok = concept_satisfied(obj, "cadastral")
    mortgage_ok = mortgage_assimilated(obj) or concept_satisfied(obj, "mortgage")
    out = []
    for q in questions or []:
        text = ""
        if hasattr(q, "question"):
            text = (q.question or "").strip().lower()
        elif isinstance(q, dict):
            text = str(q.get("question") or "").strip().lower()
        else:
            continue
        if not text:
            continue
        if cadastral_ok and ("catastale" in text or "catasto" in text or "foglio/particella" in text):
            continue
        if mortgage_ok and ("hai un mutuo" in text or "mutuo su questa casa" in text):
            continue
        out.append(q)
    return out
