"""Text extraction pipeline for Documents (Iterazione 20).

Composizione:

    Upload → TextExtractor → Cleaner → Knowledge/LifeGraph → Search index

Ogni fase indipendente. La pipeline è invocata da `DocumentService.upload`
DOPO l'insert del doc, in modo asincrono (fire-and-forget) così l'upload
resta veloce anche su documenti grossi.

Provider:
    * PDFTextProvider  → pypdf (nativo, no OCR)
    * OCRProvider      → pytesseract (binario tesseract di sistema)
    * TextFileProvider → per text/plain (pass-through)

Nessun LLM, nessun summary, nessuna classificazione — solo raw text +
metadata (pages, language, confidence, timings).
"""
from __future__ import annotations

import abc
import io
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ora.documents.extraction")


# ---------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------
@dataclass
class ExtractionResult:
    text: str = ""
    pages: int = 0
    language: Optional[str] = None
    confidence: Optional[float] = None
    ocr_used: bool = False
    engine: str = ""
    warnings: List[str] = field(default_factory=list)
    error_code: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


# ---------------------------------------------------------------------
# Provider interfaces
# ---------------------------------------------------------------------
class PDFTextProvider(abc.ABC):
    name = "pdf_abstract"

    @abc.abstractmethod
    def extract(self, blob: bytes) -> ExtractionResult: ...


class OCRProvider(abc.ABC):
    name = "ocr_abstract"

    @abc.abstractmethod
    def extract(self, blob: bytes, mime_type: str) -> ExtractionResult: ...


# ---------------------------------------------------------------------
# Impl: pypdf
# ---------------------------------------------------------------------
class PyPDFProvider(PDFTextProvider):
    name = "pypdf"

    def extract(self, blob: bytes) -> ExtractionResult:
        r = ExtractionResult(engine=self.name)
        try:
            from pypdf import PdfReader
        except Exception as e:
            r.error_code = "pdf_lib_missing"
            r.warnings.append(str(e))
            return r
        try:
            reader = PdfReader(io.BytesIO(blob))
        except Exception as e:
            r.error_code = "pdf_corrupted"
            r.warnings.append(str(e))
            return r
        if getattr(reader, "is_encrypted", False):
            try:
                reader.decrypt("")
            except Exception:
                r.error_code = "pdf_encrypted"
                return r
        pages_text: List[str] = []
        for i, page in enumerate(reader.pages):
            try:
                pages_text.append(page.extract_text() or "")
            except Exception as e:
                r.warnings.append(f"page_{i}_failed:{type(e).__name__}")
                pages_text.append("")
        r.pages = len(reader.pages)
        r.text = "\n\n".join(pages_text).strip()
        # Metadata PDF (only serializable fields)
        try:
            info = reader.metadata or {}
            r.metadata = {
                k.lstrip("/"): str(v) for k, v in info.items()
                if isinstance(v, (str, int, float)) or v is None
            }
        except Exception:
            r.metadata = {}
        return r


# ---------------------------------------------------------------------
# Impl: pytesseract
# ---------------------------------------------------------------------
class TesseractOCRProvider(OCRProvider):
    name = "tesseract"

    def extract(self, blob: bytes, mime_type: str) -> ExtractionResult:
        r = ExtractionResult(engine=self.name, ocr_used=True)
        try:
            import pytesseract
            from PIL import Image, ImageOps
        except Exception as e:
            r.error_code = "ocr_lib_missing"
            r.warnings.append(str(e))
            return r
        # Verify tesseract binary exists
        try:
            pytesseract.get_tesseract_version()
        except Exception:
            r.error_code = "ocr_engine_unavailable"
            return r
        try:
            img = Image.open(io.BytesIO(blob))
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
        except Exception as e:
            r.error_code = "image_unreadable"
            r.warnings.append(str(e))
            return r
        langs = os.environ.get("DOCUMENT_OCR_LANGS", "ita+eng")
        try:
            text = pytesseract.image_to_string(img, lang=langs)
            # Confidence via data (mean of positive confidences)
            try:
                data = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)
                confs = [int(c) for c in data.get("conf", []) if str(c).lstrip("-").isdigit() and int(c) >= 0]
                if confs:
                    r.confidence = round(sum(confs) / (len(confs) * 100.0), 3)
            except Exception:
                pass
        except Exception as e:
            r.error_code = "ocr_failed"
            r.warnings.append(str(e))
            return r
        r.text = text.strip()
        r.pages = 1
        return r


# ---------------------------------------------------------------------
# Impl: TextFileProvider (text/plain, text/csv, text/markdown, text/rtf)
# ---------------------------------------------------------------------
class TextFileProvider:
    name = "text_passthrough"

    def extract(self, blob: bytes, mime_type: str) -> ExtractionResult:
        r = ExtractionResult(engine=self.name)
        try:
            r.text = blob.decode("utf-8", errors="replace").strip()
        except Exception as e:
            r.error_code = "decode_failed"
            r.warnings.append(str(e))
            return r
        r.pages = 1
        return r


# ---------------------------------------------------------------------
# Text cleaner
# ---------------------------------------------------------------------
_MULTI_SPACE = re.compile(r"[ \t]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_CTRL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2028\u2029\ufeff]")


def clean_text(raw: str) -> str:
    if not raw:
        return ""
    txt = unicodedata.normalize("NFKC", raw)
    txt = _CTRL_CHARS.sub("", txt)
    txt = _ZERO_WIDTH.sub("", txt)
    # Line-by-line cleanup: strip whitespace ends, dedupe consecutive dup lines
    lines: List[str] = []
    prev: Optional[str] = None
    for line in txt.split("\n"):
        stripped = _MULTI_SPACE.sub(" ", line).strip()
        if not stripped:
            if lines and lines[-1] == "":
                continue
            lines.append("")
            prev = ""
            continue
        if stripped == prev:
            continue  # dedupe consecutive identical lines
        lines.append(stripped)
        prev = stripped
    joined = "\n".join(lines)
    joined = _MULTI_NEWLINE.sub("\n\n", joined)
    return joined.strip()


# ---------------------------------------------------------------------
# Language detection (lightweight — no external LLM)
# ---------------------------------------------------------------------
def detect_language(text: str) -> Optional[str]:
    """Heuristic detector on stop-word frequency. Returns 'it' | 'en' |
    None. Zero external deps."""
    if not text or len(text) < 20:
        return None
    lower = text.lower()
    it_hits = sum(1 for w in (" il ", " la ", " che ", " di ", " un ", " una ", " per ", " sono ", " del ", " gli ") if w in lower)
    en_hits = sum(1 for w in (" the ", " and ", " of ", " to ", " for ", " is ", " are ", " that ", " with ", " on ") if w in lower)
    if it_hits == 0 and en_hits == 0:
        return None
    return "it" if it_hits >= en_hits else "en"


# ---------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------
class ExtractionPipeline:
    """Sceglie il provider corretto in base al mime type e restituisce
    un ExtractionResult già ripulito. Non tocca il DB — questo lavoro
    è compito del chiamante (DocumentService)."""

    OCR_MIMES = frozenset({
        "image/jpeg", "image/jpg", "image/png", "image/webp",
        "image/heic", "image/heif", "image/tiff", "image/gif",
    })
    TEXT_MIMES = frozenset({
        "text/plain", "text/csv", "text/markdown", "text/rtf",
    })

    def __init__(self, *, pdf: Optional[PDFTextProvider] = None, ocr: Optional[OCRProvider] = None):
        self.pdf = pdf or PyPDFProvider()
        self.ocr = ocr or TesseractOCRProvider()
        self.text = TextFileProvider()

    def run(self, *, blob: bytes, mime_type: str) -> ExtractionResult:
        from time import perf_counter
        t0 = perf_counter()
        mime = (mime_type or "").lower().split(";")[0].strip()

        ocr_enabled = os.environ.get("DOCUMENT_OCR_ENABLED", "true").lower() in ("1", "true", "yes")
        extraction_enabled = os.environ.get("DOCUMENT_EXTRACTION_ENABLED", "true").lower() in ("1", "true", "yes")

        if not extraction_enabled:
            r = ExtractionResult(engine="disabled", warnings=["extraction_flag_off"])
            r.duration_ms = (perf_counter() - t0) * 1000
            return r

        if mime == "application/pdf":
            r = self.pdf.extract(blob)
            # Fallback OCR when PDF has zero text and OCR enabled — for
            # scanned PDFs. Iter20 keeps this minimal: only if the whole
            # extraction is empty AND we recognize no error.
            if ocr_enabled and (not r.text or len(r.text.strip()) < 5) and not r.error_code:
                r.warnings.append("pdf_empty_text")
        elif mime in self.OCR_MIMES:
            if not ocr_enabled:
                r = ExtractionResult(engine="ocr_disabled", warnings=["ocr_flag_off"])
            else:
                r = self.ocr.extract(blob, mime)
        elif mime in self.TEXT_MIMES:
            r = self.text.extract(blob, mime)
        else:
            r = ExtractionResult(engine="unsupported", warnings=[f"mime_not_supported:{mime}"])

        # Cleaning + language detection (always safe)
        cleaned = clean_text(r.text or "")
        r.text = cleaned
        r.language = r.language or detect_language(cleaned)
        r.duration_ms = (perf_counter() - t0) * 1000
        return r


# ---------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
