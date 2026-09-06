"""
The instruments, read together for the first time.

    A SOURCE IS NOT A SETTING. IT IS A FACT ABOUT WHAT WE CAN SEE.

Everything here already existed somewhere. The account and its scopes live in
the connector layer, the cursor lives on the instance, the archive knows when
its last document arrived. What did not exist was anywhere that read them
together and answered the only question that matters downstream: *is what I
believe about this person's calendar still true?*

So this is a view, not a second copy. `ConnectedSource` rows are derived on
demand from the systems that own the facts, and the only thing persisted is
what nobody else was keeping: what happened on the last attempt, and whether
it worked. A duplicate store of connection state is a store that disagrees
with the connector eventually, and the disagreement always surfaces as a
person being told their calendar is connected when it is not.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from connected.models import (
    ConnectedSource,
    Freshness,
    SourceStatus,
    freshness_of,
    now_iso,
)

logger = logging.getLogger("ora.connected.sources")

ATTEMPTS = "connected_source_attempts"

# How a connector instance's own status word maps onto what we can say about
# reading it. Kept small and explicit: a status we do not recognise is
# reported as degraded rather than assumed healthy, because the failure of
# guessing here is a person being told a stale calendar is current.
_INSTANCE_STATUS: Dict[str, SourceStatus] = {
    "connected": "connected",
    "active": "connected",
    "authorized": "connected",
    "syncing": "syncing",
    "revoked": "disconnected",
    "disconnected": "disconnected",
    "reauthorization_required": "auth_expired",
    "error": "degraded",
}


class SourceRegistry:
    """Every instrument this person has, and the truth about each."""

    def __init__(self, db):
        self.db = db

    async def ensure_indexes(self) -> None:
        try:
            await self.db[ATTEMPTS].create_index(
                [("owner_id", 1), ("source_id", 1)], unique=True
            )
        except Exception:
            logger.exception("indici connected sources non creati (non fatale)")

    # --- reading the instruments -----------------------------------------

    async def list(self, owner_id: str) -> List[ConnectedSource]:
        """
        What ORA can currently see this life through.

        The document archive is always present and never disconnects: it is
        ORA's own shelf rather than somebody else's service, and reporting it
        as a connection somebody could lose would be describing a risk that
        does not exist.
        """
        out: List[ConnectedSource] = []
        out.extend(await self._calendars(owner_id))
        out.extend(await self._mailboxes(owner_id))
        out.append(await self._documents(owner_id))
        return out

    async def get(self, owner_id: str, source_id: str) -> Optional[ConnectedSource]:
        return next(
            (s for s in await self.list(owner_id) if s.id == source_id), None
        )

    async def _calendars(self, owner_id: str) -> List[ConnectedSource]:
        from connectors.google_calendar.scopes import CONNECTOR_ID

        try:
            docs = await self.db.connector_instances.find(
                {"user_id": owner_id, "connector_id": CONNECTOR_ID}, {"_id": 0}
            ).sort("updated_at", -1).to_list(10)
        except Exception as e:
            logger.info("calendar instances soft-fail: %s", type(e).__name__)
            return []

        sources: List[ConnectedSource] = []
        for doc in docs:
            attempt = await self._attempt(owner_id, doc["id"])
            meta = doc.get("metadata") or {}
            status = _INSTANCE_STATUS.get(str(doc.get("status") or ""), "degraded")
            last_success = attempt.get("last_successful_sync_at") or doc.get("last_sync_at")
            fresh = freshness_of("calendar", last_success)

            # Two different unhappinesses, and they are not the same word. A
            # failing connector is `degraded` — we cannot read it. A working
            # one whose last reading is old is `stale` — we can read it, and
            # what we hold is out of date. Collapsing them would tell somebody
            # to reconnect a calendar that is fine.
            if status == "connected" and attempt.get("last_error"):
                status = "degraded"
            elif status == "connected" and fresh == "stale":
                status = "stale"

            sources.append(ConnectedSource(
                id=doc["id"],
                owner_id=owner_id,
                source_type="calendar",
                provider="Google Calendar",
                account_ref=str(meta.get("account_email") or "")[:200],
                status=status,
                read_capabilities=["calendar.read"],
                write_capabilities=["calendar.write"],
                granted_scopes=await self._scopes(owner_id, CONNECTOR_ID, doc["id"]),
                last_successful_sync_at=last_success,
                last_attempt_at=attempt.get("last_attempt_at") or doc.get("last_sync_at"),
                sync_cursor=dict(doc.get("cursor") or {}),
                freshness_state=fresh,
                health_state=str(attempt.get("health") or "")[:80],
                error_state=str(attempt.get("last_error") or "")[:120],
                provenance={"connector_id": CONNECTOR_ID, "instance_id": doc["id"]},
                created_at=str(doc.get("created_at") or now_iso()),
                updated_at=str(doc.get("updated_at") or now_iso()),
            ))
        return sources

    async def _mailboxes(self, owner_id: str) -> List[ConnectedSource]:
        """
        The mailboxes ORA can read, described exactly as a calendar is.

        Same derivation, same four unhappinesses, same freshness question —
        because a mailbox is an instrument like any other and a second way of
        describing connection state would be a second way of being wrong
        about it. The one difference is `write_capabilities`, which is empty
        and stays empty: nothing in this system can send mail, and a source
        that advertised otherwise would be the first step toward something
        that could.
        """
        from connectors.gmail.scopes import CAPABILITY_ID, CONNECTOR_ID

        try:
            docs = await self.db.connector_instances.find(
                {"user_id": owner_id, "connector_id": CONNECTOR_ID}, {"_id": 0}
            ).sort("updated_at", -1).to_list(10)
        except Exception as e:
            logger.info("mailbox instances soft-fail: %s", type(e).__name__)
            return []

        sources: List[ConnectedSource] = []
        for doc in docs:
            attempt = await self._attempt(owner_id, doc["id"])
            meta = doc.get("metadata") or {}
            status = _INSTANCE_STATUS.get(str(doc.get("status") or ""), "degraded")
            last_success = attempt.get("last_successful_sync_at") or doc.get("last_sync_at")
            fresh = freshness_of("email", last_success)
            if status == "connected" and attempt.get("last_error"):
                status = "degraded"
            elif status == "connected" and fresh == "stale":
                status = "stale"

            sources.append(ConnectedSource(
                id=doc["id"],
                owner_id=owner_id,
                source_type="email",
                provider="Gmail",
                account_ref=str(meta.get("account_email") or "")[:200],
                status=status,
                read_capabilities=[CAPABILITY_ID],
                write_capabilities=[],
                granted_scopes=await self._scopes(owner_id, CONNECTOR_ID, doc["id"]),
                last_successful_sync_at=last_success,
                last_attempt_at=attempt.get("last_attempt_at") or doc.get("last_sync_at"),
                sync_cursor=dict(doc.get("cursor") or {}),
                freshness_state=fresh,
                health_state=str(attempt.get("health") or "")[:80],
                error_state=str(attempt.get("last_error") or "")[:120],
                provenance={"connector_id": CONNECTOR_ID, "instance_id": doc["id"]},
                created_at=str(doc.get("created_at") or now_iso()),
                updated_at=str(doc.get("updated_at") or now_iso()),
            ))
        return sources

    async def _documents(self, owner_id: str) -> ConnectedSource:
        """ORA's own shelf. Always there; the only question is how full."""
        last = None
        try:
            newest = await self.db.documents.find_one(
                {"user_id": owner_id}, {"_id": 0, "created_at": 1},
                sort=[("created_at", -1)],
            )
            last = str((newest or {}).get("created_at") or "") or None
        except Exception as e:
            logger.info("documents source soft-fail: %s", type(e).__name__)

        attempt = await self._attempt(owner_id, "documents")
        seen = attempt.get("last_successful_sync_at")
        return ConnectedSource(
            id="documents",
            owner_id=owner_id,
            source_type="documents",
            provider="Documenti",
            status="connected",
            read_capabilities=["document.read"],
            write_capabilities=[],
            last_successful_sync_at=seen or last,
            last_attempt_at=attempt.get("last_attempt_at"),
            freshness_state=freshness_of("documents", seen or last),
            health_state=str(attempt.get("health") or "")[:80],
            error_state=str(attempt.get("last_error") or "")[:120],
            provenance={"owner": "documents"},
        )

    async def _scopes(self, owner_id: str, connector_id: str, instance_id: str) -> List[str]:
        """What the person actually granted, from the registry that holds it."""
        try:
            docs = await self.db.permission_consents.find(
                {
                    "user_id": owner_id,
                    "connector_id": connector_id,
                    "connector_instance_id": instance_id,
                    "status": "active",
                },
                {"_id": 0, "scopes": 1},
            ).to_list(10)
        except Exception as e:
            logger.info("scopes soft-fail: %s", type(e).__name__)
            return []
        seen: List[str] = []
        for doc in docs:
            for scope in doc.get("scopes") or []:
                if scope not in seen:
                    seen.append(str(scope)[:120])
        return seen[:20]

    # --- what happened when we last tried --------------------------------

    async def _attempt(self, owner_id: str, source_id: str) -> Dict[str, Any]:
        try:
            found = await self.db[ATTEMPTS].find_one(
                {"owner_id": owner_id, "source_id": source_id}, {"_id": 0}
            )
            return found or {}
        except Exception as e:
            logger.info("attempt read soft-fail: %s", type(e).__name__)
            return {}

    async def note_attempt(self, owner_id: str, source_id: str) -> None:
        """A reading was started. Recorded before it can succeed or fail."""
        await self.db[ATTEMPTS].update_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"$set": {"owner_id": owner_id, "source_id": source_id,
                      "last_attempt_at": now_iso()}},
            upsert=True,
        )

    async def note_success(self, owner_id: str, source_id: str) -> None:
        """
        It worked. The error is cleared, because it is no longer true.

        Clearing matters as much as recording: a source that keeps reporting
        last week's failure after four good readings is a source people stop
        believing, and then they stop believing the real failures too.
        """
        await self.db[ATTEMPTS].update_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"$set": {"owner_id": owner_id, "source_id": source_id,
                      "last_successful_sync_at": now_iso(),
                      "last_attempt_at": now_iso(),
                      "last_error": "", "health": ""}},
            upsert=True,
        )

    async def note_failure(self, owner_id: str, source_id: str, *, error: str) -> None:
        """
        It did not work, and that is all it means.

            A FAILED READING IS NOT AN EMPTY WORLD.

        Nothing is deleted here, and nothing downstream may read this as "no
        events". The single most dangerous mistake available to a connected
        system is treating a failed sync as a world where nothing is
        happening: the appointment is still tomorrow, and the only thing that
        changed is that we cannot see it.
        """
        await self.db[ATTEMPTS].update_one(
            {"owner_id": owner_id, "source_id": source_id},
            {"$set": {"owner_id": owner_id, "source_id": source_id,
                      "last_attempt_at": now_iso(),
                      "last_error": str(error)[:120],
                      "health": "l'ultima lettura non è riuscita"}},
            upsert=True,
        )

    async def forget_all(self, owner_id: str) -> int:
        result = await self.db[ATTEMPTS].delete_many({"owner_id": owner_id})
        return result.deleted_count
