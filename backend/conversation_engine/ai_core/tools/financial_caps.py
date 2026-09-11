"""
Il tool con cui ORA guarda quello che sa dei soldi di una persona.

    UNO SOLO, E DI SOLA LETTURA.

Non c'e' un secondo tool per l'orizzonte e un terzo per le domande aperte:
sarebbe un modo di far scegliere al modello quale verita' guardare, e la
verita' e' una. Questo restituisce tutto quello che c'e', diviso per come lo
si sa — quello che ORA sa, quello che ha letto, quello che deve chiedere — e
il modello ci scrive sopra una frase.

La differenza fra le tre categorie non e' un dettaglio di formato: e' la sola
cosa che non deve sbagliare. «Il tuo affitto e' 760» detto quando 760 e'
soltanto una riga letta in un'email e' una bugia con l'aria di un servizio.

E la seconda regola, che vive nel modo in cui i dati escono di qui: nessun
saldo, nessun «ti rimarranno». Le somme che escono sono etichettate per
quello che sono — «somma di cio' che conosco» — e l'elenco di cosa manca
viaggia insieme, cosi' che una risposta che lo ignora sia visibilmente una
risposta che ha ignorato qualcosa.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from conversation_engine.ai_core.models import Observation

logger = logging.getLogger("ora.ai_core.tools.financial")


async def what_do_i_know_about_money(
    arguments: Dict[str, Any], runtime: Dict[str, Any],
) -> Observation:
    """
    READ_ONLY. Tutto quello che ORA ha sui soldi di questa persona.

    `about` restringe a una cosa sola — «casa», «affitto» — e serve alle
    domande su una situazione: chiedere «cosa sai delle spese per la casa» e
    ricevere tutto sarebbe come non aver chiesto.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return Observation(
            kind="tool", name="what_do_i_know_about_money", status="failed",
            payload={"status": "failed", "reason": "NOT_CONFIGURED"},
        )

    days = int(arguments.get("days") or 30)
    about = str(arguments.get("about") or "").strip().lower()

    from financial.knowledge import what_ora_knows

    try:
        everything = await what_ora_knows(db, uid, days=max(1, min(days, 120)))
    except Exception as e:
        logger.info("financial read soft-fail: %s", type(e).__name__)
        return Observation(
            kind="tool", name="what_do_i_know_about_money", status="failed",
            payload={"status": "failed", "reason": "READ_FAILED"},
        )

    #     UN FILTRO CHE NON TROVA NIENTE NON E' NON SAPERE NIENTE.
    #
    # Il filtro `about` confronta sottostringhe: chiedere «cosa sapevi di
    # questi movimenti» cerca la parola «movimenti» dentro «Stipendio ACME
    # SRL» e «Notaio per acquisto casa», e non la trova. Fin qui il risultato
    # tornava vuoto con `nothing_known: true`, e ORA lo diceva alla persona —
    # «non risultavano registrati» — a proposito di due cose che sapeva
    # benissimo: una gliel'aveva confermata lei stessa, l'altra l'aveva letta
    # sul suo conto.
    #
    # Quindi quando il filtro svuota una risposta che non era vuota, torna
    # quella intera e si dice che il filtro non ha agganciato niente. Restringere
    # e' un aiuto; far sparire non lo e'.
    narrowed_to_nothing = ""
    if about:
        narrower = _only_about(everything, about)
        if (
            narrower["so"] or narrower["ho_letto"] or narrower["devo_chiederti"]
        ):
            everything = narrower
        else:
            narrowed_to_nothing = about

    empty = not (
        everything["so"] or everything["ho_letto"] or everything["devo_chiederti"]
    )

    return Observation(
        kind="tool", name="what_do_i_know_about_money", status="ok",
        payload={
            "status": "ok",
            "nothing_known": empty,
            # Quando c'e', dice che la parola chiesta non ha agganciato niente
            # e che quello che segue e' tutto quello che ORA sa: senza, una
            # risposta piu' larga del previsto sembrerebbe una svista.
            "nothing_matched_that_word": narrowed_to_nothing,
            # Le tre categorie, con i nomi che dicono cosa sono. Il modello le
            # legge cosi' e deve parlarne cosi'.
            "what_ora_knows": everything["so"],
            "what_ora_only_read": everything["ho_letto"],
            "what_needs_their_word": everything["devo_chiederti"],
            "what_is_coming": everything["in_arrivo"],
            # Com'e' messa la fonte adesso. Sta qui e non nel prompt perche'
            # e' la cosa che cambia il tempo verbale di tutta la risposta.
            "the_bank_right_now": everything.get("la_banca") or {},
            # I movimenti per forma: cosa torna, cosa e' successo una volta.
            "movements_by_shape": everything.get("movimenti_osservati") or {},
            # E la somma parziale del mese, con la sua etichetta.
            "this_month_partial": everything.get("questo_mese") or {},
            # Scritto qui, dentro il payload, perche' e' dove il modello
            # guarda. Una regola che sta solo nel prompt di sistema si perde
            # in fondo a una conversazione lunga.
            "how_to_say_it": (
                "Se `nothing_matched_that_word` non è vuoto, quella parola non "
                "ha agganciato niente e quello che segue è tutto quello che sai "
                "dei suoi soldi: non dire che non risultava niente. "
                "Di' come lo sai. Quello che sta in `what_ora_knows` lo puoi "
                "affermare; quello che sta in `what_ora_only_read` va detto "
                "come l'hai letto — «ho letto in un messaggio che…» — e non "
                "come un fatto; quello che sta in `what_needs_their_word` è "
                "una domanda, non una notizia. "
                "Non sommare per dire quanto resterà: non conosci il saldo, e "
                "una sottrazione fra le cose che conosci non è un saldo. Se "
                "manca qualcosa per rispondere, dillo invece di stimarlo. "
                "Guarda `the_bank_right_now`: se `posso_leggere_adesso` è "
                "falso il conto non è più collegato, quindi non conosci il "
                "saldo attuale — puoi dire quale risultava l'ultima volta che "
                "hai potuto leggerlo, e che non puoi confermare che sia "
                "ancora così. Non dire che leggerai i movimenti, non usare il "
                "presente per il saldo, non promettere di controllare. "
                "In `movements_by_shape`, «ricorrente» vuol dire soltanto che "
                "si ripete: un movimento singolo non è una spesa ricorrente "
                "per quanto grande, e una voce con `identificato: false` non "
                "ha un nome — chiamala come la scrive la banca e di' che non "
                "hai ancora capito cosa sia, senza inventare una categoria. "
                "`this_month_partial.differenza_parziale` è la somma dei "
                "movimenti che hai letto, non quello che resta: se la citi, "
                "dille come si chiama."
            ),
        },
    )


async def confirm_money_question(
    arguments: Dict[str, Any], runtime: Dict[str, Any],
) -> Observation:
    """
    REVERSIBLE_WRITE. La persona ha risposto a una domanda aperta sui soldi.

    Un si' fa entrare nel modello della vita quello che era stato solo letto;
    un no lo lascia dov'e'. In entrambi i casi la domanda si chiude — e' la
    stessa domanda, e non deve tornare a chiedere.

    Il permesso non e' implicito: `confirmed` arriva da una risposta della
    persona, e chi chiama questo tool sta riferendo quella risposta. Il
    modello non puo' confermare per conto suo, perche' una conferma che non
    e' stata data e' esattamente il modo in cui una cosa letta diventa una
    cosa creduta.
    """
    uid = runtime.get("user_id") or ""
    db = runtime.get("db")
    if not uid or db is None:
        return Observation(
            kind="tool", name="confirm_money_question", status="failed",
            payload={"status": "failed", "reason": "NOT_CONFIGURED"},
        )

    about = str(arguments.get("about") or "").strip()
    if not about:
        return Observation(
            kind="tool", name="confirm_money_question", status="failed",
            payload={"status": "failed", "reason": "INVALID_INPUT",
                     "why": "serve sapere di quale domanda si parla"},
        )
    if "confirmed" not in arguments:
        return Observation(
            kind="tool", name="confirm_money_question", status="failed",
            payload={"status": "failed", "reason": "INVALID_INPUT",
                     "why": "serve la risposta della persona, sì o no"},
        )

    from financial.knowledge import resolve_open_question

    out = await resolve_open_question(
        db, uid, about=about, confirmed=bool(arguments.get("confirmed")),
    )
    if not out.get("resolved"):
        return Observation(
            kind="tool", name="confirm_money_question", status="not_found",
            payload={"status": "not_found", **out},
        )
    return Observation(
        kind="tool", name="confirm_money_question", status="ok",
        payload={"status": "ok", **out},
    )


def _only_about(everything: Dict[str, Any], about: str) -> Dict[str, Any]:
    """
    Quello che riguarda una cosa sola.

    Il confronto e' sulle parole con cui la cosa e' chiamata, ed e' volutamente
    grossolano: e' un filtro per una domanda, non un giudizio su cosa
    appartiene a cosa. Quello lo fa il collegamento alla situazione, altrove.
    """
    def matches(row: Dict[str, Any]) -> bool:
        return about in str(row.get("cosa") or "").lower()

    return {
        "so": [r for r in everything["so"] if matches(r)],
        "ho_letto": [r for r in everything["ho_letto"] if matches(r)],
        "devo_chiederti": [
            r for r in everything["devo_chiederti"]
            if about in str(r.get("cosa") or "").lower()
        ],
        "in_arrivo": everything["in_arrivo"],
    }
