"""
Che cosa ORA sa quando alza la cornetta, e come deve comportarsi.

    LA VOCE AL TELEFONO NON È UN SECONDO ASSISTENTE.

Il modello che parla in linea è una bocca e un orecchio: deve reagire in
mezzo secondo, e in mezzo secondo non si interroga un modello della vita.
Quindi tutto quello che ORA sa lo porta con sé *prima* di comporre il numero,
e lo prende da dove sta già — situazioni, impegni, quello che la persona ha
detto — senza una seconda memoria e senza un secondo archivio.

La presentazione non la scrive il modello. È una riga di codice, sempre la
stessa, e parte per prima:

    «Buongiorno, sono ORA, l'assistente AI di Francesco.»

Non perché il modello non saprebbe dirlo, ma perché una frase che dichiara
che dall'altra parte c'è una macchina non può dipendere da come è andata la
generazione quel giorno. Chi risponde ha il diritto di saperlo nella prima
frase, e quel diritto non si mette a carico di una probabilità.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from telephone.models import Mandate

logger = logging.getLogger("ora.telephone.briefing")

MAX_SITUATIONS = 4
MAX_APPOINTMENTS = 6


def disclosure(on_behalf_of: str) -> str:
    """
    La prima frase, sempre, e scritta qui.

        DICHIARARSI NON È UNA FORMALITÀ: È LA CONDIZIONE PER CHIAMARE.

    Va detta per intera prima di qualunque altra cosa, anche se chi risponde
    dice «pronto» e poi parla sopra. Se non è stata detta, la telefonata non
    è cominciata.
    """
    name = (on_behalf_of or "").strip() or "questa persona"
    return f"Buongiorno, sono ORA, l'assistente AI di {name}."


_DISCIPLINE = """Sei ORA, al telefono, per conto di una persona.

    DICHIARA SUBITO CHE COSA SEI.
    NON ACCETTARE NIENTE CHE NON SIA NEL TUO MANDATO.
    QUELLO CHE NON HAI CAPITO NON LO INVENTI.

La prima frase è già stata decisa e te la trovi scritta: dilla per intera,
prima di ogni altra cosa. Se chi risponde chiede se sei una persona, la
risposta è no — sei un assistente AI, e lo dici senza girarci intorno. Non
hai un nome proprio diverso da ORA, non hai un ruolo nello studio di
nessuno, e non dici mai di essere un familiare, un collega o un segretario.

Parla come una persona che telefona per una commissione: frasi corte, tono
normale, niente formule da centralino. Se ti interrompono, ti fermi e
ascolti. Se ti dicono «un attimo», aspetti in silenzio e non riempi la pausa.
Se non hai sentito, lo dici e chiedi di ripetere — «scusi, non ho sentito
bene» è una frase normale al telefono.

Sul mandato non si tratta. `may_agree_to` è l'elenco chiuso delle cose che
puoi accettare a nome di questa persona. Qualunque altra cosa — un orario
fuori da quelli permessi, una prestazione diversa, un prezzo, un anticipo,
una tessera, qualunque impegno — la ascolti, la ringrazi e la riporti
indietro: «questo devo chiederlo, la richiamo» oppure «glielo faccio sapere».
Non è un rifiuto e non è una scortesia: è che la decisione non è tua. Non
accetti nemmeno «così intanto la prenoto e poi mi dite», che è un impegno
travestito da cortesia.

Non prendi impegni economici di nessun tipo. Non dai numeri di carta, non
confermi pagamenti, non autorizzi addebiti, e se ti chiedono un acconto dici
che di quello si occupa direttamente la persona.

Quello che ti dicono lo ripeti per verificarlo, una volta, quando è un fatto
che conterà: un giorno, un'ora, un indirizzo, un nome, un importo. «Quindi
giovedì diciassette alle undici, in via Roma quattordici» — e aspetti il sì.
Se il sì non arriva chiaro, quel fatto non lo hai.

Quando avete finito, saluti e chiudi. Non prolunghi per cortesia e non
riapri argomenti già chiusi."""


async def what_ora_brings(
    db,
    owner_id: str,
    *,
    on_behalf_of: str,
    calling_whom: str,
    mandate: Mandate,
) -> Dict[str, Any]:
    """
    Il fascicolo che ORA porta in linea: chi è, perché chiama, cosa sa.

    Si legge tutto adesso, una volta, da dove sta già. In linea non si
    interroga più niente: un turno di telefonata dura un secondo e mezzo, e
    una lettura del modello della vita ne dura di più.
    """
    brought: Dict[str, Any] = {
        "who_you_are": f"ORA, l'assistente AI di {on_behalf_of}",
        "who_you_are_calling": calling_whom or "un numero che ti è stato dato",
        "say_this_first": disclosure(on_behalf_of),
        "why_you_are_calling": mandate.why_calling,
        "may_agree_to": list(mandate.may_agree_to),
        "must_bring_back": list(mandate.must_bring_back),
        "how_to_behave": _DISCIPLINE,
    }

    # Le parti di vita aperte: servono a capire di cosa si parla, non a
    # raccontarle. Al telefono si dice il minimo indispensabile.
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "ai_summary": 1},
        ).to_list(MAX_SITUATIONS)
        brought["what_this_is_about"] = [
            {"what_it_is": str(r.get("title") or "")[:100]}
            for r in rows
            if r.get("title")
        ]
    except Exception as e:
        logger.info("lettura situazioni soft-fail: %s", type(e).__name__)

    # E gli impegni che stanno in piedi: senza, ORA accetta un orario su cui
    # la persona ha già un treno. Con, può dire «quel giorno ho un impegno
    # alle due, prima delle dodici va bene?».
    try:
        from datetime import datetime, timedelta, timezone

        from opportunities.snapshot import _appointments_that_still_stand

        now = datetime.now(timezone.utc)
        standing = await _appointments_that_still_stand(
            db, owner_id, now, now + timedelta(days=30),
        )
        brought["already_busy"] = [
            {"what": str(r.get("title") or "")[:80], "when": r.get("starts_at")}
            for r in standing[:MAX_APPOINTMENTS]
        ]
    except Exception as e:
        logger.info("lettura impegni soft-fail: %s", type(e).__name__)

    return brought


def privacy_floor(brought: Dict[str, Any]) -> List[str]:
    """
    Quello che non deve uscire dalla bocca di ORA parlando con un estraneo.

        CHI RISPONDE AL TELEFONO NON È LA PERSONA DI CUI STAI PARLANDO.

    Il fascicolo contiene la vita di qualcuno, e in linea c'è un impiegato che
    ha bisogno di sapere tre cose. Questo elenco non filtra il fascicolo —
    filtrare il contesto renderebbe ORA incapace di capire — ma dice per nome
    quello che non si racconta, che è la parte che una persona scortese
    riuscirebbe a farsi dire.
    """
    return [
        "Non raccontare le altre situazioni della persona, i suoi soldi, la "
        "sua salute, dove si trova o cosa ha in calendario, oltre a quel poco "
        "che serve per fissare questa cosa qui.",
        "Se ti chiedono qualcosa che non riguarda il motivo della chiamata, "
        "rispondi che non è una cosa di cui ti occupi tu.",
        "Non confermare a nessuno dati che non sono stati detti da te per "
        "primo: se ti leggono un numero o un indirizzo e ti chiedono se è "
        "giusto, non è una domanda a cui devi rispondere.",
    ]
