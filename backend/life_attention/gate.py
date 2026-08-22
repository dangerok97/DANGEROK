"""Deterministic attention gate (V2.9.3).

The model says what would help. This says what is allowed. It runs AFTER the
reasoning call and can only ever make the outcome QUIETER — a downgrade moves
left along silent ← defer ← home ← ask_user ← propose_action ← notify and can
never move right.

That one-way property is the whole point: it means no prompt, and no model
output, can grant ORA permission to interrupt someone. Every check here is a
deterministic fact (resolved clock, granted permission, measured volume,
recorded history), never a judgement.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from life_attention.models import DELIVERY_ORDER, DeliveryMode, is_quieter

# A decision this uncertain should not reach the user at all.
MIN_CONFIDENCE_TO_SPEAK = 0.45
# Interrupting with a push demands more than merely being worth showing.
MIN_CONFIDENCE_TO_NOTIFY = 0.75
MIN_UTILITY_TO_NOTIFY = 0.7
# Above this, speaking now costs more than the content is likely worth.
INTERRUPTION_COST_SOFT_CEILING = 0.6
INTERRUPTION_COST_HARD_CEILING = 0.85
# How often ORA may revisit the same corner of someone's life before the bar
# rises sharply.
REPEAT_SOFT_LIMIT = 2
REPEAT_HARD_LIMIT = 4
# Beyond this the user is clearly not receptive to this kind of item.
DISMISS_RATE_SUPPRESS = 0.7


def apply_system_gate(
    *,
    ai_delivery: DeliveryMode,
    confidence: float,
    utility: float,
    context: Dict[str, Any],
    times_already_raised: int,
    already_decided: bool = False,
) -> Tuple[DeliveryMode, List[str]]:
    """Return the permitted delivery mode and the reasons it was lowered.

    Never raises the AI's choice. `already_decided` short-circuits to silent:
    re-deciding an assessment batch that has already been evaluated would be a
    second chance to speak about the same thing.
    """
    reasons: List[str] = []
    delivery: DeliveryMode = ai_delivery if ai_delivery in DELIVERY_ORDER else "silent"

    def lower_to(target: DeliveryMode, reason: str) -> None:
        nonlocal delivery
        if is_quieter(target, delivery):
            delivery = target
            if reason not in reasons:
                reasons.append(reason)

    if already_decided:
        lower_to("silent", "already_evaluated")
        return delivery, reasons

    # Nothing to gate — the model chose to stay quiet.
    if delivery == "silent":
        return delivery, reasons

    cost = float(context.get("interruption_cost") or 0.0)
    dismiss_rate = float(context.get("user_dismiss_rate") or 0.0)

    # 1. Confidence floors. A speculative conclusion never becomes an
    #    interruption, and a merely-plausible one never becomes a push.
    if confidence < MIN_CONFIDENCE_TO_SPEAK:
        lower_to("silent", "confidence_below_floor")
        return delivery, reasons
    if delivery == "notify" and confidence < MIN_CONFIDENCE_TO_NOTIFY:
        lower_to("home", "notify_confidence_too_low")
    if delivery == "notify" and utility < MIN_UTILITY_TO_NOTIFY:
        lower_to("home", "notify_utility_too_low")

    # 2. Notification permission. Ungranted is the default, so a push the user
    #    never opted into becomes a quiet Home item rather than nothing —
    #    losing the content would be worse than delivering it silently.
    if delivery == "notify" and not context.get("notifications_allowed"):
        lower_to("home", "no_notification_permission")

    # 3. The clock, resolved in the user's own timezone.
    if context.get("likely_sleep"):
        lower_to("home", "likely_sleep")
    elif context.get("quiet_hours"):
        lower_to("home", "quiet_hours")

    # 4. Real commitment overlap — by time, never by what the entry is called.
    if context.get("busy_in_commitment_now"):
        lower_to("home", "busy_in_commitment")

    # 5. Accumulated interruption cost.
    if cost >= INTERRUPTION_COST_HARD_CEILING:
        lower_to("defer", "interruption_cost_hard")
    elif cost >= INTERRUPTION_COST_SOFT_CEILING:
        lower_to("home", "interruption_cost_soft")

    # 6. Repetition. Bounded, not permanent: the bar rises, and only a
    #    sustained pattern silences an item entirely.
    if times_already_raised >= REPEAT_HARD_LIMIT:
        lower_to("silent", "repeated_too_often")
    elif times_already_raised >= REPEAT_SOFT_LIMIT:
        lower_to("home", "recently_raised")

    # 7. Learned preference. Bounded by design — a high dismiss rate lowers
    #    this item to Home, it does not blacklist the subject forever.
    if dismiss_rate >= DISMISS_RATE_SUPPRESS:
        lower_to("home", "user_dismisses_often")

    return delivery, reasons


def creates_user_facing_item(delivery: DeliveryMode) -> bool:
    """Only these surfaces produce something the user can actually see.
    `silent` and `defer` deliberately produce nothing at all."""
    return delivery in ("home", "ask_user", "propose_action", "notify")
