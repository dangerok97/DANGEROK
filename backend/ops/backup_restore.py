"""Logical ORA backup/restore for Mongo state and document blobs."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from bson import json_util
from motor.motor_asyncio import AsyncIOMotorClient

SKIP_COLLECTIONS = {"rate_limit_buckets"}


def _safe_member(name: str) -> bool:
    p = Path(name)
    return not p.is_absolute() and ".." not in p.parts


async def _dump_mongo(db: Any, root: Path) -> list[dict[str, Any]]:
    mongo_dir = root / "mongo"
    mongo_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    for name in sorted(await db.list_collection_names()):
        if name in SKIP_COLLECTIONS or name.startswith("system."):
            continue
        target = mongo_dir / f"{name}.ndjson"
        count = 0
        with target.open("w", encoding="utf-8") as fh:
            async for doc in db[name].find({}):
                fh.write(json_util.dumps(doc, separators=(",", ":")) + "\n")
                count += 1
        manifest.append({"collection": name, "count": count})
    return manifest


def _copy_documents_to_tar(tar: tarfile.TarFile, documents_dir: Path) -> int:
    if not documents_dir.exists():
        return 0
    count = 0
    for path in sorted(documents_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(documents_dir)
        tar.add(path, arcname=str(Path("documents") / rel), recursive=False)
        count += 1
    return count


async def create_archive(db: Any, documents_dir: str | Path, archive_path: str | Path) -> dict[str, Any]:
    documents_dir = Path(documents_dir)
    archive_path = Path(archive_path)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ora-backup-") as tmp:
        root = Path(tmp)
        collections = await _dump_mongo(db, root)
        manifest = {
            "format": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": collections,
            "document_files": 0,
        }
        manifest_path = root / "manifest.json"
        with tarfile.open(archive_path, "w:gz") as tar:
            for file in sorted((root / "mongo").glob("*.ndjson")):
                tar.add(file, arcname=str(Path("mongo") / file.name), recursive=False)
            manifest["document_files"] = _copy_documents_to_tar(tar, documents_dir)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            tar.add(manifest_path, arcname="manifest.json", recursive=False)
    return manifest


async def restore_archive(
    db: Any,
    documents_dir: str | Path,
    archive_path: str | Path,
    *,
    allow_nonempty: bool = False,
) -> dict[str, Any]:
    documents_dir = Path(documents_dir)
    archive_path = Path(archive_path)
    existing_collections = [
        n for n in await db.list_collection_names()
        if not n.startswith("system.") and n not in SKIP_COLLECTIONS
    ]
    documents_nonempty = documents_dir.exists() and any(documents_dir.rglob("*"))
    if not allow_nonempty and (existing_collections or documents_nonempty):
        raise RuntimeError("restore_target_not_empty")

    restored: list[dict[str, Any]] = []
    restored_files = 0
    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        if any(not _safe_member(m.name) for m in members):
            raise RuntimeError("unsafe_archive_member")
        manifest_member = tar.getmember("manifest.json")
        manifest = json.loads(tar.extractfile(manifest_member).read().decode("utf-8"))
        for member in members:
            if member.isdir():
                continue
            if member.name.startswith("mongo/") and member.name.endswith(".ndjson"):
                name = Path(member.name).name[:-7]
                raw = tar.extractfile(member)
                docs = [json_util.loads(line) for line in raw.read().decode("utf-8").splitlines() if line.strip()]
                if allow_nonempty:
                    await db[name].delete_many({})
                if docs:
                    await db[name].insert_many(docs)
                restored.append({"collection": name, "count": len(docs)})
            elif member.name.startswith("documents/"):
                rel = Path(member.name).relative_to("documents")
                dest = documents_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    continue
                dest.write_bytes(source.read())
                restored_files += 1
    return {"manifest": manifest, "database": restored, "document_files": restored_files}


def _s3_client():
    endpoint = os.environ["BACKUP_S3_ENDPOINT"]
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("BACKUP_S3_REGION") or "auto",
        aws_access_key_id=os.environ["BACKUP_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["BACKUP_S3_SECRET_ACCESS_KEY"],
    )


def upload_archive(path: str | Path, key: str) -> None:
    _s3_client().upload_file(str(path), os.environ["BACKUP_S3_BUCKET"], key)


def download_archive(key: str, path: str | Path) -> None:
    _s3_client().download_file(os.environ["BACKUP_S3_BUCKET"], key, str(path))


async def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "ora")]


async def _main(args) -> None:
    client, db = await _db()
    documents = Path(os.environ.get("DOCUMENT_STORAGE_DIR", "/data/documents"))
    try:
        if args.command == "create":
            out = Path(args.file or f"/tmp/ora-backup-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.tar.gz")
            manifest = await create_archive(db, documents, out)
            key = args.key or f"ora/{out.name}"
            if args.upload:
                upload_archive(out, key)
            print(json.dumps({"ok": True, "file": str(out), "key": key if args.upload else None, "manifest": manifest}))
        elif args.command == "restore":
            source = Path(args.file or "/tmp/ora-restore.tar.gz")
            if args.key:
                download_archive(args.key, source)
            result = await restore_archive(db, documents, source, allow_nonempty=args.allow_nonempty)
            print(json.dumps({"ok": True, **result}, default=str))
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--file")
    create.add_argument("--key")
    create.add_argument("--upload", action="store_true")
    restore = sub.add_parser("restore")
    restore.add_argument("--file")
    restore.add_argument("--key")
    restore.add_argument("--allow-nonempty", action="store_true")
    args = parser.parse_args()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()
