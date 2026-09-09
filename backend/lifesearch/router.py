"""La porta della ricerca. Sola lettura, e niente di tecnico esce di qui."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from deps import db, get_current_user

router = APIRouter(prefix="/search", tags=["search"])


class SearchIn(BaseModel):
    q: str
    language: str = "it"


@router.post("")
async def search(body: SearchIn, user=Depends(get_current_user)):
    """
    Cerca dentro la vita di questa persona.

    Il blocco `_qa` non viene rimosso qui ma nel client: e' quello che
    permette di verificare che la relazione stia funzionando prima della
    parola, ed e' l'unico modo di accorgersi se un giorno smettesse.
    """
    from lifesearch.search import search_a_life

    return await search_a_life(
        db, user["user_id"], body.q, language=body.language,
    )


@router.get("/suggestions")
async def suggestions(user=Depends(get_current_user)):
    """
    Cosa proporre prima che qualcuno scriva: i nomi delle sue cose.

        UN CAMPO DI RICERCA VUOTO NON DEVE CHIEDERE FANTASIA.

    Nessuna chiamata al giudizio, nessun elenco fisso: le parti della vita di
    questa persona, come si chiamano.
    """
    from lifesearch.index import life_index

    index = await life_index(db, user["user_id"])
    out = [s["what_it_is"] for s in index["situations_in_this_life"]][:4]
    out += [name for name in index["what_ora_knows_about_their_money"]][:2]
    return {"prova_con": out[:6]}


@router.get("/life-area/{situation_id}")
async def life_area(situation_id: str, user=Depends(get_current_user)):
    """
    Una parte della vita, aperta: cosa so, cosa e' collegato, cosa manca.

    Accetta l'id della situazione oppure il nome del dominio con cui la Vita
    la chiama — «casa», «lavoro» — perche' e' da li' che si arriva, e
    obbligare la schermata a conoscere gli id sarebbe farle sapere una cosa
    che non deve sapere.
    """
    from lifesearch.search import what_ora_knows_about

    uid = user["user_id"]
    wanted = situation_id
    if not situation_id.startswith("lo_"):
        wanted = await _situation_named(uid, situation_id) or situation_id
    return await what_ora_knows_about(db, uid, wanted)


async def _situation_named(owner_id: str, domain: str) -> Optional[str]:
    """Da «casa» alla situazione che la Vita mostra sotto quel nome."""
    from lifesearch.resolve import _domain

    rows = await db.life_objects.find(
        {"user_id": owner_id, "status": {"$ne": "archived"}},
        {"_id": 0, "id": 1, "type": 1},
    ).to_list(40)
    for row in rows:
        if _domain(row) == domain.strip().lower():
            return str(row["id"])
    return None


@router.post("/relations")
async def maintain_relations(user=Depends(get_current_user)):
    """
    Colloca adesso quello che e' arrivato: carte e messaggi, in due chiamate.

    Il ciclo automatico lo fa gia' da solo ogni tanto. Questa porta resta
    perche' chi verifica deve poter dire «adesso» e vedere i numeri — quante
    ne ha guardate, quante collegate, quante chiamate e' costato.
    """
    from lifesearch.maintenance import keep_relations_current

    return await keep_relations_current(db, owners=[user["user_id"]])
