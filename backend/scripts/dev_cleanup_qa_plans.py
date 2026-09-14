"""DEV-only cleanup for QA-tagged Life OS / study / action sessions.

Safety rules:
- Never touches Profile, Life Memory, or unrelated real plans.
- Deletes ONLY when provenance clearly marks QA/test records.
- If provenance is insufficient, prints candidates and exits without delete.

Usage (local):
  DEV=1 python -m scripts.dev_cleanup_qa_plans --user-id <id> --dry-run
  DEV=1 python -m scripts.dev_cleanup_qa_plans --user-id <id> --apply
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys


QA_MARKERS = (
    "qa_",
    "test_",
    "fixture_",
    "e2e_",
    "playwright_",
)


def _looks_like_qa(doc: dict) -> bool:
    meta = doc.get("meta") or {}
    prov = doc.get("provenance") or meta.get("provenance") or {}
    blob = " ".join(
        str(x)
        for x in (
            doc.get("id"),
            doc.get("summary"),
            doc.get("exam_name"),
            doc.get("conversation_session_id"),
            meta.get("qa"),
            meta.get("source"),
            meta.get("created_by"),
            prov.get("source"),
            prov.get("kind"),
            doc.get("created_by"),
        )
        if x is not None
    ).lower()
    if meta.get("qa") is True or meta.get("is_qa") is True:
        return True
    if prov.get("qa") is True or str(prov.get("kind") or "").lower() in ("qa", "test"):
        return True
    return any(m in blob for m in QA_MARKERS)


async def main() -> int:
    if (os.environ.get("DEV") or "").strip().lower() not in ("1", "true", "yes", "on"):
        print("Refusing: set DEV=1 to run this utility.")
        return 2

    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    dry = not args.apply

    from motor.motor_asyncio import AsyncIOMotorClient

    mongo = os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
    db_name = os.environ.get("DB_NAME") or "ora"
    client = AsyncIOMotorClient(mongo)
    db = client[db_name]
    uid = args.user_id

    collections = ("life_os_plans", "life_os_objects", "study_plans", "action_sessions")
    report = {}
    for col in collections:
        try:
            docs = await db[col].find({"user_id": uid}, {"_id": 0}).to_list(200)
        except Exception as e:
            report[col] = {"error": type(e).__name__}
            continue
        qa_docs = [d for d in docs if _looks_like_qa(d)]
        ambiguous = [
            {"id": d.get("id"), "keys": list(d.keys())[:8]}
            for d in docs
            if not _looks_like_qa(d)
        ][:5]
        report[col] = {
            "total": len(docs),
            "qa_matched": len(qa_docs),
            "qa_ids": [d.get("id") for d in qa_docs][:40],
            "sample_non_qa": ambiguous,
        }
        if not dry and qa_docs:
            ids = [d.get("id") for d in qa_docs if d.get("id")]
            if ids:
                await db[col].delete_many({"user_id": uid, "id": {"$in": ids}})

    print("dry_run" if dry else "applied", report)
    if all((report.get(c) or {}).get("qa_matched", 0) == 0 for c in collections):
        print(
            "No safe QA provenance found. Refusing automatic wipe of unlabeled plans."
        )
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
