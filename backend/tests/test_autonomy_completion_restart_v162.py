"""Real Mongo + four exited Python processes, with no Home request to resume.

1. Admission and transient planning failure leave a durable retry.
2. A new worker reads the canonical note and leaves unfinished work.
3. A new worker completes, but the Home outbox write fails once.
4. A new worker recovers Home and proves replay/owner isolation.

The existing CI Mongo service is enough. No other infrastructure, model key,
provider source or device is used. Every process is network-bound to the one
explicit loopback Mongo port and the newly-created, nonce-guarded database.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import pytest

from test_phase2_outcome_restart_v140 import child_environment, loopback_url, restrict_network

BACKEND = Path(__file__).resolve().parents[1]
DATABASE_RE = re.compile(r"ora_autonomy_v162_[0-9a-f]{32}\Z")
PHASES = ("planning_outage", "read", "complete", "recover")


def child_run(phase, env, marker):
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", phase],
        input=json.dumps(marker), text=True, capture_output=True,
        cwd=str(BACKEND), env=env, timeout=90, check=False,
    )
    assert process.returncode == 0, (
        f"v162 synthetic child {phase} failed: {process.stderr[-2000:]}"
    )
    result = json.loads(process.stdout)
    assert result["ok"] is True and result["phase"] == phase
    return result


@pytest.mark.skipif(os.environ.get("PHASE2_REAL_MONGO") != "1",
                    reason="explicit PHASE2_REAL_MONGO=1 and isolated loopback Mongo required")
def test_separate_processes_resume_planning_read_and_home_outbox():
    from pymongo import MongoClient

    url, _, _ = loopback_url(os.environ.get("MONGO_URL", ""))
    database = "ora_autonomy_v162_" + uuid.uuid4().hex
    nonce = uuid.uuid4().hex
    assert DATABASE_RE.fullmatch(database)
    client = MongoClient(url)
    created = False
    try:
        client.admin.command("ping")
        assert database not in client.list_database_names()
        client[database].autonomy_process_guard.insert_one({"_id": "guard", "nonce": nonce})
        created = True
        marker = {"database": database, "nonce": nonce}
        env = child_environment(url, database)

        failed = child_run("planning_outage", env, marker)
        assert failed["planning_attempts"] == 1 and failed["durable_retry"]
        assert failed["read_claims"] == 0
        read = child_run("read", env, marker)
        assert read["planning_attempts"] == 0 and read["read_claims"] == 1
        assert read["unfinished_work_persisted"]
        completed = child_run("complete", env, marker)
        assert completed["state"] == "completed" and completed["home_pending"] == 1
        recovered = child_run("recover", env, marker)
        assert recovered["state"] == "completed"
        assert recovered["home_delivered"] and recovered["replay_idempotent"]
        assert recovered["owner_isolation"] and recovered["world_effects"] == 0
    finally:
        try:
            if created:
                assert DATABASE_RE.fullmatch(database)
                guard = client[database].autonomy_process_guard.find_one({"_id": "guard"})
                assert guard and guard.get("nonce") == nonce, "synthetic cleanup ownership changed"
                client.drop_database(database)
        finally:
            client.close()


@pytest.mark.parametrize("url", [
    "mongodb://example.invalid:27017", "mongodb://" + "synthetic-user:synthetic-password@127.0.0.1:27017",
    "mongodb://127.0.0.1:27017/existing_database", "mongodb+srv://example.invalid",
])
def test_restart_gate_rejects_nonisolated_mongo(url):
    with pytest.raises(ValueError):
        loopback_url(url)


def test_process_environment_does_not_inherit_credentials_or_user_database(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-marker-never-forwarded")
    monkeypatch.setenv("UNRELATED_PRIVATE_CONFIGURATION", "synthetic-marker-never-forwarded")
    monkeypatch.setenv("DB_NAME", "not-the-test-database")
    env = child_environment("mongodb://127.0.0.1:27017", "ora_autonomy_v162_" + "0" * 32)
    assert env["GEMINI_API_KEY"] == ""
    assert env["DB_NAME"] == "ora_autonomy_v162_" + "0" * 32
    assert "UNRELATED_PRIVATE_CONFIGURATION" not in env
    assert env["PYTHON_DOTENV_DISABLED"] == "1"


async def child(phase, payload):
    if os.environ.get("PHASE2_REAL_MONGO") != "1":
        raise RuntimeError("explicit_isolated_process_gate_required")
    database = str(payload.get("database") or "")
    if not DATABASE_RE.fullmatch(database) or database != os.environ.get("DB_NAME"):
        raise RuntimeError("invalid_synthetic_database")
    url, host, port = loopback_url(os.environ.get("MONGO_URL", ""))
    restrict_network(host, port)
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False

    from motor.motor_asyncio import AsyncIOMotorClient
    from scripts import autonomy_completion_eval_v162 as gate
    from agent.service import AgentService

    client = AsyncIOMotorClient(url)
    db = client[database]
    try:
        await client.admin.command("ping")
        guard = await db.autonomy_process_guard.find_one({"_id": "guard"})
        if not guard or guard.get("nonce") != payload.get("nonce"):
            raise RuntimeError("synthetic_database_ownership_mismatch")

        if phase == "planning_outage":
            with gate.isolated_engine(db, scenario="planning_outage") as probe:
                await gate.seed_case(db, "planning_outage")
                goal_id = await gate.admit(db, "planning_outage")
                await gate.fire_due(db, goal_id, probe)
                goal = await AgentService(db).repo.get_goal(gate.OWNER, goal_id)
            assert goal.status == "active" and goal.next_run_at and goal.planning_attempts == 1
            assert not goal.prepared_text and not goal.requires_user_input
            assert await db.agent_updates.count_documents({}) == 0
            assert await db.agent_evidence.count_documents({}) == 0
            await db.autonomy_process_guard.insert_one({"_id": "goal", "id": goal_id})
            return {"ok": True, "phase": phase, "planning_attempts": 1,
                    "durable_retry": True, "read_claims": 0}

        saved = await db.autonomy_process_guard.find_one({"_id": "goal"})
        assert saved and saved.get("id")
        goal_id = saved["id"]
        if phase == "read":
            with gate.isolated_engine(db) as probe:
                await gate.first_read(db, goal_id, probe)
                goal = await AgentService(db).repo.get_goal(gate.OWNER, goal_id)
            assert goal.planning_attempts == 0 and goal.next_run_at
            return {"ok": True, "phase": phase, "planning_attempts": 0,
                    "read_claims": 1, "unfinished_work_persisted": True}

        if phase == "complete":
            with gate.isolated_engine(db, scenario="home_write_retry") as probe:
                await gate.fire_due(db, goal_id, probe)
                goal = await AgentService(db).repo.get_goal(gate.OWNER, goal_id)
                assert probe.faults == ["home_write_failed_once"]
            pending = await db.agent_updates.count_documents({"owner_id": gate.OWNER, "home_pending": True})
            assert goal.status == "completed" and goal.prepared_text and pending == 1
            return {"ok": True, "phase": phase, "state": goal.status, "home_pending": pending}

        if phase != "recover":
            raise RuntimeError("unknown_synthetic_process_phase")
        with gate.isolated_engine(db) as probe:
            result = await gate.verify_result(db, goal_id, probe)
            assert not probe.steps and not probe.model_attempts
            assert not probe.push_attempts and not probe.blocked_effects and not probe.network.blocked
        effects = await db.agent_action_attempts.count_documents({})
        assert effects == 0 and await db.action_intents.count_documents({}) == 0
        return {"ok": True, "phase": phase, "state": result["state"],
                "home_delivered": result["home_delivered"],
                "replay_idempotent": result["replay_idempotent"],
                "owner_isolation": result["owner_isolation"], "world_effects": effects}
    finally:
        client.close()
        import mongo
        mongo.close_all()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--child" or sys.argv[2] not in PHASES:
        raise SystemExit("v162 guarded synthetic process evaluation only")
    payload = json.loads(sys.stdin.read())
    with contextlib.redirect_stdout(sys.stderr):
        result = asyncio.run(child(sys.argv[2], payload))
    print(json.dumps(result, separators=(",", ":")))
