"""
Quale area conviene completare adesso, e perché.

    «PASSA A CASA» DEVE AVERE UNA RAGIONE, NON UN INDICE.

Fino a V3.21.3d la schermata sceglieva la prossima area così: la prima della
lista che non fosse al 100%. Non è una raccomandazione — è l'ordine del menu
travestito da consiglio, e la frase che lo accompagnava («Casa è quasi
completa») poteva essere semplicemente falsa.

Qui la regola sta in un posto solo, è deterministica, e torna anche il
**motivo** in forma di codice: la prova lo può controllare senza leggere una
frase, e l'interfaccia mostra solo la frase.

L'ordine delle regole risponde a una domanda sola: *qual è il passo più corto
che rende ORA più utile?*

1. un'area quasi completa a cui manca una cosa sola — si chiude adesso;
2. un'area a cui manca una cosa sola, ovunque sia;
3. un'area di cui ORA non sa ancora niente — lì ogni risposta vale molto;
4. altrimenti quella dove resta più peso da imparare.

A parità, vince l'ordine del percorso: una raccomandazione che cambia a ogni
ricarica non è una raccomandazione.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

#     QUANDO UN'AREA È «QUASI COMPLETA».
# Sotto questa soglia «quasi» sarebbe una parola gentile per «a metà», e la
# frase che la persona legge diventerebbe una bugia piccola.
QUASI_COMPLETA = 70

MOTIVI = {
    "quasi_completa": "{titolo} è quasi completa: manca solo una cosa.",
    "un_solo_passo": "A {titolo} manca una cosa sola.",
    "mai_iniziata": "Di {titolo} non so ancora niente.",
    "piu_da_imparare": "È in {titolo} che posso capire di più di te.",
}


def _aperti(area: Dict[str, Any]) -> int:
    return len(area.get("open_objectives") or [])


def _ha_spazio(area: Dict[str, Any]) -> bool:
    """Un'area ha spazio quando le manca qualcosa che si può ancora chiedere."""
    return int(area.get("percent") or 0) < 100 and _aperti(area) > 0


def _peso_di(area_id: str) -> float:
    from life_profile.areas import area as trova

    trovata = trova(area_id)
    return float(trovata.weight) if trovata else 1.0


def _ordine(area: Dict[str, Any]) -> int:
    return int(area.get("order") or 99)


def next_recommended_area(
    areas: Iterable[Dict[str, Any]],
    *,
    exclude: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    L'area da consigliare adesso, con il suo motivo.

    Torna `None` quando non c'è niente da consigliare — e allora non si
    consiglia niente, invece di indicare un'area a caso.

    `exclude` serve al pannello di un'area: il consiglio è *dove andare dopo*,
    e «continua con quella in cui sei già» non è un passo.
    """
    candidati: List[Dict[str, Any]] = [
        a for a in (areas or [])
        if _ha_spazio(a) and a.get("area_id") != exclude
    ]
    if not candidati:
        return None

    def scelta(area: Dict[str, Any], codice: str) -> Dict[str, Any]:
        titolo = str(area.get("title") or "")
        return {
            "area_id": area.get("area_id"),
            "title": titolo,
            "percent": int(area.get("percent") or 0),
            "reason_code": codice,
            "reason": MOTIVI[codice].format(titolo=titolo),
        }

    # 1 · quasi completa, e le manca una cosa sola: è il passo più corto.
    quasi = [a for a in candidati if int(a.get("percent") or 0) >= QUASI_COMPLETA and _aperti(a) == 1]
    if quasi:
        return scelta(max(quasi, key=lambda a: (int(a.get("percent") or 0), -_ordine(a))), "quasi_completa")

    # 2 · una cosa sola, ovunque sia.
    singole = [a for a in candidati if _aperti(a) == 1]
    if singole:
        return scelta(max(singole, key=lambda a: (int(a.get("percent") or 0), -_ordine(a))), "un_solo_passo")

    # 3 · un'area di cui ORA non sa ancora niente.
    vuote = [a for a in candidati if int(a.get("percent") or 0) == 0]
    if vuote:
        return scelta(min(vuote, key=_ordine), "mai_iniziata")

    # 4 · dove resta più peso da imparare.
    def spazio(a: Dict[str, Any]) -> float:
        return _peso_di(str(a.get("area_id"))) * (100 - int(a.get("percent") or 0)) / 100.0

    return scelta(max(candidati, key=lambda a: (spazio(a), -_ordine(a))), "piu_da_imparare")
