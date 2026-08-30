"""
Handing a destination to whatever app the person actually navigates with.

ORA does not draw a route. It works out *where* — which is the part that needs
to know the person — and then gets out of the way, because turn-by-turn is a
solved problem owned by apps that do it well and are already installed.

No default is assumed. Somebody who uses Waze and is sent to Google Maps every
time has been told, politely, that their preference does not count; so the
first time ORA asks, and after that it remembers.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import quote

# The apps ORA can hand off to. Order is presentation, not preference: the
# person's choice is stored, and until they make one there is no winner.
NAVIGATION_APPS: Dict[str, Dict[str, str]] = {
    "google_maps": {"label": "Google Maps"},
    "apple_maps": {"label": "Apple Maps"},
    "waze": {"label": "Waze"},
}

TravelMode = str  # driving | walking | transit | cycling — passed through, not policed


def available_apps(platform: str = "web") -> List[Dict[str, str]]:
    """
    What can be offered here.

    Apple Maps is not offered on Android, and a choice that cannot open is not
    a choice — it is a dead end with a logo on it.
    """
    names = list(NAVIGATION_APPS)
    if platform == "android":
        names = [n for n in names if n != "apple_maps"]
    return [{"id": n, "label": NAVIGATION_APPS[n]["label"]} for n in names]


def navigation_url(
    app: str,
    *,
    latitude: float,
    longitude: float,
    label: str = "",
    origin: Optional[Dict[str, float]] = None,
    mode: TravelMode = "driving",
) -> Optional[str]:
    """
    The official deep link for one app, or None if we do not know it.

    Coordinates rather than a name wherever possible: a name has to be searched
    for and can land on the wrong branch of the right shop, while a pair of
    numbers is the place the person confirmed.
    """
    destination = f"{latitude},{longitude}"
    start = (
        f"{origin['latitude']},{origin['longitude']}"
        if origin and "latitude" in origin and "longitude" in origin
        else None
    )

    if app == "google_maps":
        url = (
            "https://www.google.com/maps/dir/?api=1"
            f"&destination={quote(destination)}"
            f"&travelmode={quote(_google_mode(mode))}"
        )
        if start:
            url += f"&origin={quote(start)}"
        return url

    if app == "apple_maps":
        url = f"https://maps.apple.com/?daddr={quote(destination)}&dirflg={_apple_flag(mode)}"
        if start:
            url += f"&saddr={quote(start)}"
        if label:
            url += f"&q={quote(label[:60])}"
        return url

    if app == "waze":
        # Waze routes from wherever the driver is; an origin is not part of it.
        return f"https://waze.com/ul?ll={quote(destination)}&navigate=yes"

    return None


def _google_mode(mode: TravelMode) -> str:
    return {
        "driving": "driving",
        "walking": "walking",
        "transit": "transit",
        "cycling": "bicycling",
    }.get(mode, "driving")


def _apple_flag(mode: TravelMode) -> str:
    return {"driving": "d", "walking": "w", "transit": "r", "cycling": "w"}.get(mode, "d")


def handoff(
    *,
    latitude: float,
    longitude: float,
    label: str = "",
    origin: Optional[Dict[str, float]] = None,
    mode: TravelMode = "driving",
    preferred_app: Optional[str] = None,
    platform: str = "web",
) -> Dict[str, object]:
    """
    Everything the client needs to start navigating, or to ask first.

    When a preference exists, one link. When it does not, every link and a
    question — and the client is the one that asks, because that is a moment in
    a conversation rather than a server decision.
    """
    apps = available_apps(platform)
    valid = {a["id"] for a in apps}

    if preferred_app in valid:
        url = navigation_url(
            preferred_app, latitude=latitude, longitude=longitude,
            label=label, origin=origin, mode=mode,
        )
        return {
            "needs_choice": False,
            "app": preferred_app,
            "url": url,
            "destination_label": label,
        }

    return {
        "needs_choice": True,
        "options": [
            {
                "id": a["id"],
                "label": a["label"],
                "url": navigation_url(
                    a["id"], latitude=latitude, longitude=longitude,
                    label=label, origin=origin, mode=mode,
                ),
            }
            for a in apps
        ],
        "destination_label": label,
    }
