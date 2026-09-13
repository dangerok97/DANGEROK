"""
Gli stessi strumenti, scritti in un modo che costa meno da leggere.

    QUELLO CHE IL MODELLO DEVE SAPERE NON CAMBIA. CAMBIA QUANTO PESA.

Il catalogo viaggia in ogni chiamata al modello, su ogni canale, a ogni passo
di ragionamento. Misurato: trentanove strumenti, 30.818 caratteri, e il
trentasette per cento sono le descrizioni — cioè l'unica parte che serve
davvero. Il resto è struttura JSON e sette nomi di chiave ripetuti trentanove
volte:

    {"capability": "x", "name": "x", "description": "...",
     "classification": "personal", "side_effect": "READ_ONLY",
     "freshness": "n/a", "input_schema": {"type": "object", "properties":
     {"title": {"type": "string"}}}, "availability": "available",
     "risk": "read"}

`name` è la stessa cosa di `capability`. `availability` è «available» per
tutti quelli che arrivano fin qui. `freshness` è «n/a» quasi sempre. E
`{"type": "string"}` sono ventidue caratteri per dire «testo».

Qui la stessa identica informazione diventa una riga:

    create_calendar_event(title:str, start_datetime:str «ISO 8601», …)
      [personal · REVERSIBLE_WRITE] — ADD a new calendar commitment…

    NON SI TOGLIE NIENTE CHE SERVA A SCEGLIERE.

Restano tutti i nomi degli strumenti, tutti i nomi degli argomenti, quali
sono obbligatori, i valori ammessi delle enumerazioni, le descrizioni dei
parametri che portano un vincolo, e la descrizione dello strumento per
intero. Una prova lo verifica strumento per strumento: se un giorno questa
resa perdesse un argomento o un valore, quella prova cade.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Come si scrivono i tipi. Il modello li riconosce tutti, e costano un quarto.
_TIPI = {
    "string": "str",
    "number": "num",
    "integer": "int",
    "boolean": "bool",
    "array": "list",
    "object": "obj",
}

# Valori che hanno tutti: dirli è ripetere trentanove volte la stessa cosa.
_SCONTATI = {
    "classification": "personal",
    "side_effect": "READ_ONLY",
    "freshness": "n/a",
    "availability": "available",
    "risk": "read",
}


def _un_tipo(spec: Dict[str, Any]) -> str:
    """Il tipo di un argomento, com'è più corto scriverlo."""
    scelte = spec.get("enum")
    if isinstance(scelte, list) and scelte:
        return "|".join(str(s) for s in scelte)
    tipo = _TIPI.get(str(spec.get("type") or ""), str(spec.get("type") or "any"))
    if tipo == "list":
        dentro = spec.get("items") or {}
        if isinstance(dentro, dict) and dentro.get("type"):
            return f"list[{_TIPI.get(str(dentro['type']), str(dentro['type']))}]"
    return tipo


def _un_argomento(nome: str, spec: Any, obbligatorio: bool) -> str:
    if not isinstance(spec, dict):
        return nome
    pezzo = f"{nome}{'' if obbligatorio else '?'}:{_un_tipo(spec)}"
    detto = str(spec.get("description") or "").strip()
    if detto:
        # La descrizione di un argomento non è decorazione: è dove sta scritto
        # che un formato è ISO 8601 o che per una certa intenzione questo
        # strumento è quello sbagliato.
        pezzo += f" «{detto}»"
    return pezzo


def _gli_argomenti(schema: Any) -> str:
    if not isinstance(schema, dict):
        return ""
    proprieta = schema.get("properties")
    if not isinstance(proprieta, dict) or not proprieta:
        return ""
    obbligatori = set(schema.get("required") or [])
    return ", ".join(
        _un_argomento(nome, spec, nome in obbligatori)
        for nome, spec in proprieta.items()
    )


def as_one_line(tool: Dict[str, Any]) -> str:
    """Uno strumento, in una riga sola."""
    nome = str(tool.get("capability") or tool.get("name") or "").strip()
    etichette = [
        f"{chiave}={tool.get(chiave)}"
        for chiave, scontato in _SCONTATI.items()
        if tool.get(chiave) not in (None, "", scontato)
    ]
    riga = f"{nome}({_gli_argomenti(tool.get('input_schema'))})"
    if etichette:
        riga += " [" + " · ".join(etichette) + "]"
    detto = str(tool.get("description") or "").strip()
    if detto:
        riga += f" — {detto}"
    return riga


def compact_catalogue(tools: List[Dict[str, Any]]) -> List[str]:
    """
    Il catalogo intero, una riga per strumento.

    L'ordine è quello che arriva: cambiarlo cambierebbe quale strumento il
    modello vede per primo, e non è una cosa da fare per sbaglio.
    """
    return [as_one_line(t) for t in tools if isinstance(t, dict)]
