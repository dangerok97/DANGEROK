"""
Siri, through the Shortcuts app.

A web app on iPhone cannot register with Siri. What can: a shortcut the person
builds once in Comandi Rapidi — dictate, send to ORA, show the answer — which
Siri runs by name. The shortcut has no way to sign in, so it carries a key.

    THE KEY OPENS ONE DOOR.

It is not a session. It reaches exactly one endpoint, which runs exactly the
turn the app's own chat runs (the same AI Core, the same confirmations — a
key cannot approve anything the chat would ask about), and it is revoked by
generating a new one or turning Siri off. Only its digest is stored; the key
itself is shown once, to the signed-in person.

Answers are shaped to be heard. A turn that outlasts what Siri waits for keeps
running, and the answer arrives as a notification instead of being lost.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

KEY_PREFIX = "ora_siri_"
COLLECTION = "siri_keys"
# A follow-up ("sì", "alle sei") within this window continues the same thread.
SESSION_REUSE_MINUTES = 10
# What Siri is asked to wait. Longer turns finish in the background.
WAIT_SECONDS = 25.0
RATE_PER_MINUTE = 12
MAX_TEXT = 1000

_recent: Dict[str, list] = {}
_background: set = set()

UNKNOWN_KEY = (
    "Non riconosco questa chiave. Apri ORA, vai in Profilo, Connessioni e "
    "servizi, Siri, e copia la chiave nel comando rapido."
)
TOO_MANY = "Mi stai scrivendo troppo in fretta. Riprova tra un minuto."
EMPTY = "Non ho sentito niente. Riprova dicendo cosa ti serve."
STILL_WORKING = (
    "Ci sto lavorando. Ti mando una notifica appena ho la risposta."
)
FAILED = "Adesso non riesco a rispondere. Riprova tra poco o apri ORA."
NEEDS_APP = " Per finire mi serve l'app: aprila e trovi questa conversazione."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def looks_like_key(raw: str) -> bool:
    return bool(re.fullmatch(KEY_PREFIX + r"[A-Za-z0-9_-]{32,64}", raw or ""))


async def _indexes(db) -> None:
    try:
        await db[COLLECTION].create_index("digest", unique=True)
        await db[COLLECTION].create_index("user_id", unique=True)
    except Exception:
        logger.debug("siri key indexes deferred", exc_info=True)


async def issue(db, user_id: str) -> Dict[str, Any]:
    """A new key; any previous key for this account stops working now."""
    await _indexes(db)
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    now = _now().isoformat()
    await db[COLLECTION].delete_many({"user_id": user_id})
    await db[COLLECTION].insert_one({
        "user_id": user_id,
        "digest": digest(raw),
        "created_at": now,
        "last_used_at": None,
        "last_session_id": None,
        "last_turn_at": None,
    })
    return {"active": True, "key": raw, "created_at": now, "last_used_at": None}


async def status(db, user_id: str) -> Dict[str, Any]:
    doc = await db[COLLECTION].find_one(
        {"user_id": user_id}, {"_id": 0, "created_at": 1, "last_used_at": 1},
    )
    if not doc:
        return {"active": False, "created_at": None, "last_used_at": None}
    return {
        "active": True,
        "created_at": doc.get("created_at"),
        "last_used_at": doc.get("last_used_at"),
    }


async def revoke(db, user_id: str) -> Dict[str, Any]:
    await db[COLLECTION].delete_many({"user_id": user_id})
    return {"active": False, "created_at": None, "last_used_at": None}


async def key_record(db, raw: str) -> Optional[dict]:
    if not looks_like_key(raw):
        return None
    doc = await db[COLLECTION].find_one({"digest": digest(raw)}, {"_id": 0})
    if not doc:
        return None
    user = await db.users.find_one({"user_id": doc.get("user_id")}, {"_id": 0, "user_id": 1})
    return doc if user else None


def allow(user_id: str, *, now: Optional[float] = None) -> bool:
    now = time.monotonic() if now is None else now
    hits = [t for t in _recent.get(user_id, []) if now - t < 60]
    if len(hits) >= RATE_PER_MINUTE:
        _recent[user_id] = hits
        return False
    hits.append(now)
    _recent[user_id] = hits
    return True


def spoken(answer: Dict[str, Any]) -> str:
    """What Siri reads aloud: the same answer, without what only a screen needs."""
    text = str(answer.get("ora_text") or answer.get("question") or "").strip()
    if not text:
        return ""
    try:
        from telephone.spoken import for_the_ear

        text = for_the_ear(text) or text
    except Exception:
        logger.debug("for_the_ear unavailable", exc_info=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:1200]


def _needs_device(answer: Dict[str, Any]) -> bool:
    actions = list(answer.get("client_actions") or [])
    actions += list((answer.get("pending_turn") or {}).get("client_actions") or [])
    return any(isinstance(a, dict) and a.get("type") for a in actions)


def _wants_location(answer: Dict[str, Any]) -> bool:
    actions = list(answer.get("client_actions") or [])
    actions += list((answer.get("pending_turn") or {}).get("client_actions") or [])
    return any(
        isinstance(a, dict) and a.get("type") == "request_foreground_location"
        for a in actions
    )


class SiriTurns:
    def __init__(self, db, *, core=None, location=None, provider=None):
        self.db = db
        self._core = core
        self._location = location
        self._provider = provider

    def core(self):
        if self._core is None:
            from conversation_engine.ai_core.orchestrator import AICoreOrchestrator

            self._core = AICoreOrchestrator(self.db)
        return self._core

    def location(self):
        if self._location is None:
            from location.service import LocationService

            self._location = LocationService(self.db)
        return self._location

    def provider(self):
        if self._provider is None:
            from delivery.provider import get_provider

            self._provider = get_provider()
        return self._provider

    async def _post_location(self, user_id: str, where: Optional[dict], session_id=None) -> bool:
        if not where:
            return False
        try:
            res = await self.location().ingest_foreground_signal(
                user_id,
                latitude=where["latitude"],
                longitude=where["longitude"],
                accuracy_meters=where.get("accuracy"),
                session_id=session_id,
                reverse_geocode=True,
            )
            return bool(res.get("ok"))
        except Exception:
            logger.debug("siri location soft-fail", exc_info=True)
            return False

    async def _turn(self, record: dict, text: str, where: Optional[dict]) -> Dict[str, Any]:
        user_id = record["user_id"]
        core = self.core()
        located = await self._post_location(user_id, where)
        answer: Optional[Dict[str, Any]] = None
        session_id = record.get("last_session_id")
        last = record.get("last_turn_at")
        recent = False
        if session_id and last:
            try:
                recent = _now() - datetime.fromisoformat(str(last)) < timedelta(
                    minutes=SESSION_REUSE_MINUTES,
                )
            except ValueError:
                recent = False
        if session_id and recent:
            answer = await core.message(
                user_id, session_id, text=text, response_channel="voice",
                client_message_id="siri_" + uuid.uuid4().hex[:24],
            )
            if answer.get("error") in ("not_found", "session_closed"):
                answer = None
        if answer is None:
            answer = await core.start(
                user_id, text=text, origin="voice", entry_point="siri",
                response_channel="voice",
            )
        if answer.get("ok") and answer.get("session_id") and _wants_location(answer) and located:
            # The fix the shortcut sent is fresher than anything ORA could ask
            # for; give it to this turn and let the reasoning continue.
            await self._post_location(user_id, where, answer["session_id"])
            resumed = await core.client_resume(
                user_id, answer["session_id"], completed=["request_foreground_location"],
            )
            if resumed.get("ok"):
                answer = {**resumed, "session_id": answer["session_id"]}
        if answer.get("ok") and answer.get("session_id"):
            await self.db[COLLECTION].update_one(
                {"user_id": user_id},
                {"$set": {
                    "last_session_id": answer["session_id"],
                    "last_turn_at": _now().isoformat(),
                }},
            )
        return answer

    def _say(self, answer: Dict[str, Any]) -> str:
        if not answer.get("ok"):
            return FAILED
        said = spoken(answer)
        if _needs_device(answer):
            said = (said + NEEDS_APP).strip()
        return said or "Fatto. Ti aggiorno io se cambia qualcosa."

    async def _deliver_late(self, user_id: str, task: "asyncio.Task") -> None:
        try:
            answer = task.result()
        except Exception:
            logger.exception("siri late turn failed")
            return
        if not answer.get("ok"):
            return
        session_id = answer.get("session_id") or ""
        try:
            await self.provider().send(
                owner_id=user_id,
                plan_id=f"dlv_siri{int(time.time())}",
                title="ORA",
                body=self._say(answer)[:300],
                deep_link=f"/ora/{session_id}" if session_id else "/",
                public_title="ORA",
                # The lock screen shows only this; the answer is one tap away.
                public_body="La risposta a quello che hai chiesto con Siri è pronta.",
            )
        except Exception:
            logger.exception("siri late delivery failed")

    async def handle(self, record: dict, text: str, where: Optional[dict] = None,
                     *, wait: float = WAIT_SECONDS) -> Dict[str, Any]:
        user_id = record["user_id"]
        await self.db[COLLECTION].update_one(
            {"user_id": user_id}, {"$set": {"last_used_at": _now().isoformat()}},
        )
        text = (text or "").strip()[:MAX_TEXT]
        if not text:
            return {"ok": False, "reply": EMPTY}
        if not allow(user_id):
            return {"ok": False, "reply": TOO_MANY}
        task = asyncio.ensure_future(self._turn(record, text, where))
        try:
            answer = await asyncio.wait_for(asyncio.shield(task), timeout=wait)
        except asyncio.TimeoutError:
            _background.add(task)

            def _done(t):
                _background.discard(t)
                follow = asyncio.ensure_future(self._deliver_late(user_id, t))
                _background.add(follow)
                follow.add_done_callback(_background.discard)

            task.add_done_callback(_done)
            return {"ok": True, "reply": STILL_WORKING, "pending": True}
        except Exception:
            logger.exception("siri turn failed")
            return {"ok": False, "reply": FAILED}
        return {
            "ok": bool(answer.get("ok")),
            "reply": self._say(answer),
            "session_id": answer.get("session_id"),
        }
