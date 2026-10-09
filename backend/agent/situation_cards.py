"""Human update cards for genuinely monitored temporary situations.

Expose only owner-scoped, persisted Situation and scheduled follow-up facts.
No guessed weather, drying time, notification or physical outcome.
"""
from situations.followup import read_followup
from situations.repository import SituationRepository

UNINFORMATIVE = (
    "mi manca un'informazione che sai solo tu",
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


async def situation_card(db, owner_id, goal):
    if goal.source_kind != "situation_followup":
        return None
    refs = [str(ref).split(":", 1)[1] for ref in goal.source_refs
            if str(ref).startswith("situation:")]
    if len(refs) != 1:
        return {"inactive": True}
    situation = await SituationRepository(db).get(owner_id, refs[0])
    if not situation or situation.status not in ("active", "changed"):
        return {"inactive": True}
    tracking = await read_followup(db, owner_id, situation.id)
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
            "current_state": situation.current_state_summary or None,
            "expected_outcome": situation.expected_outcome_summary or None,
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
