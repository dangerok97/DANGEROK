"""Knowledge Gap — domain-specific missing info (never random field filling)."""
from __future__ import annotations

import re
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
        {
            "key": "doc.piano_di_studi",
            "label": "piano di studi",
            "information_gain": 0.9,
            "prefer_document": True,
            "document_type": "piano_di_studi",
            "benefit_code": "studio_universita",
            "question_template": (
                "Se hai il piano di studi, caricalo: "
                "estraggo esami e percorsi senza farti compilare un questionario."
            ),
            "when": ["studio.active", "studio.universita"],
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
    # What somebody owns beyond the roof over their head. Kept apart from
    # `finanze`, which is about money moving month to month: these are standing
    # things — another flat, a loan still running, savings set aside — and they
    # change what advice is realistic in a way that a monthly outgoing does not.
    # Every one of them is offered, never required, and the area that carries
    # them is marked sensitive.
    "patrimonio": [
        {
            "key": "patrimonio.immobili_altri",
            "label": "altri immobili",
            "information_gain": 0.72,
            "prefer_document": False,
            "benefit_code": "patrimonio_immobili",
            "question_template": (
                "Oltre alla casa in cui vivi, possiedi altri immobili? "
                "Anche solo per sapere se tenerne conto."
            ),
        },
        {
            "key": "patrimonio.finanziamenti",
            "label": "finanziamenti in corso",
            "information_gain": 0.68,
            "prefer_document": False,
            "benefit_code": "patrimonio_finanziamenti",
            "question_template": (
                "Hai finanziamenti o prestiti ancora in corso, oltre "
                "all'eventuale mutuo?"
            ),
        },
        {
            "key": "patrimonio.risparmi",
            "label": "risparmi e investimenti",
            "information_gain": 0.6,
            "prefer_document": False,
            "benefit_code": "patrimonio_risparmi",
            "question_template": (
                "Se ti va, puoi dirmi a grandi linee se hai risparmi o "
                "investimenti da tenere in conto: serve solo a rendere i "
                "consigli realistici."
            ),
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

# Legacy alias — domains are NOT a wizard sequence.
# Gaps are ranked by information_gain across all domains; AI/user decide order.
OPENING_DOMAIN_ORDER: List[str] = [
    "casa",
    "auto",
    "studio",
    "lavoro",
    "salute",
    "famiglia",
    "assicurazioni",
    "finanze",
    "patrimonio",
    "viaggi",
    "animali",
    "abbonamenti",
    "documenti",
    "internet",
    "servizi",
]

# All domains eligible every turn (any order — benefit decides).
ALL_GAP_DOMAINS: List[str] = list(OPENING_DOMAIN_ORDER)


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
    refused_keys: Optional[Set[str]] = None,
    postponed_keys: Optional[Set[str]] = None,
) -> List[GapItem]:
    """Rank gaps by information_gain. focus_domain boosts but never locks a wizard path."""
    asked = asked_keys or set()
    refused = refused_keys or set()
    postponed = postponed_keys or set()
    skip = asked | refused | postponed
    # Scan all domains unless caller passes an explicit shortlist
    domain_list = list(domains) if domains is not None else list(ALL_GAP_DOMAINS)
    gaps: List[GapItem] = []
    for domain in domain_list:
        for raw in DOMAIN_GAPS.get(domain, []):
            key = raw["key"]
            if key in known_keys:
                continue
            if key in skip:
                continue
            if not _when_satisfied(raw.get("when"), known_keys):
                continue
            gain = float(raw.get("information_gain") or 0.5)
            # Soft boost when user just steered into a domain — not a fixed order
            if focus_domain and domain == focus_domain:
                gain = min(1.0, gain + 0.08)
            gaps.append(
                GapItem(
                    key=key,
                    domain=domain,  # type: ignore[arg-type]
                    label=raw["label"],
                    information_gain=gain,
                    prefer_document=bool(raw.get("prefer_document")),
                    document_type=raw.get("document_type"),
                    benefit_code=raw.get("benefit_code") or "",
                    question_template=raw.get("question_template") or "",
                    asked=False,
                )
            )
    gaps.sort(key=lambda g: (-g.information_gain, g.key))
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


# A mention is not a possession. "Senza mutuo" and "non ho la macchina" name
# the thing they are denying, so a plain substring test reads them backwards
# and files a fact about somebody's life that is the opposite of what they
# said. Found live: "la casa è di mia proprietà, senza mutuo" was recorded as
# having a mortgage.
_NEGATORS = ("non ", "senza ", "nessun", "niente ", "né ", "mai ")


def _negated(text: str, term: str) -> bool:
    """
    Is every mention of `term` inside a denial?

    One plain mention is enough to mean the thing exists — "ho un mutuo, non
    quello vecchio" is still a mortgage — so this only says yes when nobody
    said it plainly.
    """
    low = text or ""
    start = 0
    seen = False
    while True:
        at = low.find(term, start)
        if at < 0:
            return seen
        seen = True
        window = low[max(0, at - 28):at]
        if not any(neg in window for neg in _NEGATORS):
            return False
        start = at + len(term)


def infer_known_from_text(text: str) -> Dict[str, Any]:
    """Lightweight signals from natural language (not a form parser).

    Also fills Minimum Life Context keys when the user volunteers them so one
    utterance can cover multiple nuclei without re-asking.
    """
    raw = (text or "").strip()
    t = raw.lower()
    known: Dict[str, Any] = {}
    if any(x in t for x in ("ho comprato casa", "comprato casa", "abbiamo comprato", "acquistato casa")):
        known["casa.purchased"] = True
        known["casa.owned"] = True
        known["mlc.responsibilities"] = known.get("mlc.responsibilities") or "casa"
    # "La casa è di mia proprietà" is the same statement as "casa di proprietà";
    # only the word order differs, and a phrase list that misses it leaves the
    # profile blank for someone who answered plainly.
    if any(x in t for x in ("ho una casa", "casa di proprietà", "mia casa")) or (
        "casa" in t and "propriet" in t and not _negated(t, "propriet")
    ):
        known["casa.owned"] = True
        known["mlc.responsibilities"] = known.get("mlc.responsibilities") or "casa"
    if "affitto" in t or "inquilino" in t:
        known["casa.affitto"] = True
        known["mlc.responsibilities"] = known.get("mlc.responsibilities") or "affitto"
    if any(x in t for x in ("ho un'auto", "ho una macchina", "la mia auto", "la macchina")):
        # "Non ho la macchina" mentions a car in order to say there isn't one.
        denied_car = all(
            _negated(t, x)
            for x in ("auto", "macchina", "veicolo")
            if x in t
        )
        known["auto.owned"] = not denied_car
    if any(x in t for x in ("università", "universita", "studio", "esame", "esami")):
        known["studio.active"] = True
    if "mutuo" in t:
        if _negated(t, "mutuo"):
            # A stated "no" is knowledge: it also settles everything that
            # depended on there being one.
            known["casa.mutuo"] = False
        else:
            known["casa.owned"] = True
            known["casa.mutuo"] = True
            if "sotto controllo" in t or "ok" in t:
                known["casa.mutuo"] = "ok"
    if any(x in t for x in ("piano di studi", "piano studi")):
        known["studio.active"] = True
        known["doc.piano_di_studi"] = True
    if any(x in t for x in ("non voglio", "preferisco non", "non te lo dico", "salta")):
        known["_soft_refuse_signal"] = True

    # --- Minimum Life Context signals ---
    m_name = re.search(
        r"\b(?:mi chiamo|sono|il mio nome [eè])\s+([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ'\-]{1,40})",
        raw,
        flags=re.IGNORECASE,
    )
    if m_name:
        name = m_name.group(1).strip().rstrip(".,;:")
        # Avoid false positives like "sono stanco"
        if name.lower() not in {
            "stanco", "stanca", "qui", "là", "la", "lo", "un", "una", "in", "a",
            "di", "studente", "studentessa", "lavoratore",
        }:
            known["mlc.identity.name"] = name
            known["identity.preferred_name"] = name

    m_city = re.search(
        r"\b(?:vivo|abito|sto)\s+(?:a|ad|in|nel|nella|a)\s+([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ\s'\-]{1,40})",
        raw,
        flags=re.IGNORECASE,
    )
    if m_city:
        city = m_city.group(1).strip().rstrip(".,;:")
        city = re.split(r"\s+e\s+|\s*,\s*", city, maxsplit=1)[0].strip()
        if len(city) >= 2:
            known["mlc.life_places.home"] = city
            known["casa.citta"] = city

    m_job = re.search(
        r"\blavoro(?:\s+come)?\s+([A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ\s'\-]{1,60})",
        raw,
        flags=re.IGNORECASE,
    )
    if m_job or re.search(r"\b(?:lavoro|lavoratore|impiegat[oa]|architett[oa]|ingegner[ea])\b", t):
        if m_job:
            role = m_job.group(1).strip().rstrip(".,;:")
            role = re.split(r"\s+e\s+|\s+ma\s+", role, maxsplit=1)[0].strip()
            if role and role.lower() not in {"e", "anche", "poco", "tanto"}:
                known["lavoro.ruolo"] = role
                known["mlc.responsibilities"] = role
        known["lavoro.active"] = True

    works = bool(
        known.get("lavoro.active")
        or known.get("lavoro.ruolo")
        or re.search(r"\blavoro\b", t)
    )
    studies = bool(
        known.get("studio.active")
        or re.search(r"\b(?:studio|studiare|universit[aà]|esame|esami)\b", t)
    )
    if works and studies:
        known["mlc.current_situation"] = "lavoro_studio"
        known["studio.active"] = True
        known["lavoro.active"] = True
    elif works:
        known["mlc.current_situation"] = "lavoro"
    elif studies:
        known["mlc.current_situation"] = "studio"
        known["studio.active"] = True

    # Immediate priority cues
    pri = None
    m_pri = re.search(
        r"(?:pi[uù]\s+importante|priorit[aà]|vorrei\s+(?:che\s+)?(?:mi\s+)?aiutassi\s+(?:con|a)|"
        r"devo\s+(?:preparare|organizzare|gestire)|preparare\s+(?:gli\s+)?esami|"
        r"organizzare\s+(?:lo\s+)?studio|gestire\s+il\s+lavoro)",
        t,
    )
    if "preparare gli esami" in t or "preparare esami" in t or "gli esami" in t:
        pri = "preparare gli esami"
        known["studio.esame"] = True
        known["studio.active"] = True
    elif "organizzare lo studio" in t or "organizzare studio" in t:
        pri = "organizzare lo studio"
    elif "gestire il lavoro" in t or "gestire lavoro" in t:
        pri = "gestire il lavoro"
    elif "scadenze" in t:
        pri = "ricordare scadenze"
    elif "viaggio" in t or "vacanza" in t:
        pri = "preparare un viaggio"
        known["viaggi.destinazione"] = known.get("viaggi.destinazione") or True
    elif m_pri:
        pri = raw.strip()[:180]
    if pri:
        known["mlc.immediate_priority"] = pri

    return known
