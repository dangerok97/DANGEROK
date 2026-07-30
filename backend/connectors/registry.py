"""
Connector Registry — hardcoded, versioned STUB entries.

In this iteration NO CONNECTOR performs a real 3rd-party call. Each entry
declares:
  - id, category, provider, display name;
  - platform support (ios/android/web);
  - which capabilities it needs (must exist in the permissions registry);
  - runtime requirements (oauth flow / native permission / special access);
  - status: "stub" (planned, not implemented) | "planned" (design done) |
            "available" (implemented) | "disabled".

Endpoints of type "connect", "sync", "webhook", "poll" are INTENTIONALLY
absent: they will be added when we implement each connector for real.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Dict, List, Optional, Tuple

from permissions import capability_by_id

CONNECTOR_REGISTRY_VERSION = "1.0.0"


def _conn(
    *,
    id: str,
    category: str,
    provider: str,
    display_name: str,
    description: str,
    platforms: Tuple[str, ...] = ("ios", "android", "web"),
    required_capabilities: Tuple[str, ...] = (),
    optional_capabilities: Tuple[str, ...] = (),
    auth_flow: Optional[str] = None,  # oauth2 | native_permission | special_access | none
    special_access: Optional[str] = None,
    supports_multi_instance: bool = True,
    status: str = "stub",  # stub | planned | available | disabled
    docs_url: Optional[str] = None,
    icon_key: Optional[str] = None,
) -> Dict[str, Any]:
    return MappingProxyType({
        "id": id,
        "category": category,
        "provider": provider,
        "display_name": display_name,
        "description": description,
        "platforms": tuple(platforms),
        "required_capabilities": tuple(required_capabilities),
        "optional_capabilities": tuple(optional_capabilities),
        "auth_flow": auth_flow,
        "special_access": special_access,
        "supports_multi_instance": bool(supports_multi_instance),
        "status": status,
        "docs_url": docs_url,
        "icon_key": icon_key,
    })


_CONNECTORS: Tuple[Dict[str, Any], ...] = (
    # ------- Calendar -------
    _conn(
        id="calendar_google",
        category="calendar",
        provider="google",
        display_name="Google Calendar",
        description="Legge eventi da un account Google (multi-account supportato).",
        required_capabilities=("calendar.read",),
        optional_capabilities=("calendar.write",),
        auth_flow="oauth2",
        icon_key="calendar_google",
    ),
    _conn(
        id="calendar_apple",
        category="calendar",
        provider="apple",
        display_name="Apple Calendar",
        description="Legge eventi dal calendario iOS/macOS del dispositivo.",
        platforms=("ios",),
        required_capabilities=("calendar.read",),
        auth_flow="native_permission",
        supports_multi_instance=False,
        icon_key="calendar_apple",
    ),
    _conn(
        id="calendar_outlook",
        category="calendar",
        provider="microsoft",
        display_name="Outlook Calendar",
        description="Legge eventi dal calendario Microsoft 365 / Outlook.",
        required_capabilities=("calendar.read",),
        auth_flow="oauth2",
        icon_key="calendar_outlook",
    ),
    # ------- Mail -------
    _conn(
        id="mail_gmail",
        category="mail",
        provider="google",
        display_name="Gmail",
        description="Estrae bollette, ricevute e conferme dalla casella Gmail.",
        required_capabilities=("mail.metadata",),
        optional_capabilities=("mail.read",),
        auth_flow="oauth2",
        icon_key="mail_gmail",
    ),
    _conn(
        id="mail_outlook",
        category="mail",
        provider="microsoft",
        display_name="Outlook Mail",
        description="Estrae bollette, ricevute e conferme dalla casella Outlook.",
        required_capabilities=("mail.metadata",),
        optional_capabilities=("mail.read",),
        auth_flow="oauth2",
        icon_key="mail_outlook",
    ),
    # ------- Messaging -------
    _conn(
        id="messaging_whatsapp",
        category="messaging",
        provider="whatsapp",
        display_name="WhatsApp",
        description="Individua conversazioni con risposte in sospeso.",
        platforms=("ios", "android"),
        required_capabilities=("messaging.read",),
        auth_flow="special_access",
        special_access="whatsapp_business_api",
        status="planned",
        icon_key="messaging_whatsapp",
    ),
    # ------- Health -------
    _conn(
        id="health_apple",
        category="health",
        provider="apple",
        display_name="Apple Health",
        description="Legge passi, sonno e allenamenti per contesto sull'energia.",
        platforms=("ios",),
        required_capabilities=("health.read",),
        auth_flow="special_access",
        special_access="apple_health_share",
        supports_multi_instance=False,
        icon_key="health_apple",
    ),
    _conn(
        id="health_google_fit",
        category="health",
        provider="google",
        display_name="Google Fit",
        description="Legge passi, sonno e allenamenti da Google Fit / Health Connect.",
        platforms=("android",),
        required_capabilities=("health.read",),
        auth_flow="oauth2",
        icon_key="health_google",
    ),
    # ------- Banking -------
    _conn(
        id="banking_psd2",
        category="banking",
        provider="open_banking",
        display_name="Banca (PSD2)",
        description="Recupera transazioni da un conto bancario europeo (PSD2 AIS).",
        required_capabilities=("banking.read",),
        auth_flow="special_access",
        special_access="psd2_ais",
        status="planned",
        icon_key="banking_generic",
    ),
    # ------- Contacts -------
    _conn(
        id="contacts_device",
        category="contacts",
        provider="device",
        display_name="Rubrica del dispositivo",
        description="Risolve nomi in contatti salvati per rilevare risposte in sospeso.",
        platforms=("ios", "android"),
        required_capabilities=("contacts.read",),
        auth_flow="native_permission",
        supports_multi_instance=False,
        icon_key="contacts_device",
    ),
    # ------- Location -------
    _conn(
        id="location_device",
        category="location",
        provider="device",
        display_name="Posizione del dispositivo",
        description="Solo posizione approssimativa 'sei a casa/ufficio'.",
        required_capabilities=("location.read",),
        auth_flow="native_permission",
        supports_multi_instance=False,
        icon_key="location_device",
    ),
    # ------- Cloud storage -------
    _conn(
        id="cloud_google_drive",
        category="cloud_storage",
        provider="google",
        display_name="Google Drive",
        description="Legge documenti (fatture, contratti) da una cartella dedicata su Drive.",
        required_capabilities=("cloud_storage.read",),
        auth_flow="oauth2",
        status="planned",
        icon_key="cloud_drive",
    ),
    _conn(
        id="cloud_icloud",
        category="cloud_storage",
        provider="apple",
        display_name="iCloud Drive",
        description="Legge documenti da una cartella dedicata su iCloud Drive.",
        platforms=("ios",),
        required_capabilities=("cloud_storage.read",),
        auth_flow="native_permission",
        status="planned",
        icon_key="cloud_icloud",
    ),
    # ------- Notifications (delivery only) -------
    _conn(
        id="notifications_push",
        category="notifications",
        provider="device",
        display_name="Notifiche push",
        description="Consegna promemoria e insight sul dispositivo.",
        required_capabilities=("notifications.deliver",),
        auth_flow="native_permission",
        supports_multi_instance=False,
        icon_key="notifications_push",
    ),
)


# Validate at import time: every declared required capability MUST exist in
# the permissions registry. Fail fast on drift.
for _c in _CONNECTORS:
    for _cap_id in list(_c["required_capabilities"]) + list(_c["optional_capabilities"]):
        if capability_by_id(_cap_id) is None:
            raise RuntimeError(
                f"Connector registry drift: connector={_c['id']!r} references "
                f"unknown capability {_cap_id!r}. Update the permissions registry."
            )


CONNECTORS: Tuple[Dict[str, Any], ...] = _CONNECTORS
_BY_ID: Dict[str, Dict[str, Any]] = {c["id"]: c for c in _CONNECTORS}
assert len(_BY_ID) == len(_CONNECTORS), "duplicate connector id in registry"


def connector_by_id(cid: str) -> Optional[Dict[str, Any]]:
    return _BY_ID.get(cid)


def connectors_for_platform(platform: str) -> List[Dict[str, Any]]:
    return [c for c in _CONNECTORS if platform in c["platforms"]]


def as_dict(conn: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(conn)
    out["platforms"] = list(out["platforms"])
    out["required_capabilities"] = list(out["required_capabilities"])
    out["optional_capabilities"] = list(out["optional_capabilities"])
    return out
