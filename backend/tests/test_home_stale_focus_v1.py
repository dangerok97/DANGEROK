"""Home does not lead with a guided flow's stale placeholder or a vague ask.

Owner screenshot 24/10/2026: today's focus was "Admin: Conosco un pagamento
entro fine mese", due 12/10, no amount, from an idle guided flow; the ING card
said only "Manca una cosa che sai solo tu." while its need asked a concrete
question about two charges.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from mongomock_motor import AsyncMongoMockClient

from agent.situation_cards import concrete_need
from home.adapters.action_engine_adapter import load_action_engine_items
from home.adapters.decisions_adapter import load_decisions
from home.temporal import TEMPORAL_EXPIRED_STALE, enrich_item_temporal_meta

NOW = datetime.now(timezone.utc)
USER = "stale-focus-owner"


def ago(days):
    return (NOW - timedelta(days=days)).isoformat()


@pytest.mark.asyncio
async def test_guided_flow_placeholder_deadline_is_not_an_overdue_bill():
    db = AsyncMongoMockClient().stale_focus
    await db.users.insert_one({"user_id": USER, "email": "owner@example.org"})
    await db.decisions.insert_one({
        "id": "dec_admin", "user_id": USER, "title": "Admin: Conosco un pagamento entro fine mese",
        "origin": "action_engine", "category": "bill", "status": "open", "deadline": ago(12),
        "created_at": ago(15), "intent": "payment", "intent_confidence": 0.9,
        "metadata": {"action_session_id": "aes_x", "action_engine_kind": "admin"},
    })
    items, _ = await load_decisions(db, USER)
    item = next(i for i in items if i.source_id == "dec_admin")
    meta = enrich_item_temporal_meta(item, NOW)
    assert meta["temporal_state"] == TEMPORAL_EXPIRED_STALE
    assert meta["actionable_now"] is False


@pytest.mark.asyncio
async def test_week_idle_guided_flows_leave_home_recent_ones_stay():
    db = AsyncMongoMockClient().stale_flows
    await db.action_sessions.insert_many([
        {"id": "aes_old", "user_id": USER, "status": "active", "title": "Vecchia", "updated_at": ago(8)},
        {"id": "aes_new", "user_id": USER, "status": "active", "title": "Recente", "updated_at": ago(1)},
    ])
    await db.action_projects.insert_many([
        {"id": "p_old", "user_id": USER, "status": "active", "next_focus_hint": "Pratica vecchia",
         "linked": {"decision_ids": ["d"]}, "updated_at": ago(15)},
        {"id": "p_new", "user_id": USER, "status": "active", "next_focus_hint": "Pratica recente",
         "linked": {"decision_ids": ["d"]}, "updated_at": ago(2)},
    ])
    items, _ = await load_action_engine_items(db, USER)
    ids = {i.source_id for i in items}
    assert ids == {"aes_new", "p_new"}


def test_the_card_shows_the_concrete_question_not_the_placeholder():
    need = SimpleNamespace(what_is_missing="Manca una cosa che sai solo tu.",
                           summary="Riconosci UnipolMove e TIBER OIL tra i tuoi addebiti?")
    assert concrete_need(need) == "Riconosci UnipolMove e TIBER OIL tra i tuoi addebiti?"
    assert concrete_need(SimpleNamespace(what_is_missing="Serve il tuo via libera.", summary="")) == ""
