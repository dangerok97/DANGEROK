"""
Il giro completo: una domanda, una chiamata al giudizio, e quello che c'e'.

    POCHI TOKEN, ALTA PERTINENZA.

Il piano e' piccolo di proposito. Per una domanda semplice — «dentista» — c'e'
un passo solo: si capisce di cosa si parla, si espande per relazione, si
raggruppa. Per una composta — «cosa so dell'acquisto della casa e quali
documenti ci sono» — i passi sono gli stessi, e cambia solo *quanto* si
raccoglie, perche' il giudizio ha nominato piu' di una parte della vita.

Quello che non c'e', e non deve arrivare: un agente che decide da solo di
fare un altro giro, una seconda chiamata per riordinare i risultati, un
riassunto generato quando i fatti bastano. Ogni chiamata in piu' e' un costo
per persona per ricerca, e la maggior parte delle ricerche non ne ha bisogno.

Il conto di quanto e' costato viaggia con la risposta — righe guardate, righe
tenute, chiamate fatte — perche' una ricerca che rallenta lo fa in silenzio
finche' qualcuno non guarda quei tre numeri.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("ora.lifesearch")


async def search_a_life(
    db, owner_id: str, query: str, *, language: str = "it",
    interpret_with_model: bool = True, synthesize: bool = True,
) -> Dict[str, Any]:
    """
    Cerca dentro la vita di questa persona, e riporta anche cosa e' costato.

    `interpret_with_model=False` salta il giudizio e cerca con le parole
    scritte: serve ai test, che devono poter girare senza un provider, e non
    e' un'alternativa silenziosa — la risposta dice sempre come ha capito.
    """
    from lifesearch.cache import fingerprint, remember, remembered
    from lifesearch.index import life_index
    from lifesearch.interpret import fall_back, what_are_they_looking_for
    from lifesearch.present import as_sections, conflicts_kept
    from lifesearch.resolve import gather
    from lifesearch.synthesis import in_a_few_lines

    words = (query or "").strip()
    if not words:
        return _nothing("")

    index = await life_index(db, owner_id)

    calls = 0
    wanted = None
    from_cache = False

    if interpret_with_model:
        # La stessa domanda, con la vita ferma, non si paga due volte.
        #
        #     UNA RISPOSTA VECCHIA SU UNA VITA CAMBIATA E' PEGGIO DI NIENTE.
        #
        # Quindi la chiave porta dentro com'era la vita: se e' arrivato un
        # documento o e' cambiata una situazione, l'impronta cambia e questa
        # scorciatoia sparisce da sola.
        mark = await fingerprint(db, owner_id)
        wanted = remembered(owner_id, words, mark)
        from_cache = wanted is not None
        if wanted is None:
            wanted = await what_are_they_looking_for(
                words, index=index, language=language,
            )
            calls += 1
            if wanted is not None:
                remember(owner_id, words, mark, wanted)

    if wanted is None:
        wanted = fall_back(words)

    # La domanda com'e' stata scritta: serve a confrontare le cifre, che
    # nessuna parola potrebbe mai collegare a un movimento.
    wanted["asked"] = words

    found = await gather(db, owner_id, wanted=wanted)
    sections = as_sections(found, wanted=wanted)

    # La sintesi solo quando l'elenco non e' una risposta. «Documenti della
    # casa» vuole i documenti, non un paragrafo — e un paragrafo davanti a
    # una richiesta di navigazione e' una cosa in mezzo.
    said = None
    if sections and wanted.get("needs_synthesis") and synthesize:
        said = await in_a_few_lines(words, sections=sections, language=language)
        calls += 1

    return {
        "hai_cercato": words,
        # Cosa ORA ha capito della domanda, in una riga. Non un'etichetta
        # tecnica: quella resta di sotto, per chi verifica.
        "che_cosa_cerchi": wanted.get("what_they_want") or "",
        # Il paragrafo, quando la domanda ne chiedeva uno.
        "in_sintesi": said,
        "risultati": sections,
        # Due verita' diverse restano due.
        "in_conflitto": conflicts_kept(found),
        "niente_trovato": not sections,
        "in_parole": _in_words(sections, wanted),
        # Solo per il QA e per chi misura. Non arriva a nessuna schermata.
        "_qa": {
            "kind": wanted.get("kind"),
            "mode": wanted.get("mode"),
            "concepts": wanted.get("concepts"),
            "sources": wanted.get("sources"),
            "relation_hypotheses": wanted.get("relation_hypotheses"),
            "uncertainty": wanted.get("uncertainty"),
            "about_situations": wanted.get("about_situations"),
            "matched_by": {
                group: sorted({row["matched_by"] for row in rows})
                for group, rows in found.rows.items()
            },
            "candidate_count": found.looked_at,
            "retrieved_count": found.kept,
            # Le chiamate che questa ricerca costa a chi la usa. Quelle del
            # QA — rileggere, riverificare — si contano altrove, o il numero
            # che misura il prodotto diventa il numero che misura noi.
            "product_calls": calls,
            "interpretation_from_cache": from_cache,
            "used_words": wanted.get("words"),
            "judgement_answered": not wanted.get("the_judgement_did_not_answer"),
        },
    }


def _in_words(sections, wanted: Dict[str, Any]) -> str:
    """
    Una riga sopra i risultati, scritta dal codice.

    Non un riassunto generato: i fatti sono gia' li' sotto, e pagarne la
    rilettura a un modello per ottenere una frase di cortesia sarebbe un
    costo per ogni ricerca di ogni persona.
    """
    if not sections:
        return "Non ho trovato niente su questo."
    how_many = sum(len(s["cosa_c_e"]) for s in sections)
    where = ", ".join(s["gruppo"].lower() for s in sections[:3])
    return f"{how_many} cose, fra {where}."


def _nothing(query: str) -> Dict[str, Any]:
    return {
        "hai_cercato": query, "che_cosa_cerchi": "", "in_sintesi": None,
        "risultati": [],
        "in_conflitto": [], "niente_trovato": True,
        "in_parole": "Scrivi qualcosa e guardo nella tua vita.",
        "_qa": {"kind": None, "candidate_count": 0, "retrieved_count": 0,
                "product_calls": 0},
    }


async def what_ora_knows_about(
    db, owner_id: str, situation_id: str,
) -> Dict[str, Any]:
    """
    Una parte della vita, aperta: cosa so, cosa sta succedendo, cosa manca.

    E' la stessa raccolta della ricerca, con la situazione gia' nota — quindi
    zero chiamate al giudizio: non c'e' niente da interpretare quando la
    domanda e' «questa».
    """
    from lifesearch.present import as_sections, conflicts_kept
    from lifesearch.resolve import gather

    wanted = {
        "kind": "situation_lookup",
        "about_situations": [situation_id],
        "words": [],
        "since": None,
        "looking_forward": True,
        "what_they_want": "",
    }
    found = await gather(db, owner_id, wanted=wanted)
    return {
        "risultati": as_sections(found, wanted=wanted),
        "in_conflitto": conflicts_kept(found),
        "_qa": {
            "candidate_count": found.looked_at,
            "retrieved_count": found.kept,
            "product_calls": 0,
        },
    }
