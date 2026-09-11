"""ContextFile — user-supplied evidence for AI Core (domain-neutral).

Wraps Documents V2 storage/extraction. Cognition must NOT branch on document type.
"""
from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

FileStatus = Literal["uploaded", "processing", "ready", "failed"]

MAX_ATTACHMENTS_PER_MESSAGE = 5
MAX_SESSION_FILES = 20
PREVIEW_CHARS = 400
CHUNK_CHARS = 3500
MAX_CHUNKS_PER_READ = 4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_context_file_id() -> str:
    return f"lcf_{uuid.uuid4().hex[:14]}"


class ContextFile(BaseModel):
    """Canonical AI-readable file evidence (references Documents V2 blob)."""

    id: str = Field(default_factory=new_context_file_id)
    user_id: str
    document_id: str  # Documents V2 id (doc_…)
    session_id: Optional[str] = None
    original_name: str = ""
    mime_type: str = ""
    size_bytes: int = 0
    content_hash: str = ""
    status: FileStatus = "uploaded"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    # Derived (never dump full text into every prompt)
    preview: str = ""
    page_count: Optional[int] = None
    extraction_method: str = ""
    processing_notes: str = ""
    text_available: bool = False
    char_count: int = 0
    # Soft associations (opaque ids)
    goal_refs: List[str] = Field(default_factory=list)
    plan_refs: List[str] = Field(default_factory=list)
    object_refs: List[str] = Field(default_factory=list)
    message_ref: Optional[str] = None
    # AI-optional descriptive label — NOT a closed domain enum / router
    semantic_label: str = ""
    user_supplied: bool = True
    provenance: Dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = now_iso()

    def lightweight(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "name": (self.original_name or "")[:120],
            "mime_type": self.mime_type,
            "status": self.status,
            "preview": (self.preview or "")[:PREVIEW_CHARS],
            "text_available": bool(self.text_available),
            "char_count": int(self.char_count or 0),
            "page_count": self.page_count,
            "user_supplied": True,
            "semantic_label": (self.semantic_label or "")[:160],
            "plan_refs": list(self.plan_refs or [])[:4],
            "object_refs": list(self.object_refs or [])[:4],
            "processing_notes": (self.processing_notes or "")[:200],
            # Accanto al file, non in fondo a un elenco di regole.
            #
            #     UNA REGOLA LONTANA DALLA PROVA NON GOVERNA LA FRASE.
            #
            # La stessa cosa era gia' scritta nel prompt di sistema e nel
            # promemoria del payload, e non ha retto: alla domanda «che cosa
            # vedi qui?» su una schermata del conto, ORA ha risposto che il
            # bonifico dell'11 «corrisponde esattamente» all'appuntamento del
            # 17. Undici non e' diciassette. Qui la regola sta attaccata al
            # documento a cui si applica, che e' dove chi risponde guarda
            # mentre scrive quella frase.
            "how_to_say_it": (
                "Questo documento può riguardare una PARTE della sua vita: "
                "una pratica, una situazione aperta. Quello puoi dirlo, se "
                "quello che già sai lo regge. "
                #     UN DIVIETO SENZA UN'ALTERNATIVA NON È UN AIUTO.
                #
                # Chi risponde vede il documento e vede un impegno in
                # calendario con la stessa controparte, e vuole dire che le
                # due cose stanno insieme — perché in effetti stanno insieme,
                # nella stessa pratica. Dicendogli soltanto che non può
                # scrivere «si collega all'appuntamento», gli si toglie la
                # frase e non gliene si dà un'altra: e quella sbagliata resta
                # l'unica che ha.
                "Se in calendario c'è un impegno della stessa pratica e vuoi "
                "nominarlo, il modo è questo: «riguarda la pratica della "
                "casa, dentro la quale hai anche un appuntamento il 17». "
                "Entrambi stanno nella stessa pratica — questo lo sai. Quale "
                "prestazione copra questo pagamento, e se sia proprio quella "
                "di quell'appuntamento, non lo sai."
            ),
            #     UN DOCUMENTO NON È UN APPUNTAMENTO.
            #
            # Qui non c'è un livello da tradurre: c'è una cosa che questo tipo
            # di dato non può contenere. Un file è un file, e un impegno in
            # calendario è un altro oggetto; niente in un allegato identifica
            # quale evento sia. Detto come regola — «non superare il livello
            # delle prove» — si è perso; detto come divieto attaccato al
            # documento, no: alla domanda «questo riguarda la casa?» la
            # risposta diceva che il bonifico dell'11 «si collega strettamente
            # all'appuntamento del 17».
            "you_may_never_say": (
                "Che questo documento è, o si collega a, un APPUNTAMENTO "
                "preciso che la persona ha in calendario. Un allegato non "
                "contiene nessuna prova di identità con un evento: stessa "
                "controparte e stessa pratica non bastano, e un pagamento e "
                "un appuntamento restano due cose diverse. Puoi dire che "
                "entrambi appartengono alla stessa pratica; non che l'uno è "
                "l'altro, né che l'uno «si collega» all'altro. Se il "
                "collegamento con un evento ti sembra probabile, dillo come "
                "probabile e di' che cosa servirebbe per esserne certi."
            ),
        }

    def evidence_dict(self) -> Dict[str, Any]:
        name = (self.semantic_label or self.original_name or "user_file")[:120]
        return {
            "ref": self.document_id or self.id,
            "kind": "USER_PROVIDED_CONTENT",
            "label": name,
            "display_name": name,
            "source_type": "user_file",
            "source_id": self.document_id or self.id,
            "status": "active",
        }


def sanitize_filename(name: str) -> str:
    base = os.path.basename(name or "")[:255] or "file.bin"
    # Strip control chars / path tricks
    base = re.sub(r"[\x00-\x1f]", "", base)
    if ".." in base or base.startswith("\\") or base.startswith("/"):
        base = "file.bin"
    return base


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def chunk_text(text: str, *, start: int = 0, max_chunks: int = MAX_CHUNKS_PER_READ) -> List[Dict[str, Any]]:
    raw = text or ""
    if not raw:
        return []
    out: List[Dict[str, Any]] = []
    i = max(0, int(start or 0))
    n = 0
    while i < len(raw) and n < max_chunks:
        piece = raw[i : i + CHUNK_CHARS]
        out.append(
            {
                "offset": i,
                "length": len(piece),
                "text": piece,
                "has_more": i + len(piece) < len(raw),
            }
        )
        i += CHUNK_CHARS
        n += 1
    return out
