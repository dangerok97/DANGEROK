"""DocumentStorageProvider abstraction + local filesystem implementation.

L'interfaccia è volutamente minimale e stateless: il backend di storage
scambia SOLO bytes/stream con la logica di business (metadata, hash,
Life Graph) che vive dentro `DocumentService`.

Sostituzioni future (S3, GCS, Azure Blob) devono implementare la stessa
interfaccia senza toccare `DocumentService` né i router.
"""
from __future__ import annotations

import abc
import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional


@dataclass
class StoredObject:
    """Metadata di un blob salvato."""
    provider: str          # e.g. "local", "s3"
    key: str               # opaque identifier, meaningful only to the provider
    size: int              # bytes
    hash: str              # sha256 hex


class DocumentStorageProvider(abc.ABC):
    """Interfaccia astratta. TUTTI i metodi devono essere idempotenti."""

    provider_name: str = "abstract"

    @abc.abstractmethod
    async def put(
        self,
        *,
        user_id: str,
        content: bytes,
        original_filename: str,
        mime_type: str,
    ) -> StoredObject:
        """Salva `content` e restituisce metadati (key, size, hash).

        Contratto: se lo stesso `content` (stesso hash) viene ripassato,
        l'implementazione DEVE ritornare la stessa `key` (deduplica a
        livello di storage). Il DocumentService a valle userà comunque
        il proprio dedup lookup sul DB.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def read(self, *, user_id: str, key: str) -> bytes:
        """Legge i bytes. Deve verificare l'ownership tramite `user_id`."""
        raise NotImplementedError

    @abc.abstractmethod
    async def delete(self, *, user_id: str, key: str) -> bool:
        """Rimozione fisica del blob. Idempotente: True anche se già assente."""
        raise NotImplementedError

    @abc.abstractmethod
    async def exists(self, *, user_id: str, key: str) -> bool:
        raise NotImplementedError

    async def stream(self, *, user_id: str, key: str, chunk_size: int = 65536) -> AsyncIterator[bytes]:
        """Default: legge tutto e chunk-a in memoria. I provider remoti
        possono sovrascrivere con streaming reale."""
        buf = await self.read(user_id=user_id, key=key)
        for i in range(0, len(buf), chunk_size):
            yield buf[i:i + chunk_size]


class LocalFilesystemStorage(DocumentStorageProvider):
    """Salva sotto <base_dir>/<user_id>/<hash_prefix>/<hash>.bin

    * `<base_dir>` è configurabile via env `DOCUMENT_STORAGE_DIR`.
    * `<hash_prefix>` = primi 2 char di hash → evita cartelle piene di
      milioni di file (max 256 sotto-cartelle per utente).
    * Il filename salvato NON include l'originale (che vive in DB) per
      isolare metadati e storage.
    """

    provider_name = "local"

    def __init__(self, base_dir: Optional[str] = None):
        base = base_dir or os.environ.get("DOCUMENT_STORAGE_DIR") or "/app/backend/data/documents"
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, user_id: str) -> Path:
        safe = "".join(c for c in user_id if c.isalnum() or c in ("-", "_"))[:64] or "unknown"
        p = self.base / safe
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _path_for(self, user_id: str, key: str) -> Path:
        # key format: "sha256:<hex>"; use the hex prefix bucket.
        _, _, hex_ = key.partition(":")
        prefix = (hex_[:2] or "00").lower()
        d = self._user_dir(user_id) / prefix
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{hex_}.bin"

    async def put(self, *, user_id: str, content: bytes, original_filename: str, mime_type: str) -> StoredObject:
        digest = hashlib.sha256(content).hexdigest()
        key = f"sha256:{digest}"
        target = self._path_for(user_id, key)
        # Idempotency: if already present with same size, skip write.
        if not target.exists() or target.stat().st_size != len(content):
            tmp = target.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                f.write(content)
            os.replace(tmp, target)  # atomic on POSIX
        return StoredObject(provider=self.provider_name, key=key, size=len(content), hash=digest)

    async def read(self, *, user_id: str, key: str) -> bytes:
        p = self._path_for(user_id, key)
        if not p.exists():
            raise FileNotFoundError(f"blob not found: {key}")
        with open(p, "rb") as f:
            return f.read()

    async def delete(self, *, user_id: str, key: str) -> bool:
        p = self._path_for(user_id, key)
        try:
            if p.exists():
                p.unlink()
            return True
        except Exception:
            return False

    async def exists(self, *, user_id: str, key: str) -> bool:
        return self._path_for(user_id, key).exists()


def build_default_storage() -> DocumentStorageProvider:
    """Factory: at the moment only local. In future dispatch on env
    `DOCUMENT_STORAGE_BACKEND` (e.g. `s3`, `gcs`)."""
    backend = os.environ.get("DOCUMENT_STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return LocalFilesystemStorage()
    # Future: elif backend == "s3": return S3Storage(...)
    raise RuntimeError(f"Unsupported DOCUMENT_STORAGE_BACKEND: {backend}")
