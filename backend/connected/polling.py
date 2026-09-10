"""
Reading the instruments without anybody asking.

    THE USER DOES NOT SYNCHRONISE THEIR LIFE. ORA DOES.

A person connects a mailbox and a calendar. That is the whole of their part.
Everything after it — when to look, how often, what to do when a provider is
down, where to resume after a restart — is ours, and a product that answers
those questions with a button has handed its work back to the person who
asked for help.

There is no new scheduler here. The ambient runtime already ticks, already
survives restarts, already claims work without two processes doing it twice;
this is one more deterministic pass inside that tick, in the shape `sweep()`
already established. It reaches no model, forms no opinion, and cannot decide
that anything matters — it decides only *when to look*, which is arithmetic.

Four properties, each of which is a way this goes wrong if it is missing:

**A source is read on its own cadence.** A mailbox and a calendar do not move
at the same speed, and asking Google for a calendar every two minutes is
rude to no purpose. The cadences live in one table below.

**A failure slows the next attempt down.** Exponential, capped. Without it a
revoked token becomes a request every twenty seconds, forever, until somebody
notices the bill — and the person's source says the same thing either way.

**Nothing is read that should not be.** A disconnected source is not polled;
a revoked one is not polled; a source whose token is gone is not polled. The
check is `is_readable`, which is the same question the manual path asks.

**The schedule is one thing in one place.** `connected_source_attempts` holds
it, for every source, including the document shelf — which has no connector
instance at all and therefore cannot be scheduled by a field on one. The
`next_sync_at` on a connector instance stays the connector layer's own
business; two schedules would disagree the first time one of them was
skipped.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from connected.models import ConnectedSource, now_iso
from connected.sources import ATTEMPTS

logger = logging.getLogger("ora.connected.polling")

# How often each kind of instrument is worth reading, in minutes.
#
# Not one blind interval: a message arrives and matters within the hour, an
# appointment usually moves a day ahead, and the document shelf only changes
# when the person themselves put something on it. These are cost decisions
# about provider quotas and battery, not judgements about what matters in
# somebody's life — nothing here decides whether a change is worth telling
# anybody about.
#
#     QUINDICI MINUTI DI RITARDO SONO UN CALENDARIO CHE NON E' IL TUO.
#
# Erano minuti, ed erano troppi: un appuntamento spostato dal dentista
# compariva in ORA fino a un quarto d'ora dopo, e in quel quarto d'ora la
# schermata diceva con sicurezza una cosa falsa. Adesso si contano in secondi,
# perche' la domanda «ogni quanto» non ha una risposta in minuti interi.
#
# Il numero e' un compromesso di costo — quota del provider e batteria — e non
# un giudizio su cosa conti nella vita di qualcuno. Lo scaffale dei documenti
# resta lento perche' cambia solo quando e' la persona a metterci qualcosa.
#
#     LA LATENZA E' UNA CADENZA, NON UNA MEDIA.
#
# Misurato sull'account vero, tracciando la catena intera: la coda era vuota,
# la sorgente veniva presa entro 1-3 secondi da quando scadeva, e i secondi
# si perdevano tutti dentro un punto solo — fra la presa e la riga scritta.
# Il motivo non e' la lentezza del sync (2 secondi), e' che un cambiamento
# fatto su Google un istante prima non e' ancora nella delta che Google
# restituisce: quella lettura torna a mani vuote, e la successiva e' lontana
# una cadenza intera. Con 45 s facevano 52 s e 47 s: dentro il minuto, ma per
# un pelo, e con il caso peggiore fuori.
#
# Quindi la latenza tipica *e'* la cadenza, piu' il giro. 20 + 10 = 30 s per
# il calendario, che e' il bersaglio; 60 + 10 = 70 s per la posta, dentro i
# 120 promessi. Sono decisioni di costo — una lettura incrementale ogni venti
# secondi per persona — e non giudizi su cosa conti nella vita di qualcuno.
POLL_SECONDS: Dict[str, int] = {
    "calendar": 20,
    "email": 60,
    "documents": 1800,
    # Una banca non e' una casella: le righe arrivano quando la banca le
    # contabilizza, e guardarla piu' spesso non le fa arrivare prima. Sei
    # ore. Con alcuni aggregatori ogni chiamata si paga, e con tutti c'e' un
    # tetto giornaliero imposto per legge.
    "bank": 21600,
}
DEFAULT_POLL_SECONDS = 1800

# Compatibilita' all'indietro per chi leggeva i minuti. Derivato, non
# duplicato: due tabelle che dicono la stessa cosa divergono in una settimana.
POLL_MINUTES: Dict[str, int] = {
    kind: max(1, round(seconds / 60)) for kind, seconds in POLL_SECONDS.items()
}
DEFAULT_POLL_MINUTES = max(1, round(DEFAULT_POLL_SECONDS / 60))

# What a failure costs the next attempt. Doubling, capped at an hour: a
# provider that is down stays down for a while, and a retry storm helps
# nobody — least of all the person, whose source says "cannot read this"
# either way.
BACKOFF_CAP_MINUTES = 60

# Quanto puo' durare un giro, e quante sorgenti puo' toccare al massimo.
#
#     UN TETTO FISSO SU UNA CODA CHE CRESCE NON E' UN LIMITE: E' UNA FAME.
#
# Era un numero solo, quattro sorgenti a giro. Il giro parte ogni venti
# secondi: dodici letture al minuto. Con cinquecento sorgenti collegate e una
# casella da guardare ogni cinque minuti, la domanda e' molte volte
# l'offerta, e la coda non torna mai indietro: chi sta in fondo non viene
# letto mai piu'. Non «tardi»: mai. Ed e' successo — su questo database la
# casella su cui si stava lavorando e' rimasta scaduta per un'ora e mezza
# mentre il loop girava e diceva di aver letto qualcosa.
#
# Quello che davvero non deve succedere e' che un giro duri piu' del giro
# stesso. Quindi il limite e' il tempo, che e' il vincolo vero, e il conteggio
# resta solo come rete di sicurezza. Un arretrato grande viene smaltito in
# proporzione a quanto e' grande, invece che quattro alla volta per sempre.
TICK_BUDGET_SECONDS = float(os.environ.get("CONNECTED_TICK_BUDGET_SECONDS", "12"))
MAX_PER_TICK = int(os.environ.get("CONNECTED_MAX_PER_TICK", "40"))

# Quante persone e quanti segnali si prova a *capire* per giro.
#
#     LEGGERE NON E' CAPIRE.
#
# Piccolo di proposito: capire costa un giudizio, e un arretrato si smaltisce
# in piu' passaggi invece che in una fattura sola.
UNDERSTAND_PER_TICK = int(os.environ.get("CONNECTED_UNDERSTAND_PER_TICK", "2"))
UNDERSTAND_PER_OWNER = int(os.environ.get("CONNECTED_UNDERSTAND_PER_OWNER", "4"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _moment(value: Any) -> Optional[datetime]:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def interval_for(source_type: str, failures: int = 0) -> timedelta:
    """
    How long until this source is worth reading again.

    Pure arithmetic on two facts — what kind of instrument it is, and how many
    times in a row reading it has failed — so it can be reasoned about and
    tested without a clock, a provider or a database.
    """
    base = POLL_SECONDS.get(source_type, DEFAULT_POLL_SECONDS)
    if failures > 0:
        # Un provider che non risponde resta giu' per un po', e una raffica di
        # tentativi non aiuta nessuno — men che meno la persona, alla quale la
        # sorgente dice «non riesco a leggere questo» in entrambi i casi.
        base = min(BACKOFF_CAP_MINUTES * 60, base * (2 ** min(failures, 6)))
    return timedelta(seconds=base)


async def due(db, owner_id: str, *, now: Optional[datetime] = None) -> List[ConnectedSource]:
    """
    Which of this person's instruments are worth reading right now.

    A source nobody has ever read is due immediately — that is the first sync
    after connecting, and waiting a full interval for it would mean somebody
    connects a mailbox and sees nothing happen for five minutes.
    """
    from connected.service import ConnectedLifeService

    moment = now or _now()
    sources = await ConnectedLifeService(db).sources.list(owner_id)
    schedule = {
        row["source_id"]: row
        for row in await db[ATTEMPTS].find(
            {"owner_id": owner_id},
            {"_id": 0, "source_id": 1, "next_attempt_at": 1, "not_before": 1},
        ).to_list(50)
    }

    out: List[ConnectedSource] = []
    for source in sources:
        if not source.is_readable:
            # Disconnected, revoked, never authorised. Not an error and not a
            # thing to retry: there is nothing to read through.
            continue
        row = schedule.get(source.id) or {}
        # Un tetto imposto dal provider vince sulla nostra cadenza.
        #
        #     LA NOSTRA IDEA DI «OGNI SEI ORE» NON E' UN DIRITTO.
        #
        # Alcune banche concedono quattro letture al giorno per conto, per
        # obbligo di legge, e lo dicono nella risposta. Chiedere lo stesso
        # non fa arrivare i dati: fa arrivare 429, che consuma comunque.
        held = _moment(row.get("not_before"))
        if held is not None and held > moment:
            continue
        when = _moment(row.get("next_attempt_at"))
        if when is None or when <= moment:
            out.append(source)
    return out


async def hold_source(
    db, owner_id: str, source_id: str, *, until: str,
) -> str:
    """
    Non ripassare da questa sorgente prima di quest'ora — l'ha detta il provider.

    Diverso dal backoff, che e' una nostra prudenza dopo un errore: questo e'
    un limite di chi possiede i dati, e non si contratta. Resta scritto sulla
    riga di coda perche' e' li' che `due` lo guarda, e sopravvive a un
    riavvio come tutto il resto della coda.
    """
    await db[ATTEMPTS].update_one(
        {"owner_id": owner_id, "source_id": source_id},
        {"$set": {
            "owner_id": owner_id, "source_id": source_id,
            "not_before": until,
            "next_attempt_at": until,
            "health": "la banca non concede altre letture per adesso",
        }},
        upsert=True,
    )
    return until


async def schedule_next(
    db, owner_id: str, source_id: str, source_type: str, *,
    failed: bool, now: Optional[datetime] = None,
) -> str:
    """
    Write down when to look again, and how many times in a row it has failed.

    Recorded after every attempt, successful or not — a source whose next
    attempt is never written would be read on every single tick.
    """
    moment = now or _now()
    row = await db[ATTEMPTS].find_one(
        {"owner_id": owner_id, "source_id": source_id},
        {"_id": 0, "failures": 1, "not_before": 1},
    )
    failures = int((row or {}).get("failures") or 0) + 1 if failed else 0
    when = (moment + interval_for(source_type, failures)).isoformat()
    # Se il provider ha imposto un'ora, la nostra cadenza non puo' anticiparla.
    held = (row or {}).get("not_before")
    if held and str(held) > when:
        when = str(held)
    await db[ATTEMPTS].update_one(
        {"owner_id": owner_id, "source_id": source_id},
        {"$set": {"owner_id": owner_id, "source_id": source_id,
                  "failures": failures, "next_attempt_at": when}},
        upsert=True,
    )
    return when


async def park_stale(db, owner_id: str, *, now: Optional[datetime] = None) -> int:
    """
    Sposta avanti le righe di coda che non corrispondono a niente da leggere.

        UNA RIGA CHE NON PUNTA A NIENTE NON STA ASPETTANDO: STA BLOCCANDO.

    La coda e' ordinata per «chi aspetta da piu' tempo», ed e' l'ordine
    giusto. Ma una riga scaduta la cui sorgente non e' leggibile — consenso
    revocato, connettore scollegato, istanza sparita — non viene mai letta, e
    quindi non viene mai riprogrammata: resta in testa alla coda per sempre,
    e tutti quelli dietro non arrivano mai.

    Era successo, e in grande: cinquecento righe scadute, di cui le prime
    settanta di persone che non avevano piu' niente di leggibile. La casella
    su cui questa cosa veniva dimostrata era in posizione settantatre e non
    veniva letta da un'ora e mezza, mentre il loop girava ogni venti secondi
    dicendo di aver letto qualcosa.

    Quindi la riga si sposta avanti di un intervallo normale. Non si
    cancella: se la persona ricollega la sorgente, `due` la considera
    scaduta comunque, e una riga in meno sarebbe una cosa in meno da
    spiegare quando qualcuno chiede perche' non veniva letta.
    """
    moment = now or _now()
    try:
        readable = {
            source.id for source in
            await _readable_sources(db, owner_id)
        }
        rows = await db[ATTEMPTS].find(
            {"owner_id": owner_id, "next_attempt_at": {"$lte": moment.isoformat()}},
            {"_id": 0, "source_id": 1},
        ).to_list(50)
    except Exception as e:
        logger.info("park scan soft-fail: %s", type(e).__name__)
        return 0

    moved = 0
    for row in rows:
        source_id = str(row.get("source_id") or "")
        if not source_id or source_id in readable:
            continue
        await db[ATTEMPTS].update_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"$set": {
                "next_attempt_at": (
                    moment + timedelta(minutes=DEFAULT_POLL_MINUTES)
                ).isoformat(),
                "health": "non c'è niente da leggere qui",
            }},
        )
        moved += 1
    return moved


async def _readable_sources(db, owner_id: str):
    from connected.service import ConnectedLifeService

    return [
        source for source in await ConnectedLifeService(db).sources.list(owner_id)
        if source.is_readable
    ]


async def owners_to_look_at(
    db, *, now: Optional[datetime] = None, limit: int = MAX_PER_TICK,
) -> List[str]:
    """
    Whose instruments are worth looking at on this pass, oldest wait first.

        A LOOP THAT ALWAYS STARTS AT THE SAME NAME NEVER REACHES THE LAST ONE.

    Asked of the schedule rather than of the list of people. The first version
    of this walked every owner with a connected account and took the first two
    hundred — which on a database with a thousand of them meant the people
    past that cut were never read, deterministically, for ever. It looked
    like a fairness nicety and it was a source going dark: on the account this
    was being demonstrated on, neither the mailbox nor the calendar was ever
    reached.

    So the order is "who has been waiting longest", which is the same rule
    that makes any queue fair, and the people with no schedule row yet — a
    source connected a minute ago and never read — come first, because a
    first reading that waits is indistinguishable from a connection that did
    not work.
    """
    moment = now or _now()
    waiting: List[str] = []

    try:
        overdue = await db[ATTEMPTS].find(
            {"next_attempt_at": {"$lte": moment.isoformat()}},
            {"_id": 0, "owner_id": 1},
        ).sort("next_attempt_at", 1).to_list(max(1, limit) * 4)
        waiting.extend(str(r.get("owner_id") or "") for r in overdue)
    except Exception as e:
        logger.info("due scan soft-fail: %s", type(e).__name__)

    try:
        # Somebody who connected something and has never been read at all.
        # Rarer, and the one case where waiting is most visible to a person.
        fresh = await db.connector_instances.find(
            {"status": {"$in": ["connected", "syncing", "active"]}},
            {"_id": 0, "user_id": 1},
        ).sort("created_at", -1).to_list(200)
        known = {
            str(r.get("owner_id") or "")
            for r in await db[ATTEMPTS].find({}, {"_id": 0, "owner_id": 1}).to_list(500)
        }
        # Al massimo uno per giro, davanti agli altri.
        #
        # Chi ha appena collegato qualcosa va letto subito: aspettare la
        # coda vorrebbe dire guardare una schermata che non cambia dopo aver
        # detto sì a Google, che è indistinguibile da un collegamento che non
        # ha funzionato.
        #
        # Ma **uno** per giro. Metterli tutti davanti — la prima versione —
        # significa che su un database con centinaia di account di prova mai
        # letti nessuno di loro lascia mai passare gli altri: il calendario e
        # la casella veri non venivano raggiunti da nessun giro, per ore,
        # mentre il loop si dichiarava occupato.
        for row in fresh:
            owner = str(row.get("user_id") or "")
            if owner and owner not in known and owner not in waiting:
                waiting.insert(0, owner)
                break
    except Exception as e:
        logger.info("new source scan soft-fail: %s", type(e).__name__)

    seen: List[str] = []
    for owner in waiting:
        if owner and owner not in seen:
            seen.append(owner)
    return seen[: max(1, limit) * 2]


async def _what_to_read(
    db, *, now: datetime, limit: int,
) -> Tuple[List[Tuple[str, ConnectedSource]], int]:
    """
    Cosa leggere adesso, in ordine di quanto ha aspettato — e cosa togliere di mezzo.

        UNA SORGENTE SANA NON DEVE STARE DIETRO A UNA CHE NON SI PUO' LEGGERE.

    La coda si guarda per riga, non per persona. Ogni riga scaduta punta a
    una sorgente: se quella sorgente e' leggibile finisce nell'elenco da
    servire, e se non lo e' — consenso revocato, connettore scollegato,
    istanza sparita — la riga viene spostata avanti li' per li'.

    Lo spostamento non consuma il tempo del giro. E' il punto: se costasse
    budget, con qualche centinaio di righe morte in testa il budget finirebbe
    prima di arrivare a chi si poteva davvero leggere, ed e' esattamente la
    fame che questa funzione esiste per evitare.

    Il costo per giro e' limitato da `limit`: si guardano piu' righe di
    quante se ne serviranno — le righe morte non contano — ma non tutta la
    coda, e le persone risolte sono al massimo qualche decina.
    """
    from connected.service import ConnectedLifeService

    try:
        rows = await db[ATTEMPTS].find(
            {"next_attempt_at": {"$lte": now.isoformat()}},
            {"_id": 0, "owner_id": 1, "source_id": 1},
        ).sort("next_attempt_at", 1).to_list(max(1, limit) * 8)
    except Exception as e:
        logger.info("due scan soft-fail: %s", type(e).__name__)
        rows = []

    service = ConnectedLifeService(db)
    ready_by_owner: Dict[str, Dict[str, ConnectedSource]] = {}
    queue: List[Tuple[str, ConnectedSource]] = []
    dead: List[Tuple[str, str]] = []
    # Le persone di cui non si e' riusciti a sapere niente in questo giro. Le
    # loro righe non si toccano: non sapere non e' una risposta.
    unknown: set = set()

    for row in rows:
        owner_id = str(row.get("owner_id") or "")
        source_id = str(row.get("source_id") or "")
        if not owner_id or not source_id:
            continue
        if owner_id not in ready_by_owner:
            if len(ready_by_owner) >= max(1, limit) * 2:
                break
            try:
                ready_by_owner[owner_id] = {
                    s.id: s for s in await due(db, owner_id, now=now)
                }
            except Exception as e:
                # NON SO NON E' NIENTE DA LEGGERE.
                #
                # Se chiedere quali sorgenti ha questa persona fallisce — un
                # singhiozzo del database, una connessione caduta — non si sa
                # niente di lei, e non sapere non e' una risposta. Trattarlo
                # come «qui non c'e' niente» spostava avanti di mezz'ora un
                # calendario perfettamente sano: e' successo qui, su questo
                # account, e per mezz'ora ORA non ha piu' letto niente.
                #
                # Quindi si lascia la riga dov'e' e si riprova al giro dopo.
                logger.info("due soft-fail owner: %s", type(e).__name__)
                unknown.add(owner_id)
                continue
        found = ready_by_owner[owner_id].pop(source_id, None)
        if found is not None:
            queue.append((owner_id, found))
        elif owner_id not in unknown:
            dead.append((owner_id, source_id))

    # Chi si e' appena collegato e non ha ancora una riga in coda.
    #
    #     UNA PRIMA LETTURA CHE ASPETTA E' UN COLLEGAMENTO CHE SEMBRA ROTTO.
    #
    # La coda si guarda per riga, e una sorgente appena collegata non ha
    # ancora una riga: guardando solo la coda non la si troverebbe mai. Si
    # cercano quindi le persone che hanno qualcosa di collegato e nessuna
    # riga, e le loro sorgenti passano davanti — sono poche, e sono quelle
    # per cui l'attesa si vede di piu'.
    if len(queue) < limit:
        for owner_id, ready in ready_by_owner.items():
            for source in ready.values():
                queue.append((owner_id, source))
        try:
            known = {
                str(r.get("owner_id") or "")
                for r in await db[ATTEMPTS].find(
                    {}, {"_id": 0, "owner_id": 1},
                ).to_list(4000)
            }
            fresh = await db.connector_instances.find(
                {"status": {"$in": ["connected", "syncing", "active"]}},
                {"_id": 0, "user_id": 1},
            ).sort("created_at", -1).to_list(200)
        except Exception as e:
            logger.info("new source scan soft-fail: %s", type(e).__name__)
            fresh = []
            known = set()
        newcomers = []
        for row in fresh:
            owner_id = str(row.get("user_id") or "")
            if owner_id and owner_id not in known and owner_id not in ready_by_owner:
                ready_by_owner[owner_id] = {}
                for source in await due(db, owner_id, now=now):
                    newcomers.append((owner_id, source))
        queue = newcomers + queue

    parked = 0
    if dead:
        # Un solo giro di scritture, fuori dal budget del tick.
        later = (now + timedelta(seconds=DEFAULT_POLL_SECONDS)).isoformat()
        for owner_id, source_id in dead:
            try:
                await db[ATTEMPTS].update_one(
                    {"owner_id": owner_id, "source_id": source_id},
                    {"$set": {"next_attempt_at": later,
                              "health": "non c'è niente da leggere qui"}},
                )
                parked += 1
            except Exception as e:
                logger.info("park soft-fail: %s", type(e).__name__)
                break

    return queue[: max(1, limit)], parked


async def poll_once(
    db, *, now: Optional[datetime] = None, limit: int = MAX_PER_TICK,
    owners: Optional[List[str]] = None,
) -> Dict[str, int]:
    """
    One pass over everybody's instruments: read what is due, note when to look again.

    Deliberately separated from the loop so a test can drive it with its own
    clock — the loop decides when this runs, and everything that matters
    happens here.

    A sync that throws is not allowed to stop the pass. One person's revoked
    token must not mean nobody else's calendar is read, which is exactly what
    an unguarded exception in a shared loop produces.
    """
    from connected.service import ConnectedLifeService

    moment = now or _now()
    handled = {"looked_at": 0, "read": 0, "failed": 0, "skipped": 0, "parked": 0,
               "understood": 0, "noise": 0}
    started = time.monotonic()

    def out_of_time() -> bool:
        return (time.monotonic() - started) >= TICK_BUDGET_SECONDS

    # Chi guardare. Con un elenco esplicito sono quelle persone e basta:
    # serve a chiedere «guarda adesso le mie sorgenti» senza far passare
    # avanti nessuno, ed e' anche l'unico modo in cui una prova puo' parlare
    # di una persona precisa su un database condiviso con centinaia di altre.
    if owners:
        queue: List[Tuple[str, ConnectedSource]] = []
        for owner_id in owners:
            queue.extend(
                (owner_id, source) for source in await due(db, owner_id, now=moment)
            )
    else:
        queue, handled["parked"] = await _what_to_read(db, now=moment, limit=limit)

    # Chi ha portato a casa qualcosa di nuovo in questo giro. Leggere non e'
    # capire, e finora il giro finiva alla lettura.
    brought_something: List[str] = []

    for owner_id, source in queue:
        if handled["looked_at"] >= limit or out_of_time():
            break
        handled["looked_at"] += 1
        failed = False
        try:
            result = await ConnectedLifeService(db).sync(owner_id, source.id)
            if result.get("ok"):
                handled["read"] += 1
                if result.get("recorded") and owner_id not in brought_something:
                    brought_something.append(owner_id)
            else:
                # `not_connected` is not a failure to back off from — the
                # source simply is not readable, and `due` will stop offering
                # it as soon as the registry says so.
                handled["skipped"] += 1
                failed = result.get("reason") == "sync_failed"
        except Exception as e:
            logger.info(
                "auto-sync soft-fail source=%s: %s", source.id, type(e).__name__,
            )
            handled["failed"] += 1
            failed = True

        # LA PROSSIMA LETTURA SI CONTA DA QUANDO QUESTA E' FINITA.
        #
        # Si contava dall'inizio del giro. Un giro che tocca parecchie
        # sorgenti dura, e l'ultima di esse si ritrovava programmata a pochi
        # secondi dal momento in cui era appena stata letta: la cadenza
        # diventava un numero scritto da nessuna parte. Quando l'orologio
        # arriva da fuori — una prova che guida il tempo — resta quello: li'
        # il punto e' proprio che il tempo non scorra da solo.
        await schedule_next(
            db, owner_id, source.id, source.source_type,
            failed=failed, now=moment if now is not None else _now(),
        )

    # E poi si guarda cosa e' arrivato.
    #
    #     LEGGERE NON E' CAPIRE.
    #
    # Il giro leggeva le sorgenti e finiva li'. I segnali restavano in attesa
    # di un'interpretazione che partiva solo da una conversazione o da un
    # trigger manuale — e su un account vero se ne sono accumulati 180, mai
    # guardati, con la catena a valle (cambiamenti, opportunita', obiettivi,
    # consegna) ferma per mancanza di materiale invece che per prudenza.
    #
    # Nessuna pipeline nuova: e' il passo che il pacchetto possiede gia',
    # chiamato dal giro che c'era gia', e solo per chi ha portato a casa
    # qualcosa in questo giro.
    # E anche chi ha segnali fermi da prima.
    #
    #     UN ARRETRATO NON SI SMALTISCE DA SOLO SE NESSUNO LO GUARDA.
    #
    # Il primo tentativo capiva solo quello che era appena arrivato: su un
    # account vero restavano 220 segnali letti mesi prima e mai interpretati,
    # e siccome le sorgenti erano tutte fresche il giro non ne toccava
    # nessuno. Capire l'arretrato e' lo stesso lavoro, ed e' quello che
    # separa «ORA legge la tua vita» da «ORA ha letto la tua vita una volta».
    if len(brought_something) < UNDERSTAND_PER_TICK:
        for owner_id in await _owners_with_something_to_understand(
            db, limit=UNDERSTAND_PER_TICK, only=owners,
        ):
            if owner_id not in brought_something:
                brought_something.append(owner_id)

    for owner_id in brought_something[:UNDERSTAND_PER_TICK]:
        if out_of_time():
            break
        try:
            understood = await ConnectedLifeService(db).interpret(
                owner_id, limit=UNDERSTAND_PER_OWNER,
            )
            handled["understood"] += int(understood.get("passed_on") or 0)
            handled["noise"] += int(understood.get("noise") or 0)
        except Exception as e:
            logger.info("interpret soft-fail: %s", type(e).__name__)

    return handled


async def _owners_with_something_to_understand(
    db, *, limit: int, only: Optional[List[str]] = None,
) -> List[str]:
    """
    Chi ha segnali gia' letti e mai guardati.

    Una distinct su una collezione indicizzata: chi non ha niente in attesa
    non compare, e la domanda costa lo stesso su un database vuoto o pieno.
    """
    query: Dict[str, Any] = {"status": "pending"}
    if only:
        query["owner_id"] = {"$in": list(only)}
    try:
        found = await db.connected_signals.distinct("owner_id", query)
    except Exception as e:
        logger.info("pending scan soft-fail: %s", type(e).__name__)
        return []
    return [str(o) for o in found if o][:limit]


async def _owners_with_sources(db) -> List[str]:
    """
    Everybody with something connected. Kept for diagnostics, not for the loop.

    The loop must not start here: this is an unordered list, and taking a
    slice of it means the same people every time. `owners_to_look_at` asks
    the schedule instead.
    """
    try:
        found = await db.connector_instances.distinct(
            "user_id", {"status": {"$in": ["connected", "syncing", "active"]}},
        )
    except Exception as e:
        logger.info("owner scan soft-fail: %s", type(e).__name__)
        return []
    return [str(u) for u in found if u]
