"""A saved autonomous result stays readable after Home has moved on."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _loop_harness

def test_goal_detail_is_durable_private_and_not_a_cancelled_card(monkeypatch):
    from agent.models import AutonomousGoal
    from agent.service import AgentService

    goal = AutonomousGoal(
        owner_id="alice", objective="Preparare l'impegno di domani",
        desired_outcome="Bozza pronta", prepared_text="Bozza verificata",
        status="active", source_kind="home_event",
    )

    class Goals:
        async def find_one(self, query, projection):
            # Another account may know the handle, but cannot read the goal.
            if query == {"id": goal.id, "owner_id": goal.owner_id}:
                return goal.model_dump()
            return None

    class DB:
        def __getitem__(self, name):
            assert name == "agent_goals"
            return Goals()

    async def progress(owner_id, found):
        return "Bozza pronta da esaminare"

    async def source(owner_id, found):
        return "Impegno nella Home"

    async def no_needs(owner_id, goal_id):
        return []

    async def check():
        service = AgentService(DB())
        monkeypatch.setattr(service, "_progress_of", progress)
        monkeypatch.setattr(service, "_where_it_really_came_from", source)
        monkeypatch.setattr(service.needs, "open_for_goal", no_needs)

        detail = await service.for_detail("alice", goal.id)
        assert detail is not None
        assert detail["prepared_text"] == "Bozza verificata"
        assert detail["source"] == "Impegno nella Home"
        assert detail["state"] == "Bozza pronta da esaminare"
        assert "status" not in detail and "plan" not in detail
        assert await service.for_detail("bob", goal.id) is None

        goal.status = "cancelled"
        assert await service.for_detail("alice", goal.id) is None

    _loop_harness.run(check())
