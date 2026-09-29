"""One-off Mapbox Search Box lookup for a named destination.

The result is used immediately for a route preview. It is never saved as a
Life Place: a search result is not a statement about someone's routine.
"""

from __future__ import annotations

import logging
import math
import os
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
            "limit": 3, "auto_complete": "false",
            "proximity": f"{origin['longitude']},{origin['latitude']}",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.mapbox.com/search/searchbox/v1/forward", params=params)
        if response.status_code != 200:
            return None
        features = (response.json() or {}).get("features") or []
        if not features:
            return None
        query = name.strip().casefold()

        def matches(item: Dict[str, Any]) -> bool:
            properties = item.get("properties") or {}
            return (str(properties.get("name") or "").casefold() == query
                    or str(properties.get("full_address") or "").casefold() == query)

        if not matches(features[0]) or any(matches(f) for f in features[1:]):
            return None
        first = features[0]
        properties = first.get("properties") or {}
        point = (properties.get("coordinates") or {})
        routable = point.get("routable_points") or []
        if routable and isinstance(routable[0], dict):
            point = routable[0]
        lat, lon = float(point["latitude"]), float(point["longitude"])
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
