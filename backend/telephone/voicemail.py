"""
Ha risposto una persona o una segreteria?

    UN INDIZIO SOLO NON E' UN FATTO.

«Segreteria» si dichiara solo quando due segnali indipendenti dicono la stessa
cosa: l'operatore che ha riconosciuto una macchina *e* una frase da messaggio
registrato, oppure due frasi da messaggio registrato diverse. Uno solo resta un
sospetto — si annota, ma non diventa l'esito della telefonata.

I segnali:

- **l'operatore** (`machine_detection` di Vonage): un evento `machine` o
  `human` sulla chiamata. È il segnale ufficiale, ed è anche quello che sbaglia
  su una persona che risponde con un lungo «pronto, chi parla?».
- **la trascrizione** di quello che si sente: «lasci un messaggio dopo il
  segnale», «casella vocale», «segreteria telefonica». Una persona vera che
  dice «segreteria» in una frase non basta da sola — per questo servono due
  frasi diverse, o la conferma dell'operatore.

Niente audio conservato: si guardano le parole già trascritte e l'evento
dell'operatore, e nient'altro.
"""

from __future__ import annotations

import re
from typing import Dict, List

# Le frasi di un messaggio registrato. Ogni voce è un segnale a sé: due voci
# diverse sono due indizi, la stessa voce sentita due volte è uno.
_REGISTRATO: Dict[str, str] = {
    "lascia_un_messaggio": r"\blasci(?:a|ate|are)?\s+(?:pure\s+)?(?:un|il\s+suo|il\s+tuo)\s+messaggio\b",
    "dopo_il_segnale": r"\b(?:dopo|al)\s+(?:il\s+)?(?:segnale|bip|beep|tono)(?:\s+acustico)?\b",
    "segreteria": r"\bsegreteria\s+telefonica\b",
    "casella_vocale": r"\bcasella\s+vocale\b",
    "registra_messaggio": r"\bregistr(?:a|are|i)\s+(?:il\s+)?(?:suo|tuo)?\s*messaggio\b",
    "non_posso_rispondere": r"\bnon\s+(?:posso|possiamo)\s+rispondere\b",
    "leave_a_message": r"\bleave\s+(?:a|your)\s+message\b",
    "after_the_tone": r"\bafter\s+the\s+(?:tone|beep)\b",
}
_COMPILATI = {nome: re.compile(rx, re.I) for nome, rx in _REGISTRATO.items()}

Verdict = str  # "voicemail" | "suspected" | ""


class VoicemailWatch:
    """Raccoglie i segnali e dice che cosa se ne può concludere."""

    def __init__(self) -> None:
        self.carrier = ""          # "" · "machine" · "human"
        self._indizi: List[str] = []

    def carrier_says(self, answered_by: str) -> None:
        """Quello che ha riconosciuto l'operatore: «machine» o «human»."""
        detto = (answered_by or "").strip().lower()
        if detto in ("machine", "human"):
            self.carrier = detto

    def heard(self, words: str) -> None:
        """Le parole di chi ha risposto, già trascritte."""
        testo = " ".join((words or "").split())
        if not testo:
            return
        for nome, rx in _COMPILATI.items():
            if nome not in self._indizi and rx.search(testo):
                self._indizi.append(nome)

    @property
    def signals(self) -> List[str]:
        fuori = list(self._indizi)
        if self.carrier:
            fuori.insert(0, f"carrier:{self.carrier}")
        return fuori

    @property
    def verdict(self) -> Verdict:
        """
        «voicemail» solo con due segnali indipendenti. Uno solo: «suspected».

        Se l'operatore ha detto «persona», servono comunque due frasi da
        messaggio registrato: una segreteria personalizzata con la voce del
        proprietario può ingannare l'operatore, una persona che dice una frase
        sola no.
        """
        frasi = len(self._indizi)
        if self.carrier == "machine" and frasi >= 1:
            return "voicemail"
        if frasi >= 2:
            return "voicemail"
        if self.carrier == "machine" or frasi == 1:
            return "suspected"
        return ""

    def report(self) -> Dict[str, object]:
        return {"verdict": self.verdict, "signals": self.signals}
