"""
The Gmail data plane: minimal reads plus one explicitly gated send.

    A CONNECTOR THAT CAN ONLY READ CANNOT BE TALKED INTO SENDING.

The protocol below keeps mailbox sensing read-minimal: the mailbox's own position
(`profile`), what has happened since a position (`history`), a first look when
there is no position yet (`list`), the headers of a message (`metadata`), and
— separately, deliberately awkward to reach — the text of one message.

`body_of` is the only method that returns what somebody wrote, and it exists
because a judgement is allowed to ask for it once. Everything else in this
package works from headers, which is why the default reading of a mailbox
carries no content at all.

Tokens arrive already materialised, exactly as in the calendar provider; this
file never touches OAuth, never persists anything, and never sees the vault.
"""

from __future__ import annotations

import base64
import os
from email.message import EmailMessage
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

import httpx

API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Only the headers this system has a use for. Asking for fewer headers is the
# cheapest privacy measure available: what is not fetched cannot leak.
WANTED_HEADERS = ("From", "To", "Cc", "Subject", "Date", "List-Unsubscribe")

# The most of a message body that ever leaves this file. A judgement that
# cannot be made from this much is not one that should be made by reading
# more of somebody's mail.
MAX_BODY_CHARS = 1200

# Attachments are never part of the ordinary mailbox sync. They can be read
# only after the relevance judgement asks for one, and even then this is the
# hard provider-side ceiling before bytes can leave the connector.
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


class GmailAPIError(Exception):
    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message or f"gmail_http_{status_code}")
        self.status_code = status_code

    @property
    def history_gone(self) -> bool:
        """The cursor is too old to be honoured. Not a failure — a restart."""
        return self.status_code == 404


@dataclass
class MessagesPage:
    messages: List[Dict[str, str]] = field(default_factory=list)
    next_page_token: Optional[str] = None
    # Where to resume from next time, when the provider says.
    history_id: Optional[str] = None


class GmailProviderProtocol(Protocol):
    async def profile(self, *, access_token: str) -> Dict[str, Any]: ...

    async def list_messages(
        self, *, access_token: str, query: str = "", page_token: Optional[str] = None,
        max_results: int = 25,
    ) -> MessagesPage: ...

    async def history(
        self, *, access_token: str, start_history_id: str,
        page_token: Optional[str] = None,
    ) -> MessagesPage: ...

    async def metadata_of(
        self, *, access_token: str, message_id: str,
    ) -> Dict[str, Any]: ...

    async def body_of(
        self, *, access_token: str, message_id: str,
    ) -> str: ...

    async def attachment_manifest(
        self, *, access_token: str, message_id: str,
    ) -> List[Dict[str, Any]]: ...

    async def attachment_bytes(
        self, *, access_token: str, message_id: str,
        attachment_id: str = "", part_id: str = "",
    ) -> bytes: ...

    async def send_message(
        self, *, access_token: str, to: str, subject: str, body: str,
        thread_id: str = "",
    ) -> Dict[str, Any]: ...


class GmailProvider:
    """The real provider. Reads stay minimal; send exists only through Gmail OAuth."""

    def __init__(self, *, timeout: float = 20.0):
        self.timeout = timeout

    async def _get(self, path: str, *, access_token: str, params: Any = None) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{API}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
        if r.status_code >= 400:
            # The body of an error can echo request content back. Only the
            # status travels.
            raise GmailAPIError(r.status_code)
        return r.json()

    async def _post(
        self, path: str, *, access_token: str, payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(
                f"{API}{path}",
                headers={"Authorization": f"Bearer {access_token}"},
                json=payload,
            )
        if r.status_code >= 400:
            raise GmailAPIError(r.status_code)
        return r.json()

    async def profile(self, *, access_token: str) -> Dict[str, Any]:
        return await self._get("/profile", access_token=access_token)

    async def list_messages(
        self, *, access_token: str, query: str = "", page_token: Optional[str] = None,
        max_results: int = 25,
    ) -> MessagesPage:
        params: List[Any] = [("maxResults", max_results)]
        if query:
            params.append(("q", query))
        if page_token:
            params.append(("pageToken", page_token))
        data = await self._get("/messages", access_token=access_token, params=params)
        return MessagesPage(
            messages=[
                {"id": str(m.get("id") or ""), "threadId": str(m.get("threadId") or "")}
                for m in (data.get("messages") or [])
            ],
            next_page_token=data.get("nextPageToken"),
        )

    async def history(
        self, *, access_token: str, start_history_id: str,
        page_token: Optional[str] = None,
    ) -> MessagesPage:
        """
        What has arrived since a position, or a 404 saying the position is gone.

        Gmail expires history after about a week. The 404 is not an error to
        be retried — it is the provider saying "resync" — and it is carried
        through as `history_gone` so the caller can do exactly that without
        parsing anything.
        """
        params: List[Any] = [
            ("startHistoryId", start_history_id),
            ("historyTypes", "messageAdded"),
        ]
        if page_token:
            params.append(("pageToken", page_token))
        data = await self._get("/history", access_token=access_token, params=params)

        seen: List[Dict[str, str]] = []
        for entry in data.get("history") or []:
            for added in entry.get("messagesAdded") or []:
                message = added.get("message") or {}
                seen.append({
                    "id": str(message.get("id") or ""),
                    "threadId": str(message.get("threadId") or ""),
                })
        return MessagesPage(
            messages=seen,
            next_page_token=data.get("nextPageToken"),
            history_id=str(data.get("historyId") or "") or None,
        )

    async def metadata_of(self, *, access_token: str, message_id: str) -> Dict[str, Any]:
        params: List[Any] = [("format", "metadata")]
        params.extend(("metadataHeaders", h) for h in WANTED_HEADERS)
        return await self._get(
            f"/messages/{message_id}", access_token=access_token, params=params,
        )

    async def body_of(self, *, access_token: str, message_id: str) -> str:
        """
        The text of one message, bounded, for one judgement that asked.

        Prefers `text/plain`; falls back to the message's own snippet rather
        than to stripping HTML, because a half-parsed marketing template is
        not a better answer than the provider's own summary line.
        """
        data = await self._get(
            f"/messages/{message_id}", access_token=access_token,
            params=[("format", "full")],
        )
        text = _plain_text(data.get("payload") or {})
        if not text:
            text = str(data.get("snippet") or "")
        return text[:MAX_BODY_CHARS]

    async def send_message(
        self, *, access_token: str, to: str, subject: str, body: str,
        thread_id: str = "",
    ) -> Dict[str, Any]:
        """Send one plain-text RFC message through the account that owns the token."""
        message = EmailMessage()
        message["To"] = str(to or "").strip()
        message["Subject"] = str(subject or "").strip()
        message.set_content(str(body or ""))
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        payload: Dict[str, Any] = {"raw": raw}
        if thread_id:
            payload["threadId"] = str(thread_id)[:200]
        data = await self._post("/messages/send", access_token=access_token, payload=payload)
        return {
            "id": str(data.get("id") or ""),
            "threadId": str(data.get("threadId") or ""),
            "labelIds": [str(x) for x in (data.get("labelIds") or [])][:12],
        }

    async def attachment_manifest(
        self, *, access_token: str, message_id: str,
    ) -> List[Dict[str, Any]]:
        """Read descriptors only. No attachment bytes leave Gmail here."""
        data = await self._get(
            f"/messages/{message_id}", access_token=access_token,
            params=[("format", "full")],
        )
        return _attachment_parts(data.get("payload") or {})

    async def attachment_bytes(
        self, *, access_token: str, message_id: str,
        attachment_id: str = "", part_id: str = "",
    ) -> bytes:
        """Read one attachment using a locator returned by the manifest."""
        raw = ""
        if attachment_id:
            data = await self._get(
                f"/messages/{message_id}/attachments/{attachment_id}",
                access_token=access_token,
            )
            raw = str(data.get("data") or "")
        elif part_id:
            data = await self._get(
                f"/messages/{message_id}", access_token=access_token,
                params=[("format", "full")],
            )
            part = _part_by_id(data.get("payload") or {}, part_id)
            raw = str(((part or {}).get("body") or {}).get("data") or "")
        blob = _decode_urlsafe(raw)
        if len(blob) > MAX_ATTACHMENT_BYTES:
            raise GmailAPIError(413, "attachment_too_large")
        return blob


def _decode_urlsafe(raw: str) -> bytes:
    if not raw:
        return b""
    try:
        padded = raw + ("=" * (-len(raw) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        return b""


def _part_by_id(part: Dict[str, Any], part_id: str) -> Optional[Dict[str, Any]]:
    if str(part.get("partId") or "") == str(part_id or ""):
        return part
    for child in part.get("parts") or []:
        found = _part_by_id(child, part_id)
        if found is not None:
            return found
    return None


def _attachment_parts(part: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten named file parts without returning body text or bytes."""
    out: List[Dict[str, Any]] = []
    filename = str(part.get("filename") or "").strip()
    body = part.get("body") or {}
    if filename:
        disposition = ""
        for header in part.get("headers") or []:
            if str(header.get("name") or "").lower() == "content-disposition":
                disposition = str(header.get("value") or "").lower()
                break
        out.append({
            "filename": filename[:255],
            "mime_type": str(part.get("mimeType") or "application/octet-stream")[:120],
            "attachment_id": str(body.get("attachmentId") or "")[:300],
            "part_id": str(part.get("partId") or "")[:120],
            "size": int(body.get("size") or 0),
            "inline": disposition.startswith("inline"),
        })
    for child in part.get("parts") or []:
        out.extend(_attachment_parts(child))
    return out


def _plain_text(part: Dict[str, Any]) -> str:
    """Depth-first walk for the first text/plain body. No HTML rendering."""
    if str(part.get("mimeType") or "") == "text/plain":
        raw = ((part.get("body") or {}).get("data")) or ""
        if raw:
            try:
                return base64.urlsafe_b64decode(raw + "==").decode("utf-8", "replace")
            except Exception:
                return ""
    for child in part.get("parts") or []:
        found = _plain_text(child)
        if found:
            return found
    return ""


class FakeGmailProvider:
    """
    A mailbox in a dictionary, for tests and for local work.

    Deliberately shares no code with the real one: a fake that reuses the
    real parsing would pass tests the real client fails, which is the one
    thing a fake must not do.
    """

    def __init__(self, *, address: str = "io@example.com"):
        self.address = address
        self.messages: Dict[str, Dict[str, Any]] = {}
        self.bodies: Dict[str, str] = {}
        self.order: List[str] = []
        self.history_id = "1000"
        # Positions the mailbox no longer remembers. Set by a test to make
        # the provider answer the way Gmail answers a week later.
        self.expired_history: set = set()
        # Messaggi che la history nomina ma che non ci sono piu': cancellati
        # fra una lettura e l'altra. Gmail risponde 404 a chi li chiede, ed e'
        # una cosa che succede da sola in ogni casella viva.
        self.vanished: set = set()
        self.body_reads: List[str] = []
        self.attachment_reads: List[str] = []
        self.attachment_blobs: Dict[str, bytes] = {}
        self.sent_messages: List[Dict[str, str]] = []

    def add(self, message_id: str, *, thread_id: str, headers: Dict[str, str],
            body: str = "", labels: Optional[List[str]] = None,
            internal_date: Optional[str] = None, attachments: int = 0) -> None:
        parts: List[Dict[str, Any]] = []
        for n in range(attachments):
            aid = f"{message_id}:a{n}"
            blob = b"%PDF-1.4\n% fake attachment\n%%EOF"
            self.attachment_blobs[aid] = blob
            parts.append({
                "partId": f"a{n}",
                "filename": f"a{n}.pdf",
                "mimeType": "application/pdf",
                "headers": [{"name": "Content-Disposition", "value": "attachment"}],
                "body": {"attachmentId": aid, "size": len(blob)},
            })
        self.messages[message_id] = {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": list(labels or ["INBOX"]),
            "internalDate": internal_date or "0",
            "snippet": (body or "")[:80],
            "payload": {
                "headers": [{"name": k, "value": v} for k, v in headers.items()],
                "parts": parts,
            },
        }
        self.bodies[message_id] = body
        self.order.append(message_id)
        self.history_id = str(int(self.history_id) + 1)

    def add_attachment(
        self, message_id: str, *, filename: str, mime_type: str,
        content: bytes, inline: bool = False,
    ) -> str:
        if message_id not in self.messages:
            raise KeyError(message_id)
        parts = (self.messages[message_id].get("payload") or {}).setdefault("parts", [])
        idx = len(parts)
        aid = f"{message_id}:att{idx}"
        blob = bytes(content)
        self.attachment_blobs[aid] = blob
        parts.append({
            "partId": f"att{idx}",
            "filename": filename,
            "mimeType": mime_type,
            "headers": [{
                "name": "Content-Disposition",
                "value": "inline" if inline else "attachment",
            }],
            "body": {"attachmentId": aid, "size": len(blob)},
        })
        return aid

    async def profile(self, *, access_token: str) -> Dict[str, Any]:
        return {"emailAddress": self.address, "historyId": self.history_id}

    async def list_messages(
        self, *, access_token: str, query: str = "", page_token: Optional[str] = None,
        max_results: int = 25,
    ) -> MessagesPage:
        rows = [
            {"id": mid, "threadId": self.messages[mid]["threadId"]}
            for mid in self.order[-max_results:]
        ]
        return MessagesPage(messages=rows)

    async def history(
        self, *, access_token: str, start_history_id: str,
        page_token: Optional[str] = None,
    ) -> MessagesPage:
        if start_history_id in self.expired_history:
            raise GmailAPIError(404)
        rows = [
            {"id": mid, "threadId": self.messages[mid]["threadId"]}
            for mid in self.order
            if mid not in getattr(self, "_delivered", set())
        ]
        return MessagesPage(messages=rows, history_id=self.history_id)

    async def metadata_of(self, *, access_token: str, message_id: str) -> Dict[str, Any]:
        if message_id in self.vanished:
            raise GmailAPIError(404)
        found = dict(self.messages.get(message_id) or {})
        found.pop("snippet", None)
        return found

    async def body_of(self, *, access_token: str, message_id: str) -> str:
        self.body_reads.append(message_id)
        return str(self.bodies.get(message_id) or "")[:MAX_BODY_CHARS]

    async def send_message(
        self, *, access_token: str, to: str, subject: str, body: str,
        thread_id: str = "",
    ) -> Dict[str, Any]:
        row = {
            "id": f"sent_{len(self.sent_messages) + 1}",
            "threadId": thread_id or f"thread_sent_{len(self.sent_messages) + 1}",
            "to": str(to), "subject": str(subject), "body": str(body),
        }
        self.sent_messages.append(row)
        self.messages[row["id"]] = {
            "id": row["id"],
            "threadId": row["threadId"],
            "labelIds": ["SENT"],
            "internalDate": "0",
            "payload": {
                "headers": [
                    {"name": "To", "value": row["to"]},
                    {"name": "Subject", "value": row["subject"]},
                ],
                "parts": [],
            },
        }
        self.bodies[row["id"]] = row["body"]
        self.order.append(row["id"])
        return {"id": row["id"], "threadId": row["threadId"], "labelIds": ["SENT"]}

    async def attachment_manifest(
        self, *, access_token: str, message_id: str,
    ) -> List[Dict[str, Any]]:
        found = self.messages.get(message_id) or {}
        return _attachment_parts((found.get("payload") or {}))

    async def attachment_bytes(
        self, *, access_token: str, message_id: str,
        attachment_id: str = "", part_id: str = "",
    ) -> bytes:
        self.attachment_reads.append(f"{message_id}:{attachment_id or part_id}")
        blob = bytes(self.attachment_blobs.get(attachment_id, b""))
        if len(blob) > MAX_ATTACHMENT_BYTES:
            raise GmailAPIError(413, "attachment_too_large")
        return blob


def build_gmail_provider() -> GmailProviderProtocol:
    mode = (os.environ.get("GMAIL_PROVIDER_MODE") or "real").strip().lower()
    if mode == "fake":
        return FakeGmailProvider()
    return GmailProvider()
