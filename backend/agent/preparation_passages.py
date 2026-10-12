"""Code-owned, lossless passage references for the existing preparation audit.

Selection authenticates input text. It never establishes semantic entailment,
adds a model call, repairs a quotation or changes a model's verdict.
"""
from copy import deepcopy
import hashlib


PASSAGE_LIMIT = 280


def build_audit_passages(rows):
    """Replace each claim with ordered literal passages, preserving every character."""
    projected, index = [], {}
    for row in rows:
        claim, evidence_id = row["claim"], row["id"]
        digest = hashlib.sha256((evidence_id + "\0" + claim).encode()).hexdigest()[:16]
        passages, start = [], 0
        while start < len(claim):
            end = min(start + PASSAGE_LIMIT, len(claim))
            if end < len(claim):
                # Prefer a visible boundary near the end, without skipping even
                # whitespace or normalizing Unicode. A <=600-character claim
                # still needs at most three passages.
                boundary = max(claim.rfind(" ", start + 210, end),
                               claim.rfind("\n", start + 210, end))
                if boundary >= start + 210:
                    end = boundary + 1
            passage_id = f"p_{digest}_{start}_{end}"
            quote = {"evidence_id": evidence_id, "quote": claim[start:end]}
            if passage_id in index and index[passage_id] != quote:
                raise ValueError("Audit passage identity collision")
            index[passage_id] = quote
            passages.append({"id": passage_id, "text": claim[start:end]})
            start = end
        projected.append({key: deepcopy(value) for key, value in row.items() if key != "claim"}
                         | {"claim_passages": passages})
    return projected, index


def materialize_audit_passages(answer, index):
    """Resolve only supplied selections; leave the strict literal-quote guard intact.

The native schema requests passage IDs. Adapters returning the previous
literal-quote form still face the original unmodified authenticity checks.
Supplying both representations in one check is ambiguous and is rejected.
"""
    checks = answer.get("claim_review")
    if not isinstance(checks, list) or len(checks) > 12:
        return answer, []  # The existing review contract diagnoses this shape.

    def invalid(value, issue):
        kind = ("null" if value is None else "boolean" if type(value) is bool else
                "text" if isinstance(value, str) else "array" if isinstance(value, list) else
                "object" if isinstance(value, dict) else "number" if isinstance(value, (int, float)) else "other")
        return answer, [{"field": "claim_review.source_passage_ids", "issue": issue, "received": kind}]

    resolved = None
    for number, check in enumerate(checks):
        if not isinstance(check, dict) or "source_passage_ids" not in check:
            continue
        ids = check["source_passage_ids"]
        if "source_quotes" in check:
            return invalid(ids, "ambiguous")
        if not isinstance(ids, list):
            return invalid(ids, "wrong_type")
        if len(ids) > 3:
            return invalid(ids, "too_long")
        if any(not isinstance(ref, str) for ref in ids):
            return invalid(ids, "wrong_type")
        if any(ref not in index for ref in ids):
            return invalid(ids, "not_supplied")
        if resolved is None:
            resolved = deepcopy(answer)
        selected = resolved["claim_review"][number]
        selected.pop("source_passage_ids")
        selected["source_quotes"] = [dict(index[ref]) for ref in ids]
    return resolved if resolved is not None else answer, []
