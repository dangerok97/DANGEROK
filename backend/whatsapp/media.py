"""Secure media access for official Meta WhatsApp Cloud API.

Only signed webhooks are accepted upstream. Media IDs are looked up through
Meta's Graph API; download URLs are restricted to verified Meta-controlled
hosts, with no redirects and bounded content. Tokens, private phone numbers,
and media bytes are never logged.
"""
from __future__ import annotations

import hashlib
import os
import re
from urllib.parse import urlparse

import httpx

_IMAGE_TYPES = frozenset(("image/jpeg", "image/png", "image/webp", "image/heic"))
_DOCUMENT_TYPES = frozenset((
    "application/pdf", "text/plain", "text/csv", "text/markdown",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
))
_AUDIO_TYPES = frozenset((
    "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac",
    "audio/wav", "audio/x-wav", "audio/webm",
))
_MAX_IMAGE_DOC = 12 * 1024 * 1024
_MAX_AUDIO = 16 * 1024 * 1024


class MediaNotUsable(Exception):
    """Reason code only; do not expose Meta's raw HTTP response."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _is_meta_media_host(value: str) -> bool:
    try:
        target = urlparse(value)
        host = (target.hostname or "").lower()
        return (
            target.scheme == "https"
            and target.port in (None, 443)
            and target.username is None
            and target.password is None
            and (
                host in ("lookaside.fbsbx.com", "lookaside.facebook.com")
                or host.endswith(".fbcdn.net")
                or host.endswith(".whatsapp.net")
            )
        )
    except ValueError:
        return False


async def fetch_whatsapp_media(
    *, access_token: str, version: str, media_id: str,
    kind: str, declared_mime: str = "",
) -> tuple[bytes, str]:
    """Return sanitized media bytes and verified MIME, or fail safely."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,180}", str(media_id or "")):
        raise MediaNotUsable("invalid_media_reference")
    if kind not in ("image", "document", "audio"):
        raise MediaNotUsable("unsupported_kind")
    limit = _MAX_AUDIO if kind == "audio" else _MAX_IMAGE_DOC
    allowed = _IMAGE_TYPES if kind == "image" else _AUDIO_TYPES if kind == "audio" else _DOCUMENT_TYPES
    headers = {"Authorization": f"Bearer {access_token}"}
    graph_url = f"https://graph.facebook.com/{version}/{media_id}"
    try:
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=httpx.Timeout(25.0)
        ) as client:
            metadata_response = await client.get(graph_url, headers=headers)
            if metadata_response.status_code != 200:
                raise MediaNotUsable("media_metadata_unavailable")
            metadata = metadata_response.json()
            if not isinstance(metadata, dict):
                raise MediaNotUsable("media_metadata_invalid")
            mime = str(metadata.get("mime_type") or declared_mime or "").split(";")[0].strip().lower()
            if mime not in allowed:
                raise MediaNotUsable("unsupported_mime")
            size = metadata.get("file_size")
            if size is not None and (
                not isinstance(size, int) or isinstance(size, bool)
                or size < 0 or size > limit
            ):
                raise MediaNotUsable("media_too_large")
            url = metadata.get("url")
            if not isinstance(url, str) or not _is_meta_media_host(url):
                raise MediaNotUsable("media_url_not_trusted")
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    raise MediaNotUsable("media_download_unavailable")
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > limit:
                        raise MediaNotUsable("media_too_large")
            if not data:
                raise MediaNotUsable("media_empty")
            if size is not None and len(data) != size:
                raise MediaNotUsable("media_size_mismatch")
            digest = str(metadata.get("sha256") or "")
            if re.fullmatch(r"[0-9a-fA-F]{64}", digest) and hashlib.sha256(data).hexdigest() != digest.lower():
                raise MediaNotUsable("media_integrity_mismatch")
            return bytes(data), mime
    except (httpx.RequestError, ValueError, TypeError) as exc:
        raise MediaNotUsable("media_network_error") from exc


async def transcribe_voice(audio: bytes, mime_type: str, *, api_key: str | None = None) -> str:
    """Convert a user-sent WhatsApp voice note to text for the shared AI Core."""
    key = (api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")).strip()
    if not key:
        raise MediaNotUsable("transcription_not_configured")
    ext = {
        "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
        "audio/aac": ".aac", "audio/wav": ".wav",
        "audio/x-wav": ".wav", "audio/webm": ".webm",
    }.get(mime_type)
    if not ext or not audio or len(audio) > _MAX_AUDIO:
        raise MediaNotUsable("unsupported_audio")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
            response = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data={"model": "gpt-4o-mini-transcribe", "language": "it"},
                files={"file": ("ora_whatsapp" + ext, audio, mime_type)},
            )
            if response.status_code != 200:
                raise MediaNotUsable("transcription_unavailable")
            text = str((response.json() or {}).get("text") or "").strip()
            if not text:
                raise MediaNotUsable("transcription_empty")
            return text[:5000]
    except (httpx.RequestError, ValueError, TypeError) as exc:
        raise MediaNotUsable("transcription_unavailable") from exc
