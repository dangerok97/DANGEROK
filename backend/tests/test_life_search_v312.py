"""
V3.12 — Sprint 1: cercare dentro una vita.

    LA RICERCA E' UN'INTERFACCIA AL MODELLO DELLA VITA, NON UN TROVA-FILE.

Due modi di sbagliare questo pezzo, e sono entrambi comodi. Il primo e'
costruire un motore di ricerca testuale e chiamarlo Life Map: funziona nella
demo, perche' nella demo la persona scrive la parola che sta scritta nel
documento. Il secondo e' costruire un secondo modello della vita per rendere
la ricerca comoda — un indice con dentro copie di tutto — e da quel momento
esistono due verita' che divergono.

Questi test tengono ferme entrambe le cose: che la relazione venga prima
della parola, e che non nasca un secondo modello.
"""

from __future__ import annotations

import ast
import json as jsonlib
import re
import uuid
from pathlib import Path

import _loop_harness

HERE = Path(__file__).resolve().parents[1]
MONGO = "mongodb://localhost:27017"
DBNAME = "ora_test"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("life_objects", "financial_facts", "financial_observations",
                 "memories", "documents", "ingestion_events",
                 "connected_situation_links", "connected_signals",
                 "bank_accounts", "connector_instances"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


async def _a_life(db, uid):
    """
    Una vita piccola ma vera: una casa che si sta comprando, un lavoro, e le
    cose che ci girano intorno.
    """
    await db.life_objects.insert_many([
        {"id": "lo_casa", "user_id": uid, "title": "Acquisto di una nuova casa",
         "type": "HOME", "status": "active", "updated_at": "2026-09-01T10:00:00+00:00",
         "ai_summary": "Una casa ancora senza indirizzo stabile.",
         "next_reasoning": "Qual è l'indirizzo completo?"},
        {"id": "lo_lavoro", "user_id": uid, "title": "Lavoro", "type": "JOB",
         "status": "active", "updated_at": "2026-09-01T10:00:00+00:00",
         "ai_summary": "Un lavoro senza datore di lavoro."},
    ])

    from financial.durable import propose
    from financial.models import FinancialFact, Money, Provenance
    from financial.store import FinancialStore

    store = FinancialStore(db)
    notary = FinancialFact(
        owner_id=uid, kind="event", what="Notaio per acquisto casa",
        money=Money(amount=4000, currency="EUR"), direction="outgoing",
        cadence="one_time",
        provenance=[Provenance(source="bank", how_directly="l'ho visto sul tuo conto")],
        source_refs=["tx_notaio"], about_refs=["lo_casa"],
    )
    await store.remember(notary)

    salary = FinancialFact(
        owner_id=uid, kind="income", what="Stipendio ACME SRL",
        money=Money(amount=2050, currency="EUR"), direction="incoming",
        cadence="recurring", recurrence="ogni mese",
        provenance=[Provenance(source="person", how_directly="me l'hai confermato tu")],
        source_refs=["tx_stipendio"], about_refs=["lo_lavoro"],
    )
    await store.remember(salary)
    await propose(db, salary, confirmed_by_user=True)

    # Un appuntamento e la mail che lo riguarda, collegati fra loro.
    await db.ingestion_events.insert_many([
        {"id": "ing_1", "user_id": uid, "source_record_type": "calendar_event",
         "external_id": "ev_dentista", "ingested_at": "2026-09-07T10:00:00+00:00",
         "normalized_payload": {
             "title": "Visita dentistica — Studio Bianchi",
             "starts_at": "2026-12-10T09:00:00+00:00",
             "location": "Studio Bianchi"}},
        {"id": "ing_2", "user_id": uid, "source_record_type": "email_message",
         "external_id": "mail_bianchi", "ingested_at": "2026-09-06T10:00:00+00:00",
         "normalized_payload": {
             "subject": "Variazione appuntamento",
             "received_at": "2026-09-06T09:00:00+00:00"}},
    ])
    await db.connected_situation_links.insert_one({
        "id": "link_1", "owner_id": uid, "source_type": "email",
        "source_object_ref": "mail_bianchi", "relationship": "same_situation",
        "target_kind": "appointment", "target_ref": "ev_dentista",
        "reason_summary": "Riguarda lo stesso appuntamento.",
    })


# ---------------------------------------------------------------------------
# La relazione prima della parola
# ---------------------------------------------------------------------------

def test_a_word_that_appears_nowhere_still_reaches_the_right_situation():
    """
    §3: LA RELAZIONE CONTA PIU' DELLA PAROLA.

    «Notaio» non compare nel titolo della situazione, e la situazione e'
    quella giusta. A tenerle insieme e' un `about_refs` deciso dalla
    governance, non una stringa — e questo e' l'intero punto dello sprint.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.search import search_a_life

            await _a_life(db, uid)
            # Il giudizio ha nominato la casa; il codice espande per relazione.
            out = await _with_judgement(
                db, uid, "notaio",
                kind="relationship_lookup", about=["lo_casa"], words=["notaio"],
            )
            groups = {s["gruppo"] for s in out["risultati"]}
            assert "SITUAZIONI" in groups
            names = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "Acquisto di una nuova casa" in names
            assert "Notaio per acquisto casa" in names
            how = out["_qa"]["matched_by"]["cose_che_ora_sa"]
            assert "lexical" not in how, (
                f"il notaio e' stato trovato per parola, non per relazione: {how}"
            )
            assert {"governed", "situation"} & set(how), how
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


async def _with_judgement(db, uid, query, *, kind, about, words, since=None,
                          forward=False):
    """
    La ricerca con un giudizio gia' dato.

    I test non chiamano il modello: quello che il modello deciderebbe viene
    passato a mano, cosi' la prova riguarda l'espansione — che e' la parte
    che deve restare vera anche quando il provider e' giu'.
    """
    from lifesearch.present import as_sections, conflicts_kept
    from lifesearch.resolve import gather

    wanted = {
        "kind": kind, "about_situations": about, "words": words,
        "since": since, "looking_forward": forward, "what_they_want": "",
    }
    found = await gather(db, uid, wanted=wanted)
    return {
        "risultati": as_sections(found, wanted=wanted),
        "in_conflitto": conflicts_kept(found),
        "_qa": {
            "matched_by": {
                g: sorted({r["matched_by"] for r in rows})
                for g, rows in found.rows.items()
            },
            "candidate_count": found.looked_at,
            "retrieved_count": found.kept,
        },
    }


def test_a_linked_message_is_found_without_containing_the_word():
    """
    §3: un collegamento fra fonti vale piu' di una parola.

    La mail dice «Variazione appuntamento» e non dice «dentista». E' collegata
    all'appuntamento dal Connected Life, e quel collegamento e' registrato:
    quindi si trova.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            out = await _with_judgement(
                db, uid, "dentista", kind="entity_lookup", about=[],
                words=["dentist"],
            )
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "Variazione appuntamento" in blob, (
                "la mail collegata non e' stata trovata"
            )
            assert "situation" in out["_qa"]["matched_by"]["comunicazioni"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_results_are_grouped_by_meaning_and_not_by_file_type():
    """§5: i risultati non sono una lista piatta di file."""
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            out = await _with_judgement(
                db, uid, "casa", kind="broad_life_query", about=["lo_casa"],
                words=["casa"],
            )
            groups = [s["gruppo"] for s in out["risultati"]]
            assert groups, "nessun gruppo"
            assert groups == sorted(
                groups,
                key=lambda g: [x[1] for x in _order()].index(g),
            ), "i gruppi non sono nell'ordine in cui una persona li vuole"
            assert "SITUAZIONI" in groups and "COSE CHE ORA SA" in groups
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def _order():
    from lifesearch.present import GROUPS

    return GROUPS


def test_knowledge_comes_from_the_life_model_and_not_from_the_journal():
    """
    §16: il registro dei movimenti non e' conoscenza.

    «Cosa so del mio affitto» deve rispondere con quello che la governance ha
    accettato, non con una riga di conto che diceva «BONIFICO A ROSSI MARCO».
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import BankObservation, ObservationStore

            await _a_life(db, uid)
            # Un movimento grezzo che nessuno ha interpretato.
            await ObservationStore(db).record(BankObservation(
                owner_id=uid, account_ref="acc", transaction_ref="tx_raw",
                booked_at="2026-09-05T10:00:00+00:00", amount=-760.0,
                currency="EUR", direction="outgoing",
                raw_description="BONIFICO A MARCO ROSSI",
            ))
            out = await _with_judgement(
                db, uid, "affitto", kind="financial_lookup", about=[],
                words=["affitto"],
            )
            known = [s for s in out["risultati"] if s["gruppo"] == "COSE CHE ORA SA"]
            blob = jsonlib.dumps(known, ensure_ascii=False)
            assert "MARCO ROSSI" not in blob.upper(), (
                "una riga di conto e' stata presentata come conoscenza"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_ora_knows_carries_how_it_knows_it_in_words():
    """
    §8: «da dove lo sai?» ha una risposta, ed e' in italiano.

    Non «provenance: person», non un id di documento: «me l'hai confermato
    tu». La domanda e' legittima e frequente, e una risposta tecnica la
    tratta come un problema di supporto.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            out = await _with_judgement(
                db, uid, "stipendio", kind="financial_lookup",
                about=["lo_lavoro"], words=["stipendio"],
            )
            rows = [
                r for s in out["risultati"] if s["gruppo"] == "COSE CHE ORA SA"
                for r in s["cosa_c_e"]
            ]
            assert rows, "lo stipendio non e' stato trovato"
            salary = next(r for r in rows if "Stipendio" in r["cosa"])
            assert salary["stato"] == "SO"
            assert salary["come_lo_so"] == "me l'hai confermato tu"
            for technical in ("provenance", "source_ref", "person", "mem_"):
                assert technical not in jsonlib.dumps(salary, ensure_ascii=False)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_truths_stay_two():
    """
    §10: IL CODICE NON SCEGLIE QUALE FONTE DICE IL VERO.

    Una cosa confermata dalla persona e una versione diversa letta altrove
    non si fondono nella piu' recente: restano due, e la frase lo dice.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from financial.durable import propose
            from financial.models import FinancialFact, Money, Provenance
            from financial.store import FinancialStore

            await _a_life(db, uid)
            store = FinancialStore(db)
            first = FinancialFact(
                owner_id=uid, kind="commitment", what="Affitto",
                money=Money(amount=760, currency="EUR"), direction="outgoing",
                cadence="recurring", recurrence="ogni mese",
                provenance=[Provenance(source="person",
                                       how_directly="me l'hai detto tu")],
                source_refs=["a"],
            )
            await store.remember(first)
            await propose(db, first, confirmed_by_user=True)

            second = FinancialFact(
                owner_id=uid, kind="commitment", what="Affitto",
                money=Money(amount=790, currency="EUR"), direction="outgoing",
                cadence="recurring", recurrence="ogni mese",
                provenance=[Provenance(source="email",
                                       how_directly="lo ha scritto il proprietario")],
                source_refs=["b"],
            )
            await store.remember(second)
            await propose(db, second)

            out = await _with_judgement(
                db, uid, "affitto", kind="financial_lookup", about=[],
                words=["affitto"],
            )
            assert out["in_conflitto"], "il conflitto e' stato risolto in silenzio"
            said = out["in_conflitto"][0]["in_parole"]
            assert "due informazioni diverse" in said
            assert "760" in said and "790" in said
            assert "Non scelgo io" in said
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_superseded_change_is_not_offered_as_news():
    """
    §9: quello che e' stato superato non torna come corrente.

    Un segnale sostituito e' la versione vecchia di una notizia, e in una
    risposta a «cosa e' cambiato» sarebbe una notizia falsa.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            await db.connected_signals.insert_many([
                {"id": "sig_old", "owner_id": uid, "status": "superseded",
                 "payload_summary": "L'appuntamento era alle 08:00.",
                 "observed_at": "2026-09-06T10:00:00+00:00", "source_type": "calendar"},
                {"id": "sig_now", "owner_id": uid, "status": "interpreted",
                 "payload_summary": "L'appuntamento è alle 11:00.",
                 "observed_at": "2026-09-07T10:00:00+00:00", "source_type": "calendar"},
            ])
            out = await _with_judgement(
                db, uid, "cosa è cambiato", kind="timeline_lookup", about=[],
                words=[],
            )
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "alle 11:00" in blob
            assert "era alle 08:00" not in blob, (
                "una riga superata e' tornata come corrente"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_search_reads_a_little_and_keeps_less():
    """
    §12: POCHI TOKEN, ALTA PERTINENZA.

    Una ricerca che scandisce tutto e passa tutto al modello non e' una
    ricerca: e' un archivio con una casella di testo davanti. I tre numeri
    che lo dicono viaggiano con la risposta.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            # Molte righe intorno, per vedere se ne porta via troppe.
            await db.ingestion_events.insert_many([
                {"id": f"noise_{n}", "user_id": uid,
                 "source_record_type": "email_message",
                 "external_id": f"noise_{n}",
                 "ingested_at": "2026-09-01T10:00:00+00:00",
                 "normalized_payload": {"subject": f"Newsletter {n}"}}
                for n in range(60)
            ])
            out = await _with_judgement(
                db, uid, "casa", kind="situation_lookup", about=["lo_casa"],
                words=["casa"],
            )
            qa = out["_qa"]
            assert qa["candidate_count"] > qa["retrieved_count"]
            assert qa["retrieved_count"] <= 24, (
                f"{qa['retrieved_count']} righe portate via: troppe"
            )
            assert "Newsletter" not in jsonlib.dumps(out["risultati"])
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_answer_carries_nothing_technical():
    """§13 + §16: niente id, niente punteggi, niente JSON in faccia a nessuno."""
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            out = await _with_judgement(
                db, uid, "casa", kind="broad_life_query", about=["lo_casa"],
                words=["casa"],
            )
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            for technical in ("lo_casa", "lo_lavoro", "ing_", "fin_", "mem_",
                              "matched_by", "confidence", "score",
                              "about_refs", "provenance"):
                assert technical not in blob, f"in risposta compare «{technical}»"
            assert not re.search(r"0\.\d\d", blob), "un punteggio e' arrivato fino in fondo"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Le guardie strutturali
# ---------------------------------------------------------------------------

def _code_only(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        body = getattr(node, "body", [])
        if (
            body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
    return ast.unparse(tree)


def test_no_keyword_routing_decides_what_a_query_means():
    """
    §6: NON CREARE ROUTER A KEYWORD.

    La tentazione e' un dizionario: «mutuo» → finanza, «dentista» → salute.
    Funziona finche' qualcuno scrive «rogito», e la cura e' sempre aggiungere
    una parola — finche' l'elenco diventa il prodotto. Il significato lo dice
    il giudizio; il codice mette i confini.
    """
    watched = ("mutuo", "dentista", "affitto", "casa", "stipendio", "salute",
               "viaggio", "scuola", "medico", "banca", "bolletta", "notaio")

    def naming(node) -> set:
        """Le parole di una costante, se e' una costante di testo."""
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            return set()
        if len(node.value) > 60:
            # Le istruzioni al modello sono lunghe; le regole sono corte, ed
            # e' la lunghezza a distinguerle senza fingere di leggere le
            # intenzioni di chi le ha scritte.
            return set()
        return set(re.findall(r"[a-zàèéìòù]+", node.value.lower()))

    offenders = []
    for path in (HERE / "lifesearch").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # Un instradamento ha due forme sole: un confronto con una parola,
            # o una tabella che ha quella parola come chiave. Un nome di
            # campo che contiene «banca» non e' nessuna delle due.
            suspects = []
            if isinstance(node, ast.Compare):
                suspects = [node.left] + list(node.comparators)
            elif isinstance(node, ast.Dict):
                suspects = [k for k in node.keys if k is not None]
            for suspect in suspects:
                for word in naming(suspect) & set(watched):
                    offenders.append(f"{path.name}:{node.lineno} «{word}»")
    assert not offenders, f"una parola decide il significato: {offenders}"


def test_no_second_life_model_is_created():
    """
    §1: NON CREARE UN SECONDO MODELLO.

    La ricerca legge quello che c'e' — situazioni, memorie governate, fatti
    finanziari, segnali — e non se ne scrive una copia. Se cominciasse a
    tenere un proprio indice, da quel momento esisterebbero due verita', e la
    seconda invecchierebbe in silenzio.

    Una sola eccezione, ed e' il senso dello sprint: le *relazioni*. Un
    documento che appartiene a una casa deve poterlo dire da qualche parte, e
    quel posto e' la collezione dei collegamenti che il Connected Life usa
    gia'. Una relazione non e' una copia: e' un fatto nuovo su due cose che
    restano dove sono.
    """
    writes = ("insert_one", "insert_many", "update_one", "update_many",
              "replace_one", "delete_one", "delete_many", "bulk_write")
    # Le collezioni che *sono* il modello della vita. La ricerca non le tocca
    # da nessun file, nemmeno da quello che ha il permesso di scrivere.
    theirs = ("life_objects", "memories", "financial_facts",
              "financial_observations", "documents", "connected_signals",
              "ingestion_events", "bank_accounts")

    offenders = []
    for path in (HERE / "lifesearch").glob("*.py"):
        source = _code_only(path)
        writing = any(verb in source for verb in writes)
        if writing and path.name != "relations.py":
            offenders.append(f"{path.name}: scrive, e non e' il file delle relazioni")
        if not writing:
            continue
        for collection in theirs:
            if collection in source:
                offenders.append(f"{path.name}: scriverebbe in «{collection}»")
    assert not offenders, offenders


def test_relations_live_where_the_existing_links_live():
    """
    §4: preferire l'esistente.

    Un collegamento dice «queste due cose parlano dello stesso pezzo di
    vita», e non cambia natura perche' le due cose sono un documento e una
    casa invece di una mail e un appuntamento. Un secondo sistema avrebbe
    voluto dire due posti da tenere in fila e due risposte diverse alla
    domanda «perche' ORA pensa che c'entrino».
    """
    from connected.situations import LINKS
    from lifesearch.relations import LINKS as OURS
    from lifesearch.relations import RELATION_TYPES

    assert OURS == LINKS, "le relazioni vivono in una collezione tutta loro"
    assert set(RELATION_TYPES) == {
        "about", "part_of", "related_to", "supports", "contradicts", "supersedes",
    }, "i tipi di relazione sono cresciuti"


def test_the_search_does_not_dump_the_database_into_the_prompt():
    """
    §12: al modello va l'indice, non il contenuto.

    L'indice e' fatto di nomi e conteggi. Se un giorno qualcuno ci mettesse
    dentro il testo dei documenti o il corpo delle email, il costo di ogni
    ricerca crescerebbe con la vita di chi la usa.
    """
    source = _code_only(HERE / "lifesearch" / "index.py")
    for forbidden in ("extracted_text", "body", "content", "raw_payload",
                      "normalized_payload", "payload_summary"):
        assert forbidden not in source, (
            f"l'indice della vita contiene «{forbidden}»"
        )


def test_the_interpretation_cannot_invent_a_situation():
    """
    §6: il modello propone, il codice verifica.

    Un id che il giudizio si e' inventato non appartiene a nessuno, e un
    risultato che ne discende sarebbe la vita di un altro.
    """
    source = _code_only(HERE / "lifesearch" / "interpret.py")
    assert "known" in source and "about_situations" in source
    assert "if str(x) in known" in source.replace("\n", " ") or "in known" in source


def test_there_is_still_no_sixth_tab():
    """§4: la ricerca entra dalla Vita, non da una scheda nuova."""
    tabs = HERE.parent / "frontend" / "app" / "(tabs)"
    names = {p.stem.lower() for p in tabs.glob("*.tsx")} if tabs.exists() else set()
    for forbidden in ("cerca", "search", "mappa", "life-map", "lifemap"):
        assert forbidden not in names, f"c'è una scheda «{forbidden}»"

    contesti = (tabs / "contesti.tsx").read_text(encoding="utf-8")
    assert "/cerca" in contesti, "dalla Vita non si arriva alla ricerca"


def test_the_screen_never_reads_the_qa_block():
    """
    §3: `matched_by` serve a chi verifica, e a nessun altro.

    Una persona che legge «trovato per corrispondenza lessicale» ha ricevuto
    una scusa, non un risultato.
    """
    screen = (
        HERE.parent / "frontend" / "app" / "cerca.tsx"
    ).read_text(encoding="utf-8")
    for forbidden in ("_qa", "matched_by", "candidate_count", "confidence"):
        assert forbidden not in screen, f"la schermata legge «{forbidden}»"


def test_a_link_does_not_make_something_appear_in_every_search():
    """
    §3: UN COLLEGAMENTO UNISCE DUE COSE FRA LORO, NON A TUTTO IL RESTO.

    Trovato sulla vita vera, alla prima ricerca: le tre mail dello studio
    dentistico comparivano anche cercando «affitto» e «stipendio», perche'
    bastava essere collegate a qualcosa. Un collegamento e' una relazione fra
    due cose: senza una delle due, non porta da nessuna parte.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)

            # La domanda nomina il dentista: la mail collegata arriva.
            close = await _with_judgement(
                db, uid, "dentista", kind="entity_lookup", about=[],
                words=["dentist"],
            )
            assert "Variazione appuntamento" in jsonlib.dumps(
                close["risultati"], ensure_ascii=False)

            # La domanda parla d'altro: non deve arrivare niente di quello.
            far = await _with_judgement(
                db, uid, "stipendio", kind="financial_lookup",
                about=["lo_lavoro"], words=["stipendio"],
            )
            blob = jsonlib.dumps(far["risultati"], ensure_ascii=False)
            assert "Variazione appuntamento" not in blob, (
                "una mail collegata ad altro e' comparsa in una ricerca che "
                "non la riguarda"
            )
            assert "Studio Bianchi" not in blob
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Sprint 2: le carte, la cache, i doppioni, e quanto conta il giudizio
# ---------------------------------------------------------------------------

def test_a_document_is_found_through_its_situation_not_its_name():
    """
    §3 + §6: UN ROGITO NON CONTIENE LA PAROLA «CASA».

    Era il debito principale dello sprint precedente. Una volta che il
    giudizio ha stabilito che quella carta appartiene a quell'acquisto, la
    domanda «documenti della casa» e' una lettura di relazioni — e trova un
    file il cui nome non somiglia a niente di quello che e' stato scritto.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import remember_relation

            await _a_life(db, uid)
            await db.documents.insert_one({
                "id": "doc_rogito", "user_id": uid,
                "display_title": "Rogito_2026_definitivo",
                "original_filename": "Rogito_2026_definitivo.pdf",
                "created_at": "2026-09-01T10:00:00+00:00",
            })
            await remember_relation(
                db, uid, source_type="document", source_ref="doc_rogito",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about",
                why="È l'atto con cui si compra la casa.",
                decided_by="judgement", confidence=1.0,
            )

            out = await _with_judgement(
                db, uid, "documenti della casa", kind="document_lookup",
                about=["lo_casa"], words=["documenti"],
            )
            papers = [s for s in out["risultati"] if s["gruppo"] == "DOCUMENTI"]
            assert papers, "nessun documento trovato"
            row = papers[0]["cosa_c_e"][0]
            assert "Rogito" in row["cosa"]
            assert row["perche_e_qui"].startswith("È l'atto")
            assert "governed" in out["_qa"]["matched_by"]["documenti"], (
                "il rogito e' stato trovato per parola"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_relation_nobody_was_sure_of_is_not_written_down():
    """
    §3: UN FORSE NON SI SCRIVE COME UN SI'.

    Il giudizio puo' dire «non lo so», e quella e' una risposta da ricordare
    — non una relazione da inventare. Una riga scritta per prudenza diventa
    indistinguibile da una vera il giorno dopo.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import (
                RELATION_TYPES, relations_of, remember_relation,
            )

            await _a_life(db, uid)
            # Un tipo di relazione che non esiste non entra.
            assert await remember_relation(
                db, uid, source_type="document", source_ref="doc_x",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="probabilmente_riguarda", why="boh",
                decided_by="judgement",
            ) is None
            # E nemmeno una senza motivo.
            assert await remember_relation(
                db, uid, source_type="document", source_ref="doc_x",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about", why="   ", decided_by="judgement",
            ) is None
            assert await relations_of(db, uid) == []
            assert "probabilmente_riguarda" not in RELATION_TYPES
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_relation_twice_stays_one():
    """§4: la coppia sorgente-bersaglio e' l'identita' di una relazione."""
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import relations_of, remember_relation

            await _a_life(db, uid)
            for _ in range(3):
                await remember_relation(
                    db, uid, source_type="document", source_ref="doc_1",
                    target_kind="life_object", target_ref="lo_casa",
                    relation_type="about", why="Riguarda la casa.",
                    decided_by="judgement",
                )
            assert len(await relations_of(db, uid)) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_four_readings_of_one_afternoon_are_one_line():
    """
    §12: LA STESSA COSA, VISTA PIU' VOLTE, RESTA UNA COSA.

    Sulla ricerca vera di «dentista» uscivano sei righe per un appuntamento
    solo, lette da calendari diversi. Chi legge conta sei impegni.
    """
    from lifesearch.dedupe import collapse

    rows = [
        {"cosa": "QA ORA — Visita dentistica", "quando": "domani alle 08:00"},
        {"cosa": "Visita dentistica QA ORA", "quando": "domani alle 08:00"},
        {"cosa": "Visita dentistica — Studio Bianchi", "quando": "domani alle 08:00"},
        {"cosa": "Visita dentistica — Studio Bianchi", "quando": "domani alle 08:00"},
        {"cosa": "Pranzo con Marco", "quando": "domani alle 13:00"},
    ]
    kept = collapse(rows)
    assert len(kept) == 2, [r["cosa"] for r in kept]
    dentist = next(r for r in kept if "dentistica" in r["cosa"])
    # Si tiene la versione piu' completa: quella che dice anche dove.
    assert "Studio Bianchi" in dentist["cosa"]
    assert "4 calendari" in dentist["anche_altrove"]
    lunch = next(r for r in kept if "Pranzo" in r["cosa"])
    assert "anche_altrove" not in lunch, "una cosa vista una volta non si conta"


def test_two_different_appointments_are_not_merged():
    """§12: raggruppare non e' fondere. Due cose diverse restano due."""
    from lifesearch.dedupe import collapse

    kept = collapse([
        {"cosa": "Visita dentistica", "quando": "domani alle 08:00"},
        {"cosa": "Visita dentistica", "quando": "fra 4 giorni"},
    ])
    assert len(kept) == 2, "due appuntamenti in giorni diversi sono stati fusi"


def test_the_same_question_twice_costs_one_judgement():
    """§11: la stessa domanda, con la vita ferma, non si paga due volte."""
    from lifesearch.cache import forget_everything, remember, remembered

    forget_everything()
    assert remembered("u1", "casa", "mark") is None
    remember("u1", "casa", "mark", {"kind": "situation_lookup"})
    assert remembered("u1", " CASA ", "mark")["kind"] == "situation_lookup"
    # Una vita diversa: la scorciatoia sparisce da sola.
    assert remembered("u1", "casa", "un-altro-mark") is None
    # E la domanda di un'altra persona non e' la stessa domanda.
    assert remembered("u2", "casa", "mark") is None


def test_the_fingerprint_changes_when_the_life_changes():
    """
    §11: UNA RISPOSTA VECCHIA SU UNA VITA CAMBIATA E' PEGGIO DI NIENTE.

    Il caso che conta: qualcuno carica il contratto del mutuo e richiede
    «documenti del mutuo». Se l'impronta non cambiasse, ORA risponderebbe con
    quello che sapeva prima — cioe' niente.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.cache import fingerprint

            await _a_life(db, uid)
            before = await fingerprint(db, uid)

            await db.documents.insert_one({
                "id": "doc_nuovo", "user_id": uid,
                "display_title": "Contratto di mutuo",
                "created_at": "2026-09-09T10:00:00+00:00",
            })
            after = await fingerprint(db, uid)
            assert before != after, "l'impronta non si e' accorta del documento"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_observed_recurring_payment_is_not_promoted_to_rent():
    """
    §7 + §16: «questa spesa da 760 riguarda la casa?»

    La risposta onesta e' che si ripete, che e' stata osservata, e che
    nessuno ha confermato che sia un affitto — quindi non si puo' collegarla
    a una casa. Il modo sbagliato di rispondere e' comodo: chiamarla affitto
    e attaccarla alla situazione.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import BankObservation, ObservationStore

            await _a_life(db, uid)
            store = ObservationStore(db)
            for n in range(3):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc", transaction_ref=f"tx_{n}",
                    booked_at=f"2026-0{n + 6}-05T10:00:00+00:00", amount=-760.0,
                    currency="EUR", direction="outgoing",
                    raw_description="BONIFICO A MARCO ROSSI",
                ))

            out = await _with_judgement(
                db, uid, "questa spesa da 760 riguarda la casa?",
                kind="relationship_lookup", about=["lo_casa"], words=["760"],
            )
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False).lower()
            assert "affitto" not in blob, (
                "una spesa osservata e' stata battezzata affitto"
            )
            # E non esiste nessuna relazione scritta fra quel movimento e la casa.
            from lifesearch.relations import relations_of

            assert await relations_of(db, uid, target_refs=["lo_casa"]) == []
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_synthesis_only_runs_when_a_list_would_not_answer():
    """
    §8 + §10: «documenti della casa» vuole i documenti, non un paragrafo.

    Una sintesi davanti a una richiesta di navigazione e' una cosa in mezzo,
    e costa una chiamata a ogni ricerca di ogni persona.
    """
    source = (HERE / "lifesearch" / "search.py").read_text(encoding="utf-8")
    assert 'wanted.get("needs_synthesis")' in source
    assert "in_a_few_lines" in source

    # E la sintesi non puo' aggiungere: legge quello che il recupero ha gia'
    # portato, e nient'altro.
    written = (HERE / "lifesearch" / "synthesis.py").read_text(encoding="utf-8")
    assert "Add nothing that is not in what you were given" in written
    for reads_the_world in ("db.", "find(", "count_documents"):
        assert reads_the_world not in written, (
            "la sintesi rilegge il database invece di sintetizzare"
        )


def test_the_judgement_decides_the_meaning_and_the_code_the_boundaries():
    """
    §1: CODE RETRIEVES AND ENFORCES. AI UNDERSTANDS, CONNECTS AND SYNTHESIZES.

    Le due meta' devono restare separate anche a leggerle: il file che
    interpreta non tocca il database, e i file che recuperano non decidono
    significati.
    """
    interpreting = _code_only(HERE / "lifesearch" / "interpret.py")
    for touching in ("db.", "find(", "count_documents", "insert", "update_one"):
        assert touching not in interpreting, (
            f"chi interpreta tocca il database: «{touching}»"
        )

    retrieving = _code_only(HERE / "lifesearch" / "resolve.py")
    assert "_ask_model" not in retrieving, "chi recupera chiama il giudizio"
    assert "relations_of" in retrieving, "chi recupera non legge le relazioni"


def test_a_document_relation_never_copies_the_document():
    """
    §3: NON DUPLICARE IL CONTENUTO DEL DOCUMENTO DENTRO IL LIFE MODEL.

    Due copie dello stesso testo divergono alla prima modifica, e la seconda
    e' quella che nessuno aggiorna.
    """
    # I campi con cui si andrebbe a prendere il testo. L'istruzione al
    # giudizio dice «non vedi il contenuto» e contiene la parola: quello che
    # non deve esistere e' la lettura, non la frase che la vieta.
    for name in ("relations.py", "papers.py"):
        source = _code_only(HERE / "lifesearch" / name)
        for forbidden in ("extracted_text", "full_text", "raw_text",
                          "content_text", "body_text"):
            assert forbidden not in source, f"{name} copia il contenuto"


def test_a_question_that_names_an_amount_finds_that_movement():
    """
    §7: «questa spesa da 760 riguarda la casa?» nomina un movimento.

    Non lo nomina con una parola — «BONIFICO A MARCO ROSSI» non contiene
    niente della domanda — lo nomina con una cifra. Confrontare due numeri e'
    aritmetica, ed e' l'unico modo che quella domanda ha di indicare quella
    riga.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import BankObservation, ObservationStore

            await _a_life(db, uid)
            store = ObservationStore(db)
            for n in range(3):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc", transaction_ref=f"tx_{n}",
                    booked_at=f"2026-0{n + 6}-05T10:00:00+00:00", amount=-760.0,
                    currency="EUR", direction="outgoing",
                    raw_description="BONIFICO A MARCO ROSSI",
                ))

            from lifesearch.present import as_sections
            from lifesearch.resolve import gather

            wanted = {
                "kind": "financial_lookup", "mode": "answer",
                "about_situations": ["lo_casa"], "words": ["spesa", "casa"],
                "since": None, "looking_forward": False,
                "asked": "questa spesa da 760 riguarda la casa?",
            }
            found = await gather(db, uid, wanted=wanted)
            sections = as_sections(found, wanted=wanted)
            money = [s for s in sections if s["gruppo"] == "MOVIMENTI"]
            assert money, "il movimento da 760 non e stato trovato"
            assert "760" in jsonlib.dumps(money, ensure_ascii=False)
            # E resta senza nome: nessuno ha confermato che sia un affitto.
            assert "affitto" not in jsonlib.dumps(money, ensure_ascii=False).lower()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_opening_one_part_of_a_life_does_not_show_another():
    """
    §13: LO STIPENDIO NON STA DENTRO L'ACQUISTO DELLA CASA.

    Trovato aprendo «Casa» sulla vita vera: sotto «cose che ORA sa»
    compariva lo stipendio, perche' bastava che ci fosse un'ancora e nessuna
    parola perche' entrasse tutto il governato. Una parte di vita mostra
    quello che le appartiene.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.search import what_ora_knows_about

            await _a_life(db, uid)
            out = await what_ora_knows_about(db, uid, "lo_casa")
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "Notaio" in blob, "quello che appartiene alla casa non c e"
            assert "Stipendio" not in blob, (
                "dentro la casa compare una cosa che appartiene al lavoro"
            )

            work = await what_ora_knows_about(db, uid, "lo_lavoro")
            said = jsonlib.dumps(work["risultati"], ensure_ascii=False)
            assert "Stipendio" in said and "Notaio" not in said
            assert work["_qa"]["product_calls"] == 0, (
                "aprire una parte di vita non deve costare una chiamata"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Sprint 3: le comunicazioni, il rumore, e la manutenzione che gira da sola
# ---------------------------------------------------------------------------

async def _a_mailbox(db, uid):
    """Tre messaggi: uno che c'entra, uno che sembra e non c'entra, uno no."""
    await db.ingestion_events.insert_many([
        {"id": "ing_m1", "user_id": uid, "source_record_type": "email_message",
         "external_id": "mail_preventivo", "ingested_at": "2026-09-07T10:00:00+00:00",
         "connector_instance_id": "ci_mail",
         "normalized_payload": {
             "subject": "R: Richiesta preventivo acquisto prima casa",
             "sender_relationship": "known", "received_at": "2026-09-07T09:00:00+00:00"}},
        {"id": "ing_m2", "user_id": uid, "source_record_type": "email_message",
         "external_id": "mail_feedback", "ingested_at": "2026-09-07T11:00:00+00:00",
         "connector_instance_id": "ci_mail",
         "normalized_payload": {
             "subject": "Francesco, lascia un feedback sul tuo acquisto recente",
             "sender_relationship": "unknown", "received_at": "2026-09-07T10:00:00+00:00"}},
        {"id": "ing_m3", "user_id": uid, "source_record_type": "email_message",
         "external_id": "mail_news", "ingested_at": "2026-09-07T12:00:00+00:00",
         "connector_instance_id": "ci_mail",
         "normalized_payload": {
             "subject": "Le soluzioni per il tuo mutuo da 103.000€",
             "sender_relationship": "unknown", "received_at": "2026-09-07T11:00:00+00:00"}},
    ])


def test_a_message_that_only_shares_a_word_stays_out_of_the_situation():
    """
    §7: «ACQUISTO» IN UN OGGETTO NON VUOL DIRE CHE PARLA DEL TUO ACQUISTO.

    Il difetto era negli screenshot dello sprint precedente: «lascia un
    feedback sul tuo acquisto recente» — la mail di un negozio — compariva
    sotto l'acquisto di una casa. Nessun elenco di parole poteva salvarla: la
    parola c'era, ed era quella giusta nel posto sbagliato.

    Adesso, con un'ancora, una comunicazione entra solo se qualcuno ha
    stabilito che c'entra.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import note_nothing_to_link, remember_relation

            await _a_life(db, uid)
            await _a_mailbox(db, uid)

            # Il giudizio ha guardato: una c'entra, le altre no.
            await remember_relation(
                db, uid, source_type="email", source_ref="mail_preventivo",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about",
                why="È la risposta al preventivo per la casa che stai comprando.",
                decided_by="judgement", confidence=1.0,
            )
            for ref, why in (
                ("mail_feedback", "È un negozio che chiede un'opinione su un ordine."),
                ("mail_news", "È una proposta commerciale, non il tuo mutuo."),
            ):
                await note_nothing_to_link(
                    db, uid, source_type="email", source_ref=ref, why=why,
                )

            out = await _with_judgement(
                db, uid, "cosa sai sulla casa?", kind="broad_life_query",
                about=["lo_casa"], words=["casa", "acquisto", "mutuo"],
            )
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "preventivo acquisto prima casa" in blob, (
                "la mail che c'entra non e' arrivata"
            )
            assert "feedback" not in blob, (
                "una mail di marketing e' entrata per una parola in comune"
            )
            assert "soluzioni per il tuo mutuo" not in blob
            assert out["_qa"]["matched_by"]["comunicazioni"] == ["governed"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_without_an_anchor_the_words_still_work():
    """
    §7: la regola stretta vale quando la domanda parla di una situazione.

    Chi cerca «feedback» sta cercando quella mail, e deve trovarla: negarla
    sarebbe un filtro che decide cosa qualcuno ha il diritto di cercare.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            await _a_life(db, uid)
            await _a_mailbox(db, uid)
            out = await _with_judgement(
                db, uid, "feedback", kind="entity_lookup", about=[],
                words=["feedback"],
            )
            assert "feedback" in jsonlib.dumps(out["risultati"], ensure_ascii=False)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_is_judged_twice_when_nothing_changed():
    """
    §5: il secondo passaggio su una vita ferma non costa niente.

    E' la differenza fra un lavoro di manutenzione e una fattura ricorrente.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch import messages, papers
            from lifesearch.maintenance import keep_relations_current
            from lifesearch.relations import note_nothing_to_link

            await _a_life(db, uid)
            await _a_mailbox(db, uid)
            await db.documents.insert_one({
                "id": "doc_1", "user_id": uid, "display_title": "Una carta",
                "created_at": "2026-09-01T10:00:00+00:00",
            })

            # Tutto gia' deciso, in un modo o nell'altro — anche la mail
            # dello studio che arriva con la vita di prova.
            for ref in ("mail_preventivo", "mail_feedback", "mail_news",
                        "mail_bianchi"):
                await note_nothing_to_link(
                    db, uid, source_type="email", source_ref=ref, why="Niente.")
            await note_nothing_to_link(
                db, uid, source_type="document", source_ref="doc_1", why="Niente.")

            asked = {"n": 0}

            async def counted(*a, **kw):
                asked["n"] += 1
                return {}

            papers._ask_model = counted
            messages._ask_model = counted

            before = await db.connected_situation_links.count_documents(
                {"owner_id": uid})
            done = await keep_relations_current(db, owners=[uid])
            after = await db.connected_situation_links.count_documents(
                {"owner_id": uid})

            assert asked["n"] == 0, "ha rigiudicato cose gia' decise"
            assert done["chiamate"] == 0
            assert before == after, "una riga nuova su una vita ferma"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_new_message_is_the_only_thing_looked_at():
    """§4: solo il nuovo torna giudicabile, non tutto."""
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.messages import _messages
            from lifesearch.relations import already_decided, note_nothing_to_link

            await _a_life(db, uid)
            await _a_mailbox(db, uid)
            for ref in ("mail_feedback", "mail_news", "mail_bianchi"):
                await note_nothing_to_link(
                    db, uid, source_type="email", source_ref=ref, why="Niente.")

            seen = set(await already_decided(db, uid, source_type="email"))
            fresh = [m for m in await _messages(db, uid) if m["ref"] not in seen]
            assert [m["ref"] for m in fresh] == ["mail_preventivo"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_body_of_a_message_is_never_written_down():
    """
    §2: IL CORPO SI CHIEDE UNA VOLTA, E NON SI CONSERVA.

    La regola di Connected Life non cambia perche' adesso serve a collegare:
    il testo si mette davanti a un giudizio e si dimentica.
    """
    written = _code_only(HERE / "lifesearch" / "messages.py")
    # Nessuna scrittura: il file che colloca non scrive, scrive quello delle
    # relazioni — e li' non arriva nessun testo.
    for verb in ("insert_one", "insert_many", "update_one", "update_many"):
        assert verb not in written, "il file dei messaggi scrive nel database"

    relations = _code_only(HERE / "lifesearch" / "relations.py")
    for field in ("text", "body", "snippet_text"):
        assert f'"{field}"' not in relations, (
            f"una relazione porterebbe con se' «{field}»"
        )


def test_no_second_scheduler_was_started():
    """
    §4: NON CREARE UN NUOVO SCHEDULER.

    Il giro c'e' gia', sopravvive gia' a un riavvio, tollera gia' che un
    passaggio fallisca. Un secondo sarebbe una seconda cosa da avviare, da
    fermare, e da sbagliare allo spegnimento.
    """
    maintenance = _code_only(HERE / "lifesearch" / "maintenance.py")
    for forbidden in ("create_task", "asyncio.sleep", "while True", "Timer",
                      "BackgroundScheduler", "add_job"):
        assert forbidden not in maintenance, (
            f"la manutenzione avvia qualcosa di suo: «{forbidden}»"
        )

    runtime = (HERE / "ambient" / "runtime.py").read_text(encoding="utf-8")
    assert "keep_relations_current" in runtime, (
        "la manutenzione non e' dentro il giro che c'era gia'"
    )
    assert runtime.count("create_task") == 1, "e' comparso un secondo loop"


def test_relations_do_not_pile_up_on_the_same_pair():
    """§5: nessun duplicato, nemmeno dopo molti passaggi."""
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import relations_of, remember_relation

            await _a_life(db, uid)
            for n in range(4):
                await remember_relation(
                    db, uid, source_type="email", source_ref="mail_preventivo",
                    target_kind="life_object", target_ref="lo_casa",
                    relation_type="about", why=f"Motivo {n}.",
                    decided_by="judgement",
                )
            rows = await relations_of(db, uid, source_refs=["mail_preventivo"])
            assert len(rows) == 1
            # L'ultimo motivo resta, la riga non si moltiplica.
            assert rows[0]["reason_summary"] == "Motivo 3."
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_no_keyword_decides_what_a_message_is_about():
    """
    §1: NON USARE REGOLE TIPO «subject contains mutuo => casa».

    La stessa guardia delle query, applicata al file che colloca i messaggi:
    un confronto con una parola, o una tabella che ne ha una come chiave.
    """
    watched = ("mutuo", "dentista", "affitto", "casa", "stipendio", "salute",
               "banca", "notaio", "newsletter", "feedback", "acquisto")
    offenders = []
    for name in ("messages.py", "papers.py"):
        tree = ast.parse((HERE / "lifesearch" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            suspects = []
            if isinstance(node, ast.Compare):
                suspects = [node.left] + list(node.comparators)
            elif isinstance(node, ast.Dict):
                suspects = [k for k in node.keys if k is not None]
            for suspect in suspects:
                if not isinstance(suspect, ast.Constant):
                    continue
                if not isinstance(suspect.value, str) or len(suspect.value) > 60:
                    continue
                words = set(re.findall(r"[a-zàèéìòù]+", suspect.value.lower()))
                for word in words & set(watched):
                    offenders.append(f"{name}:{node.lineno} «{word}»")
    assert not offenders, f"una parola decide di cosa parla un messaggio: {offenders}"


# ---------------------------------------------------------------------------
# Hotfix: appartenere non e' assomigliare
# ---------------------------------------------------------------------------

def test_belonging_needs_a_tie_to_that_situation_and_not_another():
    """
    §1 + §3: STESSO DOMINIO NON VUOL DIRE STESSA SITUAZIONE.

    Trovato nella review degli screenshot: «Contratto di Locazione» era
    finito dentro l'acquisto di una casa perche' «un contratto di locazione e'
    collegato alla gestione di un'abitazione». La frase e' vera e non dice
    niente su *quella* casa.

    Adesso, per far entrare qualcosa dentro una situazione, il giudizio deve
    nominare cosa lo lega a quella e non a un'altra. Se non lo nomina, il
    codice declassa da solo: vicino, non dentro.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import relations_of, remember_relation

            await _a_life(db, uid)

            # Senza prova: resta vicino.
            vague = await remember_relation(
                db, uid, source_type="document", source_ref="doc_locazione",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about",
                why="Un contratto di locazione è collegato alla gestione di un'abitazione.",
                decided_by="judgement", confidence=1.0,
            )
            assert vague["relation_type"] == "related_to", (
                "una somiglianza di dominio e' entrata come appartenenza"
            )
            assert vague["belongs"] is False

            # Con la prova: entra.
            precise = await remember_relation(
                db, uid, source_type="document", source_ref="doc_rogito",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about",
                why="È l'atto di acquisto della casa.",
                ties="Stesso immobile e stessa controparte della compravendita.",
                decided_by="judgement", confidence=1.0,
            )
            assert precise["relation_type"] == "about"
            assert precise["belongs"] is True

            inside = await relations_of(db, uid, target_refs=["lo_casa"],
                                        belonging_only=True)
            assert [r["source_object_ref"] for r in inside] == ["doc_rogito"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_life_map_shows_only_what_belongs():
    """
    §5: la Vita e' piu' severa della ricerca.

    Dentro «Acquisto di una nuova casa» ci va quello che appartiene a
    quell'acquisto. Quello che parla di case in generale puo' comparire in una
    ricerca larga, non dentro la situazione.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import remember_relation
            from lifesearch.search import what_ora_knows_about

            await _a_life(db, uid)
            await db.documents.insert_many([
                {"id": "doc_locazione", "user_id": uid,
                 "display_title": "Contratto di Locazione",
                 "created_at": "2026-09-01T10:00:00+00:00"},
                {"id": "doc_rogito", "user_id": uid,
                 "display_title": "Rogito_2026_definitivo",
                 "created_at": "2026-09-02T10:00:00+00:00"},
            ])
            await remember_relation(
                db, uid, source_type="document", source_ref="doc_locazione",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about", why="Parla di un'abitazione.",
                decided_by="judgement",
            )
            await remember_relation(
                db, uid, source_type="document", source_ref="doc_rogito",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about", why="È l'atto di acquisto.",
                ties="Stesso immobile della compravendita in corso.",
                decided_by="judgement",
            )

            out = await what_ora_knows_about(db, uid, "lo_casa")
            blob = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "Rogito" in blob
            assert "Locazione" not in blob, (
                "dentro la situazione e' entrato qualcosa che le assomiglia"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_communication_that_belongs_reaches_the_life_map():
    """
    §6: dentro una situazione le comunicazioni collegate devono comparire.

    Non comparivano, e non per una questione di relazioni: la Vita guardava
    «in avanti», e una mail e' sempre arrivata prima di adesso. Il filtro le
    toglieva tutte.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import remember_relation
            from lifesearch.search import what_ora_knows_about

            await _a_life(db, uid)
            await _a_mailbox(db, uid)
            await remember_relation(
                db, uid, source_type="email", source_ref="mail_preventivo",
                target_kind="life_object", target_ref="lo_casa",
                relation_type="about",
                why="È la risposta al preventivo per la casa che stai comprando.",
                ties="Stessa conversazione sul preventivo di quell'acquisto.",
                decided_by="judgement",
            )

            out = await what_ora_knows_about(db, uid, "lo_casa")
            groups = [s["gruppo"] for s in out["risultati"]]
            assert "COMUNICAZIONI" in groups, (
                "una mail collegata non arriva nella Vita"
            )
            said = jsonlib.dumps(out["risultati"], ensure_ascii=False)
            assert "preventivo" in said.lower()
            # E niente sezioni vuote.
            for section in out["risultati"]:
                assert section["cosa_c_e"], f"sezione vuota: {section['gruppo']}"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_things_that_are_merely_similar_never_become_members():
    """
    §8: LA SOMIGLIANZA E' UN INDIZIO, NON UNA PROVA DI IDENTITA'.

    Cinque modi di sbagliare, tutti plausibili, tutti nello stesso dominio
    della situazione — e nessuno di essi e' quella situazione. Il giudizio
    puo' proporli; il codice, senza una prova specifica, li tiene fuori.
    """
    async def body():
        client, db = await _db()
        uid = f"ls_{uuid.uuid4().hex[:8]}"
        try:
            from lifesearch.relations import relations_of, remember_relation

            await _a_life(db, uid)
            plausible = [
                ("doc_bolletta_genitori", "È una bolletta di una casa."),
                ("doc_hotel", "Riguarda un alloggio per una vacanza."),
                ("doc_assicurazione_vecchia", "È l'assicurazione di un'abitazione."),
                ("mail_annunci", "Sono annunci di case in vendita."),
                ("doc_locazione", "È un contratto di locazione di un immobile."),
            ]
            for ref, why in plausible:
                await remember_relation(
                    db, uid, source_type="document", source_ref=ref,
                    target_kind="life_object", target_ref="lo_casa",
                    relation_type="part_of", why=why, decided_by="judgement",
                )

            inside = await relations_of(
                db, uid, target_refs=["lo_casa"], belonging_only=True,
            )
            assert inside == [], (
                f"qualcosa di solo somigliante e' entrato: "
                f"{[r['source_object_ref'] for r in inside]}"
            )
            # Restano tutte, come vicinanze, con il loro motivo leggibile.
            near = await relations_of(db, uid, target_refs=["lo_casa"])
            assert len(near) == len(plausible)
            for row in near:
                assert row["relation_type"] == "related_to"
                assert row["reason_summary"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_judgement_is_asked_to_name_the_tie():
    """
    §3: l'AI deve giudicare l'identita', non la categoria.

    La domanda che le si fa non e' «parla di casa?» ma «cosa lega questa cosa
    a *questa* situazione e non a un'altra?».
    """
    for name in ("papers.py", "messages.py"):
        source = (HERE / "lifesearch" / name).read_text(encoding="utf-8")
        assert "Belonging is not resemblance" in source
        assert "what_ties_it" in source
        assert "A lease is about a home" in source
