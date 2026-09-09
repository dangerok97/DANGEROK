"""
Cosa si e' visto sul conto, contato — e diviso per forma, non per importanza.

    RICORRENTE NON VUOL DIRE IMPORTANTE. UNA VOLTA SOLA NON VUOL DIRE PICCOLO.

Quattromila euro dal notaio sono la cosa piu' grossa del mese e non sono una
spesa ricorrente. Quattordici euro e novantanove che tornano ogni mese sono
la cosa piu' piccola e sono un pattern. Confondere le due e' il modo piu'
rapido di far dire a ORA una frase che nessuno riconosce come propria.

Questo file conta e basta. Guarda le osservazioni bancarie, le raggruppa con
la stessa chiave con cui vengono contate le ricorrenze — la controparte se la
banca la da', altrimenti la descrizione grezza — e restituisce tre elenchi
piu' una somma:

    entrate che tornano · uscite che tornano · movimenti singoli

Nessuno di questi elenchi porta un nome inventato. Se il giudizio ha gia'
capito una di quelle cose, il nome viene da li'; se no, la riga dice quello
che c'e' scritto sull'estratto conto e che non e' stata identificata. Un
addebito di 14,99 al mese non diventa «abbonamento» perche' e' piccolo e
regolare: diventa «un addebito che torna e che non ho identificato», che e'
piu' lungo e vero.

E la somma del mese non e' una disponibilita'.

    LA DIFFERENZA FRA QUELLO CHE HO LETTO NON E' QUELLO CHE TI RESTA.

E' il saldo parziale dei movimenti osservati: non sa dei contanti, non sa di
un altro conto, non sa di quello che la banca non ha ancora contabilizzato.
Esce con quel nome addosso, perche' un numero senza il suo nome viene letto
come il numero che chi legge sperava.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.financial.observed")


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


def _money(amount: float, currency: str = "EUR") -> str:
    from financial.models import Money

    return Money(amount=amount, currency=currency).for_human()


async def what_was_seen(db, owner_id: str) -> Dict[str, Any]:
    """
    I movimenti osservati, divisi per forma e mai per significato.

    Torna anche quanti movimenti isolati ci sono stati, senza elencarli: una
    spesa quotidiana isolata e' vera e non e' un pattern, e riempirne una
    risposta la renderebbe piu' lunga senza renderla piu' utile.
    """
    from financial.observation import ObservationStore, _grouping_key
    from financial.store import FinancialStore

    try:
        history = await ObservationStore(db).history(owner_id)
    except Exception as e:
        logger.info("observation read soft-fail: %s", type(e).__name__)
        return {"ricorrenti_in_entrata": [], "ricorrenti_in_uscita": [],
                "movimenti_singoli": [], "quanti_isolati": 0}

    # Come il giudizio ha gia' nominato alcuni di questi movimenti.
    named: Dict[str, str] = {}
    try:
        for fact in await FinancialStore(db).known(owner_id):
            for ref in fact.source_refs or []:
                named[str(ref)] = fact.what
    except Exception as e:
        logger.info("fact read soft-fail: %s", type(e).__name__)

    groups: Dict[str, List[Any]] = {}
    for observation in history:
        groups.setdefault(_grouping_key(observation), []).append(observation)

    incoming: List[Dict[str, Any]] = []
    outgoing: List[Dict[str, Any]] = []
    singles: List[Dict[str, Any]] = []
    isolated = 0

    for members in groups.values():
        members.sort(key=lambda o: str(o.booked_at))
        newest = members[-1]
        name = next(
            (named[o.transaction_ref] for o in members
             if o.transaction_ref in named),
            "",
        )
        row = {
            # Quello che c'e' scritto sull'estratto conto. Non un nome nostro.
            "come_lo_scrive_la_banca": (
                newest.raw_description or newest.counterparty or ""
            ),
            "quanto": _money(abs(newest.amount), newest.currency),
            "verso": "in entrata" if newest.direction == "incoming" else "in uscita",
            "quante_volte": len(members),
        }
        if name:
            # Se qualcuno l'ha gia' capita, il nome viene da li'.
            row["come_l_ho_chiamata"] = name
        else:
            row["identificato"] = False

        if len(members) > 1:
            gap = _typical_gap(members)
            if gap:
                row["ogni_quanti_giorni_circa"] = gap
            (incoming if newest.direction == "incoming" else outgoing).append(row)
            continue

        # Una volta sola. Che sia grande o piccola, non e' un pattern.
        row["quando"] = str(newest.booked_at)[:10]
        singles.append(row)
        isolated += 1

    # I singoli in ordine di grandezza: non perche' l'importo decida cosa
    # conta, ma perche' se una risposta ne cita uno, il piu' grosso e' quello
    # che chi legge si aspetta di sentir nominare.
    singles.sort(key=lambda r: -_amount_of(r["quanto"]))

    return {
        "ricorrenti_in_entrata": incoming[:8],
        "ricorrenti_in_uscita": outgoing[:8],
        "movimenti_singoli": singles[:6],
        "quanti_isolati": isolated,
        "come_leggerlo": (
            "«Ricorrenti» vuol dire soltanto che si ripetono: non che siano "
            "importanti, e non che sia noto cosa siano. Le voci con "
            "`identificato: false` non hanno un nome — dille come le scrive "
            "la banca e di' che non hai ancora capito cosa siano. I movimenti "
            "singoli non sono spese ricorrenti, per quanto grandi."
        ),
    }


def _amount_of(human: str) -> float:
    """Dall'importo scritto per una persona al numero, per ordinare."""
    digits = "".join(
        c for c in human.replace(".", "").replace(",", ".") if c.isdigit() or c == "."
    )
    try:
        return float(digits)
    except ValueError:
        return 0.0


def _typical_gap(members: List[Any]) -> Optional[int]:
    moments = [m for m in (_moment(o.booked_at) for o in members) if m]
    if len(moments) < 2:
        return None
    gaps = [
        (later - earlier).total_seconds() / 86400.0
        for earlier, later in zip(moments, moments[1:])
    ]
    return int(round(statistics.median(gaps)))


async def this_month(db, owner_id: str) -> Dict[str, Any]:
    """
    Entrate e uscite dei movimenti letti nel mese in corso. Con il loro nome.

        QUESTA DIFFERENZA NON E' QUELLO CHE TI RESTA.

    E' utile — «il notaio pesa quattromila euro» e' una cosa che una persona
    vuole sapere — ed e' pericolosa esattamente quanto e' utile, perche'
    somiglia a un saldo. Quindi esce con l'etichetta attaccata, e la voce che
    pesa di piu' esce accanto: e' quella che spiega il numero.
    """
    from financial.observation import ObservationStore

    now = datetime.now(timezone.utc)
    try:
        history = await ObservationStore(db).history(owner_id)
    except Exception as e:
        logger.info("observation read soft-fail: %s", type(e).__name__)
        return {}

    inside = [
        o for o in history
        if (when := _moment(o.booked_at)) is not None
        and when.year == now.year and when.month == now.month
    ]
    if not inside:
        return {}

    currency = inside[0].currency or "EUR"
    incoming = sum(o.amount for o in inside if o.amount > 0)
    outgoing = sum(-o.amount for o in inside if o.amount < 0)
    heaviest = min(inside, key=lambda o: o.amount)

    return {
        "che_cosa_e": (
            "somma parziale dei movimenti che ho letto in questo mese, non "
            "una disponibilità e non un saldo"
        ),
        "entrate_osservate": _money(incoming, currency),
        "uscite_osservate": _money(outgoing, currency),
        "differenza_parziale": _money(incoming - outgoing, currency),
        "quanti_movimenti": len(inside),
        "la_voce_che_pesa_di_piu": {
            "come_lo_scrive_la_banca": heaviest.raw_description or "",
            "quanto": _money(abs(heaviest.amount), heaviest.currency),
        } if heaviest.amount < 0 else None,
        "attenzione": (
            "Non so se questi siano tutti i movimenti: potrebbero mancare "
            "contanti, altri conti, e quello che la banca non ha ancora "
            "contabilizzato."
        ),
    }


async def the_bank_right_now(db, owner_id: str) -> Dict[str, Any]:
    """
    Se il conto e' collegato adesso, e cosa si puo' dire del saldo.

        UNA FONTE SCOLLEGATA NON HA UN SALDO ATTUALE. NE HA AVUTO UNO.

    E' la distinzione che questo file esiste per rendere impossibile da
    saltare: finche' il conto e' collegato, «l'ultimo saldo che ho letto» e'
    una cosa che si puo' dire con la sua ora accanto. Dopo lo scollegamento
    quella stessa cifra non e' piu' verificabile, e presentarla come il saldo
    di adesso e' la bugia piu' facile di tutto il prodotto.
    """
    from connectors.bank.service import accounts_of

    state = "non_collegato"
    try:
        import deps
        from connectors.bank.link import connection_state
        from connectors.bank.service import BankReadService

        service = BankReadService(
            db=db, permissions=deps.get_permissions_service(),
            vault=deps.get_token_vault(),
        )
        state = str((await connection_state(service, user_id=owner_id))["stato"])
    except Exception as e:
        logger.info("connection state soft-fail: %s", type(e).__name__)

    connected = state in ("collegato", "collegamento_in_corso")

    try:
        rows = await accounts_of(db, owner_id)
    except Exception as e:
        logger.info("account read soft-fail: %s", type(e).__name__)
        rows = []

    out: Dict[str, Any] = {
        "stato": state,
        "posso_leggere_adesso": connected,
        "saldo_attuale": None,
        "ultimo_saldo_osservato": None,
    }

    live = [r for r in rows if not r.get("source_disconnected_at")]
    picked = (live or rows)
    if not picked:
        return out

    row = picked[0]
    available = row.get("available_balance")
    booked = row.get("current_balance")
    shown = available if available is not None else booked
    if shown is None:
        return out

    reading = {
        "quanto": _money(float(shown), str(row.get("currency") or "EUR")),
        "tipo": "disponibile" if available is not None else "contabile",
        "letto_quando": str(row.get("balance_at") or row.get("updated_at") or "")[:19],
        "banca": row.get("institution") or "",
    }

    if live:
        # Il conto c'e'. Resta comunque una lettura con un'ora sopra, non un
        # numero eterno: «hai X» sarebbe vero solo nell'istante in cui e'
        # stato letto.
        out["saldo_attuale"] = None
        out["ultimo_saldo_osservato"] = reading
        out["come_dirlo"] = (
            "Il conto è collegato. Puoi dire qual è l'ultimo saldo che hai "
            "letto e quando l'hai letto. Non dire «hai X» come se fosse una "
            "verità senza tempo."
        )
        return out

    out["ultimo_saldo_osservato"] = {
        **reading,
        "non_piu_verificabile": True,
        "quando_il_conto_era_collegato": True,
    }
    out["come_dirlo"] = (
        "Il conto non è più collegato: non conosci il saldo attuale e non "
        "puoi leggerne di nuovi. Puoi dire quale saldo risultava l'ultima "
        "volta che hai potuto leggerlo, dicendo che non puoi confermare che "
        "sia ancora così. Non usare il presente, non promettere di guardare, "
        "e non dire che stai leggendo i movimenti."
    )
    return out
