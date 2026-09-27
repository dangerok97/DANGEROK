"""
Quali numeri una persona ha già confermato, e per chi.

    LA FIDUCIA NON È DEL NUMERO: È DELLA COPPIA.

«+39 333…» da solo non vuol dire niente. «+39 333… è Lorenzo Bianchi, me l'hai
detto tu martedì» sì. Lo stesso numero, trovato domani accanto al nome di uno
studio dentistico, non eredita niente: è un'altra coppia, e riparte da zero.

    PERCHÉ QUESTO FILE, E NON LA RUBRICA.

La rubrica (`contacts`) è quello che dice il telefono. Questo è quello che ha
detto la persona. Tenerli nello stesso posto vorrebbe dire che un numero
importato da iOS diventa «confermato» senza che nessuno l'abbia guardato — e
la differenza fra le due cose è esattamente quella che ORA deve saper
raccontare. Nel progetto non c'era un posto per la seconda; adesso c'è, ed è
piccolo apposta.

    TRE STATI, E NESSUNO CANCELLA.

`active` si può usare. `stale` si usava, e qualcuno l'ha sostituito. `rejected`
qualcuno ha detto che è sbagliato. Un numero rifiutato non si butta: si
ricorda, perché è il solo modo per non riproporlo alla prossima telefonata come
se non fosse mai successo niente.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("ora.preparation.trust")

TRUSTED = "trusted_numbers"

Status = Literal["active", "stale", "rejected"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def identity_of(nome: str) -> str:
    """
    L'identità di un contatto, ridotta a una forma che si può confrontare.

        «LORENZO BIANCHI» E «lorenzo  bianchi» SONO LA STESSA PERSONA.

    Minuscole, niente punteggiatura, spazi normalizzati. Non prova a capire che
    «Lorenzo» e «Lorenzo Bianchi» sono la stessa persona: quello lo decide chi
    cerca, confrontando parole intere. Qui si dà solo una chiave stabile.
    """
    pulito = re.sub(r"[^\w\s]", " ", (nome or "").lower())
    return " ".join(pulito.split())[:120]


def key_for(owner_id: str, identity: str, number: str) -> str:
    return f"{owner_id}|{identity}|{number}"[:240]


class TrustedNumber(BaseModel):
    """Un numero, per una identità, con dentro come ci si è arrivati."""

    owner_id: str = Field(min_length=1, max_length=64)
    contact_identity: str = Field(min_length=1, max_length=120)
    display_name: str = Field(default="", max_length=160)
    phone_number: str = Field(min_length=6, max_length=32)
    kind: str = Field(default="unknown", max_length=24)
    # Da dove era arrivato la prima volta: rubrica, web, te.
    source: str = Field(default="", max_length=32)
    source_detail: str = Field(default="", max_length=200)
    source_url: str = Field(default="", max_length=300)
    #     IL SÌ, E QUANDO.
    # Vero solo dopo un gesto esplicito. Un numero salvato perché è stato
    # visto, o perché è stato scritto per una telefonata sola, resta qui con
    # questo campo a falso — ed è il motivo per cui la volta dopo si chiede.
    confirmed_by_user: bool = False
    confirmed_at: str = Field(default="", max_length=40)
    status: Status = "active"
    # Other identities explicitly acknowledged as sharing this number.
    shared_with: List[str] = Field(default_factory=list)
    # Perché non è più attivo, detto a una persona.
    status_says: str = Field(default="", max_length=200)
    discovered_at: str = Field(default_factory=now_iso)
    last_seen_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)

    def is_trusted(self) -> bool:
        """L'unica domanda che conta davanti a un telefono."""
        return self.confirmed_by_user and self.status == "active"


# ---------------------------------------------------------------------------
# Leggere
# ---------------------------------------------------------------------------


async def for_whom(db, owner_id: str, who: str) -> List[TrustedNumber]:
    """
    Tutti i numeri noti per chi assomiglia a «who», in qualunque stato.

    Il confronto è per parole intere: «Lorenzo» trova «Lorenzo Bianchi», ma
    «Lore» non trova «Salvatore». È lo stesso criterio della rubrica, perché
    due criteri diversi per la stessa domanda darebbero due risposte.
    """
    from preparation.contacts import _how_well_it_matches

    righe = await _rows(db, {"owner_id": owner_id})
    fuori: List[TrustedNumber] = []
    for r in righe:
        try:
            t = TrustedNumber.model_validate(r)
        except Exception:  # pragma: no cover
            continue
        if _how_well_it_matches(who, [t.display_name, t.contact_identity]) > 0:
            fuori.append(t)
    return fuori


async def trusted_for(db, owner_id: str, who: str) -> List[TrustedNumber]:
    return [t for t in await for_whom(db, owner_id, who) if t.is_trusted()]


async def not_to_propose(db, owner_id: str, who: str) -> Dict[str, str]:
    """
    I numeri che non si ripropongono, e perché.

        UN NO SI RICORDA.

    Rifiutati e sostituiti. Tornano solo se una persona li riconferma lei,
    scrivendoli di nuovo — non perché una fonte li ha ritrovati.
    """
    return {
        t.phone_number: t.status_says or t.status
        for t in await for_whom(db, owner_id, who)
        if t.status in ("rejected", "stale")
    }


async def still_trusted(db, owner_id: str, identity: str, number: str) -> bool:
    """
    Se questa coppia è ancora affidabile adesso.

    Si chiede al momento di preparare la telefonata, non si ricorda da prima:
    fra la preparazione e il sì qualcuno può aver cambiato numero.
    """
    row = await db[TRUSTED].find_one(
        {"_id": key_for(owner_id, identity, number)}, {"_id": 0},
    )
    if not row:
        return False
    try:
        return TrustedNumber.model_validate(row).is_trusted()
    except Exception:  # pragma: no cover
        return False


async def identity_conflicts(
    db, owner_id: str, identity: str, number: str,
) -> List[Dict[str, str]]:
    """Reverse lookup, owner-scoped. A failed read must never mean no conflict."""
    from preparation.contacts import _clean_number

    number = _clean_number(number)
    identity = identity_of(identity)
    if not number or not identity or identity == "questo numero":
        return []
    rows = await db[TRUSTED].find(
        {"owner_id": owner_id, "phone_number": number}, {"_id": 0},
    ).to_list(length=None)
    known = {r["contact_identity"]: r for r in rows if r.get("contact_identity")}
    current = known.get(identity, {})
    shared = set(current.get("shared_with") or []) if (
        current.get("status") == "active" and current.get("confirmed_by_user")
    ) else set()
    conflicts: Dict[str, Dict[str, str]] = {}
    for other, row in known.items():
        if other == identity or other == "questo numero":
            continue
        if row.get("status") != "active" or not (
            row.get("confirmed_by_user") or row.get("source") == "user"
        ):
            continue
        if other in shared and identity in (row.get("shared_with") or []):
            continue
        conflicts[other] = {
            "identity": other, "name": str(row.get("display_name") or other),
            "version": str(row.get("confirmed_at") or row.get("discovered_at") or ""),
            "source": "confirmed" if row.get("confirmed_by_user") else "user",
        }
    # Older calls may predate the trust register. Retired/rejected pairs in
    # the register take precedence over historical calls, so corrections stick.
    calls = await db["phone_calls"].find(
        {"owner_id": owner_id, "to_number": number,
         "state": {"$in": ["dialling", "talking", "ended", "failed"]}},
        {"_id": 0, "calling_whom": 1, "id": 1},
    ).to_list(length=None)
    for call in calls:
        name = str(call.get("calling_whom") or "")[:160]
        other = identity_of(name)
        if not other or other in (identity, "questo numero") or other in conflicts:
            continue
        previous = known.get(other, {})
        if previous and (previous.get("status") in ("stale", "rejected")
                         or previous.get("confirmed_by_user")):
            continue
        conflicts.setdefault(other, {
            "identity": other, "name": name,
            "version": str(call.get("id") or ""), "source": "past_call",
        })
    return [conflicts[key] for key in sorted(conflicts)]


def conflict_message(number: str, name: str, conflicts: List[Dict[str, str]]) -> str:
    names = ", ".join(c["name"][:45] for c in conflicts[:2])
    if len(conflicts) > 2:
        names += " e altri"
    return (f"Il numero {number} era associato a {names}. "
            f"Ora lo indichi per {name[:50]}. "
            "È una correzione o un numero condiviso?")


# ---------------------------------------------------------------------------
# Scrivere — e ognuna di queste funzioni si può chiamare due volte
# ---------------------------------------------------------------------------


async def confirm(
    db, *, owner_id: str, identity: str, display_name: str, number: str,
    kind: str = "unknown", source: str = "", source_detail: str = "",
    source_url: str = "",
    shared_with: Optional[List[str]] = None,
) -> TrustedNumber:
    """
    Una persona ha detto «sì, è questo». Da adesso la coppia è affidabile.

        E L'ALTRO NUMERO NON SPARISCE: DIVENTA VECCHIO.

    Se la stessa identità aveva già un numero confermato, quello passa a
    `stale` con scritto perché. Non si cancella: si deve poter leggere che
    cosa si usava prima, e si deve poter tornare indietro confermandolo di
    nuovo.

    Idempotente: confermare due volte la stessa coppia non cambia niente.
    """
    adesso = now_iso()
    for vecchio in await for_whom(db, owner_id, identity):
        if (vecchio.contact_identity == identity
                and vecchio.phone_number != number and vecchio.is_trusted()):
            await _set_status(
                db, vecchio, "stale",
                f"sostituito il {_oggi()} da un altro numero che hai confermato",
            )

    previous = await db[TRUSTED].find_one(
        {"_id": key_for(owner_id, identity, number)}, {"_id": 0},
    )
    record = TrustedNumber(
        owner_id=owner_id, contact_identity=identity,
        display_name=display_name or identity, phone_number=number, kind=kind,
        source=source, source_detail=source_detail, source_url=source_url,
        confirmed_by_user=True, confirmed_at=adesso, status="active",
        shared_with=(shared_with if shared_with is not None else
                     list((previous or {}).get("shared_with") or [])),
        last_seen_at=adesso, updated_at=adesso,
    )
    await _upsert(db, record, keep_first_seen=True)
    return record


async def reject(
    db, *, owner_id: str, identity: str, display_name: str, number: str,
    source: str = "", source_detail: str = "",
) -> TrustedNumber:
    """
    «No, non è quello.» Il numero resta, ma non si ripropone.

    Se era un numero confermato, smette di esserlo: chi dice che è sbagliato
    ne sa più di chi l'aveva confermato — ed è la stessa persona, più tardi.
    """
    adesso = now_iso()
    record = TrustedNumber(
        owner_id=owner_id, contact_identity=identity,
        display_name=display_name or identity, phone_number=number,
        source=source, source_detail=source_detail,
        confirmed_by_user=False, status="rejected",
        status_says=f"mi hai detto che non è il numero giusto ({_oggi()})",
        last_seen_at=adesso, updated_at=adesso,
    )
    await _upsert(db, record, keep_first_seen=True)
    return record


async def retire(
    db, *, owner_id: str, identity: str, number: str, why: str,
) -> None:
    """
    Un numero che si usava e adesso no, perché ne arriva un altro.

    Non è un rifiuto — potrebbe essere stato giusto fino a ieri — e quindi non
    si scrive `rejected`. Si scrive `stale`, con il perché.
    """
    row = await db[TRUSTED].find_one(
        {"_id": key_for(owner_id, identity, number)}, {"_id": 0},
    )
    if not row:
        return
    try:
        vecchio = TrustedNumber.model_validate(row)
    except Exception:  # pragma: no cover
        return
    if vecchio.status == "active":
        await _set_status(db, vecchio, "stale", why)


async def remember_seen(
    db, *, owner_id: str, identity: str, display_name: str, number: str,
    kind: str = "unknown", source: str = "", source_detail: str = "",
    source_url: str = "",
) -> None:
    """
    Un numero visto, e non ancora confermato.

    Serve a una cosa sola: la volta dopo, sapere che quel numero per quella
    persona è già passato di qui. Non dà nessuna fiducia — `confirmed_by_user`
    resta a falso — e non tocca un record che ne avesse già una.
    """
    row = await db[TRUSTED].find_one(
        {"_id": key_for(owner_id, identity, number)}, {"_id": 0},
    )
    if row:
        #     NON SI ABBASSA QUELLO CHE UNA PERSONA HA ALZATO.
        await db[TRUSTED].update_one(
            {"_id": key_for(owner_id, identity, number)},
            {"$set": {"last_seen_at": now_iso()}},
        )
        return
    record = TrustedNumber(
        owner_id=owner_id, contact_identity=identity,
        display_name=display_name or identity, phone_number=number, kind=kind,
        source=source, source_detail=source_detail, source_url=source_url,
        confirmed_by_user=False, status="active",
    )
    await _upsert(db, record, keep_first_seen=True)


# ---------------------------------------------------------------------------
# Interni
# ---------------------------------------------------------------------------


async def _set_status(db, record: TrustedNumber, status: str, says: str) -> None:
    await db[TRUSTED].update_one(
        {"_id": key_for(record.owner_id, record.contact_identity, record.phone_number)},
        {"$set": {"status": status, "status_says": says[:200],
                  "updated_at": now_iso()}},
    )


async def _upsert(db, record: TrustedNumber, *, keep_first_seen: bool) -> None:
    """
    Scrive la coppia, sempre con la stessa chiave.

        LA STESSA COPPIA È UN RECORD SOLO, PER SEMPRE.

    Confermare, rifiutare, riconfermare: tutto sulla stessa riga. È quello che
    rende idempotente ogni gesto, e che tiene leggibile la storia di un numero.
    """
    chiave = key_for(record.owner_id, record.contact_identity, record.phone_number)
    campi = record.model_dump()
    if keep_first_seen:
        gia = await db[TRUSTED].find_one({"_id": chiave}, {"_id": 0, "discovered_at": 1})
        if gia and gia.get("discovered_at"):
            campi["discovered_at"] = gia["discovered_at"]
    await db[TRUSTED].update_one({"_id": chiave}, {"$set": campi}, upsert=True)


async def _rows(db, query: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        return await db[TRUSTED].find(query, {"_id": 0}).to_list(500)
    except Exception as e:  # pragma: no cover
        logger.info("numeri affidabili non letti: %s", type(e).__name__)
        return []


def _oggi() -> str:
    return datetime.now().strftime("%d/%m/%Y")
