"""Separate sandbox financial observations from real financial reasoning.

A simulated bank statement is useful for exercising ORA, but it must never
become a real monthly total, obligation, user memory, spending forecast or
proof about a person's finances. Evidence and owner identity decide reality;
amounts, merchant names and recurring intervals do not.
"""
from __future__ import annotations

from typing import Dict, Iterable, Set

from connectors.bank.service import bank_account_is_simulated


async def account_sources(db, owner_id: str) -> Dict[str, dict]:
    """Load only owner-owned metadata, never balances, credentials or bodies."""
    rows = await db.bank_accounts.find(
        {"owner_id": owner_id},
        {"_id": 0, "account_ref": 1, "provider_reality": 1,
         "institution": 1, "display_name": 1},
    ).to_list(100)
    return {
        str(row["account_ref"]): row
        for row in rows if row.get("account_ref")
    }


def is_simulated_observation(observation, account_by_ref: Dict[str, dict]) -> bool:
    provenance = getattr(observation, "provenance", None) or {}
    declared = str(provenance.get("provider_reality") or "").strip().lower()
    if declared in ("simulated", "real"):
        return declared == "simulated"
    account = account_by_ref.get(str(getattr(observation, "account_ref", "")))
    if account:
        return bank_account_is_simulated(account)
    # A disconnected legacy mock still has the label that the demo provider
    # gave it. Do not infer reality from the amount or transaction text.
    return bank_account_is_simulated({
        "institution": provenance.get("institution", "")
    })


async def simulated_fact_ids(db, owner_id: str, facts: Iterable) -> Set[str]:
    """Identify historical bank-derived facts backed only by demo transactions.

    Governed memories can store an 'inferred' provenance, but preserve the
    exact original bank transaction ref in evidence_refs/source_refs.
    Refs absent from the owner's statement are UNKNOWN, not simulated.
    """
    rows = list(facts)
    refs = {
        str(ref)
        for fact in rows
        for ref in (getattr(fact, "source_refs", None) or [])
        if ref and not str(ref).startswith(("mail:", "document:", "calendar:"))
    }
    if not refs:
        return set()
    observations = await db.financial_observations.find(
        {"owner_id": owner_id, "transaction_ref": {"$in": list(refs)[:400]}},
        {"_id": 0, "account_ref": 1, "transaction_ref": 1,
         "provenance": 1},
    ).to_list(400)
    if not observations:
        return set()
    accounts = await account_sources(db, owner_id)
    truth: Dict[str, set[bool]] = {}
    for obs in observations:
        ref = str(obs.get("transaction_ref") or "")
        if ref:
            from types import SimpleNamespace
            reality = is_simulated_observation(
                SimpleNamespace(**obs), accounts
            )
            truth.setdefault(ref, set()).add(reality)
    return {
        str(fact.id)
        for fact in rows if getattr(fact, "id", None) and (
            (connected := [
                truth[ref] for ref in map(str, (fact.source_refs or []))
                if ref in truth
            ])
            and all(group == {True} for group in connected)
            # An unrecognised source mixed with a mock is not proven synthetic.
            and all(
                str(ref) in truth
                for ref in fact.source_refs
                if not str(ref).startswith(("mail:", "document:", "calendar:"))
            )
        )
    }
