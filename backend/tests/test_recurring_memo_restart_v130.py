"""Real Mongo process-restart test for the persistent reminder recovery claim.

PHASE2_REAL_MONGO=1 is mandatory. Both children use a UUID-only disposable
Mongo loopback database and no real user, external network, model, or provider.
Child A exits abruptly after persisting the corrected Memory and pending job,
before moving the reminder. B and C are independent Python interpreters.
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
from urllib.parse import urlsplit
from unittest.mock import patch

import pytest

BASE = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"ora_phase2_memo_restart_[0-9a-f]{32}\Z")
OWNER = "phase2-synthetic-owner"


def loopback_uri(value: str):
    p = urlsplit(value)
    host = (p.hostname or "").lower()
    if (p.scheme != "mongodb" or host not in ("localhost", "127.0.0.1", "::1")
            or p.username or p.password or "," in p.netloc
            or p.path not in ("", "/") or p.fragment):
        raise ValueError("Only an unauthenticated loopback MongoDB URL is allowed")
    port = p.port or 27017
    authority = f"[{host}]" if ":" in host else host
    return (f"mongodb://{authority}:{port}/?directConnection=true"
            "&serverSelectionTimeoutMS=2500&connectTimeoutMS=2500", host, port)


def child_env(mongo, name):
    env = {key: os.environ[key] for key in (
        "PATH", "LANG", "LC_ALL", "TMPDIR", "TMP", "TEMP", "SYSTEMROOT"
    ) if key in os.environ}
    env.update({
        "PYTHONPATH": str(BASE), "PYTHONUNBUFFERED": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "PHASE2_REAL_MONGO": "1", "MONGO_URL": mongo, "DB_NAME": name,
        "JWT_SECRET": "synthetic-phase2-only", "DOCUMENT_AI_ENABLED": "0",
        "CALENDAR_PROVIDER_MODE": "fake", "AMBIENT_RUNTIME": "0",
        "OPENAI_API_KEY": "", "GEMINI_API_KEY": "", "EMERGENT_LLM_KEY": "",
    })
    return env


def child(mode, env, payload):
    p = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--phase2-child", mode],
        cwd=str(BASE), env=env, text=True, input=json.dumps(payload),
        capture_output=True, timeout=45, check=False,
    )
    assert p.returncode == 0, f"{mode} failed: {p.stderr[-3500:]}"
    output = json.loads(p.stdout)
    assert output.get("ok") is True and output.get("phase") == mode
    return output


@pytest.mark.skipif(os.environ.get("PHASE2_REAL_MONGO") != "1",
                    reason="explicit loopback Mongo flag required")
def test_recurring_memo_recovery_survives_an_abrupt_python_exit():
    from pymongo import MongoClient

    mongo, _, _ = loopback_uri(os.environ.get("MONGO_URL", ""))
    name = "ora_phase2_memo_restart_" + uuid.uuid4().hex
    marker = uuid.uuid4().hex
    assert PATTERN.fullmatch(name)
    mongo_client = MongoClient(mongo)
    owned = False
    try:
        mongo_client.admin.command("ping")
        assert name not in mongo_client.list_database_names()
        mongo_client[name].phase2_recovery_guard.insert_one({
            "_id": "guard", "nonce": marker,
        })
        owned = True
        env = child_env(mongo, name)
        seed = child("seed", env, {"name": name, "nonce": marker})
        assert seed["pending"] is True and seed["old_active"] is True
        # Child A was hard-exited. This call is a completely new interpreter.
        fixed = child("recover", env, {"name": name, "nonce": marker,
                                        "old_ref": seed["old_ref"],
                                        "new_ref": seed["new_ref"]})
        assert fixed["transferred"] == 1 and fixed["active"] == 1
        again = child("replay", env, {"name": name, "nonce": marker,
                                     "old_ref": seed["old_ref"],
                                     "new_ref": seed["new_ref"]})
        assert again["transferred"] == 0 and again["active"] == 1
        assert again["cross_owner_memos"] == 0
    finally:
        try:
            if owned:
                guard = mongo_client[name].phase2_recovery_guard.find_one({"_id": "guard"})
                assert PATTERN.fullmatch(name) and guard and guard.get("nonce") == marker
                mongo_client.drop_database(name)
        finally:
            mongo_client.close()


def restrict_network(host: str, port: int):
    allowed = {host, "localhost", "127.0.0.1", "::1"}

    def audit(event, args):
        if event == "socket.getaddrinfo":
            value = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
            if value.lower() not in allowed:
                raise RuntimeError("Non-loopback hostname forbidden")
        elif event == "socket.connect":
            address = args[1]
            if (not isinstance(address, tuple) or len(address) < 2
                    or str(address[0]).lower() not in allowed or address[1] != port):
                raise RuntimeError("Only local Mongo port is allowed")
    sys.addaudithook(audit)


async def run_child(mode: str, request: dict):
    if os.environ.get("PHASE2_REAL_MONGO") != "1":
        raise RuntimeError("Explicit Mongo flag required")
    name = str(request.get("name") or "")
    if not PATTERN.fullmatch(name) or name != os.environ.get("DB_NAME"):
        raise RuntimeError("Only isolated generated database is supported")
    mongo, host, port = loopback_uri(os.environ.get("MONGO_URL", ""))
    restrict_network(host, port)
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False

    from motor.motor_asyncio import AsyncIOMotorClient
    from conversation_engine.ai_core.models import MemoryCandidate
    from life_memory.governance import MemoryGovernanceService
    from memos.service import RecurringMemoService
    from memos.recovery import RecurringMemoRecovery

    client = AsyncIOMotorClient(mongo)
    db = client[name]
    await client.admin.command("ping")
    saved = await db.phase2_recovery_guard.find_one({"_id": "guard"})
    assert saved and saved["nonce"] == request.get("nonce")
    if mode == "seed":
        governance = MemoryGovernanceService(db)
        service = RecurringMemoService(db)
        await governance.ensure_indexes()
        await service.ensure_indexes()

        def make(day, *, old=None):
            return MemoryCandidate(
                operation="correct" if old else "propose",
                existing_memory_ref=old,
                summary=f"Compleanno della Persona Sintetica: {day} marzo.",
                kind="birthday", identity_key="birthday:synthetic",
                value={"person": "Persona Sintetica", "month": 3, "day": day},
                confidence=.99, authority="user_stated",
                epistemic_status="asserted", permanence="durable",
                recurrence="annual", sensitivity="normal",
                provenance=["synthetic_input"],
                reason_for_future_utility="Memo di prova autorizzato.",
            )
        first = (await governance.process(
            user_id=OWNER, session_id="s1", reasoning_epoch="e1",
            candidates=[make(13)],
        ))[0]
        assert first.persisted
        schedule = await service.save_annual(
            OWNER, memory_ref=first.memory_id, category="birthday",
            label="Compleanno sintetico", person="Persona Sintetica",
            month=3, day=13, remind_hour_local=0,
        )
        assert schedule["ok"]
        with patch.object(RecurringMemoService, "reconcile_governed_memory",
                          side_effect=RuntimeError("synthetic crash boundary")):
            corrected = (await governance.process(
                user_id=OWNER, session_id="s2", reasoning_epoch="e2",
                candidates=[make(14, old=first.memory_id)],
            ))[0]
        assert corrected.persisted
        original = await db.memories.find_one({"id": first.memory_id})
        old_memo = await db.recurring_memos.find_one({"memory_ref": first.memory_id})
        result = {
            "ok": True, "phase": mode, "old_ref": first.memory_id,
            "new_ref": corrected.memory_id,
            "pending": original["recurring_reconcile"]["status"] == "pending",
            "old_active": old_memo["status"] == "active",
        }
        # Nothing is left in process memory: the next interpreter has only Mongo.
        print(json.dumps(result, separators=(",", ":")), flush=True)
        os._exit(0)

    service = RecurringMemoRecovery(db)
    report = await service.run()
    old = await db.recurring_memos.find_one({"owner_id": OWNER, "memory_ref": request["old_ref"]})
    new = await db.recurring_memos.find_one({"owner_id": OWNER, "memory_ref": request["new_ref"]})
    assert old and old["status"] == "superseded"
    assert new and new["status"] == "active"
    assert new["day"] == 14 and new["remind_hour_local"] == 0
    result = {
        "ok": True, "phase": mode, "transferred": report["transferred"],
        "active": await db.recurring_memos.count_documents({"owner_id": OWNER, "status": "active"}),
        "cross_owner_memos": await db.recurring_memos.count_documents({"owner_id": "other"}),
    }
    client.close()
    return result


if __name__ == "__main__":
    if (len(sys.argv) != 3 or sys.argv[1] != "--phase2-child"
            or sys.argv[2] not in {"seed", "recover", "replay"}):
        raise SystemExit("Only isolated test child modes are allowed")
    with contextlib.redirect_stdout(sys.stderr):
        output = asyncio.run(run_child(sys.argv[2], json.loads(sys.stdin.read())))
    print(json.dumps(output, separators=(",", ":")))
