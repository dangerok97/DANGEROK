from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from ops.backup_restore import create_archive, restore_archive


class AsyncCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.i = 0
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self.i >= len(self.rows):
            raise StopAsyncIteration
        row = self.rows[self.i]
        self.i += 1
        return dict(row)


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = [dict(x) for x in (rows or [])]
    def find(self, _query):
        return AsyncCursor(self.rows)
    async def delete_many(self, _query):
        self.rows = []
    async def insert_many(self, docs):
        self.rows.extend(dict(x) for x in docs)


class FakeDb:
    def __init__(self, mapping=None):
        self.cols = {k: FakeCollection(v) for k, v in (mapping or {}).items()}
    async def list_collection_names(self):
        return list(self.cols)
    def __getitem__(self, name):
        self.cols.setdefault(name, FakeCollection())
        return self.cols[name]


@pytest.mark.asyncio
async def test_backup_restore_round_trip(tmp_path: Path):
    src = FakeDb({
        "users": [{"user_id": "u1", "email": "a@example.com"}],
        "events": [{"id": "e1", "title": "Roma"}],
        "rate_limit_buckets": [{"_id": "ephemeral", "count": 99}],
    })
    docs = tmp_path / "documents"
    (docs / "u1").mkdir(parents=True)
    (docs / "u1" / "note.txt").write_text("ciao", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"

    manifest = await create_archive(src, docs, archive)
    assert archive.exists()
    assert {x["collection"] for x in manifest["database"]} == {"users", "events"}
    assert manifest["document_files"] == 1

    dst = FakeDb()
    restored_docs = tmp_path / "restored-documents"
    restored = await restore_archive(dst, restored_docs, archive)

    assert dst["users"].rows == [{"user_id": "u1", "email": "a@example.com"}]
    assert dst["events"].rows == [{"id": "e1", "title": "Roma"}]
    assert "rate_limit_buckets" not in dst.cols
    assert (restored_docs / "u1" / "note.txt").read_text(encoding="utf-8") == "ciao"
    assert restored["document_files"] == 1


@pytest.mark.asyncio
async def test_restore_refuses_nonempty_target(tmp_path: Path):
    src = FakeDb({"users": [{"user_id": "u1"}]})
    archive = tmp_path / "backup.tar.gz"
    await create_archive(src, tmp_path / "docs", archive)

    dst = FakeDb({"users": [{"user_id": "existing"}]})
    with pytest.raises(RuntimeError, match="restore_target_not_empty"):
        await restore_archive(dst, tmp_path / "restore", archive)


@pytest.mark.asyncio
async def test_restore_rejects_path_traversal(tmp_path: Path):
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        manifest = b'{"format":1,"database":[],"document_files":0}'
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest)
        tar.addfile(info, io.BytesIO(manifest))
        payload = b"no"
        bad = tarfile.TarInfo("../escape.txt")
        bad.size = len(payload)
        tar.addfile(bad, io.BytesIO(payload))

    with pytest.raises(RuntimeError, match="unsafe_archive_member"):
        await restore_archive(FakeDb(), tmp_path / "restore", archive)
