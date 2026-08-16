"""Generic human place-label resolution from reverse-geocode address parts.

No city-specific rules. Never invents localities missing from provider evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

# Accuracy gates — GPS precision ≠ semantic precision.
# Poor GPS → do not claim micro-locality even if the provider returns one.
ACCURACY_ADMIN_ONLY_M = 2000.0  # only city/town/municipality
ACCURACY_ALLOW_HAMLET_M = 150.0  # hamlet only when fix is tight

# Bump when place-resolution semantics change so CURRENT GPS can keep coords
# while semantic labels are re-derived (no wipe; no forced new browser prompt).
PLACE_RESOLVER_VERSION = "v2_locality_settlement"

# Settlement-scale locality first (recognizable place names), then finer urban fabric.
# Do NOT prefer neighbourhood/quarter over village — that invents false "most precise"
# usefulness and loses the settlement people actually name.
_LOCALITY_KEYS: Sequence[str] = (
    "village",
    "suburb",
    "city_district",
    "neighbourhood",
    "neighborhood",  # US spelling if present
    "quarter",
)

# Micro-places — use only when no better locality and accuracy is good
_MICRO_KEYS: Sequence[str] = ("hamlet",)

# Administrative settlement / municipality tier
_ADMIN_KEYS: Sequence[str] = (
    "city",
    "town",
    "municipality",
)

_REGION_KEYS: Sequence[str] = ("state", "region", "province", "county")
_COUNTRY_KEYS: Sequence[str] = ("country",)


def _norm(val: Any) -> Optional[str]:
    if not isinstance(val, str):
        return None
    s = val.strip()
    if not s or len(s) > 80:
        return None
    return s


def _first(addr: Dict[str, Any], keys: Sequence[str]) -> Optional[str]:
    for k in keys:
        v = _norm(addr.get(k))
        if v:
            return v
    return None


def _all_present(addr: Dict[str, Any], keys: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for k in keys:
        v = _norm(addr.get(k))
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


@dataclass
class ResolvedPlace:
    """Minimized semantic place — never includes street/housenumber/raw provider dump."""

    display_label: Optional[str] = None
    locality: Optional[str] = None
    municipality: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None
    # Evidence transparency for tests / DEV (not for user-facing AI dump)
    source_fields: Dict[str, str] = field(default_factory=dict)
    precision: str = "unknown"  # locality | municipality | region | none

    def as_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.display_label:
            d["display_label"] = self.display_label
        if self.locality:
            d["locality"] = self.locality
        if self.municipality:
            d["municipality"] = self.municipality
        if self.region:
            d["region"] = self.region
        if self.country:
            d["country"] = self.country
        if self.precision and self.precision != "unknown":
            d["label_precision"] = self.precision
        return d


def resolve_place_from_address(
    addr: Optional[Dict[str, Any]],
    *,
    accuracy_meters: Optional[float] = None,
    display_name: Optional[str] = None,
) -> ResolvedPlace:
    """
    Choose a useful human display label from provider address hierarchy.

    Rules (generic):
    - Prefer settlement locality (suburb/village/…) when distinct from municipality
      and GPS accuracy is not too poor.
    - Do not blindly pick the smallest field (hamlet loses to village/suburb).
    - If only admin city/town/municipality exists → that is the display label.
    - Never invent a locality absent from addr.
    """
    addr = dict(addr or {})
    place = ResolvedPlace()

    locality_candidates = _all_present(addr, _LOCALITY_KEYS)
    micro_candidates = _all_present(addr, _MICRO_KEYS)
    admin = _first(addr, _ADMIN_KEYS)
    # County often duplicates municipality name in IT; keep as region fallback only
    region = _first(addr, ("state", "region", "province")) or None
    county = _norm(addr.get("county"))
    if not region and county and (not admin or county.lower() != admin.lower()):
        region = county
    country = _first(addr, _COUNTRY_KEYS)

    place.municipality = admin
    place.region = region
    place.country = country

    # Record which provider keys existed (values only for selected tiers)
    for k in list(_LOCALITY_KEYS) + list(_MICRO_KEYS) + list(_ADMIN_KEYS):
        v = _norm(addr.get(k))
        if v:
            place.source_fields[k] = v

    admin_only = (
        accuracy_meters is not None and float(accuracy_meters) > ACCURACY_ADMIN_ONLY_M
    )
    allow_hamlet = accuracy_meters is None or float(accuracy_meters) <= ACCURACY_ALLOW_HAMLET_M

    locality: Optional[str] = None
    if not admin_only:
        if locality_candidates:
            # Prefer first non-duplicate-of-admin in locality preference order
            for cand in locality_candidates:
                if not admin or cand.lower() != admin.lower():
                    locality = cand
                    break
            if locality is None and locality_candidates:
                locality = locality_candidates[0]
        elif micro_candidates and allow_hamlet:
            for cand in micro_candidates:
                if not admin or cand.lower() != admin.lower():
                    locality = cand
                    break

    place.locality = locality

    # Display label
    if locality and admin and locality.lower() != admin.lower():
        place.display_label = locality
        place.precision = "locality"
    elif locality:
        place.display_label = locality
        place.precision = "locality"
    elif admin:
        place.display_label = admin
        place.precision = "municipality"
    else:
        # Conservative fallback: first token of display_name if it looks like a place
        token = (display_name or "").split(",")[0].strip() if display_name else ""
        if token and len(token) <= 80:
            place.display_label = token
            place.precision = "municipality"
        else:
            place.precision = "none"

    return place


async def nominatim_reverse_place(
    lat: float,
    lon: float,
    *,
    accuracy_meters: Optional[float] = None,
) -> Optional[ResolvedPlace]:
    """
    Reverse-geocode to structured place parts.

    Uses zoom=16 so locality fields (village/suburb/…) can appear.
    Soft-fail — never invents. Does not return street/house numbers to callers.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lon_f <= 180.0):
        return None
    try:
        import httpx

        url = "https://nominatim.openstreetmap.org/reverse"
        headers = {"User-Agent": "ORA-Location/2.7.1 (local-dev; contact=dev@ora.local)"}
        params = {
            "lat": lat_f,
            "lon": lon_f,
            "format": "json",
            # 16 ≈ settlement / suburb — exposes village without requiring street zoom
            "zoom": 16,
            "addressdetails": 1,
        }
        async with httpx.AsyncClient(timeout=6.0, headers=headers) as client:
            r = await client.get(url, params=params)
            if r.status_code != 200:
                return None
            data = r.json() or {}
            addr = data.get("address") or {}
            if not isinstance(addr, dict):
                return None
            # Strip precise address lines before resolving (privacy)
            scrubbed = {
                k: v
                for k, v in addr.items()
                if k
                not in (
                    "house_number",
                    "road",
                    "pedestrian",
                    "footway",
                    "path",
                    "building",
                    "postcode",
                )
            }
            return resolve_place_from_address(
                scrubbed,
                accuracy_meters=accuracy_meters,
                display_name=data.get("display_name"),
            )
    except Exception:
        return None
