"""One bounded, opt-in blind challenge of a prepared result against owned sources.

The current provider manager can serve this separate model call. It is a
second *judgement*, not an independent provider or a semantic proof. Unlike
the preceding correction audit, the critic sees no earlier verdict and must
try to falsify the corrected candidate with the actual supplied evidence.
Default-off avoids silently increasing inference cost in production.
"""
from __future__ import annotations

import json
import os


FLAG = "ORA_PREPARATION_BLIND_CHALLENGE"
MAX_CONTEXT_CHARACTERS = 9000
MAX_ISSUES = 8


def enabled() -> bool:
    return os.environ.get(FLAG, "0").strip().lower() in ("1", "true", "yes", "on")


def schema(allowed_ids):
    ids = list(dict.fromkeys(allowed_ids))
    row = {
        "type": "object",
        "properties": {
            "claim": {"type": "string"},
            "missing_premise": {"type": "string"},
            "evidence_ids": {"type": "array", "items": {"type": "string", "enum": ids}},
        },
        "required": ["claim", "missing_premise", "evidence_ids"],
        "additionalProperties": False,
    }
    return {"type": "object", "properties": {
        "accepted": {"type": "boolean"},
        "issues": {"type": "array", "items": row},
        "reason": {"type": "string"},
    }, "required": ["accepted", "issues", "reason"], "additionalProperties": False}


def input_payload(request, corrected_content, source_rows, *, evidence_truncated=False):
    # The original audit has already reduced source rows without dropping a
    # cited source. Do not further trim or silently remove material premises.
    payload = {
        "stage": "blind_source_challenge",
        "request": request,
        "candidate_result": corrected_content,
        "evidence": source_rows,
        "evidence_truncated": evidence_truncated is True,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
    return encoded if len(encoded) <= MAX_CONTEXT_CHARACTERS else None


def verdict(answer, allowed_ids):
    """accepted / rejected / invalid, never an inferred factual verdict."""
    if not isinstance(answer, dict) or type(answer.get("accepted")) is not bool:
        return "invalid"
    reason, issues = answer.get("reason"), answer.get("issues")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
        return "invalid"
    if not isinstance(issues, list) or len(issues) > MAX_ISSUES:
        return "invalid"
    allowed = set(allowed_ids)
    for item in issues:
        if not isinstance(item, dict):
            return "invalid"
        claim, gap, ids = item.get("claim"), item.get("missing_premise"), item.get("evidence_ids")
        if (not isinstance(claim, str) or not claim.strip() or len(claim) > 240
                or not isinstance(gap, str) or not gap.strip() or len(gap) > 300
                or not isinstance(ids, list) or len(ids) > 8
                or any(not isinstance(ref, str) or ref not in allowed for ref in ids)):
            return "invalid"
    if issues or answer["accepted"] is False:
        return "rejected"
    return "accepted"


def fallible_feedback(answer, allowed_ids):
    """Bound the model's criticism; never persist the candidate or raw sources."""
    if not isinstance(answer, dict):
        return None
    from agent.preparation import _review_feedback
    issues = answer.get("issues") if isinstance(answer.get("issues"), list) else []
    reviews = []
    for item in issues[:MAX_ISSUES]:
        if not isinstance(item, dict):
            continue
        reviews.append({
            "claim": item.get("claim"), "inference_or_gap": item.get("missing_premise"),
            "support": "unsupported", "evidence_ids": item.get("evidence_ids"),
        })
    return _review_feedback({"reason": answer.get("reason"), "claim_review": reviews},
                            set(allowed_ids), origin="preparation_audit")


PROMPT = (
    "Perform a BLIND, ADVERSARIAL source check of candidate_result. You have "
    "NOT been shown the original generation or earlier positive audit. Those "
    "prior decisions confer no authority. The request defines the work, not "
    "facts about a provider or the world. Only evidence entries show recorded "
    "facts, provenance and limitations. Read the entire claim_passages sequence "
    "in source order. Attempt to falsify every material statement, comparison, "
    "omission and practical consequence in candidate_result by constructing "
    "a case consistent with evidence that defeats it. Distinguish source-stated "
    "from inferred and merely conditional assertions. Do not attribute one "
    "option's terms to another option; a user's intention is not a provider "
    "condition. Check arithmetic, time horizons, non-refund terms, permissions "
    "and the absence of claims from current sources. Correct numbers do not "
    "establish nearby qualitative claims. A person-reported figure may support "
    "a CONDITIONAL comparison without third-party verification; mark actual "
    "missing premises, not an invented requirement for an additional search. "
    "If any material claim or key requested finding is unsupported, set "
    "accepted=false and identify the specific claim and missing premise. "
    "Do NOT write a revised draft or grant permission. Return JSON with "
    "accepted (boolean), issues (0–8 entries with claim, missing_premise, "
    "evidence_ids selected only from supplied source IDs), and short reason. "
    "Opaque implementation references (mem_, evd_, gol_, sit_, prep_) are not "
    "meaningful provenance for a human; reject them in a published result and "
    "require the true person-readable origin instead. "
    "If evidence_truncated is true, parts of the source were omitted. "
    "Do not treat that omission as proof of absence. If the remaining source "
    "does not establish a material claim, do NOT claim acceptance."
)
