"""
Le cose che mancano, trasformate in domande a cui si può rispondere.

    UN BUCO CHE NON SI PUÒ RIEMPIRE NON È UN BUCO: È UN RIMPROVERO.

Il profilo sa due cose diverse. Da una parte gli **obiettivi di conoscenza**
(`objectives.py`): che cosa varrebbe la pena sapere di una vita, con il peso
che ha — è da lì che esce la percentuale. Dall'altra le **domande guidate**
(`guided.py`): come si chiede una cosa, con le sue opzioni.

Le due liste non coincidono, e non devono: certe cose si chiedono bene con tre
bottoni, altre no. Il guaio è che finora quello che stava solo nella prima
lista non aveva nessun modo di essere risposto.

    Misurato in app (V3.21.3c): Casa al 92%, un buco solo, e «Continua con
    Casa» non apriva niente — perché quel buco non aveva una domanda. Lo
    stesso per Studio al 67%, con tre cose mancanti e nessuna raggiungibile.

Qui si costruisce la domanda mancante dall'obiettivo stesso: l'etichetta che
la persona legge fra i «cosa manca» diventa la richiesta, e la risposta si
scrive **sotto lo stesso `ref`** che la percentuale conta. Nessuna parola
inventata: l'etichetta è quella che c'era già.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from life_profile.areas import all_areas, area
from life_profile.guided import GuidedObjective, objective, option_of
from life_profile.objectives import KnowledgeObjective, objectives_for_area

#     ALCUNE COSE SI LEGGONO, NON SI CHIEDONO.
# Quando l'obiettivo dice che un documento è la strada migliore, la domanda
# nasce già come richiesta di documento: chiedere a voce il numero di una
# polizza è chiedere a qualcuno di trascrivere male una cosa che ha in mano.
# I nomi sono quelli che il modello accetta già: inventarne di nuovi qui
# vorrebbe dire una schermata che non sa disegnare la domanda.
_CONTROLLO_DOCUMENTO = "document_upload"
_CONTROLLO_TESTO = "text"


def knowledge_objective(ref: str) -> Optional[KnowledgeObjective]:
    """L'obiettivo di conoscenza con questo riferimento, se esiste."""
    pulito = (ref or "").strip()
    if not pulito:
        return None
    for a in all_areas():
        for o in objectives_for_area(a):
            if o.ref == pulito:
                return o
    return None


def derived_objective(ref: str) -> Optional[GuidedObjective]:
    """
    La domanda costruita da un obiettivo di conoscenza senza domanda propria.

    Torna `None` quando una domanda scritta a mano c'è già: quella è sempre
    migliore, perché conosce le opzioni.
    """
    if objective(ref):
        return None
    conosciuto = knowledge_objective(ref)
    if conosciuto is None:
        return None

    vuole_documento = bool(conosciuto.prefer_document and conosciuto.document_type)
    return GuidedObjective(
        id=conosciuto.ref,
        area_id=conosciuto.area_id,
        # L'etichetta è quella che la persona ha appena letto fra i «cosa
        # manca»: riscriverla in forma di domanda vorrebbe dire inventare una
        # frase che nessuno ha controllato. Si tocca solo la maiuscola e il
        # punto interrogativo, dove la frase è già una domanda.
        question=_come_si_chiede(conosciuto.label),
        hint=(
            "Se ce l'hai, il documento è la via più veloce: lo leggo io."
            if vuole_documento
            else "Scrivilo come preferisci: lo tengo con le tue parole."
        ),
        control=_CONTROLLO_DOCUMENTO if vuole_documento else _CONTROLLO_TESTO,
        options=[],
        allow_other=False,
        allow_skip=True,
        allow_decline=True,
        sensitivity=conosciuto.sensitivity,
        weight=conosciuto.weight,
        document_type=conosciuto.document_type,
    )


#     LE PAROLE CON CUI UNA FRASE DIVENTA UNA DOMANDA.
# Solo queste: tutto il resto resta com'è. «Date esami e scadenze» è una cosa
# che manca, non una domanda, e va benissimo letta così sopra un campo di
# testo — mentre «dove vivi» senza maiuscola e senza punto interrogativo
# sembra un pezzo di frase caduto lì.
_INTERROGATIVE = (
    "dove", "quando", "quale", "quali", "quanto", "quanta", "quanti",
    "quante", "come", "chi", "che", "cosa", "perché",
)


def _come_si_chiede(etichetta: str) -> str:
    """L'etichetta con la maiuscola, e il punto interrogativo se è una domanda."""
    testo = (etichetta or "").strip()
    if not testo:
        return testo
    testo = testo[0].upper() + testo[1:]
    if testo.endswith("?"):
        return testo
    prima = testo.split()[0].lower().strip(",.;:")
    if prima in _INTERROGATIVE:
        return testo.rstrip(".") + "?"
    return testo


def any_objective(ref: str) -> Optional[GuidedObjective]:
    """La domanda scritta a mano se c'è, altrimenti quella costruita."""
    return objective(ref) or derived_objective(ref)


def open_gaps(area_completeness: Dict) -> List[Dict]:
    """I buchi di un'area, così come la completezza li ha già ordinati."""
    return list((area_completeness or {}).get("open_objectives") or [])


def first_answerable_gap(
    area_completeness: Dict,
    *,
    seen: Optional[set] = None,
) -> Optional[GuidedObjective]:
    """
    Il primo buco di quest'area a cui si può davvero rispondere.

    «Davvero» è la parola importante: si salta quello che la persona ha già
    risposto, rifiutato o dichiarato non pertinente, e si salta quello che non
    si sa nemmeno costruire — meglio non offrire niente che offrire un bottone
    che non apre.
    """
    gia = seen or set()
    for gap in open_gaps(area_completeness):
        ref = str(gap.get("ref") or "")
        if not ref or ref in gia:
            continue
        domanda = any_objective(ref)
        if domanda is not None:
            return domanda
    return None


#     QUELLO CHE ORA SA GIÀ, DETTO CON I FATTI E NON CON I NUMERI.
# «7 informazioni su 8» non è quello che ORA sa: è quanto sa. La reference
# mostra le cose — il corso di laurea, l'anno, la città — perché è così che una
# persona verifica se ORA ha capito bene, e può correggere.
_TROPPO_LUNGA = 34


def known_items(area_id: str, facts: Dict) -> List[Dict]:
    """I fatti che ORA ha davvero su quest'area, con la loro etichetta."""
    fuori: List[Dict] = []
    trovata = area(area_id)
    if trovata is None:
        return fuori
    for o in objectives_for_area(trovata):
        chiavi = (o.ref,) + tuple(o.satisfied_by or ())
        valore = next(
            (facts.get(k) for k in chiavi if facts.get(k) not in (None, "", [], {})),
            None,
        )
        if valore is None:
            continue
        detto = _come_si_dice_il_valore(o.ref, valore)
        if not detto:
            continue
        fuori.append({
            "ref": o.ref,
            "label": _etichetta_del_fatto(o, detto),
            "value": detto,
        })
    return fuori[:8]


def _come_si_dice_il_valore(ref: str, valore) -> str:
    """
    Il valore con le parole dell'opzione, quando l'opzione esiste.

    Nel profilo un'opzione è salvata con il suo identificativo — `universita`,
    `fine` — e mostrarlo così è mostrare il magazzino: l'etichetta che la
    persona aveva letto e scelto è lì accanto, e va usata quella.
    """
    grezzo = _come_si_legge(valore)
    if not grezzo:
        return ""
    scritta = objective(ref)
    if scritta is None or not scritta.options:
        return grezzo
    pezzi = []
    for parte in [p.strip() for p in grezzo.split(",")]:
        scelta = option_of(ref, parte)
        pezzi.append(scelta.label if scelta else parte)
    return ", ".join(p for p in pezzi if p)[:120]


#     UN SÌ SENZA LA SUA DOMANDA NON VUOL DIRE NIENTE.
# «Active: sì» non è un fatto che qualcuno possa verificare. Quando la risposta
# è un sì o un no, l'etichetta torna a essere la domanda — senza punto
# interrogativo, perché qui è un'affermazione.
_SI_O_NO = ("sì", "no", "si")


def _etichetta_del_fatto(o: KnowledgeObjective, valore: str) -> str:
    if valore.strip().lower() in _SI_O_NO:
        domanda = (o.label or "").strip().rstrip("?")
        if domanda:
            return domanda[0].upper() + domanda[1:]
    return _etichetta_breve(o)


def _etichetta_breve(o: KnowledgeObjective) -> str:
    """
    Il nome corto di un fatto: «Città», «Convivenza», «Corso di laurea».

    L'etichetta di un obiettivo è spesso la domanda intera («Dove si trova la
    casa?»), e davanti al valore si legge male. Quando è corta si usa com'è;
    quando è una domanda si ripiega sull'ultimo pezzo del riferimento, che è
    il nome del campo — non una parola inventata qui.
    """
    etichetta = (o.label or "").strip()
    if etichetta and len(etichetta) <= _TROPPO_LUNGA and not etichetta.endswith("?"):
        return etichetta[0].upper() + etichetta[1:]
    pezzo = (o.ref or "").rsplit(".", 1)[-1].replace("_", " ").strip()
    return (pezzo[0].upper() + pezzo[1:]) if pezzo else ""


def _come_si_legge(valore) -> str:
    """Un fatto come lo legge una persona. Mai una struttura in faccia."""
    if isinstance(valore, bool):
        return "sì" if valore else "no"
    if isinstance(valore, (int, float)):
        return str(valore)
    if isinstance(valore, str):
        return valore.strip()[:120]
    if isinstance(valore, (list, tuple)):
        pezzi = [_come_si_legge(v) for v in valore if v not in (None, "")]
        return ", ".join(p for p in pezzi if p)[:120]
    if isinstance(valore, dict):
        for chiave in ("label", "name", "title", "value", "city"):
            if valore.get(chiave):
                return _come_si_legge(valore[chiave])
    return ""


def area_of(ref: str) -> Optional[str]:
    """A quale parte della vita appartiene questo riferimento."""
    conosciuto = knowledge_objective(ref)
    if conosciuto is not None:
        return conosciuto.area_id
    scritta = objective(ref)
    if scritta is not None:
        return scritta.area_id
    return None


def area_title(area_id: str) -> str:
    trovata = area(area_id)
    return trovata.title if trovata else area_id
