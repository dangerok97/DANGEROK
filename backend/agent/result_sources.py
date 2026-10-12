"""Whether an Opportunity still permits surfacing its already produced work.

Completion resolves its source as part of the normal lifecycle. Resolution
therefore differs from a later dismissal, withdrawal or expiry. This is only
a source-validity fence; it never decides that a result deserves attention.
"""
from datetime import datetime, timezone

from agent.memory_fence import MemorySourcesUnavailable


async def opportunity_result_current(db, owner_id: str, goal, *, now=None) -> bool:
    """Use the same owned source check for Home and final-result delivery.

Unavailable storage is not evidence of withdrawal: callers must retain a
recoverable handoff instead of consuming it as a known stale result.
"""
    if goal.owner_id != owner_id:
        return False
    if not goal.opportunity_id:
        return True
    try:
        source = await db.opportunities.find_one({
            "owner_id": owner_id, "id": goal.opportunity_id,
        }, {"_id": 0, "status": 1, "valid_until": 1})
    except Exception as exc:
        raise MemorySourcesUnavailable("opportunity_source_check_unavailable") from exc
    if not source or source.get("status") in ("dismissed", "suppressed", "expired"):
        return False
    # Preserve the existing Delivery timestamp contract, including legacy
    # sources without a timezone-bearing deadline.
    from agent.service import _aware_wait_until

    deadline = _aware_wait_until(source.get("valid_until"))
    return deadline is None or deadline > (now or datetime.now(timezone.utc))
