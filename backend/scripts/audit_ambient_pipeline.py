"""Print aggregate autonomous-work states, without exporting personal data.

Usage: MONGO_URL=... DB_NAME=... python -m scripts.audit_ambient_pipeline
Pass --owner-id to narrow to one account; the identifier is never printed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from motor.motor_asyncio import AsyncIOMotorClient

from ambient.audit import pipeline_counts


async def main(owner_id):
    url = os.environ.get("MONGO_URL")
    name = os.environ.get("DB_NAME")
    if not url or not name:
        raise SystemExit("MONGO_URL e DB_NAME sono richiesti")
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command("ping")
        print(json.dumps(await pipeline_counts(client[name], owner_id=owner_id),
                         ensure_ascii=False, indent=2))
    except Exception as exc:
        # Do not print exception details: connection errors may embed credentials.
        raise SystemExit(f"Audit non disponibile ({type(exc).__name__})") from None
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conteggi anonimi della pipeline autonoma")
    parser.add_argument("--owner-id", help="limita il conteggio a un account; non compare nell'output")
    args = parser.parse_args()
    asyncio.run(main(args.owner_id))
