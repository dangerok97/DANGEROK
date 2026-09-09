"""
V3.11 — dopo lo scollegamento: cosa resta vero, e cosa smette di esserlo.

    FONTE SCOLLEGATA != CONOSCENZA CANCELLATA
    FONTE SCOLLEGATA != STATO ATTUALE DELLA BANCA

Le due meta' di questa frase sono state imparate una alla volta, e la seconda
e' costata un difetto vero: dopo aver scollegato il conto Enable Banking, la
schermata diceva in cima «Nessun conto collegato» e dieci righe piu' sotto
mostrava «Mock ASPSP · Disponibile €3.250». Nessuna delle due era falsa da
sola. Insieme dicevano a una persona che ORA stava guardando un conto che non
poteva piu' aprire.

Da qui in avanti la distinzione ha un posto solo dove vive — `la_banca` — e
tre superfici che la leggono: la schermata, la conversazione, il ciclo
automatico. Questi test tengono ferme tutte e tre.
"""

from __future__ import annotations

import json as jsonlib
import uuid

import _loop_harness

MONGO = "mongodb://localhost:27017"
DBNAME = "ora_test"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("financial_facts", "financial_observations", "bank_accounts",
                 "connector_instances", "memories", "life_objects",
                 "connected_source_attempts", "agent_goals"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


class _Permissions:
    class _Audit:
        async def log(self, **kw):
            return None

    def __init__(self):
        self.audit = self._Audit()


class _Vault:
    def __init__(self):
        self.revoked = []

    async def put(self, *, user_id, purpose, payload, metadata=None):
        return f"sv_{uuid.uuid4().hex[:12]}"

    async def get(self, ref, *, user_id=None):
        return {"access_token": "t"}

    async def revoke(self, ref):
        self.revoked.append(ref)
        return True


async def _connected(db, uid):
    """Una persona con un conto letto: dodici righe e un saldo."""
    from connectors.bank import BankReadService, FakeBankProvider

    svc = BankReadService(
        db=db, permissions=_Permissions(), vault=_Vault(),
        provider=FakeBankProvider(),
    )
    made = await svc.connect(user_id=uid)
    await svc.sync(user_id=uid, instance_id=made["instance_id"])
    return svc, made["instance_id"]


async def _knows_something(db, uid):
    """Una cosa che la persona ha confermato: deve sopravvivere a tutto."""
    from financial.durable import propose
    from financial.models import FinancialFact, Money, Provenance
    from financial.store import FinancialStore

    fact = FinancialFact(
        owner_id=uid, kind="income", what="Stipendio ACME SRL",
        money=Money(amount=2050, currency="EUR"), direction="incoming",
        cadence="recurring", recurrence="ogni mese",
        provenance=[Provenance(source="person", how_directly="me l'hai confermato tu")],
        source_refs=["tx_a001"],
    )
    await FinancialStore(db).remember(fact)
    await propose(db, fact, confirmed_by_user=True)
    return fact


# ---------------------------------------------------------------------------
# Dopo lo scollegamento
# ---------------------------------------------------------------------------

def test_a_disconnected_account_is_not_listed_among_connected_accounts():
    """
    §1: il difetto vero, in una riga.

    «Conti collegati» e' un titolo che promette qualcosa. Una fonte che ORA
    non puo' piu' leggere non puo' stare sotto quel titolo, nemmeno con una
    postilla accanto: chi legge vede il titolo e il saldo, non la postilla.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            before = await money_overview(db, uid)
            assert before["conti"], "il conto collegato non compare"

            await svc.disconnect(user_id=uid, instance_id=instance_id)
            after = await money_overview(db, uid)

            assert after["conti"] == [], "un conto scollegato resta fra i collegati"
            assert after["collegamento"]["stato"] == "non_collegato"
            assert after["collegamento"]["in_parole"] == "Nessun conto collegato."

            past = after["fonti_non_piu_collegate"]
            assert len(past) == 1, "la fonte passata e' sparita del tutto"
            assert past[0]["banca"] == "Banca di prova"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_last_balance_is_shown_as_a_memory_and_not_as_a_balance():
    """
    §2: «Disponibile €3.250» dopo lo scollegamento e' una cifra non verificabile.

    Puo' restare — e' l'ultima cosa che si e' potuta leggere, ed e' utile —
    ma deve dire di esserlo. Il presente e' la parte che mente.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            await svc.disconnect(user_id=uid, instance_id=instance_id)

            shown = await money_overview(db, uid)
            past = shown["fonti_non_piu_collegate"][0]

            assert past["ultimo_saldo"].startswith("Ultimo saldo osservato")
            assert "3.250" in past["ultimo_saldo"]
            assert past["letto_l_ultima_volta"]
            assert "non è più collegato" in past["in_parole"]

            # E da nessuna parte, in tutta la schermata, quel numero compare
            # come saldo disponibile corrente.
            blob = jsonlib.dumps(shown, ensure_ascii=False)
            assert "Disponibile" not in blob
            assert '"saldo_tipo": "disponibile"' not in blob
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_the_person_confirmed_survives_the_disconnection():
    """
    §3: scollegare una fonte non rende falsa una cosa confermata da chi vive.

    «Lo stipendio e' 2.050, me l'hai detto tu» resta vero anche se la banca
    non e' piu' collegata: non e' un dato in prestito dalla banca, e' una
    cosa che ORA ha capito e che la persona ha confermato.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            await _knows_something(db, uid)
            await svc.disconnect(user_id=uid, instance_id=instance_id)

            rows = (await money_overview(db, uid))["cosa_ho_capito"]
            known = [r for r in rows if r.get("stato") == "SO"]
            assert known, "quello che la persona aveva confermato e' sparito"
            assert known[0]["cosa"] == "Stipendio ACME SRL"
            assert "confermato" in known[0]["perche"]

            # E la provenienza conserva quando la fonte si e' fermata.
            fact = await db.financial_facts.find_one(
                {"owner_id": uid, "provenance.source": "bank"}, {"_id": 0},
            )
            if fact:
                assert fact.get("source_disconnected_at")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_what_was_only_seen_stops_sounding_like_something_ora_is_watching():
    """
    §4: «l'ho visto 3 volte» dopo lo scollegamento promette una verifica.

    ORA non puo' piu' guardare. La frase deve dirlo, o suggerisce che basti
    chiedere per sapere.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            fresh = [
                r for r in (await money_overview(db, uid))["cosa_ho_capito"]
                if r.get("stato") == "HO VISTO"
            ]
            assert fresh, "niente da guardare: il test non prova niente"
            assert "quando il conto era collegato" not in fresh[0]["perche"]

            await svc.disconnect(user_id=uid, instance_id=instance_id)
            later = [
                r for r in (await money_overview(db, uid))["cosa_ho_capito"]
                if r.get("stato") == "HO VISTO"
            ]
            assert later, "le osservazioni sono sparite invece di invecchiare"
            for row in later:
                assert "quando il conto era collegato" in row["perche"]
                assert "non posso più verificarlo" in row["non_so"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_nothing_is_read_from_the_bank_after_it_is_disconnected():
    """
    §6: scollegare deve fermare le letture, non solo nasconderle.

    Una sorgente revocata non entra nella coda; e se qualcuno provasse
    comunque a leggerla, il provider non verrebbe toccato.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from connected.polling import due

            svc, instance_id = await _connected(db, uid)
            await svc.disconnect(user_id=uid, instance_id=instance_id)

            waiting = [s.id for s in await due(db, uid)]
            assert instance_id not in waiting, "la banca e' ancora in coda"

            instance = await db.connector_instances.find_one(
                {"id": instance_id}, {"_id": 0},
            )
            assert instance["status"] == "revoked"
            assert not instance.get("secret_reference"), (
                "il permesso di leggere e' ancora nel documento"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Cosa arriva al modello quando qualcuno fa una domanda
# ---------------------------------------------------------------------------

def test_the_answer_material_says_the_source_is_gone():
    """
    §7 + §11: il modello non puo' indovinare che il conto e' stato scollegato.

    Deve trovarlo scritto, insieme al permesso di parlare del saldo solo al
    passato. Una regola che vive nel prompt di sistema si perde in fondo a
    una conversazione lunga; questa viaggia con i dati.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.knowledge import what_ora_knows

            svc, instance_id = await _connected(db, uid)
            live = (await what_ora_knows(db, uid))["la_banca"]
            assert live["posso_leggere_adesso"] is True
            assert live["ultimo_saldo_osservato"]["quanto"]

            await svc.disconnect(user_id=uid, instance_id=instance_id)
            gone = (await what_ora_knows(db, uid))["la_banca"]

            assert gone["posso_leggere_adesso"] is False
            assert gone["saldo_attuale"] is None
            assert gone["ultimo_saldo_osservato"]["non_piu_verificabile"] is True
            assert "non è più collegato" in gone["come_dirlo"]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_single_payment_is_never_offered_as_a_recurring_expense():
    """
    §8: RICORRENTE NON VUOL DIRE IMPORTANTE.

    Il pagamento al notaio e' la cosa piu' grossa del mese e non si e' mai
    ripetuta. Se finisse fra le ricorrenti, ORA direbbe a una persona che
    ogni mese le partono quattromila euro.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observed import what_was_seen

            await _connected(db, uid)
            seen = await what_was_seen(db, uid)

            recurring = jsonlib.dumps(
                seen["ricorrenti_in_uscita"] + seen["ricorrenti_in_entrata"],
                ensure_ascii=False,
            ).lower()
            assert "notarile" not in recurring, "una spesa unica fra le ricorrenti"

            singles = jsonlib.dumps(seen["movimenti_singoli"], ensure_ascii=False)
            assert "NOTARILE" in singles.upper(), "la spesa unica e' sparita"
            # E il piu' grosso viene per primo: e' quello che spiega il mese.
            assert "4.000" in singles.split("},")[0]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_recurring_movement_nobody_named_stays_unnamed():
    """
    §8 + §10: 14,99 al mese non e' «un abbonamento», e 760 non e' «l'affitto».

    Sono due uscite che tornano. Il nome, se arrivera', lo dara' il giudizio
    con delle prove — o la persona con una conferma. Fino ad allora la riga
    dice quello che c'e' scritto sull'estratto conto.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observed import what_was_seen

            await _connected(db, uid)
            seen = await what_was_seen(db, uid)
            outgoing = seen["ricorrenti_in_uscita"]
            assert outgoing, "nessuna uscita ricorrente riconosciuta"

            for row in outgoing:
                assert row.get("identificato") is False, (
                    f"«{row['come_lo_scrive_la_banca']}» ha preso un nome che "
                    "nessuno gli ha dato"
                )
                assert row["quante_volte"] > 1
                assert row.get("ogni_quanti_giorni_circa")

            blob = jsonlib.dumps(seen, ensure_ascii=False).lower()
            for invented in ("abbonamento", "affitto", "bolletta", "assicurazione"):
                assert invented not in blob, f"e' comparso «{invented}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_movement_the_judgement_named_carries_that_name():
    """§10: e quando un nome c'e' davvero, la riga lo porta."""
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observed import what_was_seen

            await _connected(db, uid)
            await _knows_something(db, uid)
            seen = await what_was_seen(db, uid)

            incoming = seen["ricorrenti_in_entrata"]
            named = [r for r in incoming if r.get("come_l_ho_chiamata")]
            assert named, "un fatto governato non arriva fino alla risposta"
            assert named[0]["come_l_ho_chiamata"] == "Stipendio ACME SRL"
            assert "identificato" not in named[0]
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_monthly_figure_is_a_partial_sum_and_says_so():
    """
    §9: LA DIFFERENZA FRA QUELLO CHE HO LETTO NON E' QUELLO CHE TI RESTA.

    Il numero e' utile e va dato. Quello che non si puo' fare e' darlo senza
    il suo nome, perche' un numero senza nome viene letto come il numero che
    chi legge sperava.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from financial.observation import BankObservation, ObservationStore
            from financial.observed import this_month

            store = ObservationStore(db)
            when = "2026-09-05T10:00:00+00:00"
            for ref, amount, what in (
                ("m1", 2050.00, "ACCREDITO STIPENDIO"),
                ("m2", -4000.00, "STUDIO NOTARILE BIANCHI"),
                ("m3", -760.00, "BONIFICO A MARCO ROSSI"),
                ("m4", -36.20, "PAGAMENTO POS"),
                ("m5", -12.00, "PAGAMENTO POS BAR"),
                ("m6", -14.99, "ADDEBITO SEPA 4411"),
            ):
                await store.record(BankObservation(
                    owner_id=uid, account_ref="acc", transaction_ref=ref,
                    booked_at=when, amount=amount, currency="EUR",
                    direction="incoming" if amount > 0 else "outgoing",
                    raw_description=what,
                ))

            month = await this_month(db, uid)
            assert "2.050" in month["entrate_osservate"]
            assert "4.823,19" in month["uscite_osservate"]
            assert "2.773,19" in month["differenza_parziale"]
            assert "non una disponibilità" in month["che_cosa_e"]
            assert "NOTARILE" in month["la_voce_che_pesa_di_piu"]["come_lo_scrive_la_banca"]

            blob = jsonlib.dumps(month, ensure_ascii=False).lower()
            for forbidden in ("ti resta", "rimarranno", "disponibilità residua"):
                assert forbidden not in blob, f"compare «{forbidden}»"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_conversation_tool_hands_all_three_levels_to_the_model():
    """
    §7-§11: il tool e' la porta di produzione, e deve portarli tutti.

    Stato della fonte, forma dei movimenti, somma del mese. Se uno dei tre
    non arriva, il modello puo' solo indovinare — e indovina bene finche' non
    conta.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools.financial_caps import (
                what_do_i_know_about_money,
            )

            svc, instance_id = await _connected(db, uid)
            await svc.disconnect(user_id=uid, instance_id=instance_id)

            seen = await what_do_i_know_about_money(
                {}, {"user_id": uid, "db": db},
            )
            payload = seen.payload
            assert payload["the_bank_right_now"]["posso_leggere_adesso"] is False
            assert payload["movements_by_shape"]["ricorrenti_in_uscita"]
            assert payload["this_month_partial"] or True

            told = payload["how_to_say_it"]
            assert "non è più collegato" in told
            assert "ricorrente" in told
            assert "non quello che resta" in told
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Ricollegare
# ---------------------------------------------------------------------------

def test_reconnecting_does_not_duplicate_what_was_already_read():
    """
    §14: ricollegare rilegge la stessa storia, e non la raddoppia.

    Il registro delle osservazioni e' indicizzato sul riferimento della
    transazione, e il fatto governato ha la sua identita': la seconda lettura
    riconosce entrambi.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank import BankReadService, FakeBankProvider

            svc, instance_id = await _connected(db, uid)
            await _knows_something(db, uid)

            movements = await db.financial_observations.count_documents(
                {"owner_id": uid})
            facts = await db.financial_facts.count_documents({"owner_id": uid})
            assert movements and facts

            await svc.disconnect(user_id=uid, instance_id=instance_id)

            # Un consenso nuovo: istanza nuova, stessa banca, stessa storia.
            again = BankReadService(
                db=db, permissions=_Permissions(), vault=_Vault(),
                provider=FakeBankProvider(),
            )
            made = await again.connect(user_id=uid)
            read = await again.sync(user_id=uid, instance_id=made["instance_id"])

            assert read["ok"] is True
            assert read["written"] == 0, "la stessa storia e' stata riscritta"
            assert await db.financial_observations.count_documents(
                {"owner_id": uid}) == movements
            assert await db.financial_facts.count_documents(
                {"owner_id": uid}) == facts
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_reconnecting_makes_the_balance_current_again_only_after_reading():
    """
    §14: il saldo torna «di adesso» solo dopo una lettura vera.

    Non basta ricollegare: finche' non si e' letto, quello che c'e' e'
    ancora la fotografia di prima, e va detta come tale.
    """
    async def body():
        client, db = await _db()
        uid = f"dis_{uuid.uuid4().hex[:8]}"
        try:
            from connectors.bank import BankReadService, FakeBankProvider
            from financial.overview import money_overview

            svc, instance_id = await _connected(db, uid)
            await svc.disconnect(user_id=uid, instance_id=instance_id)
            assert (await money_overview(db, uid))["conti"] == []

            again = BankReadService(
                db=db, permissions=_Permissions(), vault=_Vault(),
                provider=FakeBankProvider(),
            )
            made = await again.connect(user_id=uid)

            # Collegato, ma non ancora letto: il conto non e' ancora tornato.
            middle = await money_overview(db, uid)
            assert middle["conti"] == [], "il saldo e' tornato «attuale» senza una lettura"
            assert middle["fonti_non_piu_collegate"], "la fotografia e' sparita"

            await again.sync(user_id=uid, instance_id=made["instance_id"])
            after = await money_overview(db, uid)
            assert after["conti"], "dopo la lettura il conto non e' tornato"
            assert after["fonti_non_piu_collegate"] == []
            assert after["conti"][0]["saldo_noto"] is True
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
