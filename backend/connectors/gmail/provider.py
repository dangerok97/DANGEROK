"""
The Gmail data plane: four reads, and no way to write.

    A CONNECTOR THAT CAN ONLY READ CANNOT BE TALKED INTO SENDING.

The protocol below is the whole surface: the mailbox's own position
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


class GmailProvider:
    """The real one. Read verbs only, because there are no others."""

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

    def add(self, message_id: str, *, thread_id: str, headers: Dict[str, str],
            body: str = "", labels: Optional[List[str]] = None,
            internal_date: Optional[str] = None, attachments: int = 0) -> None:
        self.messages[message_id] = {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": list(labels or ["INBOX"]),
            "internalDate": internal_date or "0",
            "snippet": (body or "")[:80],
            "payload": {
                "headers": [{"name": k, "value": v} for k, v in headers.items()],
                "parts": [{"filename": f"a{n}.pdf"} for n in range(attachments)],
            },
        }
        self.bodies[message_id] = body
        self.order.append(message_id)
        self.history_id = str(int(self.history_id) + 1)

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


def build_gmail_provider() -> GmailProviderProtocol:
    mode = (os.environ.get("GMAIL_PROVIDER_MODE") or "real").strip().lower()
    if mode == "fake":
        return FakeGmailProvider()
    return GmailProvider()
