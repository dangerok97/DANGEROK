"""Documents module — Iterazione 19 (Foundation).

Sistema documenti definitivo di ORA. In questa iterazione:
    * Storage astratto (`DocumentStorageProvider`) con impl locale
    * CRUD REST completo
    * Soft delete + archive
    * Deduplica via SHA-256
    * Mirror automatico in Life Graph (type=document) + Knowledge Layer
      (fatti minimali: filename, mime_type, tags, notes)
    * Provider Context Assembler disabilitato via feature flag

NON incluso in questa iterazione (rimandato):
    - OCR
    - AI summary
    - Estrazione dati dal contenuto
    - Generazione automatica di decisioni
"""
from .router import router as documents_router
from .service import DocumentService
from .storage import (
    DocumentStorageProvider,
    LocalFilesystemStorage,
    build_default_storage,
)

__all__ = [
    "documents_router",
    "DocumentService",
    "DocumentStorageProvider",
    "LocalFilesystemStorage",
    "build_default_storage",
]
