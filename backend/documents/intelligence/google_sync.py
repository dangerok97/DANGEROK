"""Push calendar_event_drafts to Google Calendar (write path).

Separate from inbound Google Calendar connector polling.
Uses connector instance + vault; never logs tokens or document bodies.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from connectors.google_calendar.provider import GoogleCalendarAPIError
from connectors.google_calendar.scopes import CONNECTOR_ID

logger = logging.getLogger("ora.documents.google_sync")

# Schema-supported CalendarEventDraft fields a reschedule/update may touch.
# id and google_event_id are deliberately excluded — reschedule never
# creates a second draft/event for the same intent.
_RESCHEDULE_ALLOWED_FIELDS = frozenset(
    {"title", "start_datetime", "end_datetime", "timezone", "location", "description"}
)

_locks: dict[str, asyncio.Lock] = {}


def _lock(key: str) -> asyncio.Lock:
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    return _locks[key]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_google_description(
    *,
    draft: dict[str, Any],
    macro_category: Optional[str] = None,
    maps_url: Optional[str] = None,
) -> str:
    """Minimal description — never full document text / medical details."""
    lines: list[str] = []
    if macro_category == "medical":
        lines.append("Visita / appuntamento (dettagli in ORA)")
    else:
        # Short safe blurb — truncate any user description
        desc = (draft.get("description") or "").strip().replace("\n", " ")
        if desc:
            lines.append(desc[:240])
    if draft.get("location"):
        lines.append(f"Luogo: {draft['location']}")
    if maps_url:
        lines.append(f"Maps: {maps_url}")
    pri = draft.get("priority")
    urg = draft.get("urgency")
    if pri or urg:
        lines.append(f"Priorità: {pri or '-'}; urgenza: {urg or '-'}")
    lines.append("Creato da ORA — Life OS")
    if draft.get("source_document_id"):
        lines.append(f"Rif. documento ORA: {draft['source_document_id']}")
    return "\n".join(lines)


def build_google_event_body(
    draft: dict[str, Any],
    *,
    macro_category: Optional[str] = None,
    maps_url: Optional[str] = None,
) -> dict[str, Any]:
    title = draft.get("title") or "Evento ORA"
    if macro_category == "medical":
        title = "Visita specialistica"
    tz = draft.get("timezone") or "Europe/Rome"
    all_day = bool(draft.get("all_day"))
    start = draft.get("start_datetime")
    end = draft.get("end_datetime")
    if not start:
        raise ValueError("start_datetime richiesto per sync Google")

    body: dict[str, Any] = {
        "summary": str(title)[:200],
        "description": sanitize_google_description(
            draft=draft, macro_category=macro_category, maps_url=maps_url,
        ),
        "location": (draft.get("location") or "")[:300] or None,
        "extendedProperties": {
            "private": {
                "ora_event_id": draft["id"],
                "ora_document_id": draft.get("source_document_id") or "",
                "ora_candidate_id": draft.get("source_event_candidate_id") or "",
            }
        },
    }
    if all_day:
        # Google all-day uses date (exclusive end)
        start_d = _as_local_date(start, tz)
        end_d = _as_local_date(end or start, tz)
        body["start"] = {"date": start_d, "timeZone": tz}
        body["end"] = {"date": end_d, "timeZone": tz}
    else:
        body["start"] = {"dateTime": _ensure_rfc3339(start, tz), "timeZone": tz}
        body["end"] = {"dateTime": _ensure_rfc3339(end or start, tz), "timeZone": tz}
    # drop None location
    if not body.get("location"):
        body.pop("location", None)
    return body


def _as_local_date(iso: str, tz: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.astimezone(ZoneInfo(tz)).date().isoformat()


def _ensure_rfc3339(iso: str, tz: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt.isoformat()


class GoogleCalendarSyncService:
    def __init__(self, *, db, google_calendar_service):
        self.db = db
        self.gcal = google_calendar_service

    async def _instance_for_user(self, user_id: str) -> Optional[dict]:
        items = await self.gcal.list_instances(user_id)
        active = [i for i in items if i.get("status") != "revoked"]
        if not active:
            return None
        # Prefer real OAuth instances over leftover fake/test connectors.
        real = [
            i for i in active
            if (i.get("metadata") or {}).get("provider_mode") == "real"
            or not str((i.get("metadata") or {}).get("provider_mode") or "").startswith("fake")
        ]
        pool = real or active
        # Most recently updated first when available
        pool = sorted(pool, key=lambda x: x.get("updated_at") or "", reverse=True)
        return pool[0]

    async def connection_status(self, user_id: str) -> dict[str, Any]:
        try:
            inst = await self._instance_for_user(user_id)
        except Exception:
            inst = None
        if not inst:
            return {
                "connected": False,
                "needs_reconnect": False,
                "account_email": None,
                "default_calendar_id": None,
                "scopes": [],
                "write_capable": False,
            }
        scopes = (
            inst.get("authorized_scopes")
            or inst.get("granted_scopes")
            or inst.get("scopes")
            or []
        )
        scope_blob = " ".join(scopes) if isinstance(scopes, list) else str(scopes)
        write_capable = "calendar.events" in scope_blob
        meta = inst.get("metadata") or {}
        default_cal = meta.get("default_calendar_id") or (
            (inst.get("selected_resource_ids") or [None])[0]
        )
        return {
            "connected": True,
            "needs_reconnect": bool(scopes) and not write_capable,
            "account_email": (
                meta.get("account_email")
                or inst.get("display_label")
                or inst.get("provider_account_id")
            ),
            "instance_id": inst.get("id"),
            "default_calendar_id": default_cal,
            "selected_calendars": inst.get("selected_resource_ids") or [],
            "scopes": scopes if isinstance(scopes, list) else scope_blob.split(),
            "write_capable": write_capable,
            "last_sync_at": inst.get("last_sync_at"),
        }

    async def set_default_calendar(self, *, user_id: str, calendar_id: str) -> dict:
        inst = await self._instance_for_user(user_id)
        if not inst:
            raise RuntimeError("Google Calendar non collegato")
        meta = dict(inst.get("metadata") or {})
        meta["default_calendar_id"] = calendar_id
        selected = list(inst.get("selected_resource_ids") or [])
        if calendar_id not in selected:
            selected = [calendar_id] + selected
        await self.gcal.instances.update(
            user_id, inst["id"],
            {"metadata": meta, "selected_resource_ids": selected},
        )
        return await self.connection_status(user_id)

    async def sync_draft(
        self,
        *,
        user_id: str,
        draft_id: str,
        calendar_id: Optional[str] = None,
        macro_category: Optional[str] = None,
        maps_url: Optional[str] = None,
        delete_on_google: bool = False,
    ) -> dict[str, Any]:
        lock = _lock(f"{user_id}:{draft_id}")
        async with lock:
            draft = await self.db.calendar_event_drafts.find_one(
                {"id": draft_id, "user_id": user_id}, {"_id": 0},
            )
            if not draft:
                raise LookupError("event_not_found")
            if draft.get("status") == "cancelled" and not delete_on_google:
                raise ValueError("evento cancellato")

            inst = await self._instance_for_user(user_id)
            if not inst:
                await self._patch_draft(draft_id, user_id, {
                    "sync_provider": "google",
                    "sync_status": "failed",
                    "sync_error": "not_connected",
                    "updated_at": _now(),
                })
                raise RuntimeError("Google Calendar non collegato")

            cal_id = calendar_id or (inst.get("metadata") or {}).get("default_calendar_id")
            if not cal_id:
                cals = await self.gcal.list_calendars_for_instance(
                    user_id=user_id, instance_id=inst["id"],
                )
                primary = next((c for c in cals if c.get("primary")), None)
                cal_id = (primary or (cals[0] if cals else {})).get("id")
            if not cal_id:
                raise RuntimeError("Nessun calendario Google disponibile")

            access = await self.gcal._get_access_token(user_id=user_id, instance=inst)

            # Existing Google linkage — update (never insert a second event)
            if draft.get("google_event_id"):
                return await self._update_existing(
                    user_id=user_id,
                    draft=draft,
                    access=access,
                    calendar_id=cal_id or draft.get("google_calendar_id") or calendar_id,
                    macro_category=macro_category,
                    maps_url=maps_url,
                )

            await self._patch_draft(draft_id, user_id, {
                "sync_provider": "google",
                "sync_status": "pending",
                "sync_error": None,
                "google_calendar_id": cal_id,
                "updated_at": _now(),
            })

            body = build_google_event_body(
                {**draft, "google_calendar_id": cal_id},
                macro_category=macro_category,
                maps_url=maps_url,
            )
            try:
                created = await self.gcal.provider.create_event(
                    access_token=access, calendar_id=cal_id, body=body,
                )
            except GoogleCalendarAPIError as e:
                await self._patch_draft(draft_id, user_id, {
                    "sync_status": "failed",
                    "sync_error": f"http_{e.status_code}",
                    "updated_at": _now(),
                })
                raise

            patch = {
                "sync_provider": "google",
                "sync_status": "synced",
                "google_calendar_id": cal_id,
                "google_event_id": created.get("id"),
                "google_event_html_link": created.get("htmlLink"),
                "google_event_etag": created.get("etag"),
                "last_synced_at": _now(),
                "sync_error": None,
                "sync_version": int(draft.get("sync_version") or 0) + 1,
                "provider": "google",
                "updated_at": _now(),
            }
            await self._patch_draft(draft_id, user_id, patch)
            out = {**draft, **patch}
            return out

    async def _update_existing(
        self,
        *,
        user_id: str,
        draft: dict,
        access: str,
        calendar_id: str,
        macro_category: Optional[str],
        maps_url: Optional[str],
    ) -> dict:
        body = build_google_event_body(
            draft, macro_category=macro_category, maps_url=maps_url,
        )
        etag = draft.get("google_event_etag")
        try:
            # Detect external change
            if etag:
                try:
                    remote = await self.gcal.provider.get_event(
                        access_token=access,
                        calendar_id=calendar_id,
                        event_id=draft["google_event_id"],
                    )
                    if remote.get("etag") and remote.get("etag") != etag:
                        await self._patch_draft(draft["id"], user_id, {
                            "sync_status": "conflict",
                            "sync_error": "etag_mismatch",
                            "updated_at": _now(),
                        })
                        return {
                            **draft,
                            "sync_status": "conflict",
                            "sync_error": "etag_mismatch",
                            "remote_etag": remote.get("etag"),
                        }
                except GoogleCalendarAPIError as e:
                    if e.status_code == 404:
                        # recreate
                        created = await self.gcal.provider.create_event(
                            access_token=access, calendar_id=calendar_id, body=body,
                        )
                        patch = {
                            "sync_status": "synced",
                            "google_event_id": created.get("id"),
                            "google_event_html_link": created.get("htmlLink"),
                            "google_event_etag": created.get("etag"),
                            "last_synced_at": _now(),
                            "sync_error": None,
                            "updated_at": _now(),
                        }
                        await self._patch_draft(draft["id"], user_id, patch)
                        return {**draft, **patch}
                    raise

            updated = await self.gcal.provider.update_event(
                access_token=access,
                calendar_id=calendar_id,
                event_id=draft["google_event_id"],
                body=body,
                etag=etag,
            )
        except GoogleCalendarAPIError as e:
            if e.etag_conflict:
                await self._patch_draft(draft["id"], user_id, {
                    "sync_status": "conflict",
                    "sync_error": "etag_conflict",
                    "updated_at": _now(),
                })
                return {**draft, "sync_status": "conflict", "sync_error": "etag_conflict"}
            await self._patch_draft(draft["id"], user_id, {
                "sync_status": "failed",
                "sync_error": f"http_{e.status_code}",
                "updated_at": _now(),
            })
            raise

        patch = {
            "sync_status": "synced",
            "google_event_etag": updated.get("etag"),
            "google_event_html_link": updated.get("htmlLink") or draft.get("google_event_html_link"),
            "last_synced_at": _now(),
            "sync_error": None,
            "sync_version": int(draft.get("sync_version") or 0) + 1,
            "updated_at": _now(),
        }
        await self._patch_draft(draft["id"], user_id, patch)
        return {**draft, **patch}

    async def reschedule_draft(
        self,
        *,
        user_id: str,
        draft_id: str,
        fields: dict[str, Any],
        macro_category: Optional[str] = None,
        maps_url: Optional[str] = None,
    ) -> dict[str, Any]:
        """Canonical update/reschedule for a CalendarEventDraft.

        Updates only schema-supported fields on ORA's own draft (id and
        google_event_id are never touched here), then pushes the change to
        Google via the existing update path if the draft is already linked
        — never creates a second draft/event for the same intent. A failed
        push is reported honestly via sync_status/sync_error and never
        claims success; the same call can be retried once connectivity is
        restored, and the local intent (new title/time/etc.) is preserved
        rather than silently discarded.
        """
        lock = _lock(f"{user_id}:{draft_id}")
        async with lock:
            draft = await self.db.calendar_event_drafts.find_one(
                {"id": draft_id, "user_id": user_id}, {"_id": 0},
            )
            if not draft:
                raise LookupError("event_not_found")
            if draft.get("status") == "cancelled":
                raise ValueError("evento cancellato")

            patch = {
                k: v
                for k, v in (fields or {}).items()
                if k in _RESCHEDULE_ALLOWED_FIELDS and v is not None
            }
            if not patch:
                raise ValueError("nessun campo valido da aggiornare")
            patch["updated_at"] = _now()
            if draft.get("google_event_id"):
                patch["sync_status"] = "pending"
            await self._patch_draft(draft_id, user_id, patch)
            draft = {**draft, **patch}

            if not draft.get("google_event_id"):
                # Not yet linked to Google — local intent updated only;
                # nothing to push (a later sync_draft call will create it).
                return draft

            inst = await self._instance_for_user(user_id)
            if not inst:
                await self._patch_draft(draft_id, user_id, {
                    "sync_status": "failed",
                    "sync_error": "not_connected",
                    "updated_at": _now(),
                })
                raise RuntimeError("Google Calendar non collegato")
            access = await self.gcal._get_access_token(user_id=user_id, instance=inst)
            calendar_id = draft.get("google_calendar_id") or (
                inst.get("metadata") or {}
            ).get("default_calendar_id")
            if not calendar_id:
                raise RuntimeError("Nessun calendario Google disponibile")

            return await self._update_existing(
                user_id=user_id,
                draft=draft,
                access=access,
                calendar_id=calendar_id,
                macro_category=macro_category,
                maps_url=maps_url,
            )

    async def resolve_conflict(
        self,
        *,
        user_id: str,
        draft_id: str,
        resolution: str,
        macro_category: Optional[str] = None,
        maps_url: Optional[str] = None,
    ) -> dict:
        """resolution: keep_google | overwrite_ora | unlink"""
        draft = await self.db.calendar_event_drafts.find_one(
            {"id": draft_id, "user_id": user_id}, {"_id": 0},
        )
        if not draft:
            raise LookupError("event_not_found")
        if resolution == "unlink":
            await self._patch_draft(draft_id, user_id, {
                "sync_status": "local_only",
                "sync_provider": "internal",
                "google_event_id": None,
                "google_event_html_link": None,
                "google_event_etag": None,
                "sync_error": None,
                "updated_at": _now(),
            })
            return await self.db.calendar_event_drafts.find_one(
                {"id": draft_id, "user_id": user_id}, {"_id": 0},
            )
        if resolution == "keep_google":
            inst = await self._instance_for_user(user_id)
            if not inst or not draft.get("google_event_id"):
                raise RuntimeError("evento Google assente")
            access = await self.gcal._get_access_token(user_id=user_id, instance=inst)
            remote = await self.gcal.provider.get_event(
                access_token=access,
                calendar_id=draft["google_calendar_id"],
                event_id=draft["google_event_id"],
            )
            start = (remote.get("start") or {})
            end = (remote.get("end") or {})
            patch = {
                "title": remote.get("summary") or draft.get("title"),
                "start_datetime": start.get("dateTime") or start.get("date"),
                "end_datetime": end.get("dateTime") or end.get("date"),
                "location": remote.get("location"),
                "google_event_etag": remote.get("etag"),
                "sync_status": "synced",
                "sync_error": None,
                "last_synced_at": _now(),
                "updated_at": _now(),
            }
            await self._patch_draft(draft_id, user_id, patch)
            return {**draft, **patch}
        if resolution == "overwrite_ora":
            # Force update ignoring etag mismatch by clearing etag then sync
            await self._patch_draft(draft_id, user_id, {
                "google_event_etag": None,
                "sync_status": "pending",
                "updated_at": _now(),
            })
            return await self.sync_draft(
                user_id=user_id,
                draft_id=draft_id,
                macro_category=macro_category,
                maps_url=maps_url,
            )
        raise ValueError("resolution non valida")

    async def delete_remote(
        self,
        *,
        user_id: str,
        draft_id: str,
        also_delete_google: bool,
    ) -> dict:
        draft = await self.db.calendar_event_drafts.find_one(
            {"id": draft_id, "user_id": user_id}, {"_id": 0},
        )
        if not draft:
            raise LookupError("event_not_found")
        deleted_google = False
        if also_delete_google and draft.get("google_event_id"):
            inst = await self._instance_for_user(user_id)
            if inst:
                try:
                    access = await self.gcal._get_access_token(user_id=user_id, instance=inst)
                    await self.gcal.provider.delete_event(
                        access_token=access,
                        calendar_id=draft.get("google_calendar_id") or "primary",
                        event_id=draft["google_event_id"],
                    )
                    deleted_google = True
                except GoogleCalendarAPIError as e:
                    # 404 = already removed on Google — treat as success
                    if e.status_code == 404:
                        deleted_google = True
                    else:
                        logger.warning(
                            "google delete soft-fail draft=%s status=%s",
                            draft_id, e.status_code,
                        )
                except Exception as e:
                    logger.warning(
                        "google delete soft-fail draft=%s type=%s",
                        draft_id, type(e).__name__,
                    )
        await self._patch_draft(draft_id, user_id, {
            "status": "cancelled",
            "sync_status": "local_only" if not also_delete_google else ("synced" if deleted_google else "failed"),
            "sync_error": None if (not also_delete_google or deleted_google) else "google_delete_failed",
            "updated_at": _now(),
        })
        return {"ok": True, "deleted_google": deleted_google}

    async def _patch_draft(self, draft_id: str, user_id: str, patch: dict) -> None:
        await self.db.calendar_event_drafts.update_one(
            {"id": draft_id, "user_id": user_id},
            {"$set": patch},
        )
