"""
Le relazioni fra le cose di una vita, scritte una volta e riusabili.

    UN DOCUMENTO CHE APPARTIENE A UNA CASA DEVE DIRLO DA QUALCHE PARTE.

Era il debito piu' grosso dello sprint precedente: i documenti non avevano
nessuna relazione registrata con le situazioni, quindi si trovavano solo per
parola — «mutuo» trovava il file chiamato «mutuo», e il contratto di mutuo
intitolato «Rogito_2026_definitivo» non lo trovava nessuno.

**Dove vivono.** Nella stessa collezione dei collegamenti fra fonti che il
Connected Life scrive gia': `connected_situation_links`. Non e' pigrizia — e'
la stessa cosa. Un collegamento dice «queste due cose parlano dello stesso
pezzo di vita», e non cambia natura a seconda che le due cose siano una mail e
un appuntamento oppure un documento e una casa. Un secondo sistema avrebbe
significato due posti da tenere in fila, due formati di provenienza, e due
risposte diverse alla domanda «perche' ORA pensa che c'entrino».

**Cosa cambia rispetto a un collegamento fra segnali.** Due cose sole. Non
c'e' un segnale dietro, quindi `signal_id` resta vuoto. E non scade: un
messaggio invecchia, l'appartenenza di un rogito alla casa che si sta
comprando no — quindi niente `expires_at`, e la riga sopravvive alla TTL che
ripulisce i collegamenti effimeri.

**Sei parole, non trenta.**

    about · part_of · related_to · supports · contradicts · supersedes

Sono relazioni fra cose di una vita, non fra righe di un database. Ogni tipo
in piu' e' una distinzione che qualcuno dovra' spiegare a qualcun altro, e che
il modello sbagliera' la meta' delle volte.

**Cosa non si scrive mai.** Il contenuto. La riga porta un riferimento e una
frase che dice perche', e niente altro: duplicare il testo di un documento
dentro il modello della vita vorrebbe dire tenerne due copie che divergono
alla prima modifica.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("ora.lifesearch.relations")

LINKS = "connected_situation_links"

# Le uniche relazioni che esistono. Poche e umane.
RELATION_TYPES = (
    "about",         # questo riguarda quello
    "part_of",       # questo sta dentro quello
    "related_to",    # si toccano, senza che uno contenga l'altro
    "supports",      # questo e' la prova di quello
    "contradicts",   # questo dice il contrario di quello
    "supersedes",    # questo prende il posto di quello
)

# Come si chiama una relazione scritta da qui dentro, per distinguerla dai
# collegamenti effimeri fra segnali che vivono nella stessa collezione.
KIND = "life_relation"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def remember_relation(
    db, owner_id: str, *,
    source_type: str, source_ref: str,
    target_kind: str, target_ref: str,
    relation_type: str,
    why: str,
    decided_by: str,
    confidence: float = 0.0,
) -> Optional[Dict[str, Any]]:
    """
    Scrivi che due cose di questa vita c'entrano fra loro, e perche'.

        UNA RELAZIONE INDOVINATA NON DIVENTA UNA VERITA' PERCHE' E' SCRITTA.

    Quindi si scrive solo quello che ha un motivo che si puo' leggere, e il
    motivo viaggia con la riga. `decided_by` dice chi l'ha stabilita — il
    giudizio, la persona, o una relazione gia' governata altrove — perche' la
    domanda «chi l'ha deciso» arriva sempre, e di solito tardi.

    La stessa relazione scritta due volte resta una: la coppia
    sorgente-bersaglio e' la sua identita'.
    """
    if relation_type not in RELATION_TYPES:
        logger.info("relazione ignota rifiutata: %s", relation_type)
        return None
    if not (source_ref and target_ref and why.strip()):
        return None

    row = {
        "id": f"rel_{uuid.uuid4().hex[:12]}",
        "owner_id": owner_id,
        "kind": KIND,
        # Non c'e' un segnale dietro: questa relazione non nasce da un
        # arrivo, nasce da un giudizio su cose che ci sono gia'.
        "signal_id": "",
        "source_type": source_type,
        "source_object_ref": source_ref,
        "target_kind": target_kind,
        "target_ref": target_ref,
        "relationship": relation_type,
        "relation_type": relation_type,
        "confidence": float(confidence or 0.0),
        "reason_summary": why.strip()[:300],
        "decided_by": decided_by,
        "decided_at": _now_iso(),
        "status": "active",
        # Niente `expires_at`: l'appartenenza di un documento a una casa non
        # scade fra sei mesi, e la TTL della collezione ignora le righe che
        # non hanno quel campo.
    }
    try:
        await db[LINKS].update_one(
            {"owner_id": owner_id, "kind": KIND,
             "source_object_ref": source_ref, "target_ref": target_ref},
            {"$set": {k: v for k, v in row.items() if k != "id"},
             "$setOnInsert": {"id": row["id"]}},
            upsert=True,
        )
    except Exception as e:
        logger.info("relation write soft-fail: %s", type(e).__name__)
        return None
    return row


async def relations_of(
    db, owner_id: str, *,
    target_refs: Optional[Sequence[str]] = None,
    source_refs: Optional[Sequence[str]] = None,
    limit: int = 60,
) -> List[Dict[str, Any]]:
    """Le relazioni scritte che toccano queste cose."""
    query: Dict[str, Any] = {
        "owner_id": owner_id, "kind": KIND, "status": "active",
    }
    if target_refs is not None:
        query["target_ref"] = {"$in": [str(r) for r in target_refs]}
    if source_refs is not None:
        query["source_object_ref"] = {"$in": [str(r) for r in source_refs]}
    try:
        return await db[LINKS].find(query, {"_id": 0}).to_list(limit)
    except Exception as e:
        logger.info("relation read soft-fail: %s", type(e).__name__)
        return []


async def already_decided(db, owner_id: str, *, source_type: str) -> List[str]:
    """
    Su cosa il giudizio si e' gia' pronunciato — anche per dire di no.

    Serve a non ripagare la stessa domanda a ogni passaggio: un documento che
    non appartiene a niente e' una risposta, e va ricordata come le altre.
    """
    try:
        rows = await db[LINKS].find(
            {"owner_id": owner_id, "kind": KIND, "source_type": source_type},
            {"_id": 0, "source_object_ref": 1},
        ).to_list(400)
    except Exception:
        return []
    return [str(r.get("source_object_ref") or "") for r in rows]


async def note_nothing_to_link(
    db, owner_id: str, *, source_type: str, source_ref: str, why: str,
) -> None:
    """
    Segna che questa cosa non appartiene a niente, e che lo si e' guardato.

    Senza questa riga, ogni passaggio ripaga il giudizio per sentirsi dire di
    nuovo che una ricevuta del supermercato non c'entra con l'acquisto della
    casa. Con questa riga, si guarda una volta.
    """
    try:
        await db[LINKS].update_one(
            {"owner_id": owner_id, "kind": KIND,
             "source_object_ref": source_ref, "target_ref": ""},
            {"$set": {
                "owner_id": owner_id, "kind": KIND, "signal_id": "",
                "source_type": source_type, "source_object_ref": source_ref,
                "target_kind": "", "target_ref": "",
                "relationship": "", "relation_type": "",
                "reason_summary": why.strip()[:300],
                "decided_by": "judgement", "status": "nothing_to_link",
                "decided_at": _now_iso(),
            }, "$setOnInsert": {"id": f"rel_{uuid.uuid4().hex[:12]}"}},
            upsert=True,
        )
    except Exception as e:
        logger.info("relation write soft-fail: %s", type(e).__name__)
