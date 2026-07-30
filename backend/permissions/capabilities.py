"""
Capability Registry — hardcoded, versioned, immutable at runtime.

This registry is the CANONICAL SOURCE OF TRUTH for what capabilities ORA
knows about. It is versioned via `CAPABILITY_REGISTRY_VERSION` and any
new capability requires a code deploy (never a runtime write).

MongoDB is used as a read-through cache for OPERATIONAL metadata only
(enabled/disabled, feature-flag, rollout notes) — see `permissions.sync`.
Admins MUST NOT be able to alter capability IDs, semantics, data
categories, sensitivity or platform support from the database side.

Naming: `<connector_domain>.<verb>` (lowercase, dot-separated).

Sensitivity levels: public | personal | sensitive | highly_sensitive
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Dict, Iterable, List, Optional, Tuple

CAPABILITY_REGISTRY_VERSION = "1.0.0"


def _cap(
    *,
    id: str,
    connector_domain: str,
    verb: str,
    display_name: str,
    description: str,
    data_categories: Iterable[str],
    sensitivity: str = "personal",
    platforms: Iterable[str] = ("ios", "android", "web"),
    requires_oauth: bool = False,
    runtime_permission: Optional[Dict[str, str]] = None,
    special_access: Optional[str] = None,
    purposes: Iterable[str] = (),
    default_status: str = "planned",  # planned | available | disabled
    revocable: bool = True,
    retention_days: int = 90,
) -> Dict[str, Any]:
    return MappingProxyType({
        "id": id,
        "connector_domain": connector_domain,
        "verb": verb,
        "display_name": display_name,
        "description": description,
        "data_categories": tuple(data_categories),
        "sensitivity": sensitivity,
        "platforms": tuple(platforms),
        "requires_oauth": bool(requires_oauth),
        "runtime_permission": MappingProxyType(runtime_permission) if runtime_permission else None,
        "special_access": special_access,
        "purposes": tuple(purposes),
        "default_status": default_status,
        "revocable": bool(revocable),
        "retention_days": int(retention_days),
    })


# ============================================================
# The registry — ORDER-STABLE, IMMUTABLE. Do not edit at runtime.
# ============================================================
_CAPABILITIES: Tuple[Dict[str, Any], ...] = (
    # -------- Calendar --------
    _cap(
        id="calendar.read",
        connector_domain="calendar",
        verb="read",
        display_name="Leggi il tuo calendario",
        description="Legge eventi, orari e partecipanti per capire cosa hai in programma.",
        data_categories=("events", "attendees", "locations"),
        sensitivity="personal",
        requires_oauth=True,
        runtime_permission={"ios": "NSCalendarsUsageDescription", "android": "READ_CALENDAR"},
        purposes=("scheduling", "context_assembly", "decision_ranking"),
    ),
    _cap(
        id="calendar.write",
        connector_domain="calendar",
        verb="write",
        display_name="Aggiungi eventi al calendario",
        description="Crea o aggiorna eventi in tuo nome.",
        data_categories=("events",),
        sensitivity="personal",
        requires_oauth=True,
        runtime_permission={"ios": "NSCalendarsUsageDescription", "android": "WRITE_CALENDAR"},
        purposes=("scheduling",),
        default_status="planned",
    ),
    # -------- Mail --------
    _cap(
        id="mail.read",
        connector_domain="mail",
        verb="read",
        display_name="Leggi le tue email",
        description="Legge oggetti e mittenti per estrarre bollette, scadenze e conferme.",
        data_categories=("subjects", "senders", "receipts"),
        sensitivity="sensitive",
        requires_oauth=True,
        purposes=("bill_detection", "receipt_extraction", "context_assembly"),
    ),
    _cap(
        id="mail.metadata",
        connector_domain="mail",
        verb="metadata",
        display_name="Solo oggetti e mittenti",
        description="Accede a metadati (oggetto, mittente, data) senza leggere il corpo del messaggio.",
        data_categories=("subjects", "senders"),
        sensitivity="personal",
        requires_oauth=True,
        purposes=("bill_detection",),
    ),
    # -------- Messaging --------
    _cap(
        id="messaging.read",
        connector_domain="messaging",
        verb="read",
        display_name="Leggi messaggi in sospeso",
        description="Identifica conversazioni con risposte in sospeso.",
        data_categories=("threads", "unread_counts", "senders"),
        sensitivity="sensitive",
        requires_oauth=True,
        purposes=("pending_reply_detection",),
        default_status="planned",
    ),
    # -------- Health --------
    _cap(
        id="health.read",
        connector_domain="health",
        verb="read",
        display_name="Leggi dati sanitari",
        description="Passi, sonno e allenamenti per suggerimenti su energia e forma fisica.",
        data_categories=("activity", "sleep", "workouts"),
        sensitivity="highly_sensitive",
        platforms=("ios", "android"),
        runtime_permission={"ios": "NSHealthShareUsageDescription", "android": "GoogleFit"},
        special_access="apple_health_share",
        purposes=("wellness_insight",),
        retention_days=30,
    ),
    # -------- Banking / Finance --------
    _cap(
        id="banking.read",
        connector_domain="banking",
        verb="read",
        display_name="Leggi transazioni",
        description="Legge transazioni bancarie per rilevare bollette e scadenze.",
        data_categories=("transactions", "balances"),
        sensitivity="highly_sensitive",
        requires_oauth=True,
        special_access="psd2_ais",
        purposes=("bill_detection", "financial_insight"),
        retention_days=45,
    ),
    # -------- Contacts --------
    _cap(
        id="contacts.read",
        connector_domain="contacts",
        verb="read",
        display_name="Leggi i tuoi contatti",
        description="Risolve nomi in relazioni ('Marco' → contatto salvato) per messaggi in sospeso.",
        data_categories=("names", "phones", "emails"),
        sensitivity="sensitive",
        runtime_permission={"ios": "NSContactsUsageDescription", "android": "READ_CONTACTS"},
        purposes=("name_resolution",),
    ),
    # -------- Location --------
    _cap(
        id="location.read",
        connector_domain="location",
        verb="read",
        display_name="Leggi posizione approssimativa",
        description="Solo per confermare 'sei a casa / al lavoro'. Nessun tracciamento continuo.",
        data_categories=("coarse_location",),
        sensitivity="sensitive",
        platforms=("ios", "android", "web"),
        runtime_permission={"ios": "NSLocationWhenInUseUsageDescription", "android": "ACCESS_COARSE_LOCATION"},
        purposes=("context_place_detection",),
        retention_days=7,
    ),
    # -------- Cloud storage --------
    _cap(
        id="cloud_storage.read",
        connector_domain="cloud_storage",
        verb="read",
        display_name="Leggi file su cloud",
        description="Accede a documenti (fatture, contratti, ricevute) archiviati su Drive/iCloud.",
        data_categories=("documents",),
        sensitivity="sensitive",
        requires_oauth=True,
        purposes=("document_extraction",),
        default_status="planned",
    ),
    # -------- Notifications (system, not a data source per se) --------
    _cap(
        id="notifications.deliver",
        connector_domain="notifications",
        verb="deliver",
        display_name="Invia notifiche",
        description="Recapita promemoria e insight sul dispositivo.",
        data_categories=("prompts",),
        sensitivity="public",
        runtime_permission={"ios": "NSUserNotificationsUsageDescription", "android": "POST_NOTIFICATIONS"},
        purposes=("delivery",),
    ),
)

# Public API is a tuple; consumers get an immutable, ordered view.
CAPABILITIES: Tuple[Dict[str, Any], ...] = _CAPABILITIES

_BY_ID: Dict[str, Dict[str, Any]] = {c["id"]: c for c in _CAPABILITIES}
assert len(_BY_ID) == len(_CAPABILITIES), "duplicate capability id in registry"


def capability_by_id(cap_id: str) -> Optional[Dict[str, Any]]:
    """Return the capability dict (immutable) or None."""
    return _BY_ID.get(cap_id)


def capabilities_for_connector(connector_domain: str) -> List[Dict[str, Any]]:
    """All capabilities that belong to a given connector domain."""
    return [c for c in _CAPABILITIES if c["connector_domain"] == connector_domain]


def as_dict(cap: Dict[str, Any]) -> Dict[str, Any]:
    """Deep-mutable serialization for JSON responses."""
    out = dict(cap)
    if isinstance(out.get("runtime_permission"), MappingProxyType):
        out["runtime_permission"] = dict(out["runtime_permission"])
    out["data_categories"] = list(out.get("data_categories") or [])
    out["platforms"] = list(out.get("platforms") or [])
    out["purposes"] = list(out.get("purposes") or [])
    return out
