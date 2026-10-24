"""Human update cards for genuinely monitored temporary situations.

Expose only owner-scoped, persisted Situation and scheduled follow-up facts.
No guessed weather, drying time, notification or physical outcome.
"""
from situations.followup import read_followup
from situations.repository import SituationRepository

UNINFORMATIVE = (
    "mi manca un'informazione che sai solo tu",
    # The goal-level placeholder written into every need (24/10: the ING card
    # showed it while the need itself asked about UnipolMove and TIBER OIL).
    "manca una cosa che sai solo tu",
    "serve il tuo via libera.",
    "mi serve una tua risposta per continuare",
    "serve il tuo via libera per procedere",
)


def concrete_need(need):
    for candidate in (
        getattr(need, "what_is_missing", ""),
        getattr(need, "summary", ""),
    ):
        value = str(candidate or "").strip()
        if value and not any(x in value.lower() for x in UNINFORMATIVE):
            return value[:300]
    return ""


_CONDITION_KEYS = ("temperature_c", "humidity_pct", "wind_kmh", "precipitation_mm", "rain_chance_max_pct")


async def latest_conditions(db, owner_id, goal_id):
    """Numbers from the most recent real weather read of this goal, or None.

    Only values the provider actually returned and that were stored with the
    owner-scoped evidence. Never a default, never an estimate.
    """
    try:
        rows = await db.agent_evidence.find(
            {"owner_id": owner_id, "goal_id": goal_id,
             "provenance.capability": "weather.read",
             "superseded": {"$ne": True},
             "measures": {"$exists": True, "$ne": {}}},
            {"_id": 0, "measures": 1, "observed_at": 1, "provenance.observed_at": 1},
        ).sort("observed_at", -1).to_list(8)
    except Exception:
        return None
    if not rows:
        return None

    # Rows of one read are stored milliseconds apart; the provider observation
    # time is what they share.
    def read_time(row):
        return str((row.get("provenance") or {}).get("observed_at") or row.get("observed_at") or "")

    latest = read_time(rows[0])
    merged = {}
    for row in rows:
        if read_time(row) != latest:
            continue
        for key, value in (row.get("measures") or {}).items():
            if key in _CONDITION_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
                merged.setdefault(key, value)
    return {**merged, "observed_at": latest} if merged else None


async def situation_card(db, owner_id, goal):
    if goal.source_kind not in ("situation_followup", "situation_initial_review"):
        return None
    refs = [str(ref).split(":", 1)[1] for ref in goal.source_refs
            if str(ref).startswith("situation:")]
    if len(refs) != 1:
        return {"inactive": True}
    situation = await SituationRepository(db).get(owner_id, refs[0])
    if not situation or situation.status not in ("active", "changed"):
        return {"inactive": True}
    tracking = await read_followup(db, owner_id, situation.id)
    if tracking.get("goal_id") and tracking["goal_id"] != goal.id:
        return {"inactive": True}
    # Read the *stored* tracking purpose/notification rule. A planned check is
    # not proof that it ran or that an expected physical state already occurred.
    return {
        "inactive": False,
        "situation": {
            "id": situation.id,
            "revision": situation.revision,
            "summary": situation.summary,
            "session_id": situation.session_id,
            "created_at": situation.created_at,
            # Physical start only when the person/trusted source established it.
            "started_at": situation.started_at or None,
            "location_label": situation.location_label or None,
            "conditions": await latest_conditions(db, owner_id, goal.id),
            "current_state": situation.current_state_summary or None,
            "expected_outcome": situation.expected_outcome_summary or None,
            "desired_outcome": tracking.get("desired_outcome"),
            "outcome": tracking.get("outcome"),
            "reason": situation.attention_intent or None,
            "tracking": situation.tracking_summary or None,
            "next_check_reason": situation.next_check_summary or None,
            "followup_status": tracking["status"],
            "monitor_diagnosis": tracking.get("diagnosis"),
            "last_schedule_error": tracking.get("last_schedule_error"),
            "last_schedule_attempt_at": tracking.get("last_schedule_attempt_at"),
            "next_check_at": tracking.get("next_check_at"),
            "next_check_label": tracking.get("next_check_label"),
            "last_checked_at": tracking.get("last_checked_at"),
            "last_result": tracking.get("last_result"),
            "notify_when": tracking.get("notify_when"),
            "purpose": tracking.get("purpose"),
        }
    }
