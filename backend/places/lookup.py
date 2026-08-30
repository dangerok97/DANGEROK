"""
Turning an address somebody typed into a place on a map.

Configuration only, for now: this says whether the capability exists and can
answer one question about it. The flow that uses it — autocomplete while
typing, picking a result, dropping a pin — is the next piece of work, and
building it before the key was known to work would have been building on a
guess.

Same shape as `routing.py` deliberately: provider and key come from the
environment, an unconfigured deployment says so instead of pretending, and
nothing here knows what any of these places mean to anybody.

The key is server-side. Places (New) allows a much larger surface than a map
tile does, so it stays behind the backend and never reaches a browser.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PROVIDER = "google_places_new"
KEY_ENV = "PLACES_API_KEY"

AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"


def _key() -> str:
    return (os.environ.get(KEY_ENV) or "").strip()


def capabilities() -> Dict[str, Any]:
    """What this deployment can do with an address, stated plainly."""
    available = bool(_key())
    return {
        "places_available": available,
        "places_provider": PROVIDER if available else None,
        "why_unavailable": (
            None if available else f"nessuna chiave Places configurata ({KEY_ENV})"
        ),
    }


async def suggest(
    query: str,
    *,
    language: str = "it",
    region: Optional[str] = None,
    session_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Address suggestions for what somebody has typed so far.

    Returns `available: False` when there is no key — never an empty list
    dressed up as "no results", which would tell somebody their address does
    not exist when the truth is that nobody asked.
    """
    key = _key()
    if not key:
        return {"available": False, **capabilities()}

    typed = (query or "").strip()
    if len(typed) < 3:
        # Below this a suggestion is noise and a billed request.
        return {"available": True, "suggestions": [], "too_short": True}

    payload: Dict[str, Any] = {"input": typed, "languageCode": language}
    if region:
        payload["regionCode"] = region
    # One token covers every keystroke of a single search plus the detail call
    # that follows, and Google bills the group as one lookup instead of eight.
    if session_token:
        payload["sessionToken"] = session_token

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                AUTOCOMPLETE_URL,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": key,
                    "X-Goog-FieldMask": (
                        "suggestions.placePrediction.placeId,"
                        "suggestions.placePrediction.text,"
                        "suggestions.placePrediction.structuredFormat"
                    ),
                },
                content=json.dumps(payload),
            )
    except Exception as e:
        logger.info("places soft-fail: %s", type(e).__name__)
        return {"available": False, "why_unavailable": "il servizio non ha risposto"}

    if response.status_code != 200:
        return {
            "available": False,
            "why_unavailable": f"il servizio ha risposto {response.status_code}",
        }

    out: List[Dict[str, Any]] = []
    for item in (response.json() or {}).get("suggestions") or []:
        prediction = item.get("placePrediction") or {}
        structured = prediction.get("structuredFormat") or {}
        out.append(
            {
                "place_id": prediction.get("placeId"),
                "text": (prediction.get("text") or {}).get("text"),
                "primary": (structured.get("mainText") or {}).get("text"),
                "secondary": (structured.get("secondaryText") or {}).get("text"),
            }
        )
    return {"available": True, "suggestions": out[:8]}


async def resolve(
    place_id: str, *, language: str = "it", session_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    The address and the point behind one suggestion.

    The field mask asks for four things and no more. Places (New) will happily
    return opening hours, photographs and reviews, and every extra field is
    billed and none of them are anybody's business here: a place needs a name
    somebody can read and a point on the earth.
    """
    key = _key()
    if not key:
        return {"available": False, **capabilities()}
    if not (place_id or "").strip():
        return {"available": False, "why_unavailable": "nessun luogo indicato"}

    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "id,formattedAddress,location,addressComponents",
    }
    params = {"languageCode": language}
    if session_token:
        params["sessionToken"] = session_token

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                DETAILS_URL.format(place_id=place_id.strip()),
                headers=headers,
                params=params,
            )
    except Exception as e:
        logger.info("places resolve soft-fail: %s", type(e).__name__)
        return {"available": False, "why_unavailable": "il servizio non ha risposto"}

    if response.status_code != 200:
        return {
            "available": False,
            "why_unavailable": f"il servizio ha risposto {response.status_code}",
        }

    data = response.json() or {}
    location = data.get("location") or {}
    return {
        "available": True,
        "place_id": data.get("id") or place_id,
        "address": data.get("formattedAddress"),
        "locality": _locality(data.get("addressComponents") or []),
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
    }


def _locality(components: List[Dict[str, Any]]) -> str:
    """
    The town, in the words the person would use for it.

    Falls back through the administrative levels rather than inventing one:
    somewhere with no locality is better described by its province than by a
    guess.
    """
    wanted = ("locality", "postal_town", "administrative_area_level_3",
              "administrative_area_level_2")
    by_type: Dict[str, str] = {}
    for component in components:
        for kind in component.get("types") or []:
            by_type.setdefault(kind, component.get("longText") or "")
    for kind in wanted:
        if by_type.get(kind):
            return by_type[kind][:160]
    return ""
