"""One-off Mapbox Search Box lookup for a named destination.

The result is used immediately for a route preview. It is never saved as a
Life Place: a search result is not a statement about someone's routine.
"""

from __future__ import annotations

import logging
import math
import os
import unicodedata
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def preview_destination(name: str, origin: Dict[str, float]) -> Optional[Dict[str, Any]]:
    """Use coordinates only for a unique name match; otherwise let Maps ask."""
    from places.routing import configured_provider, KEY_ENV

    if configured_provider() != "mapbox" or not (3 <= len(name) <= 160):
        return None
    try:
        import httpx

        params = {
            "q": name, "access_token": os.environ[KEY_ENV].strip(), "language": "it",
            "limit": 5, "auto_complete": "false",
            "proximity": f"{origin['longitude']},{origin['latitude']}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.mapbox.com/search/searchbox/v1/forward", params=params)
        if response.status_code != 200:
            return None
        features = (response.json() or {}).get("features") or []
        if not features:
            return None
        def normal(text: str) -> str:
            return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

        query = normal(name)

        def matches(item: Dict[str, Any]) -> bool:
            properties = item.get("properties") or {}
            return any(normal(str(properties.get(key) or "")) == query
                       for key in ("name", "name_preferred", "full_address"))

        # Search Box ranks by proximity and relevance. A nearby business can
        # precede an exact landmark, and several POI records can describe the
        # same entrance. Require one geographic cluster of exact matches,
        # rather than requiring feature 0 to be exact and rejecting duplicates.
        exact = [feature for feature in features if matches(feature)]
        if not exact:
            logger.info("public destination lookup: no exact name in %d results", len(features))
            return None

        def coordinates(feature: Dict[str, Any]) -> tuple[float, float] | None:
            point = (feature.get("properties") or {}).get("coordinates") or {}
            if not point and feature.get("geometry", {}).get("coordinates"):
                lon, lat = feature["geometry"]["coordinates"][:2]
            else:
                lat, lon = point.get("latitude"), point.get("longitude")
            try:
                lat, lon = float(lat), float(lon)
                if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
                    return lat, lon
            except (TypeError, ValueError):
                pass
            return None

        exact = [feature for feature in exact if coordinates(feature) is not None]
        if not exact:
            return None
        first = exact[0]
        first_lat, first_lon = coordinates(first)
        # Rough upper bound in metres. At 250 m duplicate POIs are the same
        # landmark; another town's homonym still needs the person's choice.
        if any(math.hypot((coordinates(f)[0] - first_lat) * 111_000,
                          (coordinates(f)[1] - first_lon) * 111_000 * math.cos(math.radians(first_lat))) > 250
               for f in exact[1:]):
            logger.info("public destination lookup: distinct exact homonyms")
            return None
        properties = first.get("properties") or {}
        point = properties.get("coordinates") or {}
        routable = point.get("routable_points") or []
        if routable and isinstance(routable[0], dict):
            point = routable[0]
        lat, lon = float(point.get("latitude", first_lat)), float(point.get("longitude", first_lon))
        if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return {
            "latitude": lat, "longitude": lon,
            "label": str(properties.get("name") or name)[:120],
            "context": str(properties.get("place_formatted") or "")[:120],
        }
    except Exception as e:
        logger.info("public destination lookup soft-fail: %s", type(e).__name__)
        return None
