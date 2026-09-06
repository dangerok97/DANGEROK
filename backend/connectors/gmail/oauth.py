"""
Where Gmail's OAuth differs from the calendar's, which is in three places.

    ONE CLIENT, ONE STATE STORE, ONE VAULT — TWO CONSENTS.

Everything that makes an OAuth flow safe already exists in this app and is
reused verbatim: the PKCE verifier, the one-shot owner-bound state, the token
exchange, the refresh, the vault, the revoke. Building a second copy of any
of that would double the number of places a mistake could live, and OAuth
mistakes are the expensive kind.

What is genuinely different is small and worth naming.

**The callback address.** Google matches the redirect URI exactly, so a
second flow needs a second registered URI. It is derived from the one the
calendar already uses rather than typed again, so the pair stays consistent
and the URI to register is a function of what is registered already.

**The scopes.** A mailbox is a different question from a calendar, and this
asks only its own: `gmail.readonly` plus the identity scopes the shared flow
already uses. Nothing here can ask for send, compose or modify — those
strings do not exist in this package.

**Which flow a state belongs to.** The two connectors share one state store,
so a state minted for Gmail must not be spendable at the calendar callback or
the reverse. The flow name travels with the state and is checked when it is
consumed.
"""

from __future__ import annotations

from typing import List, Optional

from connectors.google_calendar.oauth import (
    OAuthConfigError,
    redirect_uris_from,
    resolve_redirect_uri as _resolve_within,
)

from .scopes import CONNECTOR_ID, GMAIL_SCOPES

# The path Google will call back on. Kept as a constant because it appears in
# three places that must agree: the router, the derived redirect URI, and the
# line in the Google Cloud console somebody has to paste it into.
CALLBACK_PATH = "/api/connectors/gmail/oauth/callback"

# The name this flow's states carry. Not the connector id by accident — it is
# the connector id on purpose, so a row in the store says which connection it
# was going to make.
FLOW = CONNECTOR_ID


def gmail_redirect_uris() -> List[str]:
    """
    The callback URIs registered for Gmail, loopback twins included.

    `GMAIL_OAUTH_REDIRECT_URI` / `GMAIL_OAUTH_REDIRECT_URIS` override; with
    neither set, the URI is the calendar's own origin with this flow's path,
    which is what makes the pair to register in Google Cloud predictable.
    """
    return redirect_uris_from(
        "GMAIL_OAUTH_REDIRECT_URI",
        "GMAIL_OAUTH_REDIRECT_URIS",
        fallback_path=CALLBACK_PATH,
    )


def resolve_gmail_redirect_uri(
    *, preferred: Optional[str] = None, request_base: Optional[str] = None,
) -> str:
    """The registered callback that matches how this person reached the app."""
    allowed = gmail_redirect_uris()
    if not allowed:
        raise OAuthConfigError(
            "GMAIL_OAUTH_REDIRECT_URI missing and no GOOGLE_OAUTH_REDIRECT_URI "
            "to derive it from"
        )
    return _resolve_within(
        preferred=preferred, request_base=request_base, allowed=allowed,
    )


def scopes_requested() -> List[str]:
    """
    What ORA asks Google for when somebody connects a mailbox.

    Read and identity. The list is returned rather than exported as a mutable
    constant so a caller cannot append to it in passing — which sounds
    paranoid until you consider what appending one string here would let this
    application do.
    """
    return list(GMAIL_SCOPES)
