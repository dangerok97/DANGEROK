"""v140: actual Python process restart and persisted autonomous completion.

Only an explicitly marked, newly-created loopback Mongo database is used.
All material is synthetic; children have no LLM credentials and forbid
network traffic except the isolated local Mongo endpoint. No user data.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

import pytest

BACKEND = Path(__file__).resolve().parents[1]
DATABASE_RE = re.compile(r"ora_phase2_outcome_v140_[0-9a-f]{32}\Z")
OWNER = "ora-synthetic-outcome-owner-v140"


def loopback_url(original):
    parsed = urlsplit(original)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "mongodb" or host not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username or parsed.password or "," in parsed.netloc
            or parsed.path not in ("", "/") or parsed.fragment):
        raise ValueError("v140 restart requires one unauthenticated local Mongo")
    port = parsed.port or 27017
    authority = "[" + host + "]" if ":" in host else host
    return (
        f"mongodb://{authority}:{port}/?directConnection=true"
        "&serverSelectionTimeoutMS=2000&connectTimeoutMS=2000&socketTimeoutMS=3000",
        host, port,
    )


def child_environment(mongo_url, database):
    env = {k: os.environ[k] for k in (
        "PATH", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT",
    ) if k in os.environ}
    env.update({
        "PYTHONPATH": str(BACKEND), "PYTHONUNBUFFERED": "1",
        "PYTHON_DOTENV_DISABLED": "1", "PHASE2_REAL_MONGO": "1",
        "MONGO_URL": mongo_url, "DB_NAME": database,
        "JWT_SECRET": "synthetic-outcome-only-do-not-use-elsewhere",
        "CALENDAR_PROVIDER_MODE": "fake", "AMBIENT_RUNTIME": "0",
        "DOCUMENT_AI_ENABLED": "0", "RESEARCH_ENABLED": "0",
        "OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "GEMINI2_API_KEY": "",
        "GROQ_API_KEY": "", "MISTRAL_API_KEY": "", "EMERGENT_LLM_KEY": "",
        "TZ": "UTC",
    })
    return env


def child_run(phase, env, marker):
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--child", phase],
        input=json.dumps(marker), text=True, capture_output=True,
        cwd=str(BACKEND), env=env, timeout=90, check=False,
    )
    assert proc.returncode == 0, (
        f"v140 child {phase} failed: {proc.stderr[-3500:]} "
        f"stdout={proc.stdout[-500:]}"
    )
    result = json.loads(proc.stdout)
    assert result["ok"] is True and result["phase"] == phase
    return result


@pytest.mark.skipif(os.environ.get("PHASE2_REAL_MONGO") != "1",
                    reason="requires PHASE2_REAL_MONGO=1 and loopback Mongo")
def test_restarted_worker_closes_one_real_read_based_autonomous_goal():
    from pymongo import MongoClient

    mongo_url, _, _ = loopback_url(os.environ.get("MONGO_URL", ""))
    database = "ora_phase2_outcome_v140_" + uuid.uuid4().hex
    nonce = uuid.uuid4().hex
    assert DATABASE_RE.fullmatch(database)
    client = MongoClient(mongo_url)
    created = False
    try:
        client.admin.command("ping")
        assert database not in client.list_database_names()
        client[database].phase2_gate.insert_one({"_id": "guard", "nonce": nonce})
        created = True
        payload = {"database": database, "nonce": nonce}
        env = child_environment(mongo_url, database)

        written = child_run("read", env, payload)
        assert written["goal_created"] and written["read_claims"] == 1
        # Python process #1 has exited: no in-memory plan or worker survives.
        resumed = child_run("resume", env, payload)
        assert resumed["result"] == "completed" and resumed["read_claims"] == 1
        assert resumed["draft_exists"] and resumed["world_effects"] == 0
        assert resumed["ambient_claimed"] >= 1
        # Process #3 proves replay after completion does not repeat anything.
        replayed = child_run("replay", env, payload)
        assert replayed["state"] == "completed"
        assert replayed["read_claims"] == 1
        assert replayed["owner_isolation"] is True
        assert replayed["world_effects"] == 0
    finally:
        try:
            if created:
                assert DATABASE_RE.fullmatch(database)
                guard = client[database].phase2_gate.find_one({"_id": "guard"})
                assert guard and guard.get("nonce") == nonce, "cleanup ownership changed"
                client.drop_database(database)
        finally:
            client.close()


def restrict_network(host, port):
    allowed_hosts = {host, "127.0.0.1", "localhost", "::1"}

    def audit(event, args):
        if event == "socket.getaddrinfo":
            name = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
            if name.lower() not in allowed_hosts:
                raise RuntimeError("external_dns_forbidden")
        elif event == "socket.connect":
            address = args[1]
            if (not isinstance(address, tuple) or len(address) < 2
                    or str(address[0]).lower() not in allowed_hosts
                    or address[1] != port):
                raise RuntimeError("external_transport_forbidden")
    sys.addaudithook(audit)


async def child(phase, payload):
    if os.environ.get("PHASE2_REAL_MONGO") != "1":
        raise RuntimeError("explicit_isolated_gate_required")
    database = str(payload.get("database") or "")
    if not DATABASE_RE.fullmatch(database) or database != os.environ.get("DB_NAME"):
        raise RuntimeError("invalid_test_database")
    url, host, port = loopback_url(os.environ.get("MONGO_URL", ""))
    restrict_network(host, port)

    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False

    from motor.motor_asyncio import AsyncIOMotorClient
    from agent.service import AgentService
    from scripts.phase2_goal_outcome_eval_v140 import (
        seed, admission, first_read, isolated_engine, OWNER,
    )

    client = AsyncIOMotorClient(url)
    db = client[database]
    try:
        await client.admin.command("ping")
        guard = await db.phase2_gate.find_one({"_id": "guard"})
        if not guard or guard.get("nonce") != payload.get("nonce"):
            raise RuntimeError("isolated_database_ownership_mismatch")

        if phase == "read":
            with isolated_engine("scripted"):
                await seed(db)
                goal_id = await admission(db)
                first = await first_read(db, goal_id)
            await db.phase2_gate.insert_one({"_id": "goal", "id": goal_id})
            pending = await db.ambient_wakes.count_documents({
                "owner_id": OWNER, "status": "pending",
                "source_ref": "goal:" + goal_id,
            })
            assert pending >= 1 and first["read_evidence"] == 1
            return {"ok": True, "phase": phase, "goal_created": True,
                    "read_claims": 1, "pending_wakes": pending}

        row = await db.phase2_gate.find_one({"_id": "goal"})
        assert row and row.get("id")
        goal_id = row["id"]
        source_query = {"owner_id": OWNER, "goal_id": goal_id}
        if phase == "resume":
            from ambient.runtime import tick
            # Advance the *synthetic* checkpoint, not a system clock or a
            # production schedule. This mimics the real 2h continuation due.
            due = datetime.now(timezone.utc) - timedelta(minutes=1)
            await db.agent_goals.update_one(
                {"owner_id": OWNER, "id": goal_id},
                {"$set": {"next_run_at": due.isoformat()}},
            )
            await db.ambient_wakes.update_many(
                {"owner_id": OWNER, "source_ref": "goal:" + goal_id, "status": "pending"},
                {"$set": {"scheduled_for": due.isoformat()}},
            )
            with isolated_engine("scripted"):
                outcome = await tick(db, now=datetime.now(timezone.utc), limit=4)
            saved = await db.agent_goals.find_one({"owner_id": OWNER, "id": goal_id})
            plan = await db.agent_plans.find_one(source_query)
            reads = await db.agent_evidence.count_documents({
                **source_query, "provenance.capability": "information.read",
            })
            assert saved and saved["status"] == "completed"
            assert saved.get("prepared_text") and saved.get("prepared_sources")
            assert plan and plan.get("status") == "completed"
            assert reads == 1
            assert all(step["status"] in ("succeeded", "skipped") for step in plan["steps"])
            assert outcome["claimed"] >= 1
            assert await db.agent_action_attempts.count_documents({"owner_id": OWNER}) == 0
            return {"ok": True, "phase": phase, "result": saved["status"],
                    "ambient_claimed": outcome["claimed"],
                    "read_claims": reads, "draft_exists": True, "world_effects": 0}

        if phase != "replay":
            raise RuntimeError("unknown_child_phase")
        with isolated_engine("scripted"):
            result = await AgentService(db).advance(OWNER, goal_id, worker_id="ambient:v140-replay")
            foreign = await AgentService(db).advance("another-synthetic-user", goal_id)
        reads = await db.agent_evidence.count_documents({
            **source_query, "provenance.capability": "information.read",
        })
        effects = await db.agent_action_attempts.count_documents({"owner_id": OWNER})
        assert result["state"] == "completed" and foreign["reason"] == "unknown_goal"
        assert reads == 1 and effects == 0
        return {"ok": True, "phase": phase, "state": result["state"],
                "read_claims": reads, "owner_isolation": True,
                "world_effects": effects}
    finally:
        client.close()
        import mongo
        mongo.close_all()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--child" or sys.argv[2] not in (
        "read", "resume", "replay",
    ):
        raise SystemExit("v140 synthetic process gate only")
    data = json.loads(sys.stdin.read())
    with contextlib.redirect_stdout(sys.stderr):
        response = asyncio.run(child(sys.argv[2], data))
    print(json.dumps(response, separators=(",", ":")))
