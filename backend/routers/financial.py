"""Quello che ORA sa dei soldi, per le schermate che devono dirlo."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from deps import db, get_current_user

router = APIRouter(prefix="/financial", tags=["financial"])


@router.get("/knowledge")
async def knowledge(
    about: str = Query(default=""),
    days: int = Query(default=30, ge=1, le=120),
    user=Depends(get_current_user),
):
    """
    Cosa ORA sa, cosa ha solo letto, cosa deve chiedere.

    Le tre categorie escono separate e restano separate fin dentro la
    schermata: unirle qui vorrebbe dire che ogni superficie deve rifare da
    sola la distinzione fra affermare e riferire, e prima o poi una la
    sbaglia.
    """
    from financial.knowledge import what_ora_knows

    uid = user["user_id"]
    out = await what_ora_knows(db, uid, days=days)
    if not about:
        return out
    return await _narrow(db, uid, out, about)


async def _narrow(db, uid: str, out: dict, about: str) -> dict:
    """
    Restringi a una parte della vita — e falla con i collegamenti, non con le parole.

        UN NOME NON E' UNA RELAZIONE.

    Il filtro per nome era un ripiego che si e' preso il posto della cosa
    vera: cercare «casa» dentro «affitto casa» funziona finche' qualcuno non
    chiama l'affitto «canone», e allora sparisce; e prende «bolletta di casa»
    dentro l'acquisto di una casa, che non c'entra niente.

    La relazione vera esiste ed e' `about_refs`: il giudizio ha detto a quale
    situazione un fatto appartiene, e quella e' la fonte. Il nome resta solo
    come ultima risorsa per quando non c'e' ancora nessun collegamento
    strutturato — e allora e' meglio di niente, ma si sa che e' un ripiego.
    """
    from financial.durable import governed_facts, identity_of
    from financial.store import FinancialStore

    needle = about.strip().lower()

    # Quali situazioni di questa persona corrispondono a quello che si chiede.
    try:
        objects = await db.life_objects.find(
            {"user_id": uid, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1},
        ).to_list(40)
    except Exception:
        objects = []
    situations = {
        str(o.get("id")) for o in objects
        if needle in str(o.get("title") or "").lower()
        or needle in str(o.get("type") or "").lower()
    }

    linked_names = set()
    if situations:
        for fact in (
            await governed_facts(db, uid)
            + await FinancialStore(db).known(uid)
        ):
            if situations & set(fact.about_refs or []):
                linked_names.add(identity_of(fact).split(":", 2)[-1])

    def by_link(rows):
        return [
            r for r in rows
            if " ".join(str(r.get("cosa") or "").lower().split()) in linked_names
        ]

    def by_name(rows):
        return [r for r in rows if needle in str(r.get("cosa") or "").lower()]

    picked = {
        "so": by_link(out["so"]),
        "ho_letto": by_link(out["ho_letto"]),
        "devo_chiederti": by_link(out["devo_chiederti"]),
    }
    if any(picked.values()):
        return {**picked, "in_arrivo": out["in_arrivo"], "matched_by": "situation"}

    # Nessun collegamento strutturato: si ripiega sul nome, e lo si dichiara.
    return {
        "so": by_name(out["so"]),
        "ho_letto": by_name(out["ho_letto"]),
        "devo_chiederti": by_name(out["devo_chiederti"]),
        "in_arrivo": out["in_arrivo"],
        "matched_by": "name",
    }


@router.get("/situation/{situation_id}")
async def situation(situation_id: str, user=Depends(get_current_user)):
    """Il lato economico di una cosa che sta succedendo in questa vita."""
    from financial.situation import money_side_of

    return await money_side_of(db, user["user_id"], situation_id)


@router.get("/overview")
async def overview(user=Depends(get_current_user)):
    """
    «Conti e denaro»: cosa ORA vede della banca e cosa ne ha capito.

    Una schermata sola, gia' divisa per gradi di certezza — perche' la
    differenza fra «ho visto un pagamento» e «penso sia l'affitto» e' tutta,
    e non deve doverla rifare chi disegna.
    """
    from financial.overview import money_overview

    return await money_overview(db, user["user_id"])


def _bank_service():
    """
    Il servizio bancario, con il provider che la configurazione dice.

    Senza credenziali `build_bank_provider` costruisce quello di prova: e'
    una scelta dichiarata, non un ripiego silenzioso, e le schermate lo
    dicono a chi guarda.
    """
    import deps
    from connectors.bank.service import BankReadService

    return BankReadService(
        db=db, permissions=deps.get_permissions_service(),
        vault=deps.get_token_vault(),
    )


@router.post("/bank/connect")
async def connect_bank(user=Depends(get_current_user)):
    """
    Collega il conto di prova. La porta vera e' `/bank/link`.

    Resta perche' e' quella che i test strutturali usano per far camminare
    il percorso senza una banca: collegare per finta e collegare davvero non
    devono essere la stessa funzione, o prima o poi una delle due mente.
    """
    return await _bank_service().connect(user_id=user["user_id"])


@router.get("/bank/state")
async def bank_state(user=Depends(get_current_user)):
    """Com'e' messo il collegamento: cinque stati, detti in italiano."""
    return await _bank_service().state(user_id=user["user_id"])


@router.get("/bank/institutions")
async def bank_institutions(
    country: str = Query(default="IT", min_length=2, max_length=2),
    user=Depends(get_current_user),
):
    """
    Le banche collegabili nel paese di questa persona.

    Torna anche in quale ambiente siamo: una persona che sta guardando un
    conto di prova ha il diritto di saperlo, e scoprirlo dopo sarebbe peggio
    che leggerlo prima.
    """
    from connectors.bank.enablebanking_provider import EnableBankingNotConfigured
    from connectors.bank.gocardless_provider import GoCardlessNotConfigured
    from connectors.bank.provider import BankAPIError

    svc = _bank_service()
    try:
        return {
            "banche": await svc.institutions(country=country.upper()),
            "ambiente": str(getattr(svc.provider, "environment", "") or ""),
            "di_prova": bool(getattr(svc.provider, "is_sandbox", False)),
        }
    except (GoCardlessNotConfigured, EnableBankingNotConfigured, NotImplementedError):
        raise HTTPException(status_code=503, detail={
            "error": "bank_provider_not_configured",
            "message": "Non posso ancora collegare una banca vera.",
        })
    except BankAPIError:
        raise HTTPException(status_code=502, detail={
            "error": "bank_unavailable",
            "message": "L'elenco delle banche non è disponibile in questo momento.",
        })


class LinkBankIn(BaseModel):
    institution_id: str
    # Dove tornare dopo l'autenticazione sul sito della banca. Passa dal
    # filtro degli origini consentiti: un redirect libero e' un regalo a
    # chiunque sappia scrivere un link.
    redirect_after: Optional[str] = None


@router.post("/bank/link")
async def bank_link(body: LinkBankIn, request: Request, user=Depends(get_current_user)):
    """
    Comincia il collegamento e dì alla persona dove deve autenticarsi.

        LE CREDENZIALI DELLA BANCA NON PASSANO DA QUI.

    Quello che torna e' un indirizzo: il percorso ufficiale della banca o
    del provider. ORA non vede e non vuole vedere cosa la persona digita li'.
    """
    from connectors.bank.enablebanking_provider import EnableBankingNotConfigured
    from connectors.bank.gocardless_provider import GoCardlessNotConfigured
    from connectors.bank.provider import BankAPIError
    from connectors.google_calendar.oauth import (
        allowed_frontend_origins, sanitize_redirect_after,
    )

    back = sanitize_redirect_after(body.redirect_after) or (
        allowed_frontend_origins()[0] + "/conti-e-denaro"
    )
    try:
        return await _bank_service().begin_link(
            user_id=user["user_id"],
            institution_id=body.institution_id.strip(),
            redirect_to=back,
        )
    except (GoCardlessNotConfigured, EnableBankingNotConfigured, NotImplementedError):
        raise HTTPException(status_code=503, detail={
            "error": "bank_provider_not_configured",
            "message": "Non posso ancora collegare una banca vera.",
        })
    except BankAPIError:
        raise HTTPException(status_code=502, detail={
            "error": "bank_unavailable",
            "message": "La banca non risponde in questo momento.",
        })


@router.get("/bank/link/{instance_id}")
async def bank_link_status(instance_id: str, user=Depends(get_current_user)):
    """A che punto è il collegamento — chiesto al ritorno, e ogni volta che serve."""
    return await _bank_service().finish_link(
        user_id=user["user_id"], instance_id=instance_id,
    )


class DisconnectBankIn(BaseModel):
    instance_id: str
    # Scollegare e' irreversibile dal lato del provider: il consenso si
    # chiude e per riaverlo si rifà tutto il percorso. Quindi si chiede.
    confirm: bool = False


@router.post("/bank/disconnect")
async def bank_disconnect(body: DisconnectBankIn, user=Depends(get_current_user)):
    """
    Scollega il conto. Chiede conferma, e non cancella quello che ORA ha capito.
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail={
            "error": "confirmation_required",
            "message": "Vuoi davvero scollegare il conto?",
        })
    return await _bank_service().disconnect(
        user_id=user["user_id"], instance_id=body.instance_id,
    )
