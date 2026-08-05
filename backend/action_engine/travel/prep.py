"""Optional prep suggestions — never mandatory medical advice."""
from __future__ import annotations

from typing import List

from action_engine.travel.models import PrepItem

_CATALOG = {
    "luggage": PrepItem(id="luggage", label="Prepara la valigia", category="luggage"),
    "docs": PrepItem(
        id="docs",
        label="Controlla CI / passaporto / biglietti",
        category="docs",
    ),
    "car": PrepItem(
        id="car",
        label="Controllo auto (gomme, liquidi, documenti)",
        category="car",
    ),
    "fuel": PrepItem(id="fuel", label="Fai benzina / ricarica EV", category="fuel"),
    "pets": PrepItem(
        id="pets",
        label="Organizza animali (trasporto, cibo, docs)",
        category="pets",
    ),
    "medicine": PrepItem(
        id="medicine",
        label="Porta i tuoi farmaci abituali (nessun consiglio medico)",
        category="medicine",
    ),
    "charger": PrepItem(id="charger", label="Caricatore / powerbank", category="charger"),
}


def build_prep_items(selected: List[str] | None) -> List[PrepItem]:
    if not selected:
        return []
    out: List[PrepItem] = []
    for code in selected:
        item = _CATALOG.get(str(code))
        if item:
            out.append(item)
    return out
