"""
Chi chiamare, e da dove lo sappiamo.

    «CHIAMA LORENZO» NON È UN NUMERO.

È un nome, e un nome da solo non fa squillare niente. Fra la frase e lo squillo
c'è un passaggio che finora faceva una persona a mano: trovare il numero. Qui
lo fa ORA — e non lo fa da sola fino in fondo, perché l'ultimo passo resta di
chi ha chiesto la telefonata.

    E LA PROVENIENZA VIAGGIA CON IL NUMERO, SEMPRE.

Un numero senza provenienza è un numero di cui nessuno può dire se fidarsi.
«L'ho preso dalla tua rubrica» e «l'ho trovato su un sito» sono due cose molto
diverse davanti alla stessa cifra, e chi deve confermare ha il diritto di
sapere quale delle due sta guardando.

    QUATTRO POSTI, IN QUEST'ORDINE, E L'ORDINE È IL PUNTO.

Rubrica, contesto di ORA, web pubblico, e infine la domanda. Non è una
graduatoria di comodità: è una graduatoria di **certezza**. Un numero che la
persona ha salvato lei vale più di uno che abbiamo dedotto, che vale più di uno
trovato su internet. Cercare prima dove si è più sicuri vuol dire, quasi
sempre, non dover cercare dove si è meno sicuri.

    E SUL WEB SI CERCANO ATTIVITÀ, NON PERSONE.

Un dentista, un'officina, un ufficio hanno un numero che hanno pubblicato loro
perché qualcuno li chiami. Una persona privata no: il suo numero, se sta su
internet, ci sta perché è finito lì. Cercarlo sarebbe una ricerca su una
persona, e questo file non ha un ramo che la faccia — non per prudenza, ma
perché non è la stessa operazione.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger("ora.preparation.contacts")

# Da dove può venire un numero. È un elenco chiuso perché ognuna di queste
# parole finisce davanti a una persona, e una provenienza che non si sa
# tradurre in italiano non si può mostrare.
Provenance = Dict[str, str]

COME_SI_DICE: Dict[str, str] = {
    "confirmed": "Confermato da te",
    "address_book": "Rubrica",
    "ora_context": "Contesto ORA",
    "past_call": "Una telefonata precedente",
    "calendar": "Un appuntamento in calendario",
    "official_site": "Sito ufficiale",
    "public_directory": "Elenco pubblico",
    "web": "Trovato sul web",
    "user": "Me l'hai detto tu",
}

# Quanto ci si fida, per provenienza. Non è un numero inventato: è l'ordine di
# ricerca scritto come confidenza, perché il chiamante possa ordinare i
# candidati senza sapere da dove vengono.
QUANTO_CI_SI_FIDA: Dict[str, float] = {
    "confirmed": 1.0,
    "user": 1.0,
    "address_book": 0.95,
    "past_call": 0.85,
    "calendar": 0.7,
    "ora_context": 0.65,
    "official_site": 0.6,
    "public_directory": 0.45,
    "web": 0.3,
}

# Quanto deve valere un candidato per essere anche solo mostrato. Sotto questa
# soglia non è un'ipotesi debole: è rumore, e mostrarlo insegnerebbe a
# confermare senza guardare.
ABBASTANZA = 0.25

# Quanti candidati si mostrano. Oltre, non si sceglie più: si tira a indovinare.
AL_MASSIMO = 5


class ContactCandidate(BaseModel):
    """
    Un possibile «chi», con addosso tutto quello che serve a giudicarlo.

        NON È UNA RISPOSTA: È UNA PROPOSTA.

    Anche quando ce n'è uno solo e la confidenza è alta. La differenza fra i
    due la fa una persona, e la fa dopo.
    """

    name: str = Field(default="", max_length=160)
    number: str = Field(default="", max_length=32)
    # Che cos'è: una persona, un'attività, un ufficio. Serve a decidere se il
    # web è un posto legittimo dove cercare — e non lo è per le persone.
    kind: str = Field(default="unknown", max_length=24)
    source: str = Field(default="ora_context", max_length=32)
    # Dove esattamente, quando si può dire: il titolo di un appuntamento, un
    # indirizzo web. Mai un identificativo interno.
    source_detail: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # Perché lo stiamo proponendo, in italiano. È la riga che legge chi deve
    # confermare, e senza di questa la conferma è un clic al buio.
    why: str = Field(default="", max_length=240)

    #     A CHI APPARTIENE QUESTO NUMERO, SECONDO CHI L'HA TROVATO.
    # La fiducia sta sulla coppia identità + numero, quindi ogni candidato
    # porta la sua identità. La mette la fonte, perché è la fonte a sapere se
    # «Lorenzo Bianchi» è il nome di un contatto o il titolo di una pagina.
    contact_identity: str = Field(default="", max_length=120)
    # Vero solo se questa coppia l'ha già confermata una persona, ed è ancora
    # attiva. È l'unica cosa che permette di non chiedere di nuovo.
    trusted: bool = False
    confirmed_at: str = Field(default="", max_length=40)
    # Per il web: l'indirizzo esatto, e quante altre fonti dicono lo stesso.
    source_url: str = Field(default="", max_length=300)
    corroborated_by: int = 0
    discovered_at: str = Field(default="", max_length=40)

    def says(self) -> str:
        """Come si legge, senza niente di tecnico dentro."""
        da = COME_SI_DICE.get(self.source, "Trovato")
        pezzo = f" — {self.source_detail}" if self.source_detail else ""
        return f"{self.name}: {self.number} ({da}{pezzo})"

    def is_a_person(self) -> bool:
        return self.kind == "person"


# ---------------------------------------------------------------------------
# Il contratto delle fonti
# ---------------------------------------------------------------------------


@runtime_checkable
class ContactSource(Protocol):
    """
    Una fonte di contatti, qualunque essa sia.

        IL GIORNO IN CUI ARRIVA LA RUBRICA DI IOS, QUESTO FILE NON CAMBIA.

    È il motivo per cui la forma è questa e non un accesso diretto a una
    collezione. ORA sarà un'app iOS, e la rubrica vera arriverà da lì: da un
    permesso di sistema, da un elenco che il telefono passa e che il server non
    conserva. Quella fonte dovrà solo rispondere a `look_for`, e si infilerà
    davanti a tutte le altre senza che nessuno la debba montare.

    `RANK` è il posto in fila, e in fila si sta per certezza, non per comodità.
    """

    NAME: str
    RANK: int

    async def look_for(
        self, db, *, owner_id: str, who: str,
    ) -> List[ContactCandidate]:
        """Chi potrebbe essere «who», secondo questa fonte. Mai solleva."""
        ...


# ---------------------------------------------------------------------------
# 0 · Quello che la persona ha già confermato
# ---------------------------------------------------------------------------


class AlreadyConfirmed:
    """
    I numeri che una persona ha già detto essere quelli giusti.

        PRIMA DELLA RUBRICA, PERCHÉ È PIÙ DELLA RUBRICA.

    La rubrica dice che cosa c'è sul telefono. Questa fonte dice che cosa una
    persona ha guardato e approvato, per quella identità. È l'unica fonte i
    cui candidati arrivano già con `trusted` a vero — e solo se la coppia è
    ancora attiva.
    """

    NAME = "confirmed"
    RANK = 0

    async def look_for(self, db, *, owner_id: str, who: str) -> List[ContactCandidate]:
        from preparation.trust import trusted_for

        fuori: List[ContactCandidate] = []
        for t in await trusted_for(db, owner_id, who):
            fuori.append(ContactCandidate(
                name=t.display_name, number=t.phone_number, kind=t.kind,
                source="confirmed",
                source_detail=f"il {_giorno(t.confirmed_at)}" if t.confirmed_at else "",
                source_url=t.source_url,
                confidence=QUANTO_CI_SI_FIDA["confirmed"],
                why="L'avevi già confermato tu.",
                contact_identity=t.contact_identity,
                trusted=True, confirmed_at=t.confirmed_at,
            ))
        return fuori


def _giorno(iso: str) -> str:
    """«18/09/2026». Una data che una persona legge senza pensarci."""
    try:
        from datetime import datetime as _dt

        return _dt.fromisoformat((iso or "").replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# A · La rubrica
# ---------------------------------------------------------------------------


class AddressBook:
    """
    La rubrica del dispositivo.

        OGGI È UN POSTO VUOTO, E NON È UN SEGNAPOSTO.

    Il connettore `contacts_device` esiste nel registro, dichiara `ios` e
    `android`, e chiede `contacts.read` — un permesso di sistema che si può
    dare solo da un telefono. Finché quel permesso non c'è, questa fonte
    risponde «niente», che è la verità.

    Quello che invece è già vero è la forma: quando i contatti arriveranno,
    arriveranno così — nome, numero, organizzazione, e come li chiama la
    persona. Averla scritta adesso vuol dire che la rubrica vera si collega, e
    non si integra.
    """

    NAME = "address_book"
    RANK = 1

    async def look_for(self, db, *, owner_id: str, who: str) -> List[ContactCandidate]:
        righe = await _rows(
            db, "contacts", {"user_id": owner_id}, limite=400,
        )
        fuori: List[ContactCandidate] = []
        for r in righe:
            nomi = [
                str(r.get("name") or ""),
                str(r.get("organization") or ""),
                *[str(a) for a in (r.get("aliases") or [])],
                str(r.get("relationship") or ""),
            ]
            quanto = _how_well_it_matches(who, nomi)
            if quanto <= 0:
                continue
            numero = _first_number(r)
            if not numero:
                continue
            fuori.append(ContactCandidate(
                name=str(r.get("name") or r.get("organization") or who)[:160],
                number=numero,
                kind=str(r.get("kind") or "person"),
                source="address_book",
                source_detail=str(r.get("relationship") or r.get("organization") or "")[:200],
                confidence=min(1.0, QUANTO_CI_SI_FIDA["address_book"] * quanto),
                why="È nella tua rubrica.",
                contact_identity=_identity(str(r.get("name") or r.get("organization") or who)),
            ))
        return fuori


# ---------------------------------------------------------------------------
# B · Quello che ORA sa già
# ---------------------------------------------------------------------------


class WhatOraAlreadyKnows:
    """
    Le telefonate di prima, gli appuntamenti, le cose che ORA ha imparato.

        IL POSTO PIÙ AFFIDABILE DOPO LA RUBRICA È LA STORIA.

    Un numero che ORA ha già composto, e da cui una persona ha risposto, è
    verificato da un fatto invece che da una somiglianza. Vale più di
    qualunque cosa si possa trovare cercando.
    """

    NAME = "ora_context"
    RANK = 2

    async def look_for(self, db, *, owner_id: str, who: str) -> List[ContactCandidate]:
        fuori: List[ContactCandidate] = []
        fuori.extend(await self._from_past_calls(db, owner_id, who))
        fuori.extend(await self._from_the_calendar(db, owner_id, who))
        fuori.extend(await self._from_what_it_learned(db, owner_id, who))
        return fuori

    async def _from_past_calls(self, db, owner_id: str, who: str):
        righe = await _rows(
            db, "phone_calls",
            {"owner_id": owner_id, "to_number": {"$ne": ""}},
            limite=300,
        )
        #     LA STESSA CONTROPARTE PUÒ AVERE PIÙ TELEFONATE. NON PIÙ NUMERI.
        visti: Dict[Tuple[str, str], ContactCandidate] = {}
        for r in righe:
            nome = str(r.get("calling_whom") or "")
            numero = _clean_number(str(r.get("to_number") or ""))
            if not nome or not numero:
                continue
            quanto = _how_well_it_matches(who, [nome])
            if quanto <= 0:
                continue
            chiave = (nome.lower(), numero)
            if chiave in visti:
                continue
            visti[chiave] = ContactCandidate(
                name=nome[:160], number=numero,
                kind=_person_or_business(nome),
                source="past_call",
                source_detail="l'avevi già chiamato con ORA",
                confidence=min(1.0, QUANTO_CI_SI_FIDA["past_call"] * quanto),
                why="ORA ha già telefonato a questo numero per te.",
                contact_identity=_identity(nome),
            )
        return list(visti.values())

    async def _from_the_calendar(self, db, owner_id: str, who: str):
        righe = await _rows(
            db, "calendar_event_drafts",
            {"user_id": owner_id, "status": {"$ne": "cancelled"}},
            limite=300,
        )
        fuori: List[ContactCandidate] = []
        for r in righe:
            titolo = str(r.get("title") or "")
            quanto = _how_well_it_matches(who, [titolo, str(r.get("location") or "")])
            if quanto <= 0:
                continue
            numero = _first_number(r) or _number_inside(
                " ".join(str(r.get(k) or "") for k in
                         ("description", "location", "notes"))
            )
            if not numero:
                continue
            fuori.append(ContactCandidate(
                name=titolo[:160] or who, number=numero,
                kind=_person_or_business(titolo),
                source="calendar",
                source_detail=titolo[:200],
                confidence=min(1.0, QUANTO_CI_SI_FIDA["calendar"] * quanto),
                why="Il numero era su un tuo appuntamento.",
                contact_identity=_identity(who),
            ))
        return fuori

    async def _from_what_it_learned(self, db, owner_id: str, who: str):
        """
        Nodi, oggetti e ricordi: i posti in cui ORA scrive quello che capisce.

        Si guarda l'etichetta e gli attributi, e si tiene solo quello che
        contiene davvero un numero. Un nodo che parla di Lorenzo ma non ha il
        suo numero non è un candidato: è un motivo per chiedere.
        """
        fuori: List[ContactCandidate] = []
        for coll, campo_nome, campi_testo in (
            ("life_nodes", "label", ("description",)),
            ("life_objects", "title", ("ai_summary",)),
            ("memories", "statement", ("content",)),
        ):
            righe = await _rows(db, coll, {"user_id": owner_id}, limite=400)
            for r in righe:
                etichetta = str(r.get(campo_nome) or "")
                if not etichetta:
                    continue
                if _how_well_it_matches(who, [etichetta]) <= 0:
                    continue
                dentro = " ".join(
                    [str(r.get(c) or "") for c in campi_testo]
                    + [str(v) for v in (r.get("attributes") or {}).values()]
                )
                numero = _number_inside(dentro)
                if not numero:
                    continue
                fuori.append(ContactCandidate(
                    name=etichetta[:160], number=numero,
                    kind=_person_or_business(etichetta),
                    source="ora_context",
                    source_detail="da quello che ORA sa di te",
                    confidence=QUANTO_CI_SI_FIDA["ora_context"],
                    why="ORA aveva già questo numero fra le tue cose.",
                    contact_identity=_identity(etichetta),
                ))
        return fuori


# ---------------------------------------------------------------------------
# C · Il web, e solo per chi un numero l'ha pubblicato
# ---------------------------------------------------------------------------


class PublicWeb:
    """
    Il numero che un'attività ha messo sul proprio sito perché la chiamino.

        UN'ATTIVITÀ PUBBLICA IL NUMERO. UNA PERSONA NO.

    È tutta la differenza, e non è una sfumatura di prudenza: sono due
    operazioni diverse. Cercare «il numero dello Studio Bianchi» è leggere
    un'insegna. Cercare «il numero di Lorenzo» è cercare una persona, e non
    c'è un ramo qui dentro che lo faccia.

    Chi è una persona lo decide chi chiama questa fonte, e in caso di dubbio
    non si cerca: si chiede. Sbagliare in questa direzione costa una domanda;
    sbagliare nell'altra costa qualcosa che non si può ritirare.

        E UNA PAGINA CHE PARLA D'ALTRO NON È UNA FONTE.

    Misurato sul vero: cercando «Farmacia Crosa Torino» il primo risultato era
    un'altra farmacia, con un altro numero. Un numero in una pagina vale solo
    se la pagina parla di chi cerchiamo — e lo si controlla guardando le
    parole, non chiedendolo a un modello.
    """

    NAME = "web"
    RANK = 3
    ONLINE = True

    async def look_for(self, db, *, owner_id: str, who: str) -> List[ContactCandidate]:
        from conversation_engine.ai_core.tools.web_search import (
            execute_web_search,
            research_enabled,
        )

        if not research_enabled():
            return []
        try:
            osservazione = await execute_web_search(
                {"query": f"{who} telefono contatti", "max_results": 8,
                 "purpose": "trovare il numero pubblico di un'attività"},
                {},
            )
        except Exception as e:
            logger.info("ricerca non riuscita: %s", type(e).__name__)
            return []
        if osservazione.status == "failed":
            return []

        from preparation.trust import now_iso

        adesso = now_iso()
        trovati = ((osservazione.payload or {}).get("external") or {}).get("sources") or []
        fuori: List[ContactCandidate] = []
        da_aprire: List[str] = []
        for hit in trovati:
            titolo = str(hit.get("title") or "")
            dove = str(hit.get("url") or "")
            testo = f"{titolo} {hit.get('snippet') or ''}"
            tipo, quanto = _how_official(dove, who, str(hit.get("authority_hint") or ""))
            numero = _number_inside(testo)
            if not numero:
                #     IL SITO UFFICIALE SENZA IL NUMERO NELL'ESTRATTO.
                # Misurato sul vero: l'estratto del sito dell'albergo non
                # portava il numero, e a vincere era un portale di recensioni.
                # Il sito lo si apre, invece di lasciarlo perdere.
                if tipo == "official_site" and dove not in da_aprire:
                    da_aprire.append(dove)
                continue
            if not _is_it_about(who, f"{testo} {_host(dove)}"):
                #     UN'ALTRA ATTIVITÀ, CON UN ALTRO NUMERO.
                continue
            fuori.append(_from_the_web(who, numero, tipo, quanto, dove, adesso))

        #     SE IL SITO UFFICIALE NON È USCITO, LO SI CERCA APPOSTA.
        # Misurato sul vero: la stessa ricerca, ripetuta, a volte porta il
        # sito dell'albergo e a volte solo portali con tre numeri diversi. Una
        # seconda domanda mirata costa poco, ed è l'unico modo di preferire
        # davvero la fonte che il numero l'ha pubblicato.
        if not any(c.source == "official_site" for c in fuori) and not da_aprire:
            da_aprire = await _official_pages_for(who)

        for dove in da_aprire[:SITI_DA_APRIRE]:
            numero = await _number_on_the_page(dove, who)
            if numero:
                tipo, quanto = _how_official(dove, who, "")
                fuori.append(_from_the_web(who, numero, tipo, quanto, dove, adesso))
        return fuori


# Quante pagine ufficiali si aprono, al massimo, per una ricerca. Due: il sito e
# la sua pagina contatti. Di più non serve e costa tempo a chi sta aspettando.
SITI_DA_APRIRE = 2
# Quanto si legge di una pagina. Il numero sta in cima o in fondo, non in mezzo
# a trecento kilobyte di script.
QUANTO_LEGGERE = 300_000


def _from_the_web(who: str, numero: str, tipo: str, quanto: float,
                  dove: str, adesso: str) -> ContactCandidate:
    """
    Un candidato trovato online.

        IL NOME È QUELLO CHE HAI DETTO TU, NON IL TITOLO DELLA PAGINA.

    Misurato sul vero: il titolo era «HOTEL EXCELSIOR - Updated July 2026 - 51
    Photos & 12 Reviews - …». Non dice niente in più di chi stiamo cercando e
    dice molto di più di quanto serva. La pagina resta nella provenienza.
    """
    return ContactCandidate(
        name=who[:160], number=numero, kind="business", source=tipo,
        source_detail=_host(dove)[:200], source_url=dove[:300],
        confidence=quanto, why=f"Pubblicato su {_host(dove)}.",
        contact_identity=_identity(who), discovered_at=adesso,
    )


async def _official_pages_for(who: str) -> List[str]:
    """Le pagine che sembrano il sito di chi cerchiamo, da una ricerca mirata."""
    from conversation_engine.ai_core.tools.web_search import execute_web_search

    try:
        o = await execute_web_search(
            {"query": f"{who} sito ufficiale contatti", "max_results": 6,
             "purpose": "trovare il sito ufficiale di un'attività"},
            {},
        )
    except Exception as e:
        logger.info("ricerca del sito non riuscita: %s", type(e).__name__)
        return []
    fuori: List[str] = []
    for hit in ((o.payload or {}).get("external") or {}).get("sources") or []:
        dove = str(hit.get("url") or "")
        if _how_official(dove, who, "")[0] == "official_site" and dove not in fuori:
            fuori.append(dove)
    return fuori


async def _number_on_the_page(url: str, who: str) -> str:
    """
    Il numero sulla pagina di un sito ufficiale, o niente.

        SI LEGGE L'INSEGNA, NON SI FRUGA.

    Solo pagine già giudicate il sito di chi cerchiamo, poche, con un limite
    di tempo e di dimensione, e solo il testo. E la pagina deve parlare di lui:
    un sito ufficiale che nomina un'altra attività non è una prova.
    """
    import html as _html

    try:
        import httpx

        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "Mozilla/5.0 (ORA)"})
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return ""
        grezzo = r.text[:QUANTO_LEGGERE]
    except Exception as e:
        logger.info("pagina non letta: %s", type(e).__name__)
        return ""
    testo = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", grezzo, flags=re.S | re.I)
    #     I LINK «tel:» SONO IL NUMERO CHE IL SITO VUOLE FAR CHIAMARE.
    tel = re.findall(r'href=["\']tel:([^"\']+)', testo, flags=re.I)
    testo = _html.unescape(re.sub(r"<[^>]+>", " ", testo))
    if not _is_it_about(who, f"{testo} {_host(url)}"):
        return ""
    for t in tel:
        numero = _clean_number(t)
        if numero:
            return numero
    return _number_inside(testo)


# Parole che dicono che cosa è un posto, non quale. Non servono a riconoscerlo:
# «Hotel» è in ogni pagina di ogni hotel.
GENERICHE = {
    "hotel", "albergo", "ristorante", "trattoria", "pizzeria", "farmacia",
    "studio", "dentistico", "medico", "clinica", "centro", "officina", "bar",
    "museo", "teatro", "negozio", "palestra", "agenzia", "ufficio", "srl",
    "spa", "snc", "sas", "dott", "dottor", "dottoressa", "avvocato", "notaio",
}

# Elenchi pubblici noti. Un numero che sta lì ce l'ha messo qualcuno che non
# è l'attività, e quindi vale meno del sito — ma più di una pagina qualsiasi.
ELENCHI = (
    "paginegialle.it", "paginebianche.it", "tripadvisor.", "booking.com",
    "yelp.", "google.com", "thefork.", "virgilio.it", "prontopro.it",
    "miodottore.it", "cylex", "infobel", "misterimprese.it",
)


def _distinctive(who: str) -> List[str]:
    """Le parole che distinguono questo posto da tutti gli altri come lui."""
    return [
        p for p in re.split(r"\W+", (who or "").lower())
        if len(p) > 3 and p not in GENERICHE
    ]


def _is_it_about(who: str, testo: str) -> bool:
    """
    Se questa pagina parla davvero di chi cerchiamo.

        TUTTE LE PAROLE CHE LO DISTINGUONO, MENO AL PIÙ UNA.

    Con due parole distintive servono tutte e due: «Crosa Torino» non si
    riconosce da «Torino». Con tre o più se ne può perdere una, perché le
    pagine scrivono «Venice» dove noi scriviamo «Venezia». Senza parole
    distintive non si può riconoscere niente, e allora non si accetta niente.
    """
    parole = _distinctive(who)
    if not parole:
        return False
    dentro = (testo or "").lower()
    trovate = sum(1 for p in parole if p in dentro)
    serve = len(parole) if len(parole) <= 2 else len(parole) - 1
    return trovate >= serve


def _how_official(url: str, who: str, hint: str) -> Tuple[str, float]:
    """
    Quanto è ufficiale questo posto.

        IL SITO DI CHI STIAMO CERCANDO VALE PIÙ DI UN ELENCO.

    Si guarda una cosa sola e osservabile: quante parole distintive del nome
    compaiono nel dominio. Almeno due, o tutte se ce n'è una sola. Una parola
    sola non basta: misurato sul vero, «visitlido.it» contiene «lido» ed è un
    portale turistico, non l'albergo.

    Non è una garanzia — è il segnale più forte disponibile senza chiedere a un
    modello di fidarsi di una pagina. E comunque non conferma niente: il
    numero resta un candidato finché una persona non lo guarda.
    """
    host = _host(url).lower()
    if any(e in host for e in ELENCHI):
        return "public_directory", QUANTO_CI_SI_FIDA["public_directory"]
    parole = _distinctive(who)
    nel_dominio = sum(1 for p in parole if p in host)
    if parole and nel_dominio >= min(2, len(parole)):
        return "official_site", QUANTO_CI_SI_FIDA["official_site"]
    return "web", QUANTO_CI_SI_FIDA["web"]


def _host(url: str) -> str:
    """Il dominio, che si vede. Quanto vale non si decide qui."""
    grezzo = (url or "").strip()
    if "://" not in grezzo:
        return ""
    host = grezzo.split("://", 1)[1].split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


def _identity(nome: str) -> str:
    from preparation.trust import identity_of

    return identity_of(nome)


# ---------------------------------------------------------------------------
# Chi mette in fila
# ---------------------------------------------------------------------------

LE_FONTI: Tuple[Any, ...] = (
    AlreadyConfirmed(), AddressBook(), WhatOraAlreadyKnows(), PublicWeb(),
)


class Resolution(BaseModel):
    """
    Che cosa si è trovato cercando «chi».

        TRE ESITI, E DUE DI QUESTI NON SONO GUASTI.

    Uno solo e forte: si mostra e si chiede conferma. Più di uno: si mostrano e
    si chiede quale. Nessuno: si chiede il numero. Nessuno dei tre porta a una
    telefonata da solo, e questa è la cosa che rende inutile sbagliare qui.
    """

    who: str = Field(default="", max_length=160)
    candidates: List[ContactCandidate] = Field(default_factory=list)
    # Vero quando si è cercato sul web: serve a raccontarlo, e a non rifarlo.
    looked_online: bool = False
    # I numeri che una fonte ha trovato e che non si ripropongono, perché una
    # persona li aveva rifiutati o sostituiti.
    left_out: List[str] = Field(default_factory=list)
    # Perché non si è cercato sul web, quando non si è cercato.
    did_not_look_online: str = Field(default="", max_length=160)

    def only_one(self) -> Optional[ContactCandidate]:
        return self.candidates[0] if len(self.candidates) == 1 else None

    def is_ambiguous(self) -> bool:
        return len(self.candidates) > 1

    def found_nothing(self) -> bool:
        return not self.candidates


async def find_who_to_call(
    db, *, owner_id: str, who: str, probably_a_person: Optional[bool] = None,
) -> Resolution:
    """
    Cerca chi chiamare, nell'ordine, e si ferma appena è abbastanza sicura.

        SI SMETTE DI CERCARE QUANDO SI È SICURI, NON QUANDO SI È STANCHI.

    Trovato in rubrica, il web non si interroga: non perché costi, ma perché
    una seconda risposta meno affidabile accanto a una più affidabile non
    aggiunge informazione — aggiunge una scelta da fare a chi non dovrebbe
    doverla fare.

    Non solleva mai. Una fonte che si rompe è una fonte che non ha trovato
    niente, e le altre continuano.
    """
    nome = " ".join((who or "").split())[:160]
    esito = Resolution(who=nome)
    if not nome:
        esito.did_not_look_online = "non mi hai detto chi chiamare"
        return esito

    persona = _person_or_business(nome) == "person" if probably_a_person is None \
        else bool(probably_a_person)

    trovati: List[ContactCandidate] = []
    for fonte in sorted(LE_FONTI, key=lambda f: f.RANK):
        if getattr(fonte, "ONLINE", False):
            #     ONLINE NON SI CERCANO PERSONE.
            if persona:
                esito.did_not_look_online = (
                    "è una persona: il suo numero non si cerca su internet"
                )
                continue
            if trovati:
                esito.did_not_look_online = "l'ho già trovato senza cercare online"
                continue
            esito.looked_online = True
        try:
            trovati.extend(await fonte.look_for(db, owner_id=owner_id, who=nome))
        except Exception as e:
            logger.info("fonte %s non ha risposto: %s", fonte.NAME, type(e).__name__)

    #     UN NUMERO RIFIUTATO NON TORNA PERCHÉ UNA FONTE L'HA RITROVATO.
    # La rubrica lo ha ancora, il sito lo pubblica ancora: non importa. Una
    # persona ha detto che non è quello, ed è una cosa che si ricorda. Torna
    # soltanto se è lei a scriverlo di nuovo.
    try:
        from preparation.trust import not_to_propose

        via = await not_to_propose(db, owner_id, nome)
    except Exception as e:  # pragma: no cover
        logger.info("numeri da non riproporre non letti: %s", type(e).__name__)
        via = {}
    if via:
        esito.left_out = sorted(via)
        trovati = [c for c in trovati if c.trusted or c.number not in via]

    esito.candidates = _the_best_of(trovati)
    return esito


def _the_best_of(trovati: List[ContactCandidate]) -> List[ContactCandidate]:
    """
    Lo stesso numero da due fonti non è due candidati: è una conferma.

    E quando succede si tiene la fonte più affidabile, non la prima arrivata.
    """
    per_numero: Dict[str, ContactCandidate] = {}
    quante: Dict[str, int] = {}
    for c in trovati:
        if c.confidence < ABBASTANZA or not c.number:
            continue
        quante[c.number] = quante.get(c.number, 0) + 1
        gia = per_numero.get(c.number)
        #     A PARITÀ DI NUMERO VINCE CHI È GIÀ STATO CONFERMATO.
        if gia is None or (c.trusted and not gia.trusted) or (
            c.trusted == gia.trusted and c.confidence > gia.confidence
        ):
            per_numero[c.number] = c
    for numero, c in per_numero.items():
        #     QUANTE ALTRE FONTI DICONO LO STESSO. SI MOSTRA, NON SI SOMMA.
        # Quattro pagine con lo stesso numero sono un indizio forte, ma non
        # una conferma: potrebbero copiarsi a vicenda. Serve a chi guarda, e
        # non cambia il fatto che a decidere è lui.
        c.corroborated_by = max(0, quante.get(numero, 1) - 1)
    ordinati = sorted(
        per_numero.values(), key=lambda c: (not c.trusted, -c.confidence),
    )
    return ordinati[:AL_MASSIMO]


# ---------------------------------------------------------------------------
# Riconoscere le cose
# ---------------------------------------------------------------------------

# Parole che dicono «questa è un'attività, non una persona». Non è un elenco
# esaustivo e non deve esserlo: quando non si riconosce niente si risponde
# «persona», che è la risposta che porta a chiedere invece che a cercare.
SEGNA_UN_ATTIVITA = (
    "museo", "teatro", "negozio", "trattoria", "osteria", "enoteca", "bar ",
    "b&b", "residence", "camping", "biblioteca", "università", "questura",
    "prefettura", "asl", "poste", "concessionaria", "lavanderia",
    "studio", "dottor", "dott", "clinica", "ospedale", "ambulatorio", "centro",
    "farmacia", "officina", "meccanico", "carrozzeria", "ristorante", "pizzeria",
    "hotel", "albergo", "banca", "agenzia", "ufficio", "comune", "scuola",
    "palestra", "parrucchiere", "veterinario", "notaio", "avvocato",
    "commercialista", "idraulico", "elettricista", "assicurazione", "srl",
    "s.r.l", "spa", "s.p.a", "snc", "sas", "studio legale", "poliambulatorio",
)


def _person_or_business(nome: str) -> str:
    """
    Persona o attività?

        NEL DUBBIO, PERSONA.

    Perché è la risposta che costa una domanda invece che una ricerca su
    internet a nome di qualcuno. Un'attività scambiata per persona fa perdere
    trenta secondi; una persona scambiata per attività fa fare a ORA una cosa
    che non deve fare.
    """
    testo = (nome or "").lower()
    return "business" if any(p in testo for p in SEGNA_UN_ATTIVITA) else "person"


def _how_well_it_matches(cercato: str, nomi: List[str]) -> float:
    """
    Quanto questo nome somiglia a quello che si cercava, fra 0 e 1.

        E ZERO VUOL DIRE «NON È LUI», NON «FORSE».

    Confronto per parole intere, non per sottostringa: «Lore» dentro
    «Salvatore» non è Lorenzo, e un confronto che lo accettasse proporrebbe il
    numero sbagliato con l'aria di saperlo.
    """
    volute = {p for p in re.split(r"\W+", (cercato or "").lower()) if len(p) > 1}
    if not volute:
        return 0.0
    migliore = 0.0
    for nome in nomi:
        presenti = {p for p in re.split(r"\W+", (nome or "").lower()) if len(p) > 1}
        if not presenti:
            continue
        in_comune = volute & presenti
        if not in_comune:
            continue
        #     TUTTE LE PAROLE CERCATE TROVATE = PIENO.
        migliore = max(migliore, len(in_comune) / len(volute))
    return migliore


_UN_NUMERO = re.compile(
    r"(?:\+39[\s.\-]?)?(?:0\d{1,3}|3\d{2})[\s.\-]?\d{3}[\s.\-]?\d{3,5}"
)


def _number_inside(testo: str) -> str:
    """Il primo numero italiano dentro un testo, o niente."""
    trovato = _UN_NUMERO.search(testo or "")
    return _clean_number(trovato.group(0)) if trovato else ""


def _clean_number(grezzo: str) -> str:
    """In forma componibile, o vuoto. Non si indovina un prefisso."""
    fuori = _clean_number_loose(grezzo)
    return fuori if _plausible(fuori) else ""


def _plausible(numero: str) -> bool:
    """
    Un numero italiano ha una forma, e quello che non ce l'ha non si propone.

    Misurato sul vero: da una pagina è uscito «+3939041271680» — un prefisso
    ripetuto. Dopo +39 un fisso comincia per 0 e ha 6–11 cifre, un cellulare
    comincia per 3 e ne ha 9–10. Gli altri paesi non si giudicano qui.
    """
    if not numero:
        return False
    if not numero.startswith("+39"):
        return True
    resto = numero[3:]
    if resto.startswith("0"):
        return 6 <= len(resto) <= 11
    if resto.startswith("3"):
        return 9 <= len(resto) <= 10
    return False


def _clean_number_loose(grezzo: str) -> str:
    cifre = re.sub(r"[^\d+]", "", grezzo or "")
    if cifre.startswith("+"):
        return cifre if 9 <= len(cifre) - 1 <= 15 else ""
    if cifre.startswith("00"):
        cifre = "+" + cifre[2:]
        return cifre if 9 <= len(cifre) - 1 <= 15 else ""
    if 9 <= len(cifre) <= 11:
        return "+39" + cifre
    return ""


def _first_number(riga: Dict[str, Any]) -> str:
    """Il numero di una riga, comunque il suo schema lo chiami."""
    for campo in ("phone", "phone_number", "number", "tel", "mobile",
                  "telefono", "to_number"):
        numero = _clean_number(str((riga or {}).get(campo) or ""))
        if numero:
            return numero
    for lista in ("phones", "numbers", "phone_numbers"):
        for v in ((riga or {}).get(lista) or []):
            numero = _clean_number(
                str(v.get("value") if isinstance(v, dict) else v)
            )
            if numero:
                return numero
    return ""


async def _rows(db, coll: str, query: Dict[str, Any], limite: int) -> List[Dict[str, Any]]:
    """Legge una collezione, e se non c'è risponde niente invece di cadere."""
    try:
        return await db[coll].find(query, {"_id": 0}).to_list(limite)
    except Exception as e:
        logger.info("collezione %s non letta: %s", coll, type(e).__name__)
        return []
