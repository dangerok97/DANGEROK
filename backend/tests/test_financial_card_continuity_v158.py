"""A source correction must reach the saved fact and the actual Home response."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from mongomock_motor import AsyncMongoMockClient

from financial.models import FinancialFact, Horizon, Money, Provenance
from financial.store import FinancialStore


def card_fact(**changes):
    values = dict(
        id="old_card", owner_id="owner", kind="commitment",
        what="Carta di credito", money=Money(amount=None), direction="outgoing",
        cadence="recurring", recurrence="ogni mese", due_at="2026-10-10",
        created_at="2026-10-08T12:00:00+00:00",
        provenance=[Provenance(source="email", source_ref="owned_message")],
        source_refs=["mail:owned_message"],
    )
    values.update(changes)
    return FinancialFact(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize("details", [
    {"what": "Addebito mensile Mastercard Gold", "counterparty": "ING"},
    {"due_at": "2026-10-10T14:25:28+02:00"},
    {"kind": "event", "occurred_at": "2026-10-10"},
])
async def test_same_source_retains_semantic_corrections_without_a_second_charge(details):
    db = AsyncMongoMockClient().financial_v158_meaning
    store = FinancialStore(db)
    old = card_fact()
    await store.remember(old)
    corrected = old.model_copy(deep=True, update={
        "id": "corrected_card", "created_at": "2026-10-11T15:00:00+00:00", **details,
    })
    outcome = await store.remember(corrected)
    assert outcome["outcome"] == "superseded"
    active = await store.known("owner")
    assert len(active) == 1
    assert active[0].id == "corrected_card"
    assert active[0].created_at == old.created_at
    for field, value in details.items():
        assert getattr(active[0], field) == value
    assert (await store.get("owner", old.id)).status == "superseded"
    assert (await store.remember(corrected.model_copy(update={"id": "retry"})))["outcome"] == "already_known"
    assert await store.get("another-owner", old.id) is None


@pytest.mark.asyncio
async def test_legacy_prefixed_source_and_shorter_specific_name_are_corrected_once():
    db = AsyncMongoMockClient().financial_v158_legacy
    store = FinancialStore(db)
    old = card_fact(
        what="Qualcosa di economico", money=Money(amount=0.99, currency="EUR"),
        provenance=[Provenance(source="email", source_ref="mail:owned_message")],
    )
    await store.remember(old)
    other = old.model_copy(deep=True, update={"id": "other_card", "owner_id": "another-owner"})
    await store.remember(other)
    corrected = old.model_copy(deep=True, update={
        "id": "icloud", "what": "iCloud+",
        "provenance": [Provenance(source="email", source_ref="owned_message")],
    })
    outcome = await store.remember(corrected)
    assert outcome["outcome"] == "superseded"
    assert [f.what for f in await store.known("owner")] == ["iCloud+"]
    assert [f.what for f in await store.known("another-owner")] == ["Qualcosa di economico"]


@pytest.mark.asyncio
async def test_a_less_precise_reread_keeps_the_known_amount_and_exact_time():
    db = AsyncMongoMockClient().financial_v158_no_downgrade
    store = FinancialStore(db)
    old = card_fact(
        due_at="2026-10-10T14:25:28+02:00",
        money=Money(amount=0.99, currency="EUR"),
    )
    await store.remember(old)
    for less_precise in (
        {"due_at": "2026-10-10"}, {"money": Money(amount=None)},
    ):
        result = await store.remember(old.model_copy(update={"id": "weaker", **less_precise}))
        assert result["outcome"] == "already_known"
        active = (await store.known("owner"))[0]
        assert active.money.amount == 0.99
        assert active.due_at == old.due_at


@pytest.mark.asyncio
@pytest.mark.parametrize("money", [
    Money(amount=25.99, currency="EUR"), Money(amount=14.99, currency="USD"),
])
async def test_conflicting_known_amount_from_the_same_email_remains_a_dispute(money):
    db = AsyncMongoMockClient().financial_v158_disagreement
    store = FinancialStore(db)
    old = card_fact(money=Money(amount=14.99, currency="EUR"))
    await store.remember(old)
    new = old.model_copy(update={"id": "conflicting", "money": money})
    result = await store.remember(new)
    assert result["outcome"] == "disputed"
    assert result["disputes"] == [old.id]
    versions = await store.known("owner")
    assert {f.status for f in versions} == {"disputed"}
    assert {(f.money.amount, f.money.currency) for f in versions} == {
        (14.99, "EUR"), (money.amount, money.currency),
    }


@pytest.mark.asyncio
async def test_bridge_governs_and_returns_the_retained_fact_when_reread_changes_nothing(monkeypatch):
    from financial import bridge, durable, reasoning

    db = AsyncMongoMockClient().financial_v158_bridge
    old = card_fact()
    await FinancialStore(db).remember(old)
    monkeypatch.setattr(bridge, "_life", AsyncMock(return_value={}))
    monkeypatch.setattr(reasoning, "read_financial_meaning", AsyncMock(return_value={
        "what_it_is": old.kind, "in_their_words": old.what, "amount": None,
        "direction": old.direction, "how_often": old.cadence,
        "recurrence": old.recurrence, "due_at": old.due_at,
        "what_is_not_known": ["l'importo"],
    }))
    governance = AsyncMock(return_value={"decision": "CLARIFY", "persisted": False})
    monkeypatch.setattr(durable, "propose", governance)
    result = await bridge.read_money_in(
        db, "owner", observation={"in_words": "Promemoria carta"},
        provenance=Provenance(source="email", source_ref="owned_message"),
        source_refs=["mail:owned_message"],
    )
    assert result["outcome"] == "already_known"
    assert result["fact_id"] == old.id
    assert governance.await_args.args[1].id == old.id
    assert await db.financial_facts.count_documents({}) == 1


@pytest.mark.asyncio
async def test_old_completed_review_can_recover_after_the_correction_then_is_idempotent(monkeypatch):
    import deps
    from financial import source_review

    db = AsyncMongoMockClient().financial_v158_review
    await FinancialStore(db).remember(card_fact())
    await db.ingestion_events.insert_one({
        "user_id": "owner", "external_id": "owned_message",
        "source_record_type": "email_message", "connector_instance_id": "gmail_owner",
        "ingestion_status": "processed", "normalized_payload": {"subject": "Promemoria carta"},
    })
    await db.financial_source_reviews.insert_one({
        "owner_id": "owner", "message_ref": "owned_message", "status": "completed",
    })
    mail = type("SyntheticMail", (), {"body_for": AsyncMock(return_value="Avviso sintetico.")})()
    monkeypatch.setattr(deps, "get_gmail_service", lambda: mail)
    reread = AsyncMock(return_value={"outcome": "superseded"})
    monkeypatch.setattr(source_review, "read_money_in", reread)
    first = await source_review.review_email_financial_sources(db, "owner")
    assert first["checked"] == first["updated"] == 1
    repeat = await source_review.review_email_financial_sources(db, "owner")
    assert repeat["checked"] == 0 and repeat["already_reviewed"] == 1
    assert mail.body_for.await_count == 1
    audits = await db.financial_source_reviews.find({}).to_list(5)
    assert "Avviso sintetico" not in str(audits)


@pytest.mark.asyncio
async def test_original_source_reaches_real_home_updates_without_becoming_focus(monkeypatch):
    from financial import durable, horizon
    from home import service as home_module
    from home.adapters.financial import load_financial_context
    from home.models import CurrentSituation

    db = AsyncMongoMockClient().financial_v158_home
    now = datetime.now(timezone.utc)
    due = (now + timedelta(days=2)).date().isoformat()
    fact = card_fact(due_at=due)
    await db.ingestion_events.insert_many([
        {
            "user_id": "owner", "external_id": "owned_message",
            "source_record_type": "email_message", "ingestion_status": "processed",
            "ingested_at": "2026-10-08T12:00:00+00:00",
            "normalized_payload": {
                "subject": {"value": "Promemoria dalla tua carta di credito"},
                "received_at": {"value": "2026-10-08T12:00:00+00:00"},
            },
        },
        {
            "user_id": "other-owner", "external_id": "owned_message",
            "source_record_type": "email_message", "ingestion_status": "processed",
            "ingested_at": "2026-10-09T12:00:00+00:00",
            "normalized_payload": {"subject": "Estratto di un'altra persona"},
        },
    ])
    incoming = Horizon(
        owner_id="owner", days=30, from_day=now.date().isoformat(), to_day=due,
        outgoing=[fact],
    )
    monkeypatch.setattr(horizon, "what_is_coming", AsyncMock(return_value=incoming))
    monkeypatch.setattr(FinancialStore, "disagreements", AsyncMock(return_value=[]))
    monkeypatch.setattr(durable, "needs_your_word", AsyncMock(return_value=[]))
    items, warnings = await load_financial_context(db, "owner")
    monkeypatch.setattr(home_module, "gather_all", AsyncMock(return_value=(
        items, warnings, {"connected": False},
    )))
    monkeypatch.setattr(home_module, "load_active_goals", AsyncMock(return_value=[]))
    service = home_module.HomeService(db)
    monkeypatch.setattr(service, "_build_situation", AsyncMock(return_value=CurrentSituation()))
    monkeypatch.setattr(service, "_weather_now", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_load_ora_ti_consiglia", AsyncMock(return_value=[]))
    home = await service.build_home("owner")
    assert home.primary_focus is None
    assert home.priorities == []
    assert len(home.insights) == 1
    insight = home.insights[0]
    assert "Promemoria dalla tua carta di credito" in insight.source
    assert "importo non noto" in insight.text.lower()
    assert "Estratto di un'altra persona" not in str(home.model_dump())
    assert insight.created_at == fact.created_at
    assert insight.valid_until == due
    assert insight.action.route == "/conti-e-denaro"
    # Refreshing the page or reinterpreting the same source cannot make an
    # old notice appear newly created. No source is reread to render Home.
    items[0].created_at = now.isoformat()
    again = await service.build_home("owner")
    assert again.insights[0].created_at == fact.created_at
    await db.home_insights.update_one(
        {"user_id": "owner", "id": insight.id}, {"$set": {"status": "read"}},
    )
    assert (await service.build_home("owner")).insights == []
    # A corrected UUID for the same original email is still the same notice.
    incoming.outgoing = [fact.model_copy(update={"id": "corrected_uuid"})]
    same_items, _ = await load_financial_context(db, "owner")
    assert same_items[0].source_id == items[0].source_id
    # A genuinely new source can surface even though the last summary was read.
    incoming.outgoing = [fact.model_copy(update={
        "id": "new_source_fact",
        "provenance": [Provenance(source="email", source_ref="a_new_message")],
        "source_refs": ["mail:a_new_message"],
    })]
    next_items, _ = await load_financial_context(db, "owner")
    monkeypatch.setattr(home_module, "gather_all", AsyncMock(return_value=(
        next_items, [], {"connected": False},
    )))
    next_home = await service.build_home("owner")
    assert len(next_home.insights) == 1
    assert next_home.insights[0].id != insight.id
    assert next_home.primary_focus is None


@pytest.mark.asyncio
async def test_undated_summary_expiry_is_fixed_and_date_only_notices_last_the_day():
    from home.models import HomeItem
    from home.service import HomeService

    db = AsyncMongoMockClient().financial_v158_expiration
    service = HomeService(db)
    now = datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc)
    item = HomeItem(
        id="summary", type="insight", title="Impegni economici conosciuti",
        source_type="financial", source_id="horizon", created_at=now.isoformat(),
        meta={"knowledge_only": True, "source_label": "Una fonte sintetica"},
    )
    first = (await service._build_insights("owner", [item], {}, now))[0]
    again = (await service._build_insights("owner", [item], {}, now + timedelta(hours=4)))[0]
    assert again.valid_until == first.valid_until
    assert await service._build_insights("owner", [item], {}, now + timedelta(days=2)) == []
    # A real day-only source expiry is valid through that day and takes
    # precedence over the generic display lifetime of an undated summary.
    item.meta["valid_until"] = "2026-10-11"
    dated = await service._build_insights("owner", [item], {}, now)
    assert len(dated) == 1 and dated[0].valid_until == "2026-10-11"
    assert await service._build_insights("owner", [item], {}, now + timedelta(days=1)) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("knowledge_location", ["node", "attributes"])
async def test_informational_calendar_node_never_enters_ranking_but_manual_event_does(
    monkeypatch, knowledge_location,
):
    from home import manual_event
    from home import service as home_module
    from home.adapters.internal_calendar import load_internal_calendar
    from home.models import CurrentSituation

    db = AsyncMongoMockClient().financial_v158_calendar_knowledge
    now = datetime.now(timezone.utc)
    node = {
        "id": "synthetic_information", "user_id": "owner", "type": "event",
        "status": "active", "label": "Informazione amministrativa sintetica",
        "origin": "action_engine", "knowledge_only": knowledge_location == "node",
        "attributes": {
            "kind": "admin_deadline", "starts_at": (now + timedelta(hours=1)).isoformat(),
            "knowledge_only": knowledge_location == "attributes",
        },
    }
    await db.life_nodes.insert_one(node)
    items, _ = await load_internal_calendar(db, "owner")
    assert items[0].meta["knowledge_only"] is True

    async def gather_synthetic_items(database, owner):
        items, warnings = await load_internal_calendar(database, owner)
        return items, warnings, {"connected": False}

    monkeypatch.setattr(home_module, "gather_all", gather_synthetic_items)
    monkeypatch.setattr(home_module, "load_active_goals", AsyncMock(return_value=[]))
    ranking = Mock(wraps=home_module.rank_items)
    monkeypatch.setattr(home_module, "rank_items", ranking)
    service = home_module.HomeService(db)
    monkeypatch.setattr(service, "_build_situation", AsyncMock(return_value=CurrentSituation()))
    monkeypatch.setattr(service, "_weather_now", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_load_ora_ti_consiglia", AsyncMock(return_value=[]))

    home = await service.build_home("owner")
    assert home.primary_focus is None
    assert home.priorities == []
    assert ranking.call_args.args[0] == []

    monkeypatch.setattr(manual_event, "_wake", AsyncMock())
    manual = await manual_event.create_manual_event(
        db, "owner", title="Impegno manuale sintetico",
        start=(now + timedelta(days=1)).isoformat(),
        end=(now + timedelta(days=1, hours=1)).isoformat(),
        tz_name="UTC", request_id="synthetic_manual_request",
    )
    home = await service.build_home("owner")
    assert home.primary_focus["source_id"] == manual["id"]
    assert home.primary_focus["start_at"] == manual["starts_at"]
    assert [item.source_id for item in ranking.call_args.args[0]] == [manual["id"]]


async def confirmed_service(db, **changes):
    from financial.durable import propose

    fact = FinancialFact(
        id="confirmed_service", owner_id="owner", kind="commitment",
        what="Servizio sintetico", money=Money(amount=None),
        direction="outgoing", cadence="recurring", recurrence="ogni mese",
        provenance=[Provenance(source="person", how_directly="Conferma sintetica dell'utente")],
        source_refs=["conversation:synthetic_confirmation"],
    ).model_copy(update=changes)
    await db.financial_facts.insert_one(fact.model_dump())
    result = await propose(db, fact, confirmed_by_user=True)
    assert result["persisted"] is True
    return fact


async def pending_service(db, current, *, source_id="pending_service", **changes):
    fact = current.model_copy(deep=True, update={
        "id": source_id,
        "provenance": [Provenance(source="email", source_ref="synthetic_message",
                                  how_directly="Email originale: fonte sintetica")],
        "source_refs": ["mail:synthetic_message"], **changes,
    })
    # Historical pending records must be handled without rewriting their
    # governance decision or asking Gmail to read them yet again.
    await db.financial_facts.insert_one({**fact.model_dump(), "governance_decision": "CLARIFY"})
    return fact


async def question_surfaces(db, monkeypatch):
    from financial import overview
    from financial.knowledge import what_ora_knows
    from home import service as home_module
    from home.adapters.financial import load_financial_context
    from home.models import CurrentSituation

    monkeypatch.setattr(overview, "_connection", AsyncMock(return_value={"stato": "non_collegato"}))
    items, warnings = await load_financial_context(db, "owner")
    monkeypatch.setattr(home_module, "gather_all", AsyncMock(return_value=(
        items, warnings, {"connected": False},
    )))
    monkeypatch.setattr(home_module, "load_active_goals", AsyncMock(return_value=[]))
    service = home_module.HomeService(db)
    monkeypatch.setattr(service, "_build_situation", AsyncMock(return_value=CurrentSituation()))
    monkeypatch.setattr(service, "_weather_now", AsyncMock(return_value={}))
    monkeypatch.setattr(service, "_load_ora_ti_consiglia", AsyncMock(return_value=[]))
    return (await what_ora_knows(db, "owner"), await overview.money_overview(db, "owner"),
            await service.build_home("owner"), items)


@pytest.mark.asyncio
async def test_historical_unknown_to_unknown_proposal_disappears_without_mutating_facts(monkeypatch):
    import deps
    from financial.durable import needs_your_word, propose
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_redundant_question
    current = await confirmed_service(db)
    pending = await pending_service(db, current, unknowns=["L'importo non compare in questa fonte"])
    assert (await propose(db, pending))["decision"] == "CLARIFY"
    before_facts = await db.financial_facts.find({}, {"_id": 0}).to_list(10)
    before_memory = await db.memories.find({}, {"_id": 0}).to_list(10)
    mail = type("SyntheticMail", (), {"body_for": AsyncMock()})()
    monkeypatch.setattr(deps, "get_gmail_service", lambda: mail)

    assert await needs_your_word(db, "owner") == []
    knowledge, overview, home, items = await question_surfaces(db, monkeypatch)
    assert knowledge["devo_chiederti"] == overview["da_capire"] == []
    assert not [q for q in home.open_questions if q["id"].startswith("ask:")]
    assert not [item for item in items if item.subtype == "financial_confirmation"]
    # A stale name-only affirmative must not promote a now-invisible proposal.
    answer = await resolve_open_question(db, "owner", about=current.what, confirmed=True)
    assert answer["resolved"] is False
    assert await db.financial_facts.find({}, {"_id": 0}).to_list(10) == before_facts
    assert await db.memories.find({}, {"_id": 0}).to_list(10) == before_memory
    mail.body_for.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("known_changes,source_changes,field,shown", [
    ({}, {"due_at": "2033-04-18"}, "due_at", "18/04/2033"),
    ({"due_at": "2032-04-18"}, {"due_at": "2033-04-18"}, "due_at", "18/04/2033"),
    ({"due_at": "2033-04-18T10:30:00+02:00"},
     {"due_at": "2033-04-18T13:30:00+02:00"}, "due_at", "13:30 UTC+02:00"),
    ({}, {"money": Money(amount=12.5, currency="EUR")}, "amount", "€12,50"),
    ({"money": Money(amount=12.5, currency="USD")},
     {"money": Money(amount=12.5, currency="EUR")}, "amount", "€12,50"),
    ({"money": Money(amount=None, currency="USD")},
     {"money": Money(amount=None, currency="EUR")}, "currency", "valuta: EUR"),
    ({}, {"recurrence": "ogni anno"}, "recurrence", "ogni anno"),
    ({}, {"cadence": "one_time", "recurrence": None}, "cadence", "una tantum"),
    ({}, {"kind": "income", "direction": "incoming"}, "kind", "entrata"),
])
async def test_material_financial_proposal_names_the_actual_change_everywhere(
    monkeypatch, known_changes, source_changes, field, shown,
):
    from financial.durable import needs_your_word

    db = AsyncMongoMockClient().financial_v158_material_question
    current = await confirmed_service(db, **known_changes)
    pending = await pending_service(db, current, **source_changes)
    before = await db.memories.find({}, {"_id": 0}).to_list(10)
    ask = (await needs_your_word(db, "owner"))[0]
    assert ask["fact_id"] == pending.id
    assert field in {change["field"] for change in ask["changes"]}
    assert shown in ask["question"]
    assert ask["question"].startswith(f"«{current.what}»")
    assert "è importo non noto?" not in ask["question"]
    assert "Email originale: fonte sintetica" in ask["why_needed"]
    knowledge, overview, home, items = await question_surfaces(db, monkeypatch)
    assert knowledge["devo_chiederti"][0]["domanda"] == ask["question"]
    assert overview["da_capire"][0]["cosa"] == ask["question"]
    question = next(q for q in home.open_questions if q["id"].startswith("ask:"))
    assert question["question"] == ask["question"]
    assert question["why_needed"] == overview["da_capire"][0]["perche"] == ask["why_needed"]
    assert next(item for item in items if item.subtype == "financial_confirmation").title == ask["question"]
    assert await db.memories.find({}, {"_id": 0}).to_list(10) == before


@pytest.mark.asyncio
async def test_real_pending_change_survives_newer_noops_and_only_visible_proposal_is_resolved():
    from financial.durable import needs_your_word, governed_facts
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_selected_question
    current = await confirmed_service(db)
    changed = await pending_service(
        db, current, money=Money(amount=12.5, currency="EUR"), observed_at="2033-04-01T10:00:00Z",
    )
    for index in range(85):
        await pending_service(db, current, source_id=f"repeated_{index}", observed_at="2033-04-02T10:00:00Z")
    for status in ("superseded", "withdrawn"):
        await pending_service(db, current, source_id=f"inactive_{status}", status=status,
                              money=Money(amount=99, currency="EUR"), observed_at="2033-04-03T10:00:00Z")
    asks = await needs_your_word(db, "owner")
    assert [q["fact_id"] for q in asks] == [changed.id]
    assert await needs_your_word(db, "another-owner") == []
    assert (await resolve_open_question(db, "another-owner", about=current.what, confirmed=True))["resolved"] is False
    result = await resolve_open_question(db, "owner", about=current.what, confirmed=True)
    assert result["in_life_model"] is True
    assert (await governed_facts(db, "owner"))[0].money.amount == 12.5
    assert (await db.financial_facts.find_one({"id": changed.id}))["governance_decision"] == "SUPERSEDE"
    assert (await db.financial_facts.find_one({"id": "repeated_0"}))["governance_decision"] == "CLARIFY"
    assert await needs_your_word(db, "owner") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("known_changes,source_changes,amount,currency,due", [
    ({"money": Money(amount=20, currency="USD")},
     {"money": Money(amount=None), "due_at": "2033-04-18",
      "unknowns": ["l'importo", "un altro dato sintetico"]}, 20, "USD", "2033-04-18"),
    ({"money": Money(amount=20, currency="USD"), "due_at": "2033-04-18T13:30:00+02:00"},
     {"money": Money(amount=25), "due_at": None}, 25, "USD", "2033-04-18T13:30:00+02:00"),
])
async def test_confirming_partial_source_keeps_other_confirmed_values_and_both_sources(
    known_changes, source_changes, amount, currency, due,
):
    from financial.durable import governed_facts, needs_your_word
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_partial_confirmation
    current = await confirmed_service(db, **known_changes)
    pending = await pending_service(db, current, **source_changes)
    ask = (await needs_your_word(db, "owner"))[0]
    assert "€" not in ask["question"], "an omitted currency must not invent EUR"
    result = await resolve_open_question(db, "owner", about=current.what, confirmed=True)
    assert result["in_life_model"] is True
    known = (await governed_facts(db, "owner"))[0]
    assert (known.money.amount, known.money.currency, known.due_at) == (amount, currency, due)
    assert set(known.source_refs) == {"mail:synthetic_message", "conversation:synthetic_confirmation"}
    assert "me lo hai confermato tu" in known.provenance[0].how_directly
    assert "l'importo" not in known.unknowns
    if "unknowns" in source_changes:
        assert known.unknowns == ["un altro dato sintetico"]
    original_source = await db.financial_facts.find_one({"id": pending.id})
    assert original_source["money"] == pending.money.model_dump()
    assert original_source["due_at"] == pending.due_at
    assert original_source["provenance"][0]["source"] == "email"
    assert original_source["unknowns"] == pending.unknowns


@pytest.mark.asyncio
@pytest.mark.parametrize("due", [None, "2033-04-18"])
async def test_changed_currency_without_amount_stays_visible_without_converting_known_money(due):
    from financial.durable import needs_your_word
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_currency_without_amount
    current = await confirmed_service(db, money=Money(amount=20, currency="USD"))
    await pending_service(db, current, money=Money(amount=None, currency="EUR"), due_at=due)
    before = await db.memories.find({}, {"_id": 0}).to_list(10)
    ask = (await needs_your_word(db, "owner"))[0]
    assert {"field": "currency", "before": "USD", "after": "EUR"} in ask["changes"]
    assert "valuta: EUR" in ask["question"]
    assert "€20" not in ask["question"]
    assert ask["can_answer"] is False
    assert "Serve l'importo nella nuova valuta" in ask["why_needed"]
    assert (await resolve_open_question(db, "owner", about=current.what, confirmed=True))["resolved"] is False
    assert await db.memories.find({}, {"_id": 0}).to_list(10) == before


@pytest.mark.asyncio
async def test_currency_can_be_confirmed_when_both_amounts_remain_unknown():
    from financial.durable import governed_facts, needs_your_word
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_currency_only_confirmation
    current = await confirmed_service(db, money=Money(amount=None, currency="USD"))
    await pending_service(db, current, money=Money(amount=None, currency="EUR"))
    assert (await needs_your_word(db, "owner"))[0]["can_answer"] is True
    result = await resolve_open_question(db, "owner", about=current.what, confirmed=True)
    assert result["in_life_model"] is True
    known = (await governed_facts(db, "owner"))[0]
    assert known.money.amount is None and known.money.currency == "EUR"


@pytest.mark.asyncio
@pytest.mark.parametrize("known_cadence", ["one_time", "unknown"])
async def test_explicit_source_recurrence_is_visible_even_without_cadence(known_cadence):
    from financial.bridge import _fact_from
    from financial.durable import needs_your_word

    db = AsyncMongoMockClient().financial_v158_recurrence_without_cadence
    current = await confirmed_service(db)
    # Represent historical governed values; the read must not reinterpret or
    # overwrite them merely because a source omits the cadence field.
    await db.memories.update_one({}, {"$set": {
        "value.cadence": known_cadence, "value.recurrence": None,
        "temporal_scope.recurrence": None,
    }})
    incoming = _fact_from("owner", {
        "what_it_is": "commitment", "in_their_words": current.what,
        "recurrence": "ogni anno",
    }, provenance=Provenance(source="email", how_directly="Fonte sintetica"),
        source_refs=["mail:synthetic_recurrence"])
    assert incoming.cadence == "unknown"
    await db.financial_facts.insert_one({**incoming.model_dump(), "governance_decision": "CLARIFY"})
    before = await db.memories.find({}, {"_id": 0}).to_list(10)
    ask = (await needs_your_word(db, "owner"))[0]
    assert "ricorrenza: ogni anno" in ask["question"]
    assert "cadence" not in {change["field"] for change in ask["changes"]}
    assert await db.memories.find({}, {"_id": 0}).to_list(10) == before


@pytest.mark.asyncio
async def test_same_name_proposals_of_different_kinds_do_not_offer_ambiguous_answers(monkeypatch):
    from financial.durable import needs_your_word
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_ambiguous_name
    current = await confirmed_service(db)
    await pending_service(db, current, money=Money(amount=12.5, currency="EUR"))
    await pending_service(db, current, source_id="different_kind", kind="income", direction="incoming")
    before = await db.memories.find({}, {"_id": 0}).to_list(10)
    asks = await needs_your_word(db, "owner")
    assert len(asks) == 2 and all(not ask["can_answer"] for ask in asks)
    _, overview, home, items = await question_surfaces(db, monkeypatch)
    assert all(not ask["posso_rispondere"] for ask in overview["da_capire"])
    assert all(not ask["answers"] for ask in home.open_questions if ask["id"].startswith("ask:"))
    assert all([action.id for action in item.actions] == ["money_ask"]
               for item in items if item.subtype == "financial_confirmation")
    assert (await resolve_open_question(db, "owner", about=current.what, confirmed=True))["resolved"] is False
    assert await db.memories.find({}, {"_id": 0}).to_list(10) == before


@pytest.mark.asyncio
async def test_multiple_current_versions_are_not_arbitrarily_selected_for_confirmation(monkeypatch):
    from financial.durable import needs_your_word
    from financial.knowledge import resolve_open_question

    db = AsyncMongoMockClient().financial_v158_ambiguous_confirmation
    current = await confirmed_service(db, money=Money(amount=20, currency="EUR"))
    other = await db.memories.find_one({}, {"_id": 0})
    other.update(id="other_current", governance_key="synthetic_other_current")
    other["value"]["amount"] = 30
    await db.memories.insert_one(other)
    await pending_service(db, current, money=Money(amount=30, currency="EUR"))
    before = await db.memories.find({}, {"_id": 0}).to_list(10)
    ask = (await needs_your_word(db, "owner"))[0]
    assert ask["can_answer"] is False
    _, overview, home, items = await question_surfaces(db, monkeypatch)
    assert overview["da_capire"][0]["posso_rispondere"] is False
    assert next(q for q in home.open_questions if q["id"].startswith("ask:"))["answers"] == []
    card = next(item for item in items if item.subtype == "financial_confirmation")
    assert [action.id for action in card.actions] == ["money_ask"]
    assert (await resolve_open_question(db, "owner", about=current.what, confirmed=True))["resolved"] is False
    assert await db.memories.find({}, {"_id": 0}).to_list(10) == before

