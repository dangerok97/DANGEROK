"""
«Conti e denaro»: cosa ORA vede della banca, e cosa ne ha capito.

    LA DOMANDA A CUI QUESTA SCHERMATA RISPONDE NON E' «QUANTO HO SPESO».

E' un'altra, e piu' scomoda: *cosa sta guardando ORA, e cosa se ne fa?* Una
persona che collega il proprio conto a un sistema che gli gestisce la vita ha
diritto di vedere esattamente questo, e di vederlo separato per gradi di
certezza — perche' la differenza fra «ho visto un pagamento» e «penso sia
l'affitto» e' tutta.

Quattro blocchi, e l'ordine e' quello che conta:

  **I conti.** Cosa e' collegato, di quale banca, aggiornato quando, con
  quale saldo — se la banca lo da'. Piu' cosa ORA puo' e non puo' fare.

  **Cosa ORA ha capito.** Le ricorrenze riconosciute, ciascuna con quanto
  ci si puo' contare.

  **Collegato alla tua vita.** Quali di queste cose stanno dentro qualcosa
  che sta succedendo.

  **Da capire.** Quello che si ripete e non si sa cosa sia. E' il blocco che
  fa la differenza fra un sistema onesto e uno che indovina.

Non c'e' un totale delle spese, non c'e' una torta per categoria e non c'e'
un «ti restano»: chi vuole quello apre la banca. Questa schermata esiste per
la fiducia, non per la contabilita'.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ora.financial.overview")

# Cosa ORA puo' fare con un conto collegato, detto a una persona. Non gli
# scope tecnici: quelli non dicono niente a nessuno, e nascondono proprio la
# cosa che uno vuole sapere.
WHAT_ORA_CAN_DO = "Posso leggere i saldi e i movimenti, per capire come stai messo."
WHAT_ORA_CANNOT_DO = "Non posso spostare denaro, pagare, né disdire niente."


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


def _how_long_ago(value: Any) -> str:
    """«12 minuti fa». Se non si sa quando, lo si dice."""
    when = _moment(value)
    if when is None:
        return "non so quando"
    minutes = int((datetime.now(timezone.utc) - when).total_seconds() // 60)
    if minutes < 1:
        return "adesso"
    if minutes < 60:
        return f"{minutes} minut{'o' if minutes == 1 else 'i'} fa"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} or{'a' if hours == 1 else 'e'} fa"
    days = hours // 24
    return f"{days} giorn{'o' if days == 1 else 'i'} fa"


def _money(amount: Optional[float], currency: str = "EUR") -> str:
    from financial.models import Money

    return Money(amount=amount, currency=currency).for_human()


async def money_overview(db, owner_id: str, *, days: int = 30) -> Dict[str, Any]:
    """
    Tutto quello che serve alla schermata, gia' diviso per come lo si sa.

    Niente id, niente stati tecnici, niente confidenze numeriche: le frasi
    escono da qui pronte, cosi' che la schermata non debba rifare da sola la
    distinzione fra affermare, riferire e chiedere.
    """
    from connectors.bank.service import accounts_of
    from financial.durable import governed_facts, needs_your_word
    from financial.knowledge import what_ora_knows
    from financial.observation import ObservationStore

    connection = await _connection(db, owner_id)
    still_connected = str(connection.get("stato")) in (
        "collegato", "collegamento_in_corso",
    )

    # I conti collegati adesso, e — separate — le fonti che non lo sono piu'.
    #
    #     UNA FONTE SCOLLEGATA NON STA DENTRO «CONTI COLLEGATI».
    #
    # Trovato sullo stato vero, dopo aver scollegato il conto Enable Banking:
    # in cima la schermata diceva «Nessun conto collegato» e dieci righe piu'
    # sotto mostrava «Mock ASPSP · Disponibile €3.250 · non più collegato».
    # Le due cose non possono stare nella stessa schermata, e la seconda e'
    # peggio della prima: un saldo di tre giorni fa presentato come il saldo,
    # sotto un titolo che promette che sia attuale.
    #
    # Quindi la riga si sposta, e cambia parole: non «Disponibile €3.250» ma
    # «Ultimo saldo osservato», con la data e senza il presente.
    accounts = []
    past_sources = []
    for row in await accounts_of(db, owner_id):
        # Contabile e disponibile non sono la stessa cosa, e la differenza si
        # vede quando conta: il disponibile tiene conto di quello che e' gia'
        # impegnato e non ancora contabilizzato. Si mostra quello che la
        # banca ha dato, dicendo quale dei due e'.
        available = row.get("available_balance")
        booked = row.get("current_balance")
        shown = available if available is not None else booked
        currency = str(row.get("currency") or "EUR")
        disconnected = row.get("source_disconnected_at")
        kind = (
            "disponibile" if available is not None
            else "contabile" if booked is not None else ""
        )

        if disconnected:
            past_sources.append({
                "banca": row.get("institution") or "Banca",
                "conto": row.get("display_name") or "Conto",
                "numero": row.get("masked_number") or "",
                # Al passato, e detto per intero: e' l'ultima cosa che si e'
                # potuta leggere, non quello che c'e' adesso.
                "ultimo_saldo": (
                    f"Ultimo saldo osservato: {_money(shown, currency)}"
                    if shown is not None else "Saldo mai comunicato dalla banca"
                ),
                "letto_l_ultima_volta": _how_long_ago(
                    row.get("balance_at") or row.get("updated_at")
                ),
                "scollegato": _how_long_ago(disconnected),
                "in_parole": (
                    "Questo conto non è più collegato: non posso più leggerlo, "
                    "e non so se il saldo sia ancora questo."
                ),
            })
            continue

        accounts.append({
            "banca": row.get("institution") or "Banca",
            "conto": row.get("display_name") or "Conto",
            # Le ultime quattro cifre, quando ci sono. Mai il numero intero.
            "numero": row.get("masked_number") or "",
            # Il saldo compare solo se la banca lo da'. Uno zero di ripiego
            # direbbe «hai il conto vuoto», che e' falso e preciso.
            "saldo": _money(shown, currency) if shown is not None
                     else "saldo non comunicato dalla banca",
            "saldo_noto": shown is not None,
            "saldo_tipo": kind,
            # Un saldo senza un'ora sopra e' una cifra che si spaccia per
            # adesso. Con l'ora e' un'osservazione, che e' quello che e'.
            "aggiornato": _how_long_ago(row.get("balance_at") or row.get("updated_at")),
            "non_piu_aggiornato": False,
            "cosa_posso_fare": WHAT_ORA_CAN_DO,
            "cosa_non_posso_fare": WHAT_ORA_CANNOT_DO,
        })

    said = await what_ora_knows(db, owner_id, days=days)

    # Cosa ORA ha capito, e con che diritto lo dice.
    #
    #     SO · PENSO · HO VISTO
    #
    # Tre gradi, e non sono una sfumatura di tono: sono tre cose diverse.
    # «So» e' passato dalla governance ed e' affermabile. «Penso» e' una
    # lettura non ancora confermata, e va detta con il come. «Ho visto» non
    # e' nemmeno un'interpretazione: e' una cosa successa sul conto che
    # nessuno ha ancora capito, e dirla cosi' e' l'unica versione onesta.
    understood: List[Dict[str, Any]] = []
    for row in said["so"]:
        understood.append({
            "cosa": row["cosa"], "quanto": row["quanto"],
            "ogni_quanto": row.get("quando") or "",
            "stato": "SO",
            "perche": row.get("come_lo_so") or "",
            # Compatibilita' con chi leggeva la versione precedente.
            "quanto_ci_conto": "lo so",
        })
    for row in said["ho_letto"]:
        understood.append({
            "cosa": row["cosa"], "quanto": row["quanto"],
            "ogni_quanto": row.get("quando") or "",
            "stato": "PENSO",
            "perche": row.get("come_lo_so", ""),
            "quanto_ci_conto": "penso",
            "come_lo_so": row.get("come_lo_so", ""),
        })
    understood.extend(await seen_not_understood(
        db, owner_id, still_connected=still_connected,
    ))

    # Collegato alla vita: le situazioni che questi fatti toccano davvero.
    linked: List[Dict[str, Any]] = []
    try:
        situations = {
            str(o.get("id")): str(o.get("title") or "")
            for o in await db.life_objects.find(
                {"user_id": owner_id, "status": {"$ne": "archived"}},
                {"_id": 0, "id": 1, "title": 1},
            ).to_list(20)
        }
        by_situation: Dict[str, List[str]] = {}
        # Anche quello che non e' diventato memoria.
        #
        #     UNA SPESA PUO' APPARTENERE A QUALCOSA SENZA DURARE.
        #
        # Il notaio dell'acquisto e' contesto di una situazione, non una cosa
        # che ORA sa di te: la governance lo rifiuta come memoria, e fa bene.
        # Ma appartiene a quell'acquisto, ed e' proprio li' che serve —
        # leggerlo solo dalle memorie lo faceva sparire dalla schermata che
        # esiste per mostrarlo.
        from financial.store import FinancialStore

        everything = (
            await governed_facts(db, owner_id)
            + await FinancialStore(db).known(owner_id)
        )
        for fact in everything:
            for ref in fact.about_refs or []:
                if ref in situations:
                    by_situation.setdefault(ref, []).append(fact.what)
        for ref, names in by_situation.items():
            linked.append({
                "situazione": situations[ref],
                "cosa_ci_metto": names[:4],
            })
    except Exception as e:
        logger.info("situation read soft-fail: %s", type(e).__name__)

    # Da capire: le domande aperte piu' le ricorrenze che nessuno ha nominato.
    to_understand: List[Dict[str, Any]] = []
    for ask in await needs_your_word(db, owner_id):
        was = f" Finora sapevo {ask['instead_of']}." if ask["instead_of"] else ""
        to_understand.append({
            "cosa": f"«{ask['what']}» è {ask['how_much']}?",
            "perche": f"L'ho letto: {ask['how_directly']}.{was}".strip(),
            "stato": "DA CAPIRE",
            "posso_rispondere": True,
        })

    return {
        "collegamento": connection,
        "conti": accounts,
        # In fondo, e in tono minore: quello che c'era.
        "fonti_non_piu_collegate": past_sources,
        "cosa_ho_capito": understood,
        "collegato_alla_tua_vita": linked,
        "da_capire": to_understand,
        "movimenti_recenti": await recent_movements(db, owner_id),
        # Se non c'e' niente da mostrare, la schermata deve saperlo e tacere.
        "vale_la_pena_mostrarlo": bool(
            accounts or past_sources or understood or linked or to_understand
        ),
    }


async def _connection(db, owner_id: str) -> Dict[str, Any]:
    """
    Com'e' messo il collegamento con la banca, in una frase.

    Sta in cima alla schermata perche' e' la prima cosa che cambia il senso
    di tutto quello che c'e' sotto: gli stessi movimenti, con un consenso
    scaduto, sono la fotografia di tre settimane fa.
    """
    import deps
    from connectors.bank.link import connection_state
    from connectors.bank.service import BankReadService

    try:
        service = BankReadService(
            db=db, permissions=deps.get_permissions_service(),
            vault=deps.get_token_vault(),
        )
        return await connection_state(service, user_id=owner_id)
    except Exception as e:
        logger.info("connection state soft-fail: %s", type(e).__name__)
        return {"stato": "non_collegato", "in_parole": "Nessun conto collegato."}


async def seen_not_understood(
    db, owner_id: str, *, still_connected: bool = True,
) -> List[Dict[str, Any]]:
    """
    Le cose che tornano sul conto e che nessuno ha ancora capito.

        «HO VISTO» NON E' UN'INTERPRETAZIONE DEBOLE: E' UN'ALTRA COSA.

    Un addebito di 14,99 che si ripete ogni mese e' un fatto osservato. Che
    cosa sia — un abbonamento, una polizza, una quota — non lo sa nessuno, e
    la riga deve dire esattamente questo. La versione sbagliata di questa
    riga e' «Abbonamento mensile · penso»: e' un nome plausibile appiccicato
    a una cosa ignota, e chi legge non ha modo di accorgersene.

    Quello che si dice qui e' solo aritmetica: quante volte, ogni quanto,
    quanto. Nessun nome, perche' non c'e'.
    """
    from financial.observation import ObservationStore, _grouping_key
    from financial.store import FinancialStore

    try:
        history = await ObservationStore(db).history(owner_id)
    except Exception as e:
        logger.info("observation read soft-fail: %s", type(e).__name__)
        return []

    # Quali movimenti sono gia' diventati qualcosa: quelli non si ripetono
    # qui, o la stessa cosa comparirebbe due volte con due gradi diversi.
    spoken_for = set()
    try:
        for fact in await FinancialStore(db).known(owner_id):
            spoken_for.update(fact.source_refs or [])
    except Exception as e:
        logger.info("fact read soft-fail: %s", type(e).__name__)

    groups: Dict[str, List[Any]] = {}
    for observation in history:
        groups.setdefault(_grouping_key(observation), []).append(observation)

    out: List[Dict[str, Any]] = []
    for members in groups.values():
        # Se anche uno solo dei movimenti di questo gruppo e' gia' diventato
        # qualcosa, il gruppo intero non e' piu' «da capire».
        #
        #     LA STESSA COSA NON PUO' COMPARIRE DUE VOLTE CON DUE GRADI.
        #
        # Un fatto nasce dal movimento piu' recente e porta il riferimento di
        # quello solo; gli altri cinque bonifici identici restavano orfani e
        # ricomparivano come «ho visto un pagamento di €760 sei volte» sotto
        # la riga «SO — Affitto €760». Due gradi di certezza sulla stessa
        # cosa, uno accanto all'altro: la confusione esatta che questa
        # schermata esiste per togliere.
        if any(o.transaction_ref in spoken_for for o in members):
            continue
        if len(members) < 2:
            # Una volta sola non e' «torna»: e' successo, e sta nei movimenti.
            continue
        members.sort(key=lambda o: str(o.booked_at))
        newest = members[-1]
        gap = _typical_gap(members)
        out.append({
            "cosa": (
                f"{'Entrata' if newest.direction == 'incoming' else 'Pagamento'} di "
                f"{_money(abs(newest.amount), newest.currency)}"
            ),
            "quanto": _money(abs(newest.amount), newest.currency),
            "ogni_quanto": "",
            "stato": "HO VISTO",
            # Al passato quando la fonte non c'e' piu'.
            #
            #     UNA COSA VISTA IERI NON E' UNA COSA CHE STO VEDENDO.
            #
            # «L'ho visto 3 volte» dopo lo scollegamento suggerisce che ORA
            # stia ancora guardando, e quindi che possa verificare. Non puo':
            # la frase deve dire quando lo guardava.
            "perche": (
                f"l'ho visto {len(members)} volte"
                + (f", all'incirca ogni {gap} giorni" if gap else "")
                + ("" if still_connected else ", quando il conto era collegato")
            ),
            "non_so": (
                "Non so ancora che cosa sia." if still_connected
                else "Non so che cosa sia, e non posso più verificarlo."
            ),
        })
    # Le cose che tornano piu' spesso per prime: sono quelle su cui una
    # risposta della persona vale di piu'.
    out.sort(key=lambda r: r["perche"], reverse=True)
    return out[:6]


def _typical_gap(members: List[Any]) -> Optional[int]:
    """Ogni quanti giorni, in media. Aritmetica, non una conclusione."""
    moments = [m for m in (_moment(o.booked_at) for o in members) if m]
    if len(moments) < 2:
        return None
    gaps = [
        (later - earlier).total_seconds() / 86400.0
        for earlier, later in zip(moments, moments[1:])
    ]
    return int(round(sum(gaps) / len(gaps)))


async def recent_movements(
    db, owner_id: str, *, limit: int = 12,
) -> List[Dict[str, Any]]:
    """
    I movimenti visti, come li ha scritti la banca.

        L'OSSERVAZIONE E L'INTERPRETAZIONE NON SI FONDONO MAI.

    Questa lista e' cruda di proposito: data, descrizione, importo. Cosa ORA
    pensa di ciascuno sta nel blocco «cosa ho capito», separato — perche' un
    elenco che scrive «Affitto» sopra una riga che diceva «BONIFICO A ROSSI
    MARCO» ha appena trasformato un'ipotesi in un fatto sotto gli occhi di
    chi legge, e nessuno se ne accorge.
    """
    from financial.observation import ObservationStore

    out = []
    for observation in await ObservationStore(db).history(owner_id, limit=limit):
        when = _moment(observation.booked_at)
        out.append({
            "quando": when.strftime("%d/%m") if when else "",
            "descrizione": observation.raw_description or observation.counterparty or "",
            "quanto": _money(abs(observation.amount), observation.currency),
            "verso": "in entrata" if observation.direction == "incoming" else "in uscita",
            "in_sospeso": (observation.provenance or {}).get("status") == "pending",
        })
    return out
