"""
Chi sa ricevere l'esito di una telefonata, dominio per dominio.

    UN REGISTRO NON È UN FRAMEWORK.

Qui dentro c'è un dizionario e una funzione che ci guarda dentro. Serve
perché il giorno in cui una telefonata dovrà disdire invece che spostare, o
toccare qualcosa che non è il calendario, il punto in cui aggiungerlo sia uno
e sia evidente — non perché oggi ci sia qualcosa da astrarre: oggi c'è un
adattatore solo, e scriverne l'interfaccia per tre immaginari sarebbe
progettare contro un futuro che non è arrivato.

    E UN DOMINIO SENZA ADATTATORE NON SCRIVE NIENTE.

`adapter_for()` torna `None` invece di sollevare, e chi applica lo tratta come
un motivo per fermarsi. È la stessa disciplina che governa tutto il resto di
questa parte: una cosa che non si sa fare si dichiara, non si approssima.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def adapter_for(domain: str) -> Optional[Any]:
    """L'adattatore di questo dominio, o niente."""
    if (domain or "").strip() == "calendar":
        from telephone.domains import calendar

        return calendar
    return None


def known_domains() -> Dict[str, str]:
    """Che cosa si sa applicare, oggi. Per poterlo dire in un rapporto."""
    return {"calendar": "reschedule"}
