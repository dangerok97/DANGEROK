"""
Dove i fatti economici restano, e cosa succede quando due si contraddicono.

    IL CODICE NON SCEGLIE QUALE FONTE DICE IL VERO.

E' la stessa regola di Connected Life, e per la stessa ragione: una tabella
che dicesse «il documento vale piu' dell'email» sarebbe una risposta
permanente, invisibile e non discutibile a una domanda che dipende dal caso.
Un contratto firmato tre anni fa e un'email di ieri: quale sia piu' vero
dipende da cosa e' successo in mezzo, e in mezzo c'e' la vita di qualcuno.

Quindi qui: due fatti che dicono cose diverse della stessa cosa restano
entrambi, marcati `disputed`, con il riferimento reciproco. Chi legge lo
vede. Il modello puo' pesarli. Nessuno viene buttato.

Una versione nuova di un fatto — l'affitto che da marzo e' un altro numero —
non e' invece un conflitto: e' una successione, e la precedente diventa
`superseded` conservando quello che diceva e da quando.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from financial.models import FinancialFact, FinancialImpact, now_iso

logger = logging.getLogger("ora.financial.store")

FACTS = "financial_facts"
IMPACTS = "financial_impacts"


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


class FinancialStore:
    """I fatti economici di una persona, con la loro storia."""

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[FACTS].create_index("id", unique=True)
            await self.db[FACTS].create_index([("owner_id", 1), ("status", 1)])
            await self.db[FACTS].create_index([("owner_id", 1), ("due_at", 1)])
            await self.db[IMPACTS].create_index([("owner_id", 1), ("fact_id", 1)])
        except Exception as e:
            logger.info("index soft-fail: %s", type(e).__name__)

    # --- scrivere ---------------------------------------------------------

    async def remember(
        self, fact: FinancialFact, *, replaces: str = "",
    ) -> Dict[str, Any]:
        """
        Metti via un fatto, e dì cosa e' successo agli altri che ne parlavano.

        Tre esiti possibili, e nessuno di essi e' «sovrascritto»:

          `kept`        non c'era niente di simile: si aggiunge.
          `superseded`  e' una versione nuova di qualcosa: la precedente resta
                        com'era, marcata, e la nuova la nomina.
          `disputed`    dice una cosa diversa da un'altra che vale nello
                        stesso periodo: restano entrambe, marcate, e nessuna
                        delle due viene scelta.
        """
        if not fact.provenance:
            raise ValueError("un fatto economico senza provenienza non si scrive")

        siblings = await self.about_the_same_thing(fact)

        # QUANDO IL GIUDIZIO DICE COSA STA CAMBIANDO, NON E' UN CONFLITTO.
        #
        # «Dal prossimo mese il canone passa da 700 a 760» non sono due
        # affitti in disaccordo: e' lo stesso affitto, dopo. Chi lo sa e' il
        # giudizio — l'ha letto nella frase — e lo dice in `changes_what`.
        #
        # Questo parametro esisteva nel prompt e non veniva usato: il fatto
        # nuovo finiva quindi nel ramo «dicono cifre diverse» e la persona si
        # ritrovava due affitti vivi, che e' esattamente la cosa che non deve
        # succedere. La data da cui vale spesso non c'e' — «dal prossimo
        # mese» non e' una data — e la sua assenza non rende il fatto un
        # conflitto: la si registra fra le cose che non si sanno.
        succeeding = _same_name(replaces)

        outcome = "kept"
        disputes: List[str] = []

        # LO STESSO FATTO, RILETTO, RESTA UNO.
        #
        # Un movimento ricorrente viene letto ogni mese e produce ogni volta
        # lo stesso fatto: stesso nome, stesso importo, stessa cadenza. Senza
        # questa riga si accumulavano — sul conto vero ce n'erano tre uguali
        # dopo tre letture — e l'orizzonte li sommava tutti, presentando un
        # affitto pagato tre volte.
        #
        # Non e' un conflitto e non e' una versione nuova: e' la stessa cosa,
        # vista di nuovo. Si aggiorna quando l'ho vista e si va avanti.
        for other in siblings:
            if _says_the_same_thing(fact, other):
                await self.db[FACTS].update_one(
                    {"id": other.id},
                    {"$set": {"observed_at": fact.observed_at},
                     "$inc": {"times_seen_again": 1}},
                )
                return {
                    "outcome": "already_known", "fact_id": other.id,
                    "disputes": [],
                }

        for other in siblings:
            if succeeding and _names_the_same_thing(other.what, succeeding):
                await self.db[FACTS].update_one(
                    {"id": other.id},
                    {"$set": {"status": "superseded",
                              "valid_until": fact.valid_from or now_iso()}},
                )
                fact.supersedes = other.id
                outcome = "superseded"
            elif _is_a_new_version_of(fact, other):
                await self.db[FACTS].update_one(
                    {"id": other.id},
                    {"$set": {"status": "superseded",
                              "valid_until": fact.valid_from or now_iso()}},
                )
                fact.supersedes = other.id
                outcome = "superseded"
            elif _says_something_different(fact, other):
                # Due versioni dello stesso fatto che valgono insieme. Restano
                # tutte e due: e' il conflitto, ed e' un'informazione.
                await self.db[FACTS].update_one(
                    {"id": other.id}, {"$set": {"status": "disputed"}},
                )
                disputes.append(other.id)
                fact.status = "disputed"
                outcome = "disputed"

        await self.db[FACTS].insert_one(fact.model_dump())
        return {"outcome": outcome, "fact_id": fact.id, "disputes": disputes}

    async def record_impact(self, impact: FinancialImpact) -> str:
        await self.db[IMPACTS].insert_one(impact.model_dump())
        return impact.id

    # --- leggere ----------------------------------------------------------

    async def known(
        self, owner_id: str, *, kinds: Optional[List[str]] = None, limit: int = 200,
    ) -> List[FinancialFact]:
        """Quello che si sa adesso: niente di superato, niente di ritirato."""
        query: Dict[str, Any] = {
            "owner_id": owner_id,
            "status": {"$in": ["known", "disputed"]},
        }
        if kinds:
            query["kind"] = {"$in": list(kinds)}
        rows = await self.db[FACTS].find(query, {"_id": 0}).sort(
            "observed_at", -1,
        ).to_list(limit)
        return [FinancialFact.model_validate(r) for r in rows]

    async def get(self, owner_id: str, fact_id: str) -> Optional[FinancialFact]:
        row = await self.db[FACTS].find_one(
            {"owner_id": owner_id, "id": fact_id}, {"_id": 0},
        )
        return FinancialFact.model_validate(row) if row else None

    async def about_the_same_thing(
        self, fact: FinancialFact,
    ) -> List[FinancialFact]:
        """
        Gli altri fatti che parlano della stessa cosa di questo.

        «La stessa cosa» qui e' deliberatamente stretta: stesso proprietario,
        stesso tipo, stesso nome normalizzato. Non e' una rete a maglie fini,
        e non deve esserlo — allargarla vorrebbe dire che il codice comincia a
        decidere che due cose sono la stessa, che e' un giudizio e sta altrove.
        """
        rows = await self.db[FACTS].find(
            {
                "owner_id": fact.owner_id,
                "kind": fact.kind,
                "status": {"$in": ["known", "disputed"]},
            },
            {"_id": 0},
        ).to_list(200)
        wanted = _same_name(fact.what)
        return [
            FinancialFact.model_validate(r) for r in rows
            if r.get("id") != fact.id and _same_name(r.get("what")) == wanted
        ]

    async def history_of(self, owner_id: str, what: str) -> List[FinancialFact]:
        """Tutto quello che si e' saputo di questa cosa, anche cio' che non vale piu'."""
        rows = await self.db[FACTS].find(
            {"owner_id": owner_id}, {"_id": 0},
        ).sort("observed_at", 1).to_list(400)
        wanted = _same_name(what)
        return [
            FinancialFact.model_validate(r) for r in rows
            if _same_name(r.get("what")) == wanted
        ]

    async def disagreements(self, owner_id: str) -> List[Dict[str, Any]]:
        """
        Le cose su cui due fonti non vanno d'accordo, con tutte le versioni.

        Serve a una schermata che deve poter dire «ho trovato due cifre
        diverse per l'affitto» senza sceglierne una.
        """
        rows = await self.db[FACTS].find(
            {"owner_id": owner_id, "status": "disputed"}, {"_id": 0},
        ).to_list(100)
        by_name: Dict[str, List[FinancialFact]] = {}
        for row in rows:
            fact = FinancialFact.model_validate(row)
            by_name.setdefault(_same_name(fact.what), []).append(fact)
        out = []
        for versions in by_name.values():
            if len(versions) < 2:
                continue
            out.append({
                "what": versions[0].what,
                "versions": [
                    {
                        "how_much": v.money.for_human(),
                        "said_by": v.provenance[0].source,
                        "how_directly": v.provenance[0].how_directly,
                        "observed_at": v.provenance[0].observed_at,
                    }
                    for v in versions
                ],
            })
        return out


def _names_the_same_thing(known: Any, said: str) -> bool:
    """
    Se il giudizio sta parlando di questa cosa qui.

    Il confronto e' tollerante di proposito. L'identita' l'ha gia' dichiarata
    il giudizio — «questo sostituisce quello» — e qui si deve solo capire
    quale delle cose note intendesse: chiedergli la stringa esatta e poi
    scartarlo per una parola in piu' vorrebbe dire buttare via una risposta
    corretta e lasciare due affitti alla persona.
    """
    mine = _same_name(known)
    theirs = _same_name(said)
    if not mine or not theirs:
        return False
    return mine == theirs or mine in theirs or theirs in mine


def _same_name(what: Any) -> str:
    return " ".join(str(what or "").strip().lower().split())


def _is_a_new_version_of(fresh: FinancialFact, older: FinancialFact) -> bool:
    """
    Se il fatto nuovo e' la versione successiva del vecchio.

    Lo e' quando dice esplicitamente da quando vale, e da quando vale e' dopo
    l'altro. E' il caso dell'affitto che cambia dal mese prossimo: nessuno dei
    due e' sbagliato, si succedono.
    """
    if fresh.kind != older.kind or fresh.cadence != "recurring":
        return False
    since = _moment(fresh.valid_from)
    if since is None:
        return False
    before = _moment(older.valid_from) or _moment(older.observed_at)
    return before is None or since > before


def _says_the_same_thing(fresh: FinancialFact, older: FinancialFact) -> bool:
    """
    Se i due fatti dicono esattamente la stessa cosa.

    Stesso importo, stessa valuta, stessa cadenza e stessa scadenza. Non e'
    una somiglianza: e' l'identita' di quello che affermano. Due letture
    dello stesso addebito mensile finiscono qui, e ne resta una.
    """
    if fresh.cadence != older.cadence or fresh.direction != older.direction:
        return False
    if (fresh.due_at or "")[:10] != (older.due_at or "")[:10]:
        return False
    if fresh.money.is_known != older.money.is_known:
        return False
    if not fresh.money.is_known:
        return True
    return (
        fresh.money.currency == older.money.currency
        and round(fresh.money.amount, 2) == round(older.money.amount, 2)
    )


def _says_something_different(fresh: FinancialFact, older: FinancialFact) -> bool:
    """
    Se i due dicono cifre diverse della stessa cosa senza succedersi.

    Solo sugli importi noti: due fatti di cui uno non conosce l'importo non
    sono in disaccordo, sono uno piu' informato dell'altro.
    """
    if not (fresh.money.is_known and older.money.is_known):
        return False
    if fresh.money.currency != older.money.currency:
        return True
    # Al centesimo. Non e' una soglia di importanza — quelle non esistono in
    # questo modulo — e' il modo di chiedere «sono lo stesso numero» a due
    # decimali senza farsi ingannare dai float.
    return round(fresh.money.amount, 2) != round(older.money.amount, 2)
