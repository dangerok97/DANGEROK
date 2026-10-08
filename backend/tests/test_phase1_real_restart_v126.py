"""Optional real Mongo/process-boundary gate; the model remains scripted.

Run only with PHASE1_REAL_MONGO=1 and a loopback MONGO_URL. The test creates
its own UUID database, then starts and exits two independent Python processes.
Only that newly-created, ownership-marked database may be deleted afterwards.
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
from urllib.parse import urlsplit
import uuid

import pytest


BACKEND = Path(__file__).resolve().parents[1]
DATABASE_PATTERN = re.compile(r"ora_phase1_restart_[0-9a-f]{32}\Z")
OWNER = "phase1-synthetic-owner"
MESSAGE_ID = "phase1-restart-birthday"
MESSAGE = "Ricordami ogni anno il compleanno della Persona Sintetica."


def _loopback_mongo_url(value: str) -> tuple[str, str, int]:
    """Accept one unauthenticated local endpoint; discard caller URI options."""
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "mongodb"
        or host not in {"127.0.0.1", "localhost", "::1"}
        or "," in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.fragment
    ):
        raise ValueError("Phase 1 restart test requires an unauthenticated loopback Mongo endpoint")
    port = parsed.port or 27017
    authority = f"[{host}]" if ":" in host else host
    url = (
        f"mongodb://{authority}:{port}/?directConnection=true"
        "&serverSelectionTimeoutMS=2000&connectTimeoutMS=2000&socketTimeoutMS=3000"
    )
    return url, host, port


def _child_environment(mongo_url: str, database_name: str) -> dict[str, str]:
    # Do not copy the caller's service credentials or model configuration.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP", "SYSTEMROOT") if key in os.environ}
    env.update({
        "PYTHONPATH": str(BACKEND),
        "PYTHONUNBUFFERED": "1",
        "PYTHON_DOTENV_DISABLED": "1",
        "PHASE1_REAL_MONGO": "1",
        "MONGO_URL": mongo_url,
        "DB_NAME": database_name,
        "JWT_SECRET": "phase1-restart-synthetic-test-secret-only",
        "CALENDAR_PROVIDER_MODE": "fake",
        "DOCUMENT_AI_ENABLED": "0",
        "AI_CORE_TRACE": "0",
        "AMBIENT_RUNTIME_ENABLED": "0",
        "OPENAI_API_KEY": "",
        "EMERGENT_LLM_KEY": "",
        "GEMINI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "TZ": "UTC",
    })
    return env


def _run_child(mode: str, env: dict[str, str], payload: dict) -> dict:
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--phase1-child", mode],
        cwd=str(BACKEND), env=env, input=json.dumps(payload),
        text=True, capture_output=True, timeout=45, check=False,
    )
    assert completed.returncode == 0, f"{mode} child failed: {completed.stderr[-6000:]}"
    result = json.loads(completed.stdout)
    assert result.get("ok") is True and result.get("phase") == mode
    return result


@pytest.mark.skipif(os.environ.get("PHASE1_REAL_MONGO") != "1", reason="requires explicit PHASE1_REAL_MONGO=1 and loopback MongoDB")
def test_completed_message_replays_after_real_python_process_exit():
    from pymongo import MongoClient

    mongo_url, _, _ = _loopback_mongo_url(os.environ.get("MONGO_URL", ""))
    database_name = "ora_phase1_restart_" + uuid.uuid4().hex
    guard = uuid.uuid4().hex
    assert DATABASE_PATTERN.fullmatch(database_name)
    client = MongoClient(mongo_url)
    created = False
    try:
        # An explicitly requested gate fails if Mongo is unavailable; it does
        # not silently turn into a mock or a passing skip.
        client.admin.command("ping")
        assert database_name not in client.list_database_names()
        client[database_name].phase1_restart_control.insert_one({"_id": "guard", "nonce": guard})
        created = True
        env = _child_environment(mongo_url, database_name)
        payload = {"database_name": database_name, "guard": guard}
        written = _run_child("write", env, payload)
        assert written["ai_calls"] == 2 and written["memo_count"] == 1
        # subprocess.run has waited for the first interpreter to exit here.
        # Only MongoDB carries the session and original result into process B.
        replayed = _run_child("replay", env, {**payload, "session_id": written["session_id"]})
        assert replayed["session_id"] == written["session_id"]
        assert replayed["ai_calls"] == 0 and replayed["memo_count"] == 1
        assert replayed["owner_isolation"] is True
    finally:
        try:
            if created:
                # Cleanup can only target the generated name with this test's
                # still-matching ownership marker, never the configured DB_NAME.
                assert DATABASE_PATTERN.fullmatch(database_name)
                marker = client[database_name].phase1_restart_control.find_one({"_id": "guard"})
                assert marker and marker.get("nonce") == guard, "isolated database ownership marker changed; cleanup refused"
                client.drop_database(database_name)
        finally:
            client.close()


def _restrict_child_network(host: str, port: int) -> None:
    """A mistaken provider lookup cannot leave this local integration test."""
    allowed_hosts = {host, "127.0.0.1", "localhost", "::1"}

    def audit(event, args):
        if event == "socket.getaddrinfo":
            address = args[0].decode() if isinstance(args[0], bytes) else str(args[0])
            if address.lower() not in allowed_hosts:
                raise RuntimeError("external DNS forbidden in synthetic restart test")
        elif event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or len(address) < 2 or str(address[0]).lower() not in allowed_hosts or address[1] != port:
                raise RuntimeError("only the selected loopback Mongo port is allowed")

    sys.addaudithook(audit)


async def _child(mode: str, payload: dict) -> dict:
    if os.environ.get("PHASE1_REAL_MONGO") != "1":
        raise RuntimeError("explicit real Mongo test flag required")
    database_name = str(payload.get("database_name") or "")
    if not DATABASE_PATTERN.fullmatch(database_name) or database_name != os.environ.get("DB_NAME"):
        raise RuntimeError("only the test-generated isolated database is allowed")
    mongo_url, host, port = _loopback_mongo_url(os.environ.get("MONGO_URL", ""))
    _restrict_child_network(host, port)

    # Even an old python-dotenv version must not load a developer's .env.
    import dotenv
    dotenv.load_dotenv = lambda *args, **kwargs: False

    from motor.motor_asyncio import AsyncIOMotorClient
    from conversation_engine.ai_core.orchestrator import AICoreOrchestrator
    from conversation_engine.models import ConversationSession
    from conversation_engine.repository import ConversationRepository
    from memos.service import RecurringMemoService

    client = AsyncIOMotorClient(mongo_url)
    db = client[database_name]
    calls = 0
    try:
        await client.admin.command("ping")
        marker = await db.phase1_restart_control.find_one({"_id": "guard"})
        assert marker and marker.get("nonce") == payload.get("guard")

        if mode == "write":
            repo = ConversationRepository(db)
            await repo.ensure_indexes()
            await RecurringMemoService(db).ensure_indexes()
            sess = ConversationSession(
                user_id=OWNER, engine_version="ai-core-1.0",
                meta={"ui_mode": "ai_core", "ai_core": {}},
            )
            await repo.insert(sess)
            await db.memories.insert_one({
                "id": "mem_phase1_synthetic_birthday", "user_id": OWNER,
                "status": "active", "kind": "birthday",
                "statement": "Il 13 marzo è il compleanno della Persona Sintetica.",
                "value": {"person": "Persona Sintetica", "month": 3, "day": 13},
            })

            async def decide(system, context):
                nonlocal calls
                calls += 1
                if calls == 1:
                    return {
                        "response_mode": "tool", "reasoning_status": "needs_tool",
                        "tool_call": {
                            "capability": "save_recurring_memo",
                            "arguments": {
                                "memory_ref": "mem_phase1_synthetic_birthday", "category": "birthday",
                                "label": "Compleanno della Persona Sintetica", "person": "Persona Sintetica",
                                "month": 3, "day": 13, "timezone": "Europe/Rome", "remind_hour_local": 9,
                            },
                        },
                        "situation_update": {"operation": "none"},
                    }
                return {
                    "response_mode": "answer", "reasoning_status": "enough_information",
                    "message_to_user": "Te lo ricorderò ogni 13 marzo.",
                    "situation_update": {"operation": "none"},
                }

            response = await AICoreOrchestrator(db, decision_fn=decide).message(
                OWNER, sess.id, text=MESSAGE, client_message_id=MESSAGE_ID,
            )
            assert response["ok"] and not response["error"] and calls == 2
            assert response["tool_calls"] == 1
            memo = await db.recurring_memos.find_one({"owner_id": OWNER})
            assert memo is not None and await db.recurring_memos.count_documents({}) == 1
            stored = await db.conversation_sessions.find_one({"id": sess.id, "user_id": OWNER})
            assert stored is not None and len(stored["history"]) == 2
            await db.phase1_restart_control.insert_one({
                "_id": "baseline", "session_id": sess.id,
                "response": response, "session": stored, "memo": memo,
            })
            return {"ok": True, "phase": mode, "session_id": sess.id, "ai_calls": calls, "memo_count": 1}

        if mode != "replay":
            raise RuntimeError("unknown isolated test phase")
        baseline = await db.phase1_restart_control.find_one({"_id": "baseline"})
        assert baseline is not None and baseline["session_id"] == payload.get("session_id")
        session_id = baseline["session_id"]

        async def must_not_reason(system, context):
            nonlocal calls
            calls += 1
            raise AssertionError("persisted message retry reached the model after process restart")

        orch = AICoreOrchestrator(db, decision_fn=must_not_reason)
        foreign = await orch.message("phase1-other-synthetic-owner", session_id, text=MESSAGE, client_message_id=MESSAGE_ID)
        assert foreign == {"ok": False, "error": "not_found"}
        assert await orch.repo.get_by_resume_token("phase1-other-synthetic-owner", baseline["session"]["resume_token"]) is None
        replay = await orch.message(OWNER, session_id, text=MESSAGE, client_message_id=MESSAGE_ID)
        assert calls == 0 and replay == baseline["response"]
        assert await db.conversation_sessions.find_one({"id": session_id, "user_id": OWNER}) == baseline["session"]
        assert await db.recurring_memos.count_documents({}) == 1
        assert await db.recurring_memos.find_one({"owner_id": OWNER}) == baseline["memo"]
        return {
            "ok": True, "phase": mode, "session_id": session_id,
            "ai_calls": calls, "memo_count": 1, "owner_isolation": True,
        }
    finally:
        client.close()
        import mongo
        mongo.close_all()


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--phase1-child" or sys.argv[2] not in {"write", "replay"}:
        raise SystemExit("This helper only runs an explicitly authorized isolated test phase")
    supplied = json.loads(sys.stdin.read())
    # Keep the subprocess protocol to one small JSON object, including when
    # imported application modules write diagnostic output.
    with contextlib.redirect_stdout(sys.stderr):
        result = asyncio.run(_child(sys.argv[2], supplied))
    print(json.dumps(result, separators=(",", ":")))
