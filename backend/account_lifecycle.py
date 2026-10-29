"""
Your data, yours to take and yours to erase.

Until 29/10/2026 the privacy page said, honestly, that neither existed: to
leave ORA you had to write to support. The App Store requires in-app account
deletion, Google's OAuth verification requires a way to delete the data read
from Gmail and Calendar, and the GDPR requires both access and erasure.

* Export: everything stored under this person's id, in every collection, as
  one JSON file. Secrets are left out: passwords, OAuth tokens, keys and
  encrypted blobs are not data about the person but means of access.
* Deletion: every document under this person's id in every collection, the
  files stored for them (documents, photos, scans), and the sessions. It is
  immediate and cannot be undone; the daily encrypted backups roll off within
  BACKUP_RETENTION_DAYS. What is kept is one line without personal data:
  that an account was deleted, when, and how many records.

Ownership is the same field everywhere: user_id or owner_id. A collection is
scanned only for documents carrying exactly this id.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("ora.account")

OWNER_FIELDS = ("user_id", "owner_id")
EXPORT_LIMIT_PER_COLLECTION = 5000
SKIP_COLLECTIONS = {"account_deletions", "backup_runs", "system.views"}
_SECRET_HINTS = ("password", "token", "secret", "credential", "api_key", "key_hash", "digest",
                 "encrypted", "cipher", "private_key", "refresh", "otp", "nonce", "salt")


def _is_secret(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in _SECRET_HINTS)


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[non esportato: credenziale]" if _is_secret(k) else _clean(v))
                for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return f"[dato binario, {len(value)} byte]"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _query(uid: str) -> Dict[str, Any]:
    return {"$or": [{f: uid} for f in OWNER_FIELDS]}


async def _collections(db) -> list[str]:
    names = await db.list_collection_names()
    return sorted(n for n in names if not n.startswith("system.") and n not in SKIP_COLLECTIONS)


async def export(db, uid: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "about": ("Esportazione dei dati di ORA. Contiene tutto ciò che è salvato con il tuo "
                  "identificativo; password, token di accesso e chiavi non sono inclusi."),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "collections": {},
    }
    for name in await _collections(db):
        rows = await db[name].find(_query(uid)).limit(EXPORT_LIMIT_PER_COLLECTION).to_list(EXPORT_LIMIT_PER_COLLECTION)
        if rows:
            out["collections"][name] = [_clean(r) for r in rows]
    return out


def _storage_dirs(uid: str) -> list[Path]:
    safe = "".join(c for c in uid if c.isalnum() or c in ("-", "_"))[:64]
    if not safe:
        return []
    bases = {os.environ.get("DOCUMENT_STORAGE_DIR") or "/app/backend/data/documents", "/data/documents"}
    return [Path(b) / safe for b in bases]


async def delete(db, uid: str, email: str = "") -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for name in await _collections(db):
        try:
            result = await db[name].delete_many(_query(uid))
            if result.deleted_count:
                counts[name] = result.deleted_count
            if email and ("identit" in name or name in ("users", "password_resets")):
                extra = await db[name].delete_many({"email": email})
                if extra.deleted_count:
                    counts[name] = counts.get(name, 0) + extra.deleted_count
        except Exception as exc:
            logger.warning("account delete collection=%s failed: %s", name, type(exc).__name__)
            counts[name] = -1
    files = 0
    for folder in _storage_dirs(uid):
        try:
            if folder.is_dir():
                files += sum(1 for p in folder.rglob("*") if p.is_file())
                shutil.rmtree(folder, ignore_errors=True)
        except Exception as exc:
            logger.warning("account delete files failed: %s", type(exc).__name__)
    failed = [n for n, c in counts.items() if c < 0]
    await db.account_deletions.insert_one({
        "account_digest": hashlib.sha256(uid.encode()).hexdigest()[:24],
        "at": datetime.now(timezone.utc).isoformat(),
        "records": sum(c for c in counts.values() if c > 0), "files": files,
        "collections": len([c for c in counts.values() if c > 0]), "failed": failed,
    })
    return {"ok": not failed, "records": sum(c for c in counts.values() if c > 0), "files": files,
            "failed_collections": failed}
