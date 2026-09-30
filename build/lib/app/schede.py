"""Scheda di preparazione e autorizzazione del controllo (Vol. IV, Allegato 23)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Campo:
    codice: str
    etichetta: str
    sezione: str
    aiuto: str = ""
    multilinea: bool = False


_A = "A. Dati identificativi del contribuente"
_B = "B. Dati sulla posizione fiscale del contribuente"
_C = "C. Elementi informativi di rilievo ai fini della selezione e strategie operative"

CAMPI_IMPRESA: tuple[Campo, ...] = (
    Campo("A1", "Partita IVA", _A), Campo("A2", "Codice fiscale", _A),
    Campo("A3", "Sede legale", _A),
    Campo("A4", "Sede dell'amministrazione e luogo di conservazione delle scritture contabili", _A),
    Campo("A5", "Luogo di esercizio dell'attivita'", _A), Campo("A6", "Codice attivita'", _A),
    Campo("A7", "Oggetto dell'attivita'", _A), Campo("A8", "Domicilio fiscale", _A),
    Campo("A9", "Generalita' del rappresentante legale (solo per le imprese)", _A),
    Campo("A10", "Fonti delle notizie riportate ai punti precedenti", _A, multilinea=True),
    Campo("B1", "Annualita' da sottoporre a controllo", _B),
    Campo("B2", "Volume d'affari dichiarato per le annualita' da controllare", _B),
    Campo("B3", "Ricavi dichiarati per le annualita' da controllare", _B),
    Campo("B4", "Regime contabile dichiarato", _B),
    Campo("B5", "Adesione a istituti di compliance",  _B,
          "Ravvedimento operoso, voluntary disclosure, interpelli, ruling internazionale, adempimento "
          "collaborativo, comunicazioni dell'Agenzia delle Entrate finalizzate all'emersione delle basi imponibili",
          multilinea=True),
    Campo("B6", "Precedenti fiscali", _B, multilinea=True), Campo("B7", "Precedenti di polizia", _B, multilinea=True),
    Campo("B8", "Fonti delle notizie riportate ai punti precedenti", _B, multilinea=True),
    Campo("C1", "Risultanze agli atti", _C, multilinea=True),
    Campo("C2", "Accertamenti svolti", _C,
          "Investigazioni svolte nella fase preparatoria (sopralluoghi, banche dati, documenti presso enti esterni)",
          multilinea=True),
    Campo("C3", "Ragioni giustificative del controllo", _C,
          "D'iniziativa o a richiesta di altri reparti/organi (quali); fonte di innesco del servizio",
          multilinea=True),
    Campo("C4", "Oggetto del controllo", _C,
          "Atto di gestione o necessita' ricognitiva, arco temporale e tributi di interesse", multilinea=True),
    Campo("C5", "Luogo di esecuzione dell'attivita' ispettiva", _C),
    Campo("C6", "Modalita' esecutive del controllo", _C,
          "Indicazione previsionale della metodologia ispettiva", multilinea=True),
)

# Per i privati non imprenditori la sezione A e B si rimodulano (note 2 e 4 dell'Allegato 23)
_PRIVATO = {"A1": "Luogo e data di nascita", "A2": "Residenza anagrafica", "A3": "Codice fiscale",
            "A4": "Domicilio fiscale", "B2": "Reddito complessivo imponibile dichiarato per le annualita' da controllare",
            "B3": "Posizione ai fini delle sanatorie fiscali per le annualita' da controllare",
            "B4": "Precedenti fiscali"}
_SOLO_IMPRESA_PRIVATO = {"A5", "A6", "A7", "A8", "A9", "B5", "B6"}


def campi_allegato23(privato: bool = False) -> list[Campo]:
    if not privato:
        return list(CAMPI_IMPRESA)
    out = []
    for c in CAMPI_IMPRESA:
        if c.codice in _SOLO_IMPRESA_PRIVATO:
            continue
        out.append(Campo(c.codice, _PRIVATO.get(c.codice, c.etichetta), c.sezione, c.aiuto, c.multilinea))
    return out


def completezza(valori: dict[str, str], privato: bool = False) -> list[str]:
    """Codici dei campi ancora vuoti. La scheda ammette l'impossibilita' di acquisire un dato
    (nota 1) purche' se ne indichi la ragione: un campo vuoto va segnalato, non riempito."""
    return [c.codice for c in campi_allegato23(privato) if not (valori.get(c.codice) or "").strip()]
