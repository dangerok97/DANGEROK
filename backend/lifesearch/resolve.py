"""
Da una domanda alle cose che la riguardano — per relazione, non per parola.

    LA RELAZIONE CONTA PIU' DELLA PAROLA.

Sei modi di trovare qualcosa, in ordine di quanto valgono. Il primo che
risponde vince, e ogni risultato porta scritto quale dei sei l'ha trovato:

    1. esplicito     la persona ha nominato proprio quella cosa
    2. governato     una relazione scritta e passata dalla governance
                     (`about_refs`, `life_object_id`)
    3. situazione    un collegamento fra fonti, deciso e registrato
    4. provenienza   la catena da dove viene: questo fatto nasce da quel
                     movimento, quel movimento sta su quel conto
    5. semantica     il giudizio dice che questa domanda parla di quella
                     parte della vita, e la parola non c'entra
    6. parola        l'ultima risorsa, e si sa che e' l'ultima

Il `matched_by` viaggia fino al confine dell'API e li' si ferma: serve a chi
verifica che il primo criterio stia funzionando, e non dice niente a chi
cerca. Una persona che legge «trovato per corrispondenza lessicale» ha
ricevuto una scusa, non un risultato.

E il numero che conta: quante righe si sono guardate e quante se ne sono
portate via. Una ricerca che legge tutto e lo passa al modello non e' una
ricerca — e' un archivio con una casella di testo davanti.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("ora.lifesearch.resolve")

# Quante righe si guardano al massimo per tipo, e quante se ne tengono.
# Il primo numero e' il costo della ricerca, il secondo e' quello del
# ragionamento: tenerli distinti e' l'unico modo di sapere quale dei due
# sta crescendo.
LOOKED_AT = 300
KEPT = 6

HOW = ("explicit", "governed", "situation", "provenance", "semantic", "lexical")


def _rank(how: str) -> int:
    return HOW.index(how) if how in HOW else len(HOW)


def _moment(value: Any) -> Optional[datetime]:
    try:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return found if found.tzinfo else found.replace(tzinfo=timezone.utc)


def _amounts_in(query: str) -> List[str]:
    """
    Le cifre scritte in una domanda, come le scriverebbe un conto.

    Aritmetica su una stringa, non un giudizio: «760» e «€760,00» sono lo
    stesso importo, e chi chiede di una spesa da 760 non ha nessun altro modo
    di indicarla.
    """
    import re

    out = []
    for raw in re.findall(r"\d[\d.,]*", query or ""):
        digits = raw.replace(".", "").replace(",", ".")
        try:
            value = float(digits)
        except ValueError:
            continue
        if value >= 1:
            # Nel formato in cui gli importi vengono scritti per una persona.
            out.append(f"{int(value):,}".replace(",", "."))
    return out


def _mentions(text: str, words: List[str]) -> bool:
    """La parola c'e'. Ultima risorsa, e dichiarata come tale."""
    lowered = (text or "").lower()
    return any(w in lowered for w in words if w)


class Gathered:
    """Quello che si e' trovato, con il conto di quanto e' costato trovarlo."""

    def __init__(self) -> None:
        self.rows: Dict[str, List[Dict[str, Any]]] = {}
        self.looked_at = 0
        self.kept = 0

    def add(self, group: str, item: Dict[str, Any]) -> None:
        rows = self.rows.setdefault(group, [])
        # La stessa cosa trovata due volte tiene il modo migliore.
        for existing in rows:
            if existing.get("key") == item.get("key"):
                if _rank(item["matched_by"]) < _rank(existing["matched_by"]):
                    existing["matched_by"] = item["matched_by"]
                return
        rows.append(item)
        self.kept += 1

    def trim(self) -> None:
        for group, rows in self.rows.items():
            rows.sort(key=lambda r: (_rank(r["matched_by"]), r.get("order") or ""))
            self.rows[group] = rows[:KEPT]
        self.kept = sum(len(r) for r in self.rows.values())


async def gather(
    db, owner_id: str, *, wanted: Dict[str, Any],
) -> Gathered:
    """
    Raccogli quello che riguarda questa domanda, e conta cosa hai guardato.
    """
    found = Gathered()
    anchors: Set[str] = set(wanted.get("about_situations") or [])
    # Le parole scritte dalla persona piu' quelle che il giudizio ha
    # riconosciuto sotto — «rogito» per «casa», «canone» per «affitto». Non e'
    # un dizionario di sinonimi: e' quello che il modello ha capito di questa
    # domanda, e vale come ultima risorsa quanto le altre parole.
    words: List[str] = [
        w for w in list(wanted.get("words") or [])
        + [c.lower() for c in (wanted.get("concepts") or [])]
        if len(w) > 2
    ]

    await _situations(db, owner_id, anchors, words, found)
    await _what_ora_knows(db, owner_id, anchors, words, found, wanted)
    await _calendar_and_mail(db, owner_id, anchors, words, found, wanted)
    await _documents(db, owner_id, anchors, words, found, wanted)
    await _money(db, owner_id, words, found, wanted)
    await _changes(db, owner_id, words, found, wanted)

    found.trim()

    # Sei righe che sembrano lo stesso pomeriggio sono un errore, non un
    # elenco: si tiene la versione piu' completa e si dice quante volte la si
    # e' vista.
    from lifesearch.dedupe import collapse

    for group in ("appuntamenti", "comunicazioni"):
        if found.rows.get(group):
            found.rows[group] = collapse(found.rows[group])
    found.kept = sum(len(r) for r in found.rows.values())
    return found


async def _situations(db, owner_id, anchors, words, found) -> None:
    """Le parti della vita: nominate dal giudizio, o riconosciute a parole."""
    try:
        rows = await db.life_objects.find(
            {"user_id": owner_id, "status": {"$ne": "archived"}},
            {"_id": 0, "id": 1, "title": 1, "type": 1, "ai_summary": 1,
             "next_reasoning": 1, "updated_at": 1},
        ).to_list(40)
    except Exception as e:
        logger.info("situation read soft-fail: %s", type(e).__name__)
        return
    found.looked_at += len(rows)

    for row in rows:
        how = None
        if row["id"] in anchors:
            how = "semantic"
        elif _mentions(str(row.get("title") or ""), words):
            how = "lexical"
        if not how:
            continue
        found.add("situazioni", {
            "key": row["id"],
            "matched_by": how,
            "order": str(row.get("updated_at") or ""),
            "cosa": str(row.get("title") or ""),
            "in_una_riga": str(row.get("ai_summary") or "")[:220],
            "da_chiarire": str(row.get("next_reasoning") or "")[:160],
            "apri": f"/life-area/{_domain(row)}",
        })


def _domain(row: Dict[str, Any]) -> str:
    """La superficie umana di questa situazione, come la conosce la Vita."""
    kind = str(row.get("type") or "").lower()
    return {
        "home": "casa", "house": "casa", "job": "lavoro",
        "university": "studio", "course": "studio",
    }.get(kind, kind or "vita")


async def _what_ora_knows(db, owner_id, anchors, words, found, wanted) -> None:
    """
    Quello che ORA sa, dal modello governato — mai dal registro grezzo.

        IL GIORNALE DEI MOVIMENTI NON E' CONOSCENZA.

    Un movimento e' successo; che cosa significhi lo dice la governance. Una
    ricerca che pescasse dal registro risponderebbe «il tuo affitto e' 760»
    per una riga che diceva soltanto «BONIFICO A ROSSI MARCO».
    """
    try:
        from financial.durable import governed_facts
        from financial.knowledge import what_ora_knows

        from financial.store import FinancialStore

        said = await what_ora_knows(db, owner_id)
        governed = await governed_facts(db, owner_id)
        recorded = await FinancialStore(db).known(owner_id)
    except Exception as e:
        logger.info("knowledge read soft-fail: %s", type(e).__name__)
        return

    # A quale parte della vita appartiene ciascuna cosa, e con che autorita'.
    #
    #     UNA RELAZIONE SCRITTA VALE ANCHE PRIMA DELLA GOVERNANCE.
    #
    # Il notaio dei quattromila euro appartiene all'acquisto della casa: lo ha
    # deciso il giudizio e sta scritto in `about_refs`. Che la governance
    # abbia poi rifiutato di ricordarlo per sempre — e fa bene, e' contesto di
    # una cosa che finisce — non cancella l'appartenenza. Leggerla solo dai
    # fatti governati faceva ritrovare il notaio per la parola «notaio», che
    # e' esattamente il criterio che questo sprint esiste per superare.
    by_name: Dict[str, str] = {}
    how_by_name: Dict[str, str] = {}
    for fact, authority in (
        [(f, "situation") for f in recorded] + [(f, "governed") for f in governed]
    ):
        for ref in fact.about_refs or []:
            name = " ".join(str(fact.what).lower().split())
            by_name[name] = str(ref)
            how_by_name[name] = authority

    for grade, rows in (("SO", said["so"]), ("PENSO", said["ho_letto"])):
        found.looked_at += len(rows)
        for row in rows:
            name = " ".join(str(row.get("cosa") or "").lower().split())
            how = None
            if by_name.get(name) in anchors:
                # Una relazione scritta: governata se e' passata di li',
                # registrata se il giudizio l'ha stabilita e basta.
                how = how_by_name.get(name, "situation")
            elif anchors and by_name.get(name):
                # Appartiene a un'altra parte della vita: non e' questa.
                #
                #     LO STIPENDIO NON STA DENTRO L'ACQUISTO DELLA CASA.
                #
                # Il primo tentativo faceva entrare tutto quello che ORA sa
                # ogni volta che c'era un'ancora e nessuna parola — che e'
                # esattamente il caso della schermata di una parte di vita.
                # Aprire «Casa» e trovarci lo stipendio e' la stessa
                # confusione che questo sprint esiste per togliere.
                how = None
            elif _mentions(str(row.get("cosa") or ""), words):
                how = "lexical"
            if not how:
                continue
            found.add("cose_che_ora_sa", {
                "key": f"{grade}:{name}",
                "matched_by": how,
                "order": name,
                "cosa": row.get("cosa"),
                "quanto": row.get("quanto"),
                "ogni_quanto": row.get("quando") or "",
                "stato": grade,
                "come_lo_so": row.get("come_lo_so") or "",
            })

    # E le domande aperte: due versioni che convivono restano due.
    for row in said["devo_chiederti"]:
        found.looked_at += 1
        name = " ".join(str(row.get("cosa") or "").lower().split())
        if not (anchors or _mentions(str(row.get("cosa") or ""), words)):
            continue
        found.add("da_chiarire", {
            "key": f"ASK:{name}",
            "matched_by": "governed" if anchors else "lexical",
            "order": name,
            "cosa": row.get("cosa"),
            "quanto": row.get("quanto"),
            "invece_di": row.get("invece_di") or "",
            "come_lo_so": row.get("come_lo_so") or "",
        })


async def _calendar_and_mail(db, owner_id, anchors, words, found, wanted) -> None:
    """
    Appuntamenti e messaggi, in due passaggi.

        UN COLLEGAMENTO UNISCE DUE COSE FRA LORO, NON A TUTTO IL RESTO.

    Il primo passaggio trova quello che la domanda nomina. Il secondo tira
    dentro cio' che e' collegato a quello — la mail dello studio dentistico
    che non dice «dentista» ma parla di quell'appuntamento.

    Il primo tentativo saltava il primo passaggio: bastava che una cosa
    fosse collegata a qualcosa perche' comparisse, e quelle tre mail dello
    studio dentistico uscivano anche cercando «affitto» e «stipendio». Un
    collegamento non e' una promozione a risultato universale: e' una
    relazione fra due cose, e senza una delle due non porta da nessuna parte.
    """
    from ingestion.reading import plain

    since = wanted.get("since")
    forward = bool(wanted.get("looking_forward"))
    broad = wanted.get("kind") in ("timeline_lookup", "broad_life_query")
    joined = await _joined_pairs(db, owner_id)

    # I messaggi che il giudizio ha collegato a queste parti della vita.
    #
    #     «ACQUISTO» IN UN OGGETTO NON VUOL DIRE CHE PARLA DEL TUO ACQUISTO.
    #
    # Con un'ancora, una comunicazione entra solo se qualcuno ha stabilito
    # che c'entra — non perche' condivide una parola. E' il difetto visto
    # nello screenshot: «lascia un feedback sul tuo acquisto recente», una
    # mail di un negozio, dentro l'acquisto di una casa.
    from lifesearch.relations import relations_of

    belongs: Dict[str, Dict[str, Any]] = {}
    if anchors:
        for relation in await relations_of(
            db, owner_id, target_refs=list(anchors),
            belonging_only=bool(wanted.get("only_what_belongs")),
        ):
            if relation.get("source_type") == "email":
                belongs[str(relation.get("source_object_ref"))] = relation

    try:
        rows = await db.ingestion_events.find(
            {"user_id": owner_id,
             "source_record_type": {"$in": ["calendar_event", "email_message"]}},
            {"_id": 0, "normalized_payload": 1, "source_record_type": 1,
             "external_id": 1, "ingested_at": 1},
        ).sort("ingested_at", -1).to_list(LOOKED_AT)
    except Exception as e:
        logger.info("ingestion read soft-fail: %s", type(e).__name__)
        return
    found.looked_at += len(rows)

    now = datetime.now(timezone.utc)
    seen: List[Dict[str, Any]] = []
    for row in rows:
        payload = plain(row.get("normalized_payload"))
        is_event = row.get("source_record_type") == "calendar_event"
        when = _moment(payload.get("starts_at") or payload.get("received_at"))
        # Il tempo non decide la pertinenza, ma la restringe quando la
        # domanda parla di tempo.
        #
        #     «COSA HO DAVANTI» RIGUARDA GLI APPUNTAMENTI, NON LA POSTA.
        #
        # Guardare avanti aveva senso per gli impegni e nessuno per i
        # messaggi: una mail e' sempre arrivata prima di adesso, quindi il
        # filtro le toglieva tutte — ed e' il motivo per cui dentro «Casa»
        # non compariva nessuna comunicazione, nemmeno quelle collegate.
        if when is not None:
            if forward and is_event and when < now:
                continue
            if since and str(when.isoformat()) < str(since) and not forward:
                continue
        seen.append({
            "ref": str(row.get("external_id") or ""),
            "is_event": is_event,
            "title": str(payload.get("title") or payload.get("subject") or ""),
            "where": str(payload.get("location") or ""),
            "when": when,
        })

    # Primo passaggio: quello che la domanda nomina.
    named = {
        item["ref"] for item in seen
        if _mentions(f"{item['title']} {item['where']}", words)
    }
    # Secondo: quello che e' collegato a uno di quelli.
    linked: Set[str] = set()
    for ref in named:
        linked |= joined.get(ref, set())

    for item in seen:
        how = None
        relation = belongs.get(item["ref"])
        if relation:
            how = "governed"
        elif anchors and not item["is_event"]:
            # Ancorata a una situazione: per una comunicazione serve una
            # relazione, non una parola in comune. Se non ce l'ha, il posto
            # in cui compare non e' questo.
            how = "situation" if item["ref"] in linked else None
        elif item["ref"] in named:
            how = "lexical"
        elif item["ref"] in linked:
            how = "situation"
        elif broad and not words:
            # «Cosa e' cambiato» non nomina niente: si guarda largo, e la
            # finestra di tempo e' gia' stata applicata sopra.
            how = "provenance"
        if not how:
            continue
        row = {
            "key": item["ref"] or item["title"],
            "matched_by": how,
            "order": (item["when"].isoformat() if item["when"] else ""),
            "cosa": item["title"][:160],
            "quando": _as_people_say_it(item["when"]),
            "dove": item["where"][:120],
        }
        if relation and relation.get("reason_summary"):
            row["perche_e_qui"] = str(relation["reason_summary"])[:200]
        if relation and not relation.get("belongs", True):
            row["vicino_non_dentro"] = True
        found.add("appuntamenti" if item["is_event"] else "comunicazioni", row)


async def _joined_pairs(db, owner_id: str) -> Dict[str, Set[str]]:
    """
    Chi e' stato messo insieme a chi, dal Connected Life.

    Una mappa simmetrica: se la mail parla di quell'appuntamento, allora
    quell'appuntamento porta a quella mail, e viceversa.
    """
    try:
        rows = await db.connected_situation_links.find(
            {"owner_id": owner_id},
            {"_id": 0, "target_ref": 1, "source_object_ref": 1},
        ).to_list(60)
    except Exception:
        return {}
    pairs: Dict[str, Set[str]] = {}
    for row in rows:
        here = str(row.get("source_object_ref") or "")
        there = str(row.get("target_ref") or "")
        if not here or not there:
            continue
        pairs.setdefault(here, set()).add(there)
        pairs.setdefault(there, set()).add(here)
    return pairs


async def _documents(db, owner_id, anchors, words, found, wanted) -> None:
    """
    Le carte: prima per relazione scritta, poi — e solo poi — per nome.

        UN ROGITO NON CONTIENE LA PAROLA «CASA».

    Era il debito dello sprint precedente: senza una relazione registrata, il
    documento piu' importante di una situazione si trovava solo se qualcuno
    ne indovinava il titolo. Adesso l'appartenenza e' scritta — il giudizio
    l'ha stabilita guardando le carte una volta sola — e «documenti della
    casa» e' una lettura di relazioni che non costa niente.
    """
    from lifesearch.relations import relations_of

    by_ref: Dict[str, Dict[str, Any]] = {}
    if anchors:
        for relation in await relations_of(
            db, owner_id, target_refs=list(anchors),
            belonging_only=bool(wanted.get("only_what_belongs")),
        ):
            if relation.get("source_type") != "document":
                continue
            by_ref[str(relation.get("source_object_ref"))] = relation

    try:
        rows = await db.documents.find(
            {"user_id": owner_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "display_title": 1, "original_filename": 1,
             "created_at": 1},
        ).sort("created_at", -1).to_list(LOOKED_AT)
    except Exception as e:
        logger.info("document read soft-fail: %s", type(e).__name__)
        return
    found.looked_at += len(rows)

    for row in rows:
        name = str(row.get("display_title") or row.get("original_filename") or "")
        relation = by_ref.get(row["id"])
        if relation:
            how = "governed"
        elif _mentions(name, words):
            how = "lexical"
        else:
            continue
        item = {
            "key": row["id"],
            "matched_by": how,
            "order": str(row.get("created_at") or ""),
            "cosa": name[:160],
            "apri": f"/document/{row['id']}",
        }
        if relation and relation.get("reason_summary"):
            # Perche' questa carta e' qui. Una frase, non un punteggio.
            item["perche_e_qui"] = str(relation["reason_summary"])[:200]
        if relation and not relation.get("belongs", True):
            # Vicino per argomento, non dentro la situazione. Detto.
            item["vicino_non_dentro"] = True
        found.add("documenti", item)


async def _money(db, owner_id, words, found, wanted) -> None:
    """
    I movimenti, solo quando la domanda li vuole davvero.

    Un elenco di righe di conto dentro la risposta a «casa» sarebbe un
    estratto conto messo dove serviva un significato.
    """
    if wanted.get("kind") not in ("financial_lookup", "relationship_lookup",
                                  "broad_life_query"):
        return
    try:
        from financial.observed import what_was_seen

        seen = await what_was_seen(db, owner_id)
    except Exception as e:
        logger.info("movement read soft-fail: %s", type(e).__name__)
        return

    rows = (
        seen.get("ricorrenti_in_entrata", [])
        + seen.get("ricorrenti_in_uscita", [])
        + seen.get("movimenti_singoli", [])
    )
    found.looked_at += len(rows)

    # Le cifre scritte nella domanda. «Questa spesa da 760 riguarda la casa?»
    # nomina un movimento senza nominarne la descrizione, e nessuna parola
    # potra' mai collegarli: e' un numero, e si confronta con un numero.
    amounts = _amounts_in(wanted.get("asked") or "")

    for row in rows:
        described = str(row.get("come_lo_scrive_la_banca") or "")
        named = str(row.get("come_l_ho_chiamata") or "")
        by_amount = any(a in str(row.get("quanto") or "") for a in amounts)
        if words and not by_amount and not _mentions(f"{described} {named}", words):
            continue
        found.add("movimenti", {
            "key": described,
            "matched_by": (
                "explicit" if by_amount
                else "provenance" if named else "lexical"
            ),
            "order": described,
            "cosa": named or described[:120],
            "quanto": row.get("quanto"),
            "verso": row.get("verso"),
            "quante_volte": row.get("quante_volte"),
        })


async def _changes(db, owner_id, words, found, wanted) -> None:
    """
    Cosa e' cambiato. Solo per le domande che parlano di tempo.

    Le righe superate non tornano: una cosa che e' stata sostituita non e'
    una notizia, e' la versione vecchia di una notizia.
    """
    if wanted.get("kind") not in ("timeline_lookup", "broad_life_query"):
        return
    query: Dict[str, Any] = {
        "owner_id": owner_id,
        "status": {"$nin": ["superseded", "skipped"]},
    }
    if wanted.get("since"):
        query["observed_at"] = {"$gte": wanted["since"]}
    try:
        rows = await db.connected_signals.find(
            query,
            {"_id": 0, "id": 1, "payload_summary": 1, "observed_at": 1,
             "before": 1, "after": 1, "source_type": 1},
        ).sort("observed_at", -1).to_list(60)
    except Exception as e:
        logger.info("change read soft-fail: %s", type(e).__name__)
        return
    found.looked_at += len(rows)

    for row in rows:
        summary = str(row.get("payload_summary") or "")
        if not summary:
            continue
        if words and not _mentions(summary, words):
            continue
        found.add("cambiamenti", {
            "key": row["id"],
            "matched_by": "provenance",
            "order": str(row.get("observed_at") or ""),
            "cosa": summary[:200],
            "quando": _as_people_say_it(_moment(row.get("observed_at"))),
            "prima": str(row.get("before") or "")[:80],
            "dopo": str(row.get("after") or "")[:80],
        })


def _as_people_say_it(when: Optional[datetime]) -> str:
    """Una data come la direbbe qualcuno. Mai un ISO in faccia a nessuno."""
    if when is None:
        return ""
    days = (when.date() - datetime.now(timezone.utc).date()).days
    if days == 0:
        return f"oggi alle {when.strftime('%H:%M')}"
    if days == 1:
        return f"domani alle {when.strftime('%H:%M')}"
    if days == -1:
        return "ieri"
    if 1 < days <= 7:
        return f"fra {days} giorni"
    if -7 <= days < -1:
        return f"{abs(days)} giorni fa"
    return when.strftime("%d/%m/%Y")
