"""Full native calendar test including a genuine extra user-confirmation turn.

Only the TEST DRIVER is adapted. The real Core, calendar authority checks,
frozen proposal/snapshot and original continuation handler remain unchanged.
A waiting cancellation is never called completed: it must complete after one
explicit synthetic user confirmation, or the original acceptance still fails.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from unittest.mock import patch

from scripts import calendar_core_acceptance_v163 as base


async def run(output):
    from conversation_engine.ai_core import loop as core

    original = core.run_cognitive_loop
    confirmations = []

    async def user_turn(**kwargs):
        result = await original(**kwargs)
        message = kwargs.get("user_message", "")
        exact_request = message.startswith(
            f"Cancella dal calendario ORA l'appuntamento '{base.TITLE}'"
        )
        if not exact_request or result.mode != "ask":
            return result
        base.require(kwargs["sess"].user_id == base.OWNER, "CONFIRM_OWNER_MISMATCH")
        question = str(result.ora_text or result.question or "")
        base.require(base.TITLE in question and "?" in question, "UNRECOGNIZED_CONFIRMATION")
        base.require(not confirmations, "SECOND_CONFIRMATION_NOT_ALLOWED")
        db = kwargs["db"]
        active = await db.life_nodes.find({
            "user_id": base.OWNER, "type": "event", "status": "active",
        }, {"_id": 0}).to_list(5)
        base.require(len(active) == 1 and active[0].get("label") == base.TITLE,
                     "UNSAFE_PENDING_CANCELLATION")
        answer = f"Sì, confermo: elimina soltanto l'appuntamento '{base.TITLE}' appena indicato."
        record = {"request_result": "awaiting_explicit_confirmation", "question": question,
                  "synthetic_user_reply": answer, "active_before_confirmation": len(active),
                  "event_id": active[0]["id"], "assent_injected_into_runtime": False}
        confirmations.append(record)
        print("ORA_CAL163_CONFIRMATION_REQUEST " + json.dumps(record, ensure_ascii=False), flush=True)
        # This is a new real Core turn with a synthetic user utterance. No
        # consent field, stored proposal, clock or handler result is fabricated.
        confirmed = await original(**{**kwargs, "user_message": answer})
        print("ORA_CAL163_CONFIRMATION_RESULT " + json.dumps({
            "mode": confirmed.mode, "reply": confirmed.ora_text,
            "active_after_confirmation": await db.life_nodes.count_documents({
                "user_id": base.OWNER, "type": "event", "status": "active"}),
        }, ensure_ascii=False), flush=True)
        return confirmed

    # This is an existing native calendar skill, not a permission bypass.
    # The base driver still fences Google and unrelated network operations.
    allowed = base.CAPS | {"continue_calendar_action"}
    with patch.object(base, "CAPS", allowed), patch.object(core, "run_cognitive_loop", user_turn):
        status = await base.run(output)
    print("ORA_CAL163_DIALOGUE_SCOPE " + json.dumps({
        "explicit_extra_user_confirmations": len(confirmations),
        "one_turn_cancellation_required": False,
        "prior_direct_cancellation_failure_preserved": True,
        "runtime_application_changed": False,
    }), flush=True)
    return status


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/ora-cal163-confirmation.json")
    args = parser.parse_args()
    base.selftest()
    raise SystemExit(asyncio.run(run(args.output)))
