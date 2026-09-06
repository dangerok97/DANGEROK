"""Gmail connector — identifiers, scopes, and why they are the ones asked for.

    EMAIL IS NOT A FEATURE. IT IS A SENSOR OF THE LIFE.

Two scopes were possible and the choice is worth writing down.

`gmail.metadata` would give headers and nothing else — no body, ever, at any
point. It is the smaller ask, and it would make the design's own promise
unkeepable: a judgement that genuinely cannot decide without seeing what a
message says would have nowhere to look, and the honest answer would be to
report the fact and stop.

`gmail.readonly` is what is asked for, because the design is built the other
way round: nothing but headers is read by default, the body is fetched only
when a judgement says it cannot decide without it, that fetch is bounded and
audited, and what comes back is never stored. The scope is wider than the
default behaviour deliberately — the narrowing lives in the code and is
enforced by tests, where it can be checked, rather than in a scope string
that would also forbid the one legitimate case.

Nothing here asks for send, modify, or labels. Those scopes are not requested
because ORA does not do those things.
"""

from __future__ import annotations

GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "email",
    "profile",
)

# Header-only mode: kept named because it is a real product option (a person
# who does not want ORA able to read a body at all), and naming it is how the
# option stays visible rather than being rediscovered later.
GMAIL_METADATA_SCOPES = (
    "https://www.googleapis.com/auth/gmail.metadata",
    "openid",
    "email",
    "profile",
)

CONNECTOR_ID = "mail_gmail"
CAPABILITY_ID = "mail.metadata"
CAPABILITY_READ_ID = "mail.read"

# The record type every mail row carries into ingestion. The email sensor
# reads by this and not by `source_type`, which holds the connector's own id.
EMAIL_RECORD_TYPE = "email_message"
