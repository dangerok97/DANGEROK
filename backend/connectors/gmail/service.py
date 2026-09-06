"""
Reading a mailbox the way ORA reads a calendar: incrementally, and minimally.

    A MAILBOX IS NOT A THING TO COPY. IT IS A THING TO NOTICE CHANGES IN.

This is the smallest connector that can honestly be called a read: connect,
resume from where we were, fetch the headers of what is new, write an
ingestion row per message, move the cursor. There is no send, no reply, no
label, no archive and no delete, because none of those verbs exists anywhere
in this package.

Three things it is careful about.

**The cursor is Gmail's own.** A mailbox's position is its `historyId`, and
Gmail forgets positions older than about a week. That expiry is not a
failure: it is answered with a bounded resync of recent messages, and the
dedupe below turns the overlap into nothing. Inventing our own cursor from
timestamps would have been a second position to keep in step with the first.

**Nothing that was written is stored.** The row holds who it is from, what it
is about, when it arrived, which thread it belongs to and whether anything
was attached. The body is not fetched here at all — it is fetched, once and
transiently, only if a judgement says it cannot decide without it.

**A failure leaves a mailbox saying so.** Every exit path either advances the
cursor after a real reading or leaves it exactly where it was. A sync that
half-worked and moved the cursor would silently lose everything in the gap.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from connectors.google_calendar.oauth import (
    OAuthConfigError,
    OAuthStateStore,
    build_authorize_url,
    exchange_code_for_tokens,
    fetch_userinfo,
    revoke_token,
    sanitize_redirect_after,
)
from connectors.instances import ConnectorInstanceService
from ingestion.deduplication import (
    DEDUP_ACTION_SKIP_UNCHANGED,
    DEDUP_ACTION_UPDATE_SUPERSEDED,
    DeduplicationService,
)
from ingestion.event_model import IngestionEventRepository, compute_payload_hash

from .oauth import FLOW, resolve_gmail_redirect_uri, scopes_requested
from .provider import GmailAPIError, GmailProviderProtocol, build_gmail_provider
from .scopes import CAPABILITY_ID, CAPABILITY_READ_ID, CONNECTOR_ID, EMAIL_RECORD_TYPE

logger = logging.getLogger("ora.connectors.gmail")

# How many messages one pass will look at. A mailbox is unbounded and a
# person coming back from holiday must not become an unbounded amount of
# work — the rest is still there on the next pass.
MAX_PER_SYNC = 25

# How far back a resync reaches when the cursor has expired. Recent enough to
# recover the gap, short enough not to become an import of somebody's archive.
RESYNC_QUERY = "newer_than:7d"

_ROLE_LOCAL_PARTS = ("noreply", "no-reply", "donotreply", "do-not-reply", "notifications")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _header(message: Dict[str, Any], name: str) -> str:
    headers = ((message.get("payload") or {}).get("headers")) or []
    for row in headers:
        if str(row.get("name") or "").lower() == name.lower():
            return str(row.get("value") or "")
    return ""


def _address(raw: str) -> str:
    """The address out of a `Name <a@b>` header. Never the display name."""
    value = str(raw or "").strip()
    if "<" in value and ">" in value:
        value = value[value.index("<") + 1:value.index(">")]
    return value.strip().lower()[:200]


def _received_at(message: Dict[str, Any]) -> str:
    raw = str(message.get("internalDate") or "").strip()
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc).isoformat()
        except Exception:
            pass
    return _now_iso()


def sender_relationship(message: Dict[str, Any], *, account: str, known: set) -> str:
    """
    What can be *known* about who sent this, and nothing more.

        A RELATIONSHIP IS A FACT ABOUT THE SENDER, NEVER A VERDICT ON THE MAIL.

    Three answers are derivable from evidence and are given; everything else
    is `unknown`, which is a true answer.

      `self`          the address is this person's own account.
      `automated`     the message carries List-Unsubscribe, or is from a
                      no-reply address. Both are facts about the message.
      `known_person`  this address already appears in their own calendar, as
                      an organiser or a guest. Evidence, not inference.

    What is deliberately absent is a guess at "organization" from the domain.
    A hospital, a bank and an airline all look like a stranger from here, and
    a code path that sorted them by domain would be deciding what matters in
    somebody's life from a string — which is the whole thing this design is
    against. `automated` in particular must never read as unimportant: it is
    what a flight change and a bank alert both look like.
    """
    sender = _address(_header(message, "From"))
    if not sender:
        return "unknown"
    if account and sender == str(account).strip().lower():
        return "self"
    if _header(message, "List-Unsubscribe"):
        return "automated"
    if sender.split("@")[0] in _ROLE_LOCAL_PARTS:
        return "automated"
    if sender in known:
        return "known_person"
    return "unknown"


def normalize(message: Dict[str, Any], *, account: str, known: set) -> Dict[str, Any]:
    """
    One message, reduced to what a life can be sensed through.

    The subject travels because it is the message's own statement of what it
    is about, and nothing downstream could link an email to an appointment
    without it. The body does not travel at all, the recipients travel as a
    count, and the sender travels as a relationship rather than as an address.
    """
    payload = message.get("payload") or {}
    parts = payload.get("parts") or []
    recipients = [
        a for a in (_header(message, "To") + "," + _header(message, "Cc")).split(",")
        if a.strip()
    ]
    return {
        "message_ref": str(message.get("id") or ""),
        "thread_ref": str(message.get("threadId") or ""),
        "subject": _header(message, "Subject")[:200],
        "sender_relationship": sender_relationship(
            message, account=account, known=known,
        ),
        "recipient_count": len(recipients),
        "received_at": _received_at(message),
        "attachments_present": any(p.get("filename") for p in parts),
        "attachment_count": sum(1 for p in parts if p.get("filename")),
        # The provider's own filing, as a fact. Never as a verdict: a
        # promotions label is what Google thinks, and what Google thinks
        # about somebody's life is evidence at best.
        "provider_categories": [
            str(l)[:40] for l in (message.get("labelIds") or [])
            if str(l).startswith("CATEGORY_")
        ][:4],
        "in_inbox": "INBOX" in (message.get("labelIds") or []),
        # Whether there is more to read, so a judgement knows that asking is
        # possible rather than guessing that it is not.
        "content_available": True,
    }


class GmailReadService:
    """Connect a mailbox, read what is new, and stop there."""

    def __init__(self, *, db, permissions, vault, provider: Optional[GmailProviderProtocol] = None):
        self.db = db
        self.permissions = permissions
        self.vault = vault
        self.provider: GmailProviderProtocol = provider or build_gmail_provider()
        self.instances = ConnectorInstanceService(db)
        self.repo = IngestionEventRepository(db)
        self.dedup = DeduplicationService(self.repo)
        # The same store the calendar flow uses. Shared deliberately: one
        # place where a state is minted, expired and spent is one place to
        # get right.
        self.oauth_state = OAuthStateStore(db)

    # --- connecting ------------------------------------------------------

    async def start_oauth(
        self,
        *,
        user_id: str,
        redirect_after: Optional[str] = None,
        request_base: Optional[str] = None,
        preferred_redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Begin a connection: mint a state, and say where to send the person.

        The state is owner-bound, one-shot, short-lived and carries this
        flow's name — so a state minted here cannot be spent at the
        calendar's callback, which asked Google for entirely different
        permissions.
        """
        redirect_uri = resolve_gmail_redirect_uri(
            preferred=preferred_redirect_uri, request_base=request_base,
        )
        session = await self.oauth_state.create(
            user_id=user_id,
            redirect_after=sanitize_redirect_after(redirect_after),
            redirect_uri=redirect_uri,
            flow=FLOW,
        )
        await self.permissions.audit.log(
            user_id=user_id, event_type="oauth.start", connector_id=CONNECTOR_ID,
            capability_id=CAPABILITY_ID, success=True, reason_code="state_created",
            data_classification="public",
        )
        return {
            "authorize_url": build_authorize_url(
                state=session["state"],
                code_challenge=session["code_challenge"],
                redirect_uri=redirect_uri,
                scopes=scopes_requested(),
            ),
            "state": session["state"],
            "expires_at": session["expires_at"],
        }

    async def handle_oauth_callback(self, *, state: str, code: str) -> Dict[str, Any]:
        """
        Finish a connection: spend the state, keep the tokens, build the instance.

        Order matters and is the calendar's order for the same reasons: the
        state is spent before anything is trusted, tokens go to the vault and
        never to the ordinary database, and the ORA-side consent is recorded
        against this exact instance rather than against the person in
        general.
        """
        session = await self.oauth_state.consume(state=state, expect_flow=FLOW)
        user_id = session["user_id"]
        redirect_after = sanitize_redirect_after(session.get("redirect_after"))

        tokens = await exchange_code_for_tokens(
            code=code,
            code_verifier=session["code_verifier"],
            redirect_uri=session.get("redirect_uri"),
        )
        userinfo = await fetch_userinfo(tokens["access_token"])
        account_id = userinfo.get("sub") or userinfo.get("email")
        if not account_id:
            await self.permissions.audit.log(
                user_id=user_id, event_type="oauth.callback", connector_id=CONNECTOR_ID,
                capability_id=CAPABILITY_ID, success=False,
                reason_code="userinfo_missing_sub",
            )
            raise OAuthConfigError("userinfo missing account identifier")

        granted = (tokens.get("scope") or "").split()
        if not any("gmail.readonly" in scope for scope in granted):
            # They reached the end of the flow without granting the one thing
            # this connection is for. Refusing here rather than building a
            # mailbox that cannot be read is the difference between an honest
            # error and a source that silently reports nothing forever.
            await self.permissions.audit.log(
                user_id=user_id, event_type="oauth.callback", connector_id=CONNECTOR_ID,
                capability_id=CAPABILITY_ID, success=False,
                reason_code="gmail_scope_not_granted",
            )
            raise OAuthConfigError("gmail.readonly was not granted")

        secret_ref = await self.vault.put(
            user_id=user_id,
            purpose=f"{CONNECTOR_ID}:oauth",
            payload={
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "token_type": tokens.get("token_type"),
                "expires_at": (
                    _now() + timedelta(seconds=int(tokens.get("expires_in") or 3600))
                ).isoformat(),
                "scope": tokens.get("scope"),
            },
            metadata={"connector_id": CONNECTOR_ID,
                      "account_hint": userinfo.get("email")},
        )

        instance = await self.instances.upsert(
            user_id=user_id,
            connector_id=CONNECTOR_ID,
            provider_account_id=str(account_id),
            display_label=userinfo.get("email") or "Gmail",
            platform="web",
            authorized_scopes=granted,
            sync_mode="polling",
            secret_reference=secret_ref,
            status="connected",
            # The account, and nothing else. No cursor is invented here: a
            # mailbox with no position has never been read, and the first
            # sync says so by doing a bounded resync rather than by trusting
            # a number nobody obtained from Google.
            metadata={"account_email": userinfo.get("email")},
        )

        try:
            await self.permissions.grant(
                user_id=user_id,
                capability_id=CAPABILITY_ID,
                connector_id=CONNECTOR_ID,
                connector_instance_id=instance["id"],
                purpose_id="context_assembly",
                scopes=scopes_requested(),
                actor_type="user",
            )
            # Reading a body is a second, narrower thing, and it is granted
            # here because it is what the person just authorised Google to
            # allow. What keeps it rare is not the absence of the grant: it
            # is that nothing reads a body unless a judgement says it cannot
            # decide without one, and every such read is written down.
            await self.permissions.grant(
                user_id=user_id,
                capability_id=CAPABILITY_READ_ID,
                connector_id=CONNECTOR_ID,
                connector_instance_id=instance["id"],
                purpose_id="context_assembly",
                scopes=scopes_requested(),
                actor_type="user",
            )
        except Exception:
            logger.exception("permissions grant failed post-callback")

        await self.permissions.audit.log(
            user_id=user_id, event_type="oauth.callback", connector_id=CONNECTOR_ID,
            connector_instance_id=instance["id"], capability_id=CAPABILITY_ID,
            success=True, reason_code="connected", data_classification="personal",
        )
        return {"instance": instance, "redirect_after": redirect_after}

    async def revoke(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        """
        Disconnect a mailbox: stop reading it, and give the tokens back.

            DISCONNECTING IS NOT FORGETTING.

        What is undone is the ability to read: the token is revoked at Google
        and dropped from the vault, the ORA-side consents are withdrawn, and
        the instance is marked revoked so the source reports itself
        disconnected and no sync will run. What is deliberately left alone is
        everything already learned — observations that went through
        governance are part of what ORA knows about this person's life, and
        unplugging a mailbox is not a request to forget their life.
        """
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")

        if instance.get("secret_reference"):
            try:
                payload = await self.vault.get(
                    instance["secret_reference"], user_id=user_id,
                )
                token = payload.get("refresh_token") or payload.get("access_token")
                if token:
                    await revoke_token(token)
            except Exception:
                logger.exception("gmail token revoke at google failed")
            await self.vault.revoke(instance["secret_reference"])

        for capability in (CAPABILITY_ID, CAPABILITY_READ_ID):
            try:
                await self.permissions.revoke(
                    user_id=user_id, capability_id=capability,
                    connector_id=CONNECTOR_ID, connector_instance_id=instance_id,
                    reason="user_revoked",
                )
            except Exception:
                logger.exception("gmail consent revoke failed")

        updated = await self.instances.mark_status(user_id, instance_id, "revoked")
        await self.permissions.audit.log(
            user_id=user_id, event_type="mail.revoke", connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
            success=True, reason_code="user_revoked", data_classification="public",
        )
        return {"ok": True, "instance": updated}

    async def list_instances(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.instances.list(user_id, connector_id=CONNECTOR_ID)

    async def get_instance(self, user_id: str, instance_id: str) -> Optional[Dict[str, Any]]:
        return await self.instances.get(user_id, instance_id)

    def config_status(self) -> Dict[str, Any]:
        """
        Whether a mailbox could be connected at all. Booleans only.

        Never a value, a secret, or a redirect URI: a diagnostic endpoint
        that echoed configuration back would be a way to read the
        configuration.
        """
        from .oauth import gmail_redirect_uris

        return {
            "client_configured": bool(
                os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
                and os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
            ),
            "callback_registered": bool(gmail_redirect_uris()),
        }

    # --- reading ---------------------------------------------------------

    async def sync(self, *, user_id: str, instance_id: str) -> Dict[str, Any]:
        """
        Read what has arrived since last time.

        Returns counts rather than content, which is also all a caller needs:
        the messages themselves are now ingestion rows, and what they mean is
        somebody else's job entirely.
        """
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        await self._require_consent(user_id=user_id, instance_id=instance_id)

        token = await self._access_token(user_id=user_id, instance=instance)
        cursor = dict(instance.get("cursor") or {})
        account = str((instance.get("metadata") or {}).get("account_email") or "")

        page, resynced = await self._what_is_new(token, cursor.get("history_id"))
        known = await self._addresses_they_already_deal_with(user_id)

        written = 0
        skipped = 0
        for row in page.messages[:MAX_PER_SYNC]:
            try:
                message = await self.provider.metadata_of(
                    access_token=token, message_id=row["id"],
                )
            except GmailAPIError as e:
                # UN MESSAGGIO SPARITO NON E' UNA CASELLA ROTTA.
                #
                # La history dice cosa e' cambiato, e una mail arrivata e poi
                # cancellata resta nominata li'. Chiederla risponde 404 — e
                # fino a qui quel 404 usciva dall'intera lettura: bastava un
                # messaggio buttato via perche' la casella non venisse piu'
                # letta, mai piu', in silenzio. Era esattamente lo stato di
                # questo account.
                #
                # Un messaggio che non c'e' piu' si salta. Tutto il resto
                # continua a essere un guasto, e come tale esce.
                if e.status_code != 404:
                    raise
                logger.info("messaggio non piu' disponibile: saltato")
                skipped += 1
                continue
            if not message:
                continue
            outcome = await self._record(
                user_id=user_id, instance_id=instance_id,
                message=message, account=account, known=known,
            )
            if outcome == "written":
                written += 1
            else:
                skipped += 1

        # The position moves only after a reading that finished, and so does
        # the note of when the mailbox was last read — which is the one fact
        # a person is shown about it. Written even when the provider gave no
        # new position: the reading still happened, and a screen saying "mai
        # sincronizzato" after a successful sync is the screen lying.
        position = page.history_id or await self._position(token)
        touched: Dict[str, Any] = {"last_sync_at": _now_iso()}
        if position:
            cursor["history_id"] = position
            touched["cursor"] = cursor
        await self.instances.update(user_id, instance_id, touched)

        await self.permissions.audit.log(
            user_id=user_id, event_type="mail.sync", connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, capability_id=CAPABILITY_ID,
            success=True, records_returned=written,
            reason_code="resynced" if resynced else "incremental",
            data_classification="sensitive",
        )
        return {
            "ok": True, "written": written, "skipped": skipped,
            "resynced": resynced, "history_id": cursor.get("history_id"),
        }

    async def _what_is_new(
        self, token: str, history_id: Optional[str],
    ) -> Tuple[Any, bool]:
        """
        The incremental read, and the honest fallback when it is not possible.

        A mailbox with no position has never been read, and a position Gmail
        has forgotten is the same situation with a different cause. Both are
        answered by a bounded look at recent messages — never by an unbounded
        one, and never by pretending the mailbox is empty.
        """
        if history_id:
            try:
                return await self.provider.history(
                    access_token=token, start_history_id=history_id,
                ), False
            except GmailAPIError as e:
                if not e.history_gone:
                    raise
                logger.info("gmail history expired; bounded resync")
        return await self.provider.list_messages(
            access_token=token, query=RESYNC_QUERY, max_results=MAX_PER_SYNC,
        ), bool(history_id)

    async def _record(
        self, *, user_id: str, instance_id: str, message: Dict[str, Any],
        account: str, known: set,
    ) -> str:
        """
        One message as one ingestion row, deduped the way every source is.

        The same message seen twice — by a history replay, by a resync after
        an expired cursor, by two overlapping passes — hashes the same and is
        skipped. A message whose thread state moved supersedes the row before
        it, which is what lets a sensor say what changed rather than that
        something exists.
        """
        normalized = normalize(message, account=account, known=known)
        external_id = normalized["message_ref"]
        if not external_id:
            return "skipped"
        payload_hash = compute_payload_hash(normalized)

        decision = await self.dedup.decide(
            user_id=user_id, connector_instance_id=instance_id,
            external_id=external_id, external_version=payload_hash,
            payload_hash=payload_hash,
        )
        if decision.action == DEDUP_ACTION_SKIP_UNCHANGED:
            return "skipped"

        doc = await self.repo.insert(
            user_id=user_id,
            connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id,
            external_id=external_id,
            external_version=payload_hash,
            source_type=CONNECTOR_ID,
            source_record_type=EMAIL_RECORD_TYPE,
            # A pointer, never the message. Somebody asking "which mail was
            # this" gets an answer; nobody reading this collection gets to
            # read the mail.
            raw_reference={"message_id": external_id,
                           "thread_id": normalized["thread_ref"]},
            normalized_payload=normalized,
            payload_hash=payload_hash,
            source_created_at=normalized["received_at"],
            source_updated_at=normalized["received_at"],
            provenance={"connector_id": CONNECTOR_ID,
                        "connector_instance_id": instance_id,
                        "source_type": CONNECTOR_ID},
            sensitivity="sensitive",
            status="processed",
        )
        if decision.action == DEDUP_ACTION_UPDATE_SUPERSEDED and decision.previous_event_id:
            await self.repo.mark_superseded(decision.previous_event_id)
            await self.repo.update_status(
                doc["id"], status="processed",
                supersedes_event_id=decision.previous_event_id,
            )
        return "written"

    async def _addresses_they_already_deal_with(self, user_id: str) -> set:
        """
        Who is already in this person's calendar, as evidence for "known".

        Read from what has already been observed rather than from a contacts
        scope nobody granted. It answers a narrow question narrowly: has this
        address been in a room with them before.
        """
        found: set = set()
        try:
            rows = await self.db.ingestion_events.find(
                {"user_id": user_id, "source_record_type": "calendar_event"},
                {"_id": 0, "normalized_payload": 1},
            ).sort("ingested_at", -1).to_list(60)
        except Exception as e:
            logger.info("known addresses soft-fail: %s", type(e).__name__)
            return found

        from connected.calendar_sensor import _unwrap

        for row in rows:
            payload = _unwrap(row.get("normalized_payload"))
            for value in [payload.get("organizer")] + list(payload.get("attendees") or []):
                address = _address(str(value or ""))
                if "@" in address:
                    found.add(address)
        return found

    # --- plumbing --------------------------------------------------------

    async def _position(self, token: str) -> Optional[str]:
        try:
            profile = await self.provider.profile(access_token=token)
        except Exception as e:
            logger.info("gmail profile soft-fail: %s", type(e).__name__)
            return None
        return str(profile.get("historyId") or "") or None

    async def _require_consent(self, *, user_id: str, instance_id: str) -> None:
        from permissions.errors import ConsentDenied

        ok = await self.permissions.check_access(
            user_id=user_id, capability_id=CAPABILITY_ID, connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, purpose_id="context_assembly",
        )
        if not ok:
            raise ConsentDenied(
                capability_id=CAPABILITY_ID, connector_id=CONNECTOR_ID,
                connector_instance_id=instance_id,
            )

    async def _access_token(self, *, user_id: str, instance: Dict[str, Any]) -> str:
        """
        The same vault, the same refresh, the same reauthorisation state.

        Reused rather than reimplemented: a second token path is a second
        place for a refresh to go wrong, and the failure mode of that is a
        mailbox that looks empty because a token quietly expired.
        """
        from connectors.google_calendar.oauth import refresh_access_token

        secret_ref = instance.get("secret_reference")
        if not secret_ref:
            raise LookupError("instance_has_no_secret")
        payload = await self.vault.get(secret_ref, user_id=user_id)
        expires_at = payload.get("expires_at")
        if expires_at and expires_at < _now_iso():
            fresh = await refresh_access_token(refresh_token=payload["refresh_token"])
            payload["access_token"] = fresh["access_token"]
            payload["expires_at"] = (
                _now() + timedelta(seconds=int(fresh.get("expires_in") or 3600))
            ).isoformat()
            await self.vault.rotate(secret_ref, payload=payload)
        return payload["access_token"]

    async def body_for(self, *, user_id: str, instance_id: str, message_id: str) -> str:
        """
        The text of one message, for a judgement that said it needed it.

        Public because the transient-content layer calls it, and narrow
        because that is the only caller it should ever have: one message, by
        id, returning a bounded string that this service does not keep.
        """
        instance = await self.instances.get(user_id, instance_id)
        if not instance:
            raise LookupError("instance_not_found")
        await self._require_consent(user_id=user_id, instance_id=instance_id)
        token = await self._access_token(user_id=user_id, instance=instance)
        text = await self.provider.body_of(access_token=token, message_id=message_id)
        await self.permissions.audit.log(
            user_id=user_id, event_type="mail.body_read", connector_id=CONNECTOR_ID,
            connector_instance_id=instance_id, capability_id="mail.read",
            success=True, records_returned=1, reason_code="judgement_asked",
            data_classification="sensitive",
        )
        return text
