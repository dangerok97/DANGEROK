"""
Il piano come lo legge chi l'ha chiesto.

    DALL'ALTRA PARTE NON C'È CHI HA SCRITTO L'ORCHESTRATORE.

C'è qualcuno che ha detto «sposta il dentista alle sei» e adesso vuole sapere
se è spostato. Gli stati con cui il backend ragiona restano dove sono e non
cambiano — servono a decidere, e decidere non è raccontare. Qui accanto ne
nasce un secondo insieme, che serve solo a essere letto.

    «FATTO.» — NON «state=completed, verified=true».

È la stessa disciplina della scheda delle telefonate, per la stessa ragione:
il giorno in cui uno stato tecnico finisce davanti a una persona, è perché
qualcuno ha avuto fretta, e da lì in poi ce ne finiscono altri.

    E LA FRASE PIÙ DIFFICILE È QUELLA CHE NON RASSICURA.

«Non sono riuscita a completarlo» è scomoda da mostrare e va mostrata: un
piano che fallisce in silenzio lascia una persona convinta che una cosa sia
stata fatta. Fra le due, la frase scomoda è quella che costa meno.
"""

from __future__ import annotations

from typing import Any, Dict, List

# Come si legge, stato per stato. Una riga, al presente, in italiano.
COME_SI_LEGGE: Dict[str, str] = {
    "proposed": "Ti propongo una cosa",
    "waiting_authority": "Aspetto il tuo via libera",
    "authorised": "Pronta a partire",
    "executing": "Sto chiamando",
    "waiting_user": "Serve una tua decisione",
    "applying": "Sto aggiornando le tue cose",
    "completed": "Fatto",
    "failed": "Non sono riuscita a completarlo",
    "cancelled": "Lasciato perdere",
}

#     TRE STATI CHIEDONO QUALCOSA. GLI ALTRI RACCONTANO.
# Serve a un elenco che deve poter dire «questi aspettano te» senza filtrare
# su nove stati sperando di ricordarseli tutti.
ASPETTANO_TE = ("proposed", "waiting_authority", "waiting_user")


def in_one_line(plan) -> str:
    """
    Che cosa sta succedendo a questo proposito, in una frase.

        L'ULTIMA COSA VERA, NON L'ETICHETTA DELLO STATO.

    La storia del piano porta già la frase che descrive dove è arrivato — «Lo
    studio non può alle 18», «Appuntamento spostato alle 18:00», «Non ha
    risposto nessuno» — ed è sempre più precisa dell'etichetta. L'etichetta
    resta come rete: un piano appena nato non ha ancora una storia.
    """
    for riga in reversed(plan.history or []):
        detto = (getattr(riga, "says", "") or "").strip()
        if detto:
            return detto
    stato = str(plan.state or "")
    return COME_SI_LEGGE.get(stato, "In corso") + "."


def as_a_card(plan) -> Dict[str, Any]:
    """
    Un piano come si legge in elenco.

        NIENTE DI TECNICO QUI DENTRO.

    Non c'è la chiave di idempotenza, non c'è il nome della missione, non c'è
    l'identificativo dell'oggetto canonico — quello soprattutto, che è lo
    stesso dato che non viaggia con la voce e non ha motivo di viaggiare
    nemmeno qui.
    """
    stato = str(plan.state or "")
    return {
        "plan_id": plan.plan_id,
        "goal": plan.goal or "",
        "reason": plan.reason or "",
        "what_it_touches": _in_italiano(plan.domain, plan.operation),
        "status_label": COME_SI_LEGGE.get(stato, "In corso"),
        "summary": in_one_line(plan),
        "needs_you": bool(plan.needs_user_decision) or stato in ASPETTANO_TE,
        #     DUE ESITI, DUE CAMPI — COME PER LE TELEFONATE.
        # Dove è arrivato il giro è una cosa; se il mondo è davvero cambiato è
        # un'altra. Un campo solo mentirebbe, e mentirebbe dalla parte
        # rassicurante.
        "done": stato == "completed",
        "verified": bool(plan.verified),
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def in_full(plan) -> Dict[str, Any]:
    """Il piano per intero, storia compresa. Sempre in italiano."""
    scheda = as_a_card(plan)
    scheda["history"] = [
        {
            "at": riga.at,
            "says": riga.says,
            "status_label": COME_SI_LEGGE.get(str(riga.state or ""), ""),
        }
        for riga in (plan.history or [])
    ]
    #     PERCHÉ NON È RIUSCITO SI DICE, NON SI NASCONDE IN UN CODICE.
    if plan.error:
        scheda["why_not"] = plan.error
    return scheda


def what_you_can_answer(plan) -> List[str]:
    """
    Che cosa una persona può rispondere adesso.

    Vuoto quando non c'è niente da rispondere, e non è la stessa cosa di «non
    si sa»: un piano in corso non aspetta nessuno, e mostrargli dei pulsanti
    vorrebbe dire chiedere una decisione a chi non ne deve prendere nessuna.
    """
    stato = str(plan.state or "")
    if stato in ("proposed", "waiting_authority"):
        return ["yes", "no"]
    if stato == "waiting_user":
        #     LE RISPOSTE VERE LE ELENCA LA CONTINUATION, NON QUESTO FILE.
        # Qui si dice soltanto che ce n'è una da dare: quali siano dipende da
        # che cosa ha proposto la controparte, e lo sa chi c'era.
        return ["decide"]
    return []


def _in_italiano(domain: str, operation: str) -> str:
    """Che cosa tocca questo piano, detto senza nomi di tabelle."""
    cosa = {
        "calendar": "il calendario",
        "commitments": "i tuoi impegni",
        "study": "il tuo piano di studio",
    }.get((domain or "").strip(), "")
    verbo = {
        "reschedule": "spostare", "book": "prenotare", "cancel": "disdire",
        "complete": "chiudere", "postpone": "rimandare",
    }.get((operation or "").strip(), "")
    if verbo and cosa:
        return f"{verbo} — {cosa}"
    return cosa or verbo or ""
