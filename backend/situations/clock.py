"""Presentation-only projection of persisted instants. Never reschedule a job."""
from datetime import datetime
from zoneinfo import ZoneInfo

_MONTHS = ("gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic")


def local_check_fields(value, timezone_name):
    """Return a local display of an aware timestamp; invalid inputs remain unknown."""
    try:
        instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if instant.tzinfo is None:
            return {}
        local = instant.astimezone(ZoneInfo(timezone_name))
    except (ValueError, TypeError, KeyError):
        return {}
    return {
        "next_check_at_local": local.isoformat(),
        "next_check_time_local": local.strftime("%H:%M"),
        "next_check_label": f"{local.day} {_MONTHS[local.month - 1]} {local.year}, {local:%H:%M}",
    }
