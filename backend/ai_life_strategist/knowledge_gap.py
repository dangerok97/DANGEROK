"""Knowledge Gap — domain-specific missing info (never random field filling)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from ai_life_strategist.models import GapItem

# Declarative gaps per domain: key → question, gain, document preference.
# Order within domain is benefit priority, not a rigid wizard sequence.
DOMAIN_GAPS: Dict[str, List[Dict[str, Any]]] = {
    "casa": [
        {
            "key": "casa.owned",
            "label": "possesso casa",
            "information_gain": 0.95,
            "prefer_document": False,
            "benefit_code": "casa_documenti",
            "question_template": "Hai una casa di proprietà, in affitto, o stai ancora valutando?",
        },
        {
            "key": "doc.rogito",
            "label": "rogito / atto",
            "information_gain": 0.92,
            "prefer_document": True,
            "document_type": "rogito",
            "benefit_code": "casa_documenti",
            "question_template": (
                "Se hai il rogito o l’atto di compravendita, caricalo: "
                "estraggo indirizzo e dati utili senza farti compilare moduli."
            ),
            "when": ["casa.purchased", "casa.owned"],
        },
        {
            "key": "casa.mutuo",
            "label": "mutuo",
            "information_gain": 0.88,
            "prefer_document": False,
            "benefit_code": "casa_mutuo_scadenze",
            "question_template": "Il mutuo è sotto controllo, oppure vuoi che ORA ti aiuti con le scadenze?",
            "when": ["casa.purchased", "casa.owned", "doc.rogito"],
        },
        {
            "key": "casa.utenze",
            "label": "utenze / bollette",
            "information_gain": 0.75,
            "prefer_document": True,
            "document_type": "bolletta",
            "benefit_code": "casa_bollette",
            "question_template": "Vuoi caricare una bolletta recente per collegare le utenze alla casa?",
            "when": ["casa.owned", "casa.purchased"],
        },
        {
            "key": "casa.assicurazione",
            "label": "assicurazione casa",
            "information_gain": 0.7,
            "prefer_document": True,
            "document_type": "polizza_casa",
            "benefit_code": "casa_assicurazione",
            "question_template": "Hai una polizza casa? Se sì, puoi caricarla o dirmi la scadenza.",
            "when": ["casa.owned", "casa.purchased"],
        },
    ],
    "auto": [
        {
            "key": "auto.owned",
            "label": "possesso auto",
            "information_gain": 0.9,
            "prefer_document": False,
            "benefit_code": "auto_scadenze",
            "question_template": "Hai un’auto o un veicolo di cui ORA dovrebbe tenere le scadenze?",
        },
        {
            "key": "doc.libretto",
            "label": "libretto",
            "information_gain": 0.85,
            "prefer_document": True,
            "document_type": "libretto",
            "benefit_code": "auto_documenti",
            "question_template": "Se hai il libretto di circolazione, caricalo: estraggo targa e dati utili.",
            "when": ["auto.owned"],
        },
        {
            "key": "auto.assicurazione_scadenza",
            "label": "scadenza RC auto",
            "information_gain": 0.8,
            "prefer_document": True,
            "document_type": "polizza_auto",
            "benefit_code": "auto_scadenze",
            "question_template": "Quando scade l’assicurazione auto, o preferisci caricare la polizza?",
            "when": ["auto.owned"],
        },
    ],
    "finanze": [
        {
            "key": "finanze.spese_ricorrenti",
            "label": "spese ricorrenti",
            "information_gain": 0.7,
            "prefer_document": False,
            "benefit_code": "finanze_budget",
            "question_template": (
                "Ci sono spese ricorrenti importanti (mutuo, affitto, abbonamenti) "
                "di cui vuoi che ORA tenga conto? Non serve l’accesso al conto."
            ),
        },
    ],
    "studio": [
        {
            "key": "studio.active",
            "label": "studio attivo",
            "information_gain": 0.9,
            "prefer_document": False,
            "benefit_code": "studio_universita",
            "question_template": "Stai studiando all’università o preparando un esame in questo periodo?",
        },
        {
            "key": "studio.universita",
            "label": "università",
            "information_gain": 0.75,
            "prefer_document": False,
            "benefit_code": "studio_universita",
            "question_template": "Quale università o percorso stai seguendo?",
            "when": ["studio.active"],
        },
        {
            "key": "studio.esame",
            "label": "esame",
            "information_gain": 0.88,
            "prefer_document": True,
            "document_type": "dispensa",
            "benefit_code": "studio_esami",
            "question_template": "Quale esame vuoi preparare? Se hai una dispensa o un programma, puoi caricarlo.",
            "when": ["studio.active"],
        },
    ],
    "lavoro": [
        {
            "key": "lavoro.ruolo",
            "label": "ruolo lavorativo",
            "information_gain": 0.7,
            "prefer_document": False,
            "benefit_code": "lavoro_scadenze",
            "question_template": "Vuoi che ORA tenga conto del tuo lavoro attuale (ruolo o azienda, in sintesi)?",
        },
    ],
    "salute": [
        {
            "key": "salute.visita",
            "label": "visite mediche",
            "information_gain": 0.75,
            "prefer_document": True,
            "document_type": "referti",
            "benefit_code": "salute_visite",
            "question_template": (
                "Hai visite o controlli in programma? Puoi dirmi la data "
                "o caricare un documento di prenotazione — senza dati clinici sensibili."
            ),
        },
    ],
    "famiglia": [
        {
            "key": "famiglia.membri",
            "label": "nucleo familiare",
            "information_gain": 0.65,
            "prefer_document": False,
            "benefit_code": "famiglia_contatti",
            "question_template": "Ci sono familiari con cui ORA dovrebbe collegare eventi o documenti?",
        },
    ],
    "animali": [
        {
            "key": "animali.pet",
            "label": "animali",
            "information_gain": 0.6,
            "prefer_document": False,
            "benefit_code": "famiglia_contatti",
            "question_template": "Hai animali domestici di cui vuoi ricordare vaccinazioni o visite?",
        },
    ],
    "viaggi": [
        {
            "key": "viaggi.destinazione",
            "label": "prossimo viaggio",
            "information_gain": 0.8,
            "prefer_document": False,
            "benefit_code": "viaggi_prep",
            "question_template": "Hai un viaggio in programma che ORA può aiutarti a organizzare?",
        },
    ],
    "documenti": [
        {
            "key": "documenti.prioritari",
            "label": "documenti prioritari",
            "information_gain": 0.55,
            "prefer_document": True,
            "document_type": "documento",
            "benefit_code": "casa_documenti",
            "question_template": "Hai un documento importante da caricare adesso (contratto, polizza, bolletta)?",
        },
    ],
    "assicurazioni": [
        {
            "key": "assicurazioni.tipo",
            "label": "polizze",
            "information_gain": 0.78,
            "prefer_document": True,
            "document_type": "polizza",
            "benefit_code": "assicurazioni_rinnovi",
            "question_template": "Quali polizze vuoi tenere sotto controllo? Puoi caricarne una.",
        },
    ],
    "abbonamenti": [
        {
            "key": "abbonamenti.list",
            "label": "abbonamenti",
            "information_gain": 0.6,
            "prefer_document": False,
            "benefit_code": "finanze_budget",
            "question_template": "Ci sono abbonamenti (streaming, palestra, telefonia) da non dimenticare?",
        },
    ],
    "internet": [
        {
            "key": "internet.contratto",
            "label": "contratto internet",
            "information_gain": 0.55,
            "prefer_document": True,
            "document_type": "contratto_internet",
            "benefit_code": "casa_bollette",
            "question_template": "Vuoi collegare il contratto internet/casa alle scadenze delle utenze?",
        },
    ],
    "servizi": [
        {
            "key": "servizi.prioritari",
            "label": "servizi",
            "information_gain": 0.4,
            "prefer_document": False,
            "benefit_code": "finanze_budget",
            "question_template": "Ci sono altri servizi della vita quotidiana su cui ORA può aiutarti?",
        },
    ],
}

# Opening domain order for first launch — benefit-driven, not alphabetical form.
OPENING_DOMAIN_ORDER: List[str] = [
    "casa",
    "auto",
    "studio",
    "lavoro",
    "salute",
    "famiglia",
    "assicurazioni",
    "finanze",
    "viaggi",
    "animali",
    "abbonamenti",
    "documenti",
    "internet",
    "servizi",
]


def _when_satisfied(when: Optional[List[str]], known: Set[str]) -> bool:
    if not when:
        return True
    return any(w in known for w in when)


def compute_gaps(
    known_keys: Set[str],
    *,
    asked_keys: Optional[Set[str]] = None,
    domains: Optional[List[str]] = None,
    focus_domain: Optional[str] = None,
) -> List[GapItem]:
    asked = asked_keys or set()
    domain_list = [focus_domain] if focus_domain else (domains or OPENING_DOMAIN_ORDER)
    gaps: List[GapItem] = []
    for domain in domain_list:
        for raw in DOMAIN_GAPS.get(domain, []):
            key = raw["key"]
            if key in known_keys:
                continue
            if key in asked:
                continue
            if not _when_satisfied(raw.get("when"), known_keys):
                # Special: if when requires purchased/owned and we have signal, ok
                continue
            gaps.append(
                GapItem(
                    key=key,
                    domain=domain,  # type: ignore[arg-type]
                    label=raw["label"],
                    information_gain=float(raw.get("information_gain") or 0.5),
                    prefer_document=bool(raw.get("prefer_document")),
                    document_type=raw.get("document_type"),
                    benefit_code=raw.get("benefit_code") or "",
                    question_template=raw.get("question_template") or "",
                    asked=False,
                )
            )
    gaps.sort(key=lambda g: (-g.information_gain, g.domain, g.key))
    return gaps


def infer_domain_from_text(text: str) -> Optional[str]:
    t = (text or "").lower()
    rules = [
        ("casa", ["casa", "appartamento", "mutuo", "rogito", "affitto", "bolletta", "utenze"]),
        ("auto", ["auto", "macchina", "targa", "libretto", "revisione", "bollo"]),
        ("studio", ["esame", "università", "universita", "studio", "laurea", "corso"]),
        ("lavoro", ["lavoro", "ufficio", "datore", "contratto di lavoro", "stipendio"]),
        ("salute", ["visita", "medico", "salute", "ospedale", "analisi"]),
        ("famiglia", ["famiglia", "moglie", "marito", "figli", "genitori"]),
        ("animali", ["cane", "gatto", "animale", "veterinario"]),
        ("viaggi", ["viaggio", "vacanza", "parto", "volo", "hotel"]),
        ("assicurazioni", ["assicurazione", "polizza", "rc auto"]),
        ("abbonamenti", ["abbonamento", "netflix", "spotify", "palestra"]),
        ("finanze", ["finanze", "budget", "spese", "rata"]),
        ("documenti", ["documento", "caricare", "pdf"]),
        ("internet", ["internet", "fibra", "wifi", "tim", "vodafone"]),
    ]
    best = None
    best_score = 0
    for domain, kws in rules:
        score = sum(1 for k in kws if k in t)
        if score > best_score:
            best_score = score
            best = domain
    return best if best_score > 0 else None


def infer_known_from_text(text: str) -> Dict[str, Any]:
    """Lightweight signals from natural language (not a form parser)."""
    t = (text or "").lower()
    known: Dict[str, Any] = {}
    if any(x in t for x in ("ho comprato casa", "comprato casa", "abbiamo comprato", "acquistato casa")):
        known["casa.purchased"] = True
        known["casa.owned"] = True
    if any(x in t for x in ("ho una casa", "casa di proprietà", "mia casa")):
        known["casa.owned"] = True
    if "affitto" in t or "inquilino" in t:
        known["casa.affitto"] = True
    if any(x in t for x in ("ho un'auto", "ho una macchina", "la mia auto", "la macchina")):
        known["auto.owned"] = True
    if any(x in t for x in ("università", "universita", "studio", "esame")):
        known["studio.active"] = True
    if "mutuo" in t:
        known["casa.owned"] = True
        if "sotto controllo" in t or "ok" in t:
            known["casa.mutuo"] = "ok"
    return known
