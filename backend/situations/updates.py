"""Only evidence-backed *consequences* of temporary Situations reach Home.

A monitoring Goal, calendar checkpoint or generic progress line is NOT news.
The AI that interpreted a Situation already chose what is worth saying in the
visibility ledger; this read-only projection verifies that the evidence is
still fresh, the Situation still exists, and the last user change did not
invalidate it. One Situation -> at most one current update, across all goals.
No keyword routing for laundry, plants, medication or other user topics.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from typing import Any


MAX_CANDIDATES = 30
MAX_VISIBLE = 3
RECENT_HOURS = 6
WEATHER_EVIDENCE_MINUTES = 100

_NOT_AN_OUTCOME = re.compile(
    r"^\s*(?:sto\s+(?:lavorando|monitorando|verificando)|"
    r"ho\s+(?:avviato|programmato|pianificato|controllato)\s+(?:un\s+)?(?:controllo|monitoraggio)|"
    r"mi\s+manca\s+un['’]?\s*informazione\s+che\s+sai\s+solo\s+tu|"
    r"capire\s+quando\s+la\s+situazione)\b",
    re.IGNORECASE,
)


def _when(raw: Any) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _is_material_line(text: str) -> bool:
    value = " ".join(str(text or "").split()).strip()
    if not 18 <= len(value) <= 200 or _NOT_AN_OUTCOME.search(value):
        return False
    return True


def _real_observation(item: dict, *, now: datetime, situation_changed: datetime | None):
    provenance = item.get("provenance")
    if not isinstance(provenance, dict):
        return None
    if provenance.get("source_class") in (None, "simulated"):
        return None
    if provenance.get("freshness") == "stale":
        return None
    stamp = _when(item.get("observed_at") or provenance.get("observed_at"))
    if not stamp or stamp > now + timedelta(minutes=5):
        return None
    if situation_changed and stamp < situation_changed:
        return None
    # Forecasts change faster than most other background facts. Never display
    # a yesterday forecast as an action that is still urgent right now.
    capability = str(provenance.get("capability") or "")
    max_age = (timedelta(minutes=WEATHER_EVIDENCE_MINUTES)
               if capability.startswith("weather.") else timedelta(hours=RECENT_HOURS))
    if now - stamp > max_age:
        return None
    if item.get("expires_at") and _when(item["expires_at"]) and _when(item["expires_at"]) <= now:
        return None
    return stamp


async def current_situation_updates(db, owner_id: str, *, now: datetime | None = None) -> list[dict]:
    """Project verified, recent AI consequences; never start a job on Home read."""
    moment = now or datetime.now(timezone.utc)
    start = (moment - timedelta(hours=RECENT_HOURS)).isoformat()
    rows = await db.agent_updates.find(
        {"owner_id": owner_id,
         "outcome": {"$in": ["inform_user", "requires_attention"]},
         "moment_type": {"$in": ["action_now", "outcome_estimate"]},
         "at": {"$gte": start, "$lte": moment.isoformat()}},
        {"_id": 0},
    ).sort("at", -1).to_list(MAX_CANDIDATES)

    results: list[dict] = []
    used_situations: set[str] = set()
    for row in rows:
        headline = " ".join(str(row.get("headline") or "").split())[:200]
        if not _is_material_line(headline):
            continue
        goal_id = str(row.get("goal_id") or "")
        if not goal_id:
            continue
        goal = await db.agent_goals.find_one(
            {"owner_id": owner_id, "id": goal_id,
             "status": {"$in": ["active", "waiting", "completed"]}},
            {"_id": 0, "id": 1, "source_refs": 1},
        )
        if not goal:
            continue
        sources = [
            ref.split(":", 1)[1] for ref in goal.get("source_refs", [])
            if isinstance(ref, str) and ref.startswith("situation:")
        ]
        if len(sources) != 1:
            # No guessing which of several Situations this result concerns.
            continue
        sid = sources[0]
        if not sid or sid in used_situations:
            continue
        situation = await db.situations.find_one(
            {"user_id": owner_id, "id": sid,
             "status": {"$in": ["active", "changed"]}},
            {"_id": 0, "summary": 1, "created_at": 1, "updated_at": 1,
             "revision": 1, "status": 1},
        )
        if not situation:
            continue

        emitted = _when(row.get("at"))
        changed = _when(situation.get("updated_at"))
        if not emitted or (changed and emitted < changed):
            continue
        refs = [str(ref) for ref in row.get("refs", []) if isinstance(ref, str)]
        if not refs:
            continue
        evidence = await db.agent_evidence.find(
            {"owner_id": owner_id, "goal_id": goal_id,
             "id": {"$in": refs}},
            {"_id": 0, "id": 1, "claim": 1, "observed_at": 1,
             "expires_at": 1, "provenance": 1},
        ).sort("observed_at", -1).to_list(12)
        verified = []
        for item in evidence:
            stamp = _real_observation(item, now=moment, situation_changed=changed)
            if stamp:
                verified.append((stamp, item))
        if not verified:
            continue
        stamp, observed = max(verified, key=lambda pair: pair[0])
        summary = " ".join(str(situation.get("summary") or "").split())[:200]
        if not summary:
            continue

        results.append({
            "id": "su_" + hashlib.sha256(f"{owner_id}:{sid}".encode()).hexdigest()[:20],
            "situation_id": sid,
            "summary": summary,
            "headline": headline,
            "evidence_summary": " ".join(str(observed.get("claim") or "").split())[:200],
            "evidence_at": stamp.isoformat(),
            "source_label": "Controllo recente di ORA",
            "created_at": str(situation.get("created_at") or ""),
            "revision": int(situation.get("revision") or 1),
        })
        used_situations.add(sid)
        if len(results) >= MAX_VISIBLE:
            break
    return results
