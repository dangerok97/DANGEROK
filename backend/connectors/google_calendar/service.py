"""GoogleCalendarService — high-level orchestration.

Composes:
  - OAuth (auth code + PKCE) via oauth.py;
  - TokenVault to store refresh + access tokens (encrypted);
  - PermissionService to gate every read;
  - ConnectorInstanceService for per-account state;
  - IngestionService for normalize/dedupe/route;
  - CalendarProvider (real or fake).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from permissions import ConsentDenied
from permissions.models import INSTANCE_WILDCARD

from ..instances import ConnectorInstanceService
from .oauth import (
    OAuthConfigError,
    OAuthStateInvalid,
    OAuthStateStore,
    build_authorize_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    refresh_access_token,
    revoke_token,
)
from .provider import (
    CalendarProviderProtocol,
    ProviderNotConfigured,
    build_calendar_provider,
    is_real_provider_configured,
)
from .scopes import CAPABILITY_ID, CONNECTOR_ID, GOOGLE_CALENDAR_SCOPES

logger = logging.getLogger("ora.connectors.google_calendar")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _flag_provider_mode() -> str:
    return os.environ.get("CALENDAR_PROVIDER_MODE", "real").strip().lower()


class GoogleCalendarService:
    def __init__(
        self,
        *,
        db,
        permissions,
        ingestion,
        vault,
        provider: Optional[CalendarProviderProtocol] = None,
    ):
        self.db = db
        self.permissions = permissions
        self.ingestion = ingestion
        self.vault = vault
        self.provider: CalendarProviderProtocol = provider or build_calendar_provider()
        self.instances = ConnectorInstanceService(db)
        self.oauth_state = OAuthStateStore(db)

    # ------------------------------------------------------------------
    # Configuration guard: any operation that talks to real Google MUST
    # go through this. Fake mode skips it because it doesn't need config.
    # ------------------------------------------------------------------
    def _require_real_or_fake(self) -> str:
        mode = _flag_provider_mode()
        if mode == "fake":
            return "fake"
        if not is_real_provider_configured():
            raise ProviderNotConfigured(
                "Google Calendar real provider is not configured. Set "
                "GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / "
                "GOOGLE_OAUTH_REDIRECT_URI, or run with CALENDAR_PROVIDER_MODE=fake in tests."
            )
        from security import is_configured as vault_configured
        if not vault_configured(self.vault):
            raise ProviderNotConfigured("Token Vault not configured (TOKEN_VAULT_KEY missing)")
        return "real"

    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------
    async def start_oauth(self, *, user_id: str, redirect_after: Optional[str] = None) -> Dict[str, Any]:
        self._require_real_or_fake()  # config check
        session = await self.oauth_state.create(user_id=user_id, redirect_after=redirect_after)
        await self.permissions.audit.log(
            user_id=user_id, event_type="oauth.start", connector_id=CONNECTOR_ID,
            capability_id=CAPABILITY_ID, success=True, reason_code="state_created",
            data_classification="public",
        )
        mode = _flag_provider_mode()
        if mode == "fake":
            # Fake mode: return a synthetic authorize URL clients can hit
            # directly against /oauth/callback in tests.
            return {
                "authorize_url": f"about:blank?state={session['state']}",
                "state": session["state"],
                "provider_mode": "fake",
                "expires_at": session["expires_at"],
            }
        return {
            "authorize_url": build_authorize_url(state=session["state"], code_challenge=session["code_challenge"]),
            "state": session["state"],
            "provider_mode": "real",
            "expires_at": session["expires_at"],
        }

    async def handle_oauth_callback(
        self,
        *,
        state: str,
        code: str,
        fake_account: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        session = await self.oauth_state.consume(state=state)
        user_id = session["user_id"]

        mode = _flag_provider_mode()
        if mode == "fake":
            if not fake_account:
                raise ValueError("fake_account payload required in fake mode")
            tokens = {
                "access_token": "fake-access-token",
                "refresh_token": "fake-refresh-token",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
            }
            userinfo = fake_account
        else:
            tokens = await exchange_code_for_tokens(code=code, code_verifier=session["code_verifier"])
            userinfo = await fetch_userinfo(tokens["access_token"])

        provider_account_id = userinfo.get("sub") or userinfo.get("email")
        if not provider_account_id:
            await self.permissions.audit.log(
                user_id=user_id, event_type="oauth.callback", connector_id=CONNECTOR_ID,
                capability_id=CAPABILITY_ID, success=False, reason_code="userinfo_missing_sub",
            )
            raise OAuthConfigError("userinfo missing account identifier")

        # Persist tokens in the vault. Never in the ordinary DB.
        secret_ref = await self.vault.put(
            user_id=user_id,
            purpose=f"{CONNECTOR_ID}:oauth",
            payload={
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "token_type": tokens.get("token_type"),
                "expires_at": (_now() + timedelta(seconds=int(tokens.get("expires_in") or 3600))).isoformat(),
                "scope": tokens.get("scope"),
            },
            metadata={"connector_id": CONNECTOR_ID, "account_hint": userinfo.get("email")},
        )

        display_label = userinfo.get("email") or userinfo.get("name") or "Google Calendar"
        authorized_scopes = (tokens.get("scope") or "").split()
        instance = await self.instances.upsert(
            user_id=user_id,
            connector_id=CONNECTOR_ID,
            provider_account_id=str(provider_account_id),
            display_label=display_label,
            platform="web",
            authorized_scopes=authorized_scopes,
            sync_mode="polling",
            secret_reference=secret_ref,
            status="connected",
            metadata={"account_email": userinfo.get("email"), "provider_mode": mode},
            poll_interval_min=int(os.environ.get("GOOGLE_CALENDAR_POLL_INTERVAL_MIN", "15")),
            window_past_days=int(os.environ.get("GOOGLE_CALENDAR_INITIAL_WINDOW_PAST_DAYS", "30")),
            window_future_days=int(os.environ.get("GOOGLE_CALENDAR_INITIAL_WINDOW_FUTURE_DAYS", "180")),
        )

        # Automatically grant the ORA-side consent for calendar.read on the
        # exact connector-instance. Separate from the Google-side consent.
        try:
            await self.permissions.grant(
                user_id=user_id,
                capability_id=CAPABILITY_ID,
                connector_id=CONNECTOR_ID,
                connector_instance_id=instance["id"],
                purpose_id="context_assembly",
                scopes=list(GOOGLE_CALENDAR_SCOPES),
                actor_type="user",
            )
        except Exception:
            logger.exception("permissions grant failed post-callback")

        await self.permissions.audit.log(
            user_id=user_id, event_type="oauth.callback", connector_id=CONNECTOR_ID,
            connector_instance_id=instance["id"], capability_id=CAPABILITY_ID,
            success=True, reason_code="connected",
            data_classification="personal",
        )
        return instance

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _get_access_token(self, *, user_id: str, instance: Dict[str, Any]) -> str:
        secret_ref = instance.get("secret_reference")
        if not secret_ref:
            raise ProviderNotConfigured("connector instance has no secret_reference")
        payload = await self.vault.get(secret_ref, user_id=user_id)
        expires_at = payload.get("expires_at")
        if expires_at and expires_at < _now_iso():
            new_tokens = await refresh_access_token(refresh_token=payload["refresh_token"])
            payload["access_token"] = new_tokens["access_token"]
            payload["expires_at"] = (_now() + timedelta(seconds=int(new_tokens.get("expires_in") or 3600))).isoformat()
            await self.vault.rotate(secret_ref, payload=payload)
            await self.permissions.audit.log(
                user_id=user_id, event_type="oauth.refresh", connector_id=CONNECTOR_ID,
                connector_instance_id=instance["id"], capability_id=CAPABILITY_ID,
                success=True, reason_code="refreshed", data_classification="public",
            )
        return payload["access_token"]

    async def _require_consent(self, *, user_id: str, instance_id: str, purpose_id: str = "context_assembly") -> None:
        ok = await self.permissions.check_access(
            user_id=user_id,
            capability_id=CAPABILITY_ID,
            connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id,
            purpose_id=purpose_id,
        )
        if not ok:
            raise ConsentDenied(
                capability_id=CAPABILITY_ID,
                connector_id=CONNECTOR_ID,
                connector_instance_id=instance_id,
            )

    # ------------------------------------------------------------------
    # Instance operations
    # ------------------------------------------------------------------
    async def list_instances(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.instances.list(user_id, connector_id=CONNECTOR_ID)

    async def get_instance(self, user_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        return await self.instances.get(user_id, instance_id)

    async def list_calendars_for_instance(self, *, user_id: str, instance_id: str) -> List[Dict[str, Any]]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        await self._require_consent(user_id=user_id, instance_id=instance_id)
        access_token = await self._get_access_token(user_id=user_id, instance=instance)
        calendars = await self.provider.list_calendars(access_token=access_token)
        await self.permissions.audit.log(
            user_id=user_id, event_type="calendar.list", connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
            success=True, records_returned=len(calendars), data_classification="personal",
        )
        return [c.__dict__ for c in calendars]

    async def select_calendars(self, *, user_id: str, instance_id: str, calendar_ids: List[str]) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        updated = await self.instances.update(
            user_id, instance_id, {"selected_resource_ids": list(calendar_ids)},
        )
        await self.permissions.audit.log(
            user_id=user_id, event_type="calendar.select", connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
            success=True, records_requested=len(calendar_ids),
            details={"selected_count": len(calendar_ids)},
        )
        return updated

    async def sync(
        self,
        *,
        user_id: str,
        instance_id: str,
        force_full: bool = False,
    ) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        await self._require_consent(user_id=user_id, instance_id=instance_id)
        await self.instances.mark_status(user_id, instance_id, "syncing")

        access_token = await self._get_access_token(user_id=user_id, instance=instance)

        calendars = instance.get("selected_resource_ids") or []
        if not calendars:
            # If no explicit selection, fall back to primary calendar only.
            all_cals = await self.provider.list_calendars(access_token=access_token)
            primary = next((c for c in all_cals if c.primary), None)
            if primary:
                calendars = [primary.id]

        totals = {"received": 0, "processed": 0, "skipped": 0, "quarantined": 0, "failed": 0, "cancelled": 0}
        per_calendar: List[Dict[str, Any]] = []
        cursor_map = dict(instance.get("cursor") or {})

        max_window = int(os.environ.get("GOOGLE_CALENDAR_MAX_WINDOW_DAYS", "730"))
        past = min(int(instance.get("window_past_days") or 30), max_window)
        future = min(int(instance.get("window_future_days") or 180), max_window)
        time_min = (_now() - timedelta(days=past)).isoformat()
        time_max = (_now() + timedelta(days=future)).isoformat()

        for calendar_id in calendars:
            sync_token = None if force_full else (cursor_map.get(calendar_id) or {}).get("sync_token")
            page_token = None
            calendar_name = calendar_id
            cal_totals = {"received": 0, "processed": 0, "skipped": 0, "quarantined": 0}
            new_sync_token = None
            try:
                while True:
                    page = await self.provider.list_events(
                        access_token=access_token,
                        calendar_id=calendar_id,
                        time_min=time_min if not sync_token else None,
                        time_max=time_max if not sync_token else None,
                        page_token=page_token,
                        sync_token=sync_token,
                    )
                    if page.events:
                        outcomes = await self.ingestion.ingest_calendar_events(
                            user_id=user_id,
                            connector_id=CONNECTOR_ID,
                            connector_instance_id=instance_id,
                            calendar_id=calendar_id,
                            calendar_name=calendar_name,
                            raw_events=page.events,
                        )
                        cal_totals["received"] += len(page.events)
                        for o in outcomes:
                            if o.status == "processed":
                                cal_totals["processed"] += 1
                            elif o.status == "skipped":
                                cal_totals["skipped"] += 1
                            elif o.status == "quarantined":
                                cal_totals["quarantined"] += 1
                    page_token = page.next_page_token
                    if page.next_sync_token:
                        new_sync_token = page.next_sync_token
                    if not page_token:
                        break
            except Exception as e:
                logger.exception("sync failed for calendar=%s", calendar_id)
                totals["failed"] += 1
                await self.permissions.audit.log(
                    user_id=user_id, event_type="calendar.sync", connector_id=CONNECTOR_ID,
                    connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
                    success=False, reason_code=str(e)[:80], data_classification="personal",
                    details={"calendar_id": calendar_id},
                )
                per_calendar.append({"calendar_id": calendar_id, "error": str(e)[:200], **cal_totals})
                continue

            if new_sync_token:
                await self.instances.set_cursor(user_id, instance_id, calendar_id=calendar_id, sync_token=new_sync_token)

            await self.permissions.audit.log(
                user_id=user_id, event_type="calendar.sync", connector_id=CONNECTOR_ID,
                connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
                success=True, records_returned=cal_totals["received"],
                data_classification="personal",
                details={"calendar_id": calendar_id, **cal_totals},
            )
            per_calendar.append({"calendar_id": calendar_id, **cal_totals})
            for k in ("received", "processed", "skipped", "quarantined"):
                totals[k] += cal_totals[k]

        await self.instances.mark_status(user_id, instance_id, "connected", extra={"last_sync_at": _now_iso()})
        return {"instance_id": instance_id, "totals": totals, "per_calendar": per_calendar}

    async def refresh(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        # Refresh forces a fresh window (bypasses sync_token) — same code path.
        return await self.sync(user_id=user_id, instance_id=instance_id, force_full=True)

    async def revoke(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        # 1) revoke tokens on Google side (best-effort; skip in fake mode)
        mode = _flag_provider_mode()
        if mode != "fake" and instance.get("secret_reference"):
            try:
                payload = await self.vault.get(instance["secret_reference"], user_id=user_id)
                token_to_revoke = payload.get("refresh_token") or payload.get("access_token")
                if token_to_revoke:
                    await revoke_token(token_to_revoke)
            except Exception:
                logger.exception("google-side token revoke failed")
        # 2) revoke vault entry
        if instance.get("secret_reference"):
            await self.vault.revoke(instance["secret_reference"])
        # 3) revoke ORA consent for this instance
        await self.permissions.revoke(
            user_id=user_id,
            capability_id=CAPABILITY_ID,
            connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id,
            reason="user_revoked",
        )
        # 4) mark instance as revoked (soft; nothing else is deleted)
        updated = await self.instances.mark_status(user_id, instance_id, "revoked")
        # 5) DataRevocationPlan document (marks ingested data as detached)
        await self.db.data_revocation_plans.insert_one({
            "id": f"drp_{instance_id}",
            "user_id": user_id,
            "connector_id": CONNECTOR_ID,
            "connector_instance_id": instance_id,
            "created_at": _now_iso(),
            "policy": "detach",
            "notes": "Ingested events are detached from source; user-verified facts kept.",
        })
        await self.db.ingestion_events.update_many(
            {"user_id": user_id, "connector_instance_id": instance_id},
            {"$set": {"source_status": "detached", "updated_at": _now_iso()}},
        )
        await self.permissions.audit.log(
            user_id=user_id, event_type="connector.revoke", connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
            success=True, reason_code="user_revoked",
        )
        return updated

    async def status(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        # Vault health check
        vault_health = await self.vault.health_check()
        consent_ok = await self.permissions.check_access(
            user_id=user_id,
            capability_id=CAPABILITY_ID,
            connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id,
            audit=False,
        )
        return {
            "instance": instance,
            "vault": vault_health,
            "consent_active": consent_ok,
            "provider_mode": _flag_provider_mode(),
            "real_provider_configured": is_real_provider_configured(),
        }
