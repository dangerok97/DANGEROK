"""Location service — foreground signals → PresenceContext."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from location.models import (
    CURRENT_MAX_AGE_SEC,
    RECENT_MAX_AGE_SEC,
    SIGNAL_TTL_SECONDS,
    LocationPreference,
    LocationSignal,
    PermissionState,
    PresenceContext,
    PresenceFreshness,
    now_iso,
)
from location.place_label import PLACE_RESOLVER_VERSION
from location.repository import LocationRepository

logger = logging.getLogger("ora.location")


def runtime_location_capabilities(
    *,
    preference: LocationPreference = "off",
    platform: str = "web",
) -> Dict[str, str]:
    """Honesty map for AI Core — never claim native/background if unsupported.

    Preference ``off`` (default / not yet consented) is NOT device-disabled.
    It means ORA foreground consent is still required — the model MUST call
    get_current_location so the client can show the Quiet Premium consent sheet.
    """
    native = "unsupported"  # V2.7.1: web foreground only
    background = "unavailable"
    if preference == "off":
        # Consent not granted to ORA yet — tool will emit needs_client / consent UI
        foreground = "requires_consent"
    elif platform == "web":
        foreground = "available"
    else:
        foreground = "unsupported"
    return {
        "current_location": foreground,
        "foreground_location": foreground,
        "background_location": background,
        "native_location": native,
        "presence_history": "limited",  # latest presence only in slice 1
        "ora_location_consent": "granted" if preference == "while_using" else "not_requested",
    }


def classify_freshness(timestamp_iso: Optional[str], *, now: Optional[datetime] = None) -> PresenceFreshness:
    if not timestamp_iso:
        return "UNKNOWN"
    try:
        ts = datetime.fromisoformat(str(timestamp_iso).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception:
        return "UNKNOWN"
    now = now or datetime.now(timezone.utc)
    age = (now - ts.astimezone(timezone.utc)).total_seconds()
    if age < 0:
        age = 0
    if age <= CURRENT_MAX_AGE_SEC:
        return "CURRENT"
    if age <= RECENT_MAX_AGE_SEC:
        return "RECENT"
    return "STALE"


class LocationService:
    def __init__(self, db):
        self.db = db
        self.repo = LocationRepository(db)

    async def ensure_indexes(self) -> None:
        await self.repo.ensure_indexes()

    async def get_preference(self, user_id: str) -> LocationPreference:
        return await self.repo.get_preference(user_id)

    async def set_preference(self, user_id: str, mode: str) -> LocationPreference:
        pref: LocationPreference = (
            "while_using" if str(mode).strip().lower() == "while_using" else "off"
        )
        await self.repo.set_preference(user_id, pref)
        return pref

    async def ingest_foreground_signal(
        self,
        user_id: str,
        *,
        latitude: float,
        longitude: float,
        accuracy_meters: Optional[float] = None,
        session_id: Optional[str] = None,
        goal_ref: Optional[str] = None,
        reverse_geocode: bool = True,
    ) -> Dict[str, Any]:
        pref = await self.repo.get_preference(user_id)
        if pref != "while_using":
            return {
                "ok": False,
                "error": "location_disabled",
                "preference": pref,
            }
        try:
            lat = float(latitude)
            lon = float(longitude)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid_coordinates"}
        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return {"ok": False, "error": "invalid_coordinates"}

        place = None
        if reverse_geocode:
            place = await self._reverse_place(lat, lon, accuracy_meters=accuracy_meters)

        expires = datetime.now(timezone.utc) + timedelta(seconds=SIGNAL_TTL_SECONDS)
        label = (place.display_label if place else None) or None
        signal = LocationSignal(
            user_id=user_id,
            latitude=lat,
            longitude=lon,
            accuracy_meters=accuracy_meters,
            source="foreground_device",
            permission_state="granted_foreground",
            freshness="CURRENT",
            session_id=str(session_id)[:64] if session_id else None,
            goal_ref=str(goal_ref)[:64] if goal_ref else None,
            expires_at=expires,
            place_label=str(label)[:80] if label else None,
            place_locality=(place.locality[:80] if place and place.locality else None),
            place_municipality=(
                place.municipality[:80] if place and place.municipality else None
            ),
            place_region=(place.region[:80] if place and place.region else None),
            place_country=(place.country[:80] if place and place.country else None),
            place_label_precision=(place.precision if place else None),
            place_resolver_version=(PLACE_RESOLVER_VERSION if place else None),
        )
        await self.repo.insert_signal(signal)
        presence = self._presence_from_signal(user_id, signal, preference=pref)
        await self.repo.upsert_presence(presence)
        logger.info(
            "location_signal user=%s freshness=%s has_label=%s precision=%s",
            user_id[:12],
            presence.freshness,
            bool(label),
            (place.precision if place else None),
        )
        return {
            "ok": True,
            "signal_id": signal.id,
            "presence": presence.for_ai(),
            "ttl_seconds": SIGNAL_TTL_SECONDS,
            # Honesty: coords accepted but not returned in this ACK to minimize leakage
            "persists_coordinates": True,
            "memory_written": False,
        }

    async def build_presence(
        self,
        user_id: str,
        *,
        platform: str = "web",
    ) -> PresenceContext:
        pref = await self.repo.get_preference(user_id)
        stored = await self.repo.get_presence(user_id)
        latest = await self.repo.latest_signal(user_id)
        if latest:
            # GPS may still be CURRENT while place semantics are outdated
            # (e.g. resolver upgraded). Re-derive labels from stored coords.
            latest = await self._ensure_place_resolver_current(latest)
            presence = self._presence_from_signal(user_id, latest, preference=pref)
            # Preserve a recent client-bridge failure (timeout/denied/…) so we do not
            # immediately re-emit needs_client on the same STALE signal after resume.
            if stored and (stored.acquisition_error or "").strip():
                same_obs = (stored.last_seen_at or "") == (presence.last_seen_at or "")
                if same_obs or not stored.last_seen_at:
                    presence.acquisition_error = stored.acquisition_error
                    if stored.permission_state == "denied":
                        presence.permission_state = "denied"
                    elif stored.permission_state == "unavailable" and not presence.acquisition_error:
                        presence.permission_state = stored.permission_state
            await self.repo.upsert_presence(presence)
            return presence
        if stored:
            stored.preference = pref
            stored.freshness = classify_freshness(stored.last_seen_at)
            if (
                stored.latitude is not None
                and stored.longitude is not None
                and (stored.place_resolver_version or "") != self._resolver_version()
            ):
                # Upgrade presence-only docs that still hold coords
                synth = LocationSignal(
                    id="presence_upgrade",
                    user_id=user_id,
                    latitude=float(stored.latitude),
                    longitude=float(stored.longitude),
                    accuracy_meters=stored.accuracy_meters,
                    timestamp=stored.last_seen_at or now_iso(),
                    place_label=stored.place_label,
                    place_resolver_version=stored.place_resolver_version,
                )
                upgraded = await self._ensure_place_resolver_current(
                    synth, persist_signal=False
                )
                stored.place_label = upgraded.place_label
                stored.place_locality = upgraded.place_locality
                stored.place_municipality = upgraded.place_municipality
                stored.place_region = upgraded.place_region
                stored.place_country = upgraded.place_country
                stored.place_label_precision = upgraded.place_label_precision
                stored.place_resolver_version = upgraded.place_resolver_version
                await self.repo.upsert_presence(stored)
            if stored.freshness == "STALE" and stored.latitude is not None:
                pass
            elif stored.freshness not in ("CURRENT", "RECENT"):
                stored.freshness = "UNKNOWN" if not stored.last_seen_at else stored.freshness
            return stored
        return PresenceContext(
            user_id=user_id,
            freshness="UNKNOWN",
            preference=pref,
            permission_state="not_requested" if pref == "off" else "granted_foreground",
        )

    async def capability_get_current_location(
        self,
        user_id: str,
        *,
        session_id: Optional[str] = None,
        platform: str = "web",
    ) -> Dict[str, Any]:
        pref = await self.repo.get_preference(user_id)
        caps = runtime_location_capabilities(preference=pref, platform=platform)
        if pref == "off":
            return {
                "capability": "get_current_location",
                "status": "consent_required",
                "freshness": "UNKNOWN",
                "error": "ora_consent_required",
                "user_facing_hint": (
                    "ORA does not yet have foreground-location consent. "
                    "A client consent sheet will be shown. Do NOT tell the user that "
                    "device location services are disabled."
                ),
                "runtime_capabilities": caps,
                "needs_client": True,
                "client_action": {
                    "type": "request_location_permission",
                    "reason": (
                        "ORA può usare la tua posizione mentre usi l'app per capire meglio "
                        "dove ti trovi e aiutarti quando il luogo è rilevante."
                    ),
                },
                "memory_eligible": False,
            }
        if platform != "web" and caps.get("native_location") == "unsupported":
            return {
                "capability": "get_current_location",
                "status": "unavailable",
                "freshness": "UNKNOWN",
                "error": "native_unsupported",
                "runtime_capabilities": caps,
                "needs_client": False,
            }
        presence = await self.build_presence(user_id, platform=platform)
        if presence.permission_state == "denied" or (
            (presence.acquisition_error or "").strip().lower() == "denied"
        ):
            return {
                "capability": "get_current_location",
                "status": "denied",
                "freshness": "UNKNOWN",
                "error": "permission_denied",
                "user_facing_hint": (
                    "Browser/OS denied location permission. Say ORA does not have "
                    "permission to access current location — not that device services "
                    "are disabled."
                ),
                "runtime_capabilities": caps,
                "needs_client": False,
                "memory_eligible": False,
            }
        # Client-bridge attempt just failed (or sticky provider failure) — terminal
        # for this turn. Transient errors are cleared on the next user message so
        # contextual retries can refresh again.
        acq = (presence.acquisition_error or "").strip().lower()
        if acq == "timeout":
            return {
                "capability": "get_current_location",
                "status": "timeout",
                "freshness": presence.freshness
                if presence.freshness in ("STALE", "RECENT", "CURRENT")
                else "UNKNOWN",
                "error": "geolocation_timeout",
                "place_label": presence.place_label,
                "note": (
                    "Foreground refresh timed out. You may mention last known place "
                    "only as not current. Do not claim permission is disabled."
                ),
                "user_facing_hint": (
                    "Location request timed out. Do not claim device location "
                    "services are disabled or that browser permission is off."
                ),
                "runtime_capabilities": caps,
                "needs_client": False,
                "memory_eligible": False,
            }
        if acq == "position_unavailable":
            return {
                "capability": "get_current_location",
                "status": "unavailable",
                "freshness": "UNKNOWN",
                "error": "position_unavailable",
                "place_label": presence.place_label,
                "user_facing_hint": (
                    "The device/provider returned POSITION_UNAVAILABLE. "
                    "Say the current position could not currently be determined. "
                    "Do not claim permission is disabled."
                ),
                "runtime_capabilities": caps,
                "needs_client": False,
                "memory_eligible": False,
            }
        if acq == "unavailable" or presence.permission_state == "unavailable":
            return {
                "capability": "get_current_location",
                "status": "unavailable",
                "freshness": "UNKNOWN",
                "error": "geolocation_unavailable",
                "user_facing_hint": (
                    "Geolocation API unavailable in this environment. "
                    "Do not claim browser permission is disabled."
                ),
                "runtime_capabilities": caps,
                "needs_client": False,
                "memory_eligible": False,
            }
        if presence.freshness in ("CURRENT", "RECENT"):
            ai = presence.for_ai()
            return {
                "capability": "get_current_location",
                "status": "ok",
                "freshness": presence.freshness,
                "timestamp": presence.last_seen_at,
                "accuracy_meters": presence.accuracy_meters,
                "source": presence.source,
                "place_label": presence.place_label,
                "place": ai.get("place"),
                "coordinates": ai.get("coordinates"),
                "runtime_capabilities": caps,
                "needs_client": False,
                "memory_eligible": False,
            }
        if presence.freshness == "STALE":
            # MUST include client_action — needs_client alone does not pause the loop.
            if pref == "while_using":
                client_action = {
                    "type": "request_foreground_location",
                    "reason": "Device presence is STALE — refresh foreground location.",
                    "refresh": True,
                }
            else:
                client_action = {
                    "type": "request_location_permission",
                    "reason": (
                        "ORA può usare la tua posizione mentre usi l'app per capire meglio "
                        "dove ti trovi e aiutarti quando il luogo è rilevante."
                    ),
                    "refresh": True,
                }
            return {
                "capability": "get_current_location",
                "status": "stale",
                "freshness": "STALE",
                "timestamp": presence.last_seen_at,
                "source": presence.source,
                "place_label": presence.place_label,
                "place": presence.for_ai().get("place"),
                "note": (
                    "Stale device location — do not claim the user is here now. "
                    "A client foreground refresh will run; wait for the fresh observation."
                ),
                "user_facing_hint": (
                    "Last known place may be mentioned only as not current. "
                    "Do not say browser permission is disabled unless a later observation "
                    "status is denied."
                ),
                "runtime_capabilities": caps,
                "needs_client": True,
                "client_action": client_action,
                "memory_eligible": False,
            }
        # No usable signal — ask client bridge
        return {
            "capability": "get_current_location",
            "status": "needs_client",
            "freshness": "UNKNOWN",
            "error": "no_signal",
            "runtime_capabilities": caps,
            "needs_client": True,
            "client_action": {
                "type": "request_foreground_location",
                "reason": "ORA needs a fresh device location for this turn.",
            },
            "memory_eligible": False,
        }

    async def capability_get_current_presence(
        self, user_id: str, *, platform: str = "web"
    ) -> Dict[str, Any]:
        pref = await self.repo.get_preference(user_id)
        caps = runtime_location_capabilities(preference=pref, platform=platform)
        presence = await self.build_presence(user_id, platform=platform)
        needs = False
        client_action = None
        if presence.permission_state in ("denied", "unavailable"):
            needs = False
            client_action = None
        elif pref == "off":
            needs = True
            client_action = {
                "type": "request_location_permission",
                "reason": (
                    "ORA può usare la tua posizione mentre usi l'app per capire meglio "
                    "dove ti trovi e aiutarti quando il luogo è rilevante."
                ),
            }
        elif presence.freshness in ("UNKNOWN", "STALE") and pref == "while_using":
            needs = True
            client_action = {
                "type": "request_foreground_location",
                "reason": "ORA needs a fresh device location for this turn.",
            }
        status = "ok" if presence.freshness != "UNKNOWN" else "unknown"
        if presence.permission_state == "denied":
            status = "denied"
        elif presence.permission_state == "unavailable":
            status = "unavailable"
        return {
            "capability": "get_current_presence",
            "status": status,
            "presence": presence.for_ai(),
            "runtime_capabilities": caps,
            "needs_client": needs,
            "client_action": client_action,
            "memory_eligible": False,
        }

    async def clear_transient_acquisition_error(self, user_id: str) -> None:
        """Allow a new user turn to retry foreground geolocation after timeout/unavailable."""
        stored = await self.repo.get_presence(user_id)
        if not stored:
            return
        acq = (stored.acquisition_error or "").strip().lower()
        if not acq:
            return
        if stored.permission_state == "denied" or acq == "denied":
            return
        stored.acquisition_error = None
        pref = await self.repo.get_preference(user_id)
        if stored.permission_state == "unavailable":
            stored.permission_state = (
                "granted_foreground" if pref == "while_using" else "not_requested"
            )
        stored.preference = pref
        await self.repo.upsert_presence(stored)

    async def record_permission_outcome(
        self,
        user_id: str,
        *,
        state: str,
    ) -> Dict[str, Any]:
        """Record browser deny/unavailable/timeout without inventing coordinates."""
        pref = await self.repo.get_preference(user_id)
        state_l = str(state or "").strip().lower()
        perm: PermissionState
        acquisition_error: Optional[str] = None
        if state_l == "denied":
            perm = "denied"
            acquisition_error = "denied"
        elif state_l == "timeout":
            # Timeout is not a permanent permission denial
            perm = "granted_foreground" if pref == "while_using" else "not_requested"
            acquisition_error = "timeout"
        elif state_l == "position_unavailable":
            perm = "unavailable"
            acquisition_error = "position_unavailable"
        elif state_l == "unavailable":
            perm = "unavailable"
            acquisition_error = "unavailable"
        else:
            perm = "not_requested"
        # Preserve last known STALE/CURRENT observation when a refresh fails
        latest = await self.repo.latest_signal(user_id)
        if latest:
            presence = self._presence_from_signal(user_id, latest, preference=pref)
            presence.acquisition_error = acquisition_error
            if state_l == "denied":
                presence.permission_state = "denied"
            elif state_l in ("position_unavailable", "unavailable"):
                presence.permission_state = "unavailable"
            else:
                presence.permission_state = perm
        else:
            presence = PresenceContext(
                user_id=user_id,
                freshness="UNKNOWN",
                permission_state=perm,
                preference=pref,
                source=None,
                last_seen_at=None,
                acquisition_error=acquisition_error,
            )
        await self.repo.upsert_presence(presence)
        return {
            "ok": True,
            "permission_state": presence.permission_state,
            "acquisition_error": acquisition_error,
            "presence": presence.for_ai(),
            "memory_written": False,
        }

    def _presence_from_signal(
        self,
        user_id: str,
        signal: LocationSignal,
        *,
        preference: LocationPreference,
    ) -> PresenceContext:
        freshness = classify_freshness(signal.timestamp)
        return PresenceContext(
            user_id=user_id,
            freshness=freshness,
            last_seen_at=signal.timestamp,
            accuracy_meters=signal.accuracy_meters,
            latitude=signal.latitude,
            longitude=signal.longitude,
            place_label=signal.place_label,
            place_locality=signal.place_locality,
            place_municipality=signal.place_municipality,
            place_region=signal.place_region,
            place_country=signal.place_country,
            place_label_precision=signal.place_label_precision,
            place_resolver_version=signal.place_resolver_version,
            source=signal.source,
            permission_state=signal.permission_state,
            source_refs=[signal.id],
            preference=preference,
            acquisition_error=None,
            updated_at=now_iso(),
        )

    def _resolver_version(self) -> str:
        return PLACE_RESOLVER_VERSION

    async def _ensure_place_resolver_current(
        self,
        signal: LocationSignal,
        *,
        persist_signal: bool = True,
    ) -> LocationSignal:
        """
        Keep GPS timestamp/freshness; refresh semantic place when resolver version
        is missing or outdated. Does not invent locality — re-queries provider.
        """
        current = self._resolver_version()
        if (signal.place_resolver_version or "") == current:
            return signal
        place = await self._reverse_place(
            float(signal.latitude),
            float(signal.longitude),
            accuracy_meters=signal.accuracy_meters,
        )
        if place is None:
            # Soft-fail: keep prior labels and prior version so we can retry
            logger.info(
                "place_resolve_upgrade soft-fail user=%s",
                (signal.user_id or "")[:12],
            )
            return signal
        signal.place_label = (
            str(place.display_label)[:80] if place.display_label else None
        )
        signal.place_locality = (
            str(place.locality)[:80] if place.locality else None
        )
        signal.place_municipality = (
            str(place.municipality)[:80] if place.municipality else None
        )
        signal.place_region = str(place.region)[:80] if place.region else None
        signal.place_country = str(place.country)[:80] if place.country else None
        signal.place_label_precision = place.precision
        signal.place_resolver_version = current
        logger.info(
            "place_resolve_upgrade user=%s precision=%s has_locality=%s has_muni=%s",
            (signal.user_id or "")[:12],
            signal.place_label_precision,
            bool(signal.place_locality),
            bool(signal.place_municipality),
        )
        if persist_signal and signal.id and signal.id != "presence_upgrade":
            try:
                await self.repo.update_signal_place(signal)
            except Exception:
                logger.info("place_resolve_upgrade persist soft-fail")
        return signal

    async def _reverse_place(
        self,
        lat: float,
        lon: float,
        *,
        accuracy_meters: Optional[float] = None,
    ):
        try:
            from location.place_label import nominatim_reverse_place

            return await nominatim_reverse_place(
                lat, lon, accuracy_meters=accuracy_meters
            )
        except Exception:
            logger.info("reverse_geocode soft-fail")
            return None
