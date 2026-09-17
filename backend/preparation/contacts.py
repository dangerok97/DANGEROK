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
    """

    NAME = "web"
    RANK = 3

    async def look_for(self, db, *, owner_id: str, who: str) -> List[ContactCandidate]:
        from conversation_engine.ai_core.tools.web_search import (
            execute_web_search,
            research_enabled,
        )

        if not research_enabled():
            return []
        try:
            osservazione = await execute_web_search(
                {"query": f"{who} telefono contatti", "max_results": 6,
                 "purpose": "trovare il numero pubblico di un'attività"},
                {},
            )
        except Exception as e:
            logger.info("ricerca non riuscita: %s", type(e).__name__)
            return []
        if osservazione.status == "failed":
            return []

        trovati = ((osservazione.payload or {}).get("external") or {}).get("sources") or []
        fuori: List[ContactCandidate] = []
        for hit in trovati:
            testo = f"{hit.get('title') or ''} {hit.get('snippet') or ''}"
            numero = _number_inside(testo)
            if not numero:
                continue
            dove = str(hit.get("url") or "")
            quanto_vale = _how_official(dove, who, str(hit.get("authority_hint") or ""))
            fuori.append(ContactCandidate(
                name=str(hit.get("title") or who)[:160],
                number=numero,
                kind="business",
                source=quanto_vale[0],
                source_detail=_host(dove)[:200],
                confidence=quanto_vale[1],
                why=f"Pubblicato su {_host(dove)}.",
            ))
        return fuori


def _how_official(url: str, who: str, hint: str) -> Tuple[str, float]:
    """
    Quanto è ufficiale questo posto.

        IL SITO DI CHI STIAMO CERCANDO VALE PIÙ DI UN ELENCO.

    Si guarda una cosa sola e osservabile: se il nome di chi cerchiamo compare
    nel dominio. Non è una garanzia — è il segnale più forte disponibile senza
    chiedere a un modello di fidarsi di una pagina.
    """
    host = _host(url).lower()
    parole = [p for p in re.split(r"\W+", (who or "").lower()) if len(p) > 3]
    if parole and any(p in host for p in parole):
        return "official_site", QUANTO_CI_SI_FIDA["official_site"]
    if (hint or "").upper() in ("OFFICIAL", "HIGH"):
        return "public_directory", QUANTO_CI_SI_FIDA["public_directory"]
    return "web", QUANTO_CI_SI_FIDA["web"]


# ---------------------------------------------------------------------------
# Chi mette in fila
# ---------------------------------------------------------------------------

LE_FONTI: Tuple[Any, ...] = (AddressBook(), WhatOraAlreadyKnows(), PublicWeb())


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
        if fonte.NAME == "web":
            #     SUL WEB NON SI CERCANO PERSONE.
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

    esito.candidates = _the_best_of(trovati)
    return esito


def _the_best_of(trovati: List[ContactCandidate]) -> List[ContactCandidate]:
    """
    Lo stesso numero da due fonti non è due candidati: è una conferma.

    E quando succede si tiene la fonte più affidabile, non la prima arrivata.
    """
    per_numero: Dict[str, ContactCandidate] = {}
    for c in trovati:
        if c.confidence < ABBASTANZA or not c.number:
            continue
        gia = per_numero.get(c.number)
        if gia is None or c.confidence > gia.confidence:
            per_numero[c.number] = c
    ordinati = sorted(per_numero.values(), key=lambda c: -c.confidence)
    return ordinati[:AL_MASSIMO]


# ---------------------------------------------------------------------------
# Riconoscere le cose
# ---------------------------------------------------------------------------

# Parole che dicono «questa è un'attività, non una persona». Non è un elenco
# esaustivo e non deve esserlo: quando non si riconosce niente si risponde
# «persona», che è la risposta che porta a chiedere invece che a cercare.
SEGNA_UN_ATTIVITA = (
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
