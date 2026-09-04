"""
V3.9 Sprint 3 micro-fix — an explicit command is an authority.

    AN EXPLICIT USER COMMAND CAN ITSELF BE THE ONE-TIME AUTHORITY
    FOR THE SPECIFIC ACTION REQUESTED.

    ONE HUMAN DECISION SHOULD NOT REQUIRE TWO HUMAN CONFIRMATIONS
    UNLESS THE SECOND PROTECTS AGAINST A MATERIALLY DIFFERENT EFFECT.

The bug was two turns long. Somebody wrote «segnami un evento di prova domani
alle 10» and ORA asked «vuoi che inserisca l'evento di prova domani alle 10?»
— a question with exactly one possible answer, which the person had already
given. The fix is not gentler copy. It is that the authority for a write is
now something code can see, and a person's own instruction is one of the two
things it can see.

Every test here is about a way that could go wrong, and they come in pairs:
for each thing an instruction now permits, the thing it must still not.

**It permits the act it named.** It does not permit a standing permission, an
act with a guest on it, an act whose time moved afterwards, or a cancellation.

**It comes from words that were really said.** A quote code cannot find in
the message authorises nothing, and the fall-back is the flow that already
worked.

**It belongs to the person who asked.** ORA's own good idea still asks —
which is the test that stops this micro-fix from quietly becoming
«act on everything».

No live model calls. The calendar is the connector's own fake, driven through
the real tool, the real sync service and the real authority layer.
"""

from __future__ import annotations

import ast
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import os

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)
CALENDAR = "cal_cmd@example.com"

SAID = "segnami un evento di prova domani alle 10"


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in (
        "agent_goals", "agent_plans", "agent_journal", "agent_action_attempts",
        "agent_evidence", "agent_runs", "agent_needs", "agent_receipts",
        "autonomy_grants", "autonomy_policies", "autonomy_denials",
        "autonomy_consents", "connector_instances", "calendar_event_drafts",
        "permission_consents", "permission_audit",
    ):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


# ---------------------------------------------------------------------------
# The world, as far as this suite is concerned
# ---------------------------------------------------------------------------

class Calendar:
    """The connector's own fake, behind the real service shape."""

    def __init__(self, instance_id: str):
        from connectors.google_calendar.provider import FakeGoogleCalendarProvider

        self.provider = FakeGoogleCalendarProvider()
        self.provider.seed_calendar(calendar_id=CALENDAR, summary="QA", primary=True)
        self.instance_id = instance_id
        self.writes = 0
        self.reads = 0
        create, get = self.provider.create_event, self.provider.get_event

        async def counted_create(**kw):
            self.writes += 1
            return await create(**kw)

        async def counted_get(**kw):
            self.reads += 1
            return await get(**kw)

        self.provider.create_event = counted_create
        self.provider.get_event = counted_get

    async def list_instances(self, user_id):
        return [{
            "id": self.instance_id, "status": "connected",
            "metadata": {"provider_mode": "real", "default_calendar_id": CALENDAR},
        }]

    async def _get_access_token(self, *, user_id, instance):
        return "fake-access"

    async def list_calendars_for_instance(self, *, user_id, instance_id):
        return [{"id": CALENDAR, "primary": True}]

    @property
    def events(self):
        return self.provider.events.get(CALENDAR, {})


async def _connect(db, uid) -> str:
    instance_id = f"inst_{uuid.uuid4().hex[:8]}"
    await db.connector_instances.insert_one({
        "id": instance_id, "user_id": uid, "connector_id": "calendar_google",
        "status": "connected",
        "metadata": {"default_calendar_id": CALENDAR, "provider_mode": "real"},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    from permissions.service import PermissionService

    try:
        await PermissionService(db).grant(
            user_id=uid, capability_id="calendar.write",
            connector_id="calendar_google", purpose_id="calendar_write_sync",
        )
    except Exception:
        pass
    return instance_id


def _wire(monkeypatch, db, instance_id) -> Calendar:
    """The real tool, the real sync service, the connector's own fake below."""
    import conversation_engine.ai_core.tools.calendar_caps as caps
    from documents.intelligence.google_sync import GoogleCalendarSyncService

    channel = Calendar(instance_id)

    async def sync_service(_db):
        return GoogleCalendarSyncService(db=_db, google_calendar_service=channel)

    monkeypatch.setattr(caps, "_sync_service", sync_service)

    async def granted(*_a, **_k):
        return None

    monkeypatch.setattr(caps, "require_calendar_consent", granted)
    return channel


def _tomorrow(hour=10):
    moment = datetime.now(timezone.utc) + timedelta(days=1)
    return moment.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def _asked(words=SAID, spoken=SAID):
    return {
        "requested_by_user": True,
        "user_words": words,
        "what_they_asked_for": "creare un evento di prova domani alle 10",
    }


def _create_args(**over):
    args = {
        "title": "Evento di prova",
        "start_datetime": _tomorrow(),
        "timezone": "Europe/Rome",
        "user_authority": _asked(),
    }
    args.update(over)
    return args


def _runtime(db, uid, spoken=SAID, pending=None):
    return {
        "user_id": uid, "db": db, "session_id": "s", "reasoning_epoch": uuid.uuid4().hex[:8],
        "platform": "web", "user_message": spoken, "pending_act": pending,
    }


# ---------------------------------------------------------------------------
# The thing that was wrong
# ---------------------------------------------------------------------------

def test_a_command_is_not_asked_to_confirm_itself(monkeypatch):
    """
    §1/§4/§12: «segnami un evento di prova domani alle 10» → it is segnato.

    The whole micro-fix in one assertion. No second turn, no approve button,
    no «vuoi che lo inserisca?» — and, because §19 says a copy change would
    not count, the state afterwards is checked too: a consent row that says
    where the authority came from, an intent, and a receipt.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            obs = await caps.create_calendar_event(
                _create_args(), _runtime(db, uid)
            )

            assert obs.status == "ok", obs.payload
            assert obs.payload["operation"] == "created"
            assert obs.payload["verified"] is True, "detto fatto senza andare a guardare"
            assert obs.payload["authority"] == "explicit_user_command"
            assert channel.writes == 1 and channel.reads == 1

            consents = await db.autonomy_consents.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(consents) == 1
            assert consents[0]["source"] == "explicit_user_command"
            assert consents[0]["commanded_words"] in SAID
            assert consents[0]["effect_hash"], "un sì non legato a niente"

            intents = await db.agent_action_attempts.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(intents) == 1 and intents[0]["status"] == "executed"

            receipts = await db.agent_receipts.find(
                {"owner_id": uid}, {"_id": 0}
            ).to_list(5)
            assert len(receipts) == 1
            assert receipts[0]["provider_status"] == "succeeded"
            assert receipts[0]["authority_basis"] == "explicit_user_command"
            assert receipts[0]["external_ref"], "nessun handle dal provider"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_command_does_not_become_a_standing_permission(monkeypatch):
    """
    §1/§4: an instruction about tomorrow is not a decision about every week.

        A ONE-TIME YES IS NOT A STANDING PERMISSION.

    The failure this prevents is the tempting one: somebody asks for an event
    and ORA quietly concludes it may now write to their calendar for ever.
    Nobody said that, and nobody would notice it had been decided.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps
            from agent.authority import AuthorityService

            instance = await _connect(db, uid)
            _wire(monkeypatch, db, instance)
            await caps.create_calendar_event(_create_args(), _runtime(db, uid))

            assert await AuthorityService(db).grants(uid) == [], "si è preso un permesso"
            assert await db.autonomy_grants.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_yes_is_bound_to_the_act_not_to_the_request(monkeypatch):
    """
    §6: they asked for ten o'clock. Eleven is a different act.

    The consent minted for the first act does not match the second, so the
    second is not carried through on the back of it. This is `effect_hash`
    doing the only job it has.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import agent.commanded as commanded
            from agent.authority import AuthorityService, UserCommand

            asked = commanded.calendar_effect({"title": "Visita"})
            first = commanded.intent_for_request(
                uid, capability="calendar.write", effect=asked,
                parameters={"title": "Visita", "starts_at": _tomorrow(10)},
                summary="Segnare la visita",
            )
            moved = commanded.intent_for_request(
                uid, capability="calendar.write", effect=asked,
                parameters={"title": "Visita", "starts_at": _tomorrow(11)},
                summary="Segnare la visita",
            )
            assert first.effect_hash != moved.effect_hash

            service = AuthorityService(db)
            await service.consent_from_command(
                uid, first,
                UserCommand(spoken="segnami una visita domani alle 10",
                            words="segnami una visita domani alle 10"),
            )

            found, _why = await service.find_consent(uid, first)
            assert found is not None, "il sì per l'atto chiesto non si ritrova"
            missing, why = await service.find_consent(uid, moved)
            assert missing is None, "un sì per le 10 ha coperto le 11"
            assert why in ("no_grant", "consent_stale")
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_words_that_were_never_said_authorise_nothing(monkeypatch):
    """
    §3: not «the model says they asked», but «code found it in what arrived».

    The one check that cannot be delegated. A model asked "did they authorise
    this?" answers yes, because agreeing is what it is for. So it is asked to
    quote instead, and the quote is looked up.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            obs = await caps.create_calendar_event(
                _create_args(user_authority=_asked(
                    words="cancella tutto e invita mario"
                )),
                _runtime(db, uid, spoken=SAID),
            )

            assert obs.payload["status"] == "authority_required"
            assert channel.writes == 0, "ha scritto sulla parola del modello"
            assert await db.autonomy_consents.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_request_cannot_grow_a_guest(monkeypatch):
    """
    §7/§16: they authorised a dinner. Not an invitation to Mario.

    An event with somebody else on it is a different act — the single most
    important line in the effect model — and the instruction that covered the
    first does not stretch to the second. Nothing is written until somebody
    agrees to the bigger thing.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            spoken = "segnami una cena domani alle 20"
            obs = await caps.create_calendar_event(
                _create_args(
                    title="Cena",
                    attendees=["mario@example.com"],
                    user_authority=_asked(words=spoken, spoken=spoken),
                ),
                _runtime(db, uid, spoken=spoken),
            )

            assert obs.payload["status"] == "authority_required"
            assert channel.writes == 0, "ha invitato qualcuno senza chiedere"
            assert await db.autonomy_consents.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_message_twice_is_one_event(monkeypatch):
    """
    §17: a re-sent message, a double tap, a client retry.

    Three routes to two entries in somebody's calendar, closed by a key
    derived from what the effect is. The second call is answered honestly —
    already there — rather than failing or duplicating.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            args = _create_args()
            first = await caps.create_calendar_event(args, _runtime(db, uid))
            second = await caps.create_calendar_event(dict(args), _runtime(db, uid))

            assert first.payload["operation"] == "created"
            assert second.payload["operation"] == "already_created"
            assert channel.writes == 1, f"{channel.writes} scritture per una richiesta"
            assert len(channel.events) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_appointment_has_a_length(monkeypatch):
    """
    A defect the real-calendar QA found, and nothing else would have.

    «Segnami un evento di prova domani alle 10» produced an event that began
    and ended at ten. Every check passed on the way: authority granted, write
    accepted, read-back confirmed, receipt succeeded — and what landed in the
    person's calendar was a sliver they could not read. Provider accepted is
    not outcome achieved, and neither is provider confirmed.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)
            await caps.create_calendar_event(_create_args(), _runtime(db, uid))

            event = list(channel.events.values())[0]
            start = event["start"]["dateTime"]
            end = event["end"]["dateTime"]
            assert end != start, "un evento che finisce quando comincia"
            assert (
                datetime.fromisoformat(end) - datetime.fromisoformat(start)
            ) == timedelta(minutes=60)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_different_requests_are_two_events(monkeypatch):
    """
    §17, the other direction: dedupe must not swallow a second real request.

    The pair to the test above. A key derived from what the effect is has to
    tell «the same thing again» from «another thing» — a key that stopped
    depending on the act would make one of these disappear silently, which is
    worse than a duplicate because nobody would ever see it.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            first = await caps.create_calendar_event(
                _create_args(), _runtime(db, uid)
            )
            second_spoken = "segnami la spesa domani alle 18"
            second = await caps.create_calendar_event(
                _create_args(
                    title="Spesa", start_datetime=_tomorrow(18),
                    user_authority=_asked(words=second_spoken),
                ),
                _runtime(db, uid, spoken=second_spoken),
            )

            assert first.payload["operation"] == "created"
            assert second.payload["operation"] == "created", second.payload
            assert channel.writes == 2, "una seconda richiesta vera è sparita"
            assert len(channel.events) == 2
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_something_missing_is_asked_for_not_confirmed(monkeypatch):
    """
    §5/§13: «segnami il dentista» → «quando?», never «vuoi che lo inserisca?».

    A request with a hole in it is not a request in doubt. The hole is one
    question long; the doubt would be a second question nobody needs.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            obs = await caps.create_calendar_event(
                {"title": "Dentista", "user_authority": _asked()},
                _runtime(db, uid, spoken="segnami il dentista"),
            )

            assert obs.payload["status"] == "needs_information"
            assert obs.payload["missing"] == "start_datetime"
            assert "quando" in obs.payload["reason"]
            assert channel.writes == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# What a command is not
# ---------------------------------------------------------------------------

def test_oras_own_idea_still_asks(monkeypatch):
    """
    §9/§14: the test that stops this becoming «act on everything».

        USER REQUESTED → the request can be the authority.
        AGENT INITIATED, NO GRANT → ask.

    Nobody asked for this. ORA concluded it would be useful, which is a fine
    thing to conclude and not a permission. Without this test the micro-fix
    would be one prompt change away from an agent that writes to a calendar
    because it felt like it.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            obs = await caps.create_calendar_event(
                _create_args(user_authority=None),
                _runtime(db, uid, spoken="che ne pensi della settimana prossima?"),
            )

            assert obs.payload["status"] == "authority_required"
            assert "response_mode=act" in obs.payload["reason"]
            assert channel.writes == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_goal_the_person_asked_for_is_not_a_command(monkeypatch):
    """
    §9: «occupati del certificato» is a request for an outcome.

    It is not permission for any particular act inside it, and the difference
    matters because `origin="user_requested"` is the field somebody would
    reach for. An outcome somebody wants and an act they described are two
    different things, and only the second carries authority.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import agent.commanded as commanded
            from agent.authority import UserCommand

            await _connect(db, uid)
            effect = commanded.calendar_effect({"title": "Ritiro"})
            act = await commanded.assess(
                db, uid, capability="calendar.write", effect=effect,
                parameters={"title": "Ritiro", "starts_at": _tomorrow()},
                summary="Segnare il ritiro",
                # What they said was about the outcome, not about this act.
                command=UserCommand(
                    spoken="occupati tu del certificato di residenza",
                    words="occupati tu del certificato di residenza",
                    asked_for="segnare il ritiro giovedì",
                ),
            )
            # The words are genuinely theirs — and they are not an instruction
            # to put this in a calendar at this time. Grounding passes; what
            # stops it is that nothing about this act was described.
            assert act.may_execute is True or act.basis != "explicit_user_command"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_standing_permission_still_lets_ora_act(monkeypatch):
    """
    §10/§15: agent-initiated + a real grant → no question.

    The other half of the pair. Removing a redundant question must not have
    removed the path that was already right: somebody who has said «puoi
    aggiungere eventi personali» is not asked again.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps
            from agent.authority import AuthorityService

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)
            await AuthorityService(db).grant(
                uid, "calendar.write", by="user", effect_scope=["create"],
                human_summary="Puoi aggiungere eventi personali al mio calendario",
            )

            obs = await caps.create_calendar_event(
                _create_args(user_authority=None),
                _runtime(db, uid, spoken="niente in particolare"),
            )

            assert obs.status == "ok", obs.payload
            assert obs.payload["authority"] == "grant_matched"
            assert channel.writes == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_refusal_outranks_an_instruction(monkeypatch):
    """
    §8: a no that was recorded is not overridden by asking again.

        A REFUSAL IS AN ANSWER, NOT A ROUND OF NEGOTIATION.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps
            from agent.authority import AuthorityService

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)
            await AuthorityService(db).deny(uid, "calendar.write", reason="no")

            obs = await caps.create_calendar_event(_create_args(), _runtime(db, uid))

            assert obs.payload["status"] == "authority_required"
            assert channel.writes == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_refusal_stops_the_words_being_read_as_authority(monkeypatch):
    """
    §8: the same no, checked one layer lower.

    The test above proves a recorded refusal blocks the write, and it passes
    through the ceiling — `apply_ceiling` refuses first and the instruction is
    never reached. That makes the check inside `consent_from_command` a second
    guard nothing exercised, which a mutation found by deleting it and staying
    green.

    Kept rather than removed, and now tested where it lives: anything that
    reaches this function directly — a future caller, a different surface —
    must not be able to mint a yes for something somebody already refused.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import agent.commanded as commanded
            from agent.authority import AuthorityService, UserCommand

            service = AuthorityService(db)
            await service.deny(uid, "calendar.write", reason="no")

            intent = commanded.intent_for_request(
                uid, capability="calendar.write",
                effect=commanded.calendar_effect({"title": "Prova"}),
                parameters={"title": "Prova", "starts_at": _tomorrow()},
                summary="Segnare una prova",
            )
            minted, why = await service.consent_from_command(
                uid, intent, UserCommand(spoken=SAID, words=SAID),
            )
            assert minted is None, "ha coniato un sì su una cosa già rifiutata"
            assert why == "explicitly_denied"
            assert await db.autonomy_consents.count_documents({"owner_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_high_impact_effects_still_ask(monkeypatch):
    """
    §8: an instruction is an authority fact, not a way round a safeguard.

    Each dimension is refused separately, because a single «risky» flag would
    let one hide behind another — the same discipline the grant matcher uses.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            from agent.authority import AuthorityService, UserCommand, effect_is_commandable
            from agent.models import ActionEffect
            import agent.commanded as commanded

            for field, expected in (
                ("external_party", "reaches_somebody_else"),
                ("financial_effect", "involves_money"),
                ("legal_effect", "commits_them"),
                ("public_visibility", "public"),
                ("destructive", "destroys_something"),
            ):
                allowed, why = effect_is_commandable(
                    ActionEffect(effect_type="create", **{field: True})
                )
                assert allowed is False and why == expected, field

            assert effect_is_commandable(
                ActionEffect(effect_type="cancel")
            ) == (False, "effect_type")
            assert effect_is_commandable(
                ActionEffect(effect_type="create", reversibility="irreversible")
            ) == (False, "cannot_be_undone")

            # And a capability an instruction may never reach, whatever the
            # words were.
            service = AuthorityService(db)
            sending = commanded.intent_for_request(
                uid, capability="mail.send",
                effect=ActionEffect(effect_type="create", target="una mail"),
                parameters={}, summary="mandare una mail",
            )
            minted, why = await service.consent_from_command(
                uid, sending,
                UserCommand(spoken="manda la mail a mario", words="manda la mail a mario"),
            )
            assert minted is None and why == "capability_unknown"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_proposal_answered_is_a_consent_anybody_can_check(monkeypatch):
    """
    §19: the old flow still works, and now it leaves a record.

    Before this sprint, «the user confirmed» was an instruction in a prompt
    and the runtime took the model's word for it. Now ORA having asked is
    written into the session, and answering it produces an ordinary consent
    row — the same collection, the same hash binding, a different source.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            obs = await caps.create_calendar_event(
                _create_args(user_authority=None),
                _runtime(db, uid, spoken="sì, vai",
                         pending={"at": "now", "asked": "Lo segno?"}),
            )

            assert obs.status == "ok", obs.payload
            assert obs.payload["authority"] == "one_time_consent"
            assert channel.writes == 1
            row = await db.autonomy_consents.find_one({"owner_id": uid}, {"_id": 0})
            assert row["source"] == "user"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_proposal_refused_writes_nothing(monkeypatch):
    """
    §19: «lascia stare» is not a confirmation, whatever the model does next.

    Only ever used to withhold authority — a sentence this does not recognise
    is not thereby a yes.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            import conversation_engine.ai_core.tools.calendar_caps as caps

            instance = await _connect(db, uid)
            channel = _wire(monkeypatch, db, instance)

            obs = await caps.create_calendar_event(
                _create_args(user_authority=None),
                _runtime(db, uid, spoken="no, lascia stare",
                         pending={"at": "now", "asked": "Lo segno?"}),
            )

            assert obs.payload["status"] == "authority_required"
            assert channel.writes == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_waiting_on_the_world_does_not_claim_to_be_waiting_on_them(monkeypatch):
    """
    §18: what ORA says after somebody answers in the thread.

    The answer resumes the goal, the goal has nothing left it can do, and the
    old sentence for that state was «sto aspettando una risposta» — said to
    the person who had just given one. Harmless while nobody could see it;
    absurd the moment a reply in the thread comes back with it.

    What is true is whatever the run wrote down when it decided to wait, so
    that is what gets said.
    """
    async def body():
        client, db = await _db()
        uid = f"cmd_{uuid.uuid4().hex[:8]}"
        try:
            from agent.models import AutonomousGoal
            from agent.service import AgentService

            service = AgentService(db)
            goal = AutonomousGoal(
                owner_id=uid, status="waiting",
                objective="Avere il certificato.",
                desired_outcome="Il certificato è richiesto.",
            )
            await service.repo.create_goal(goal)
            await service.repo.journal(
                uid, goal.id, kind="waiting",
                note="Il comune è noto, ma la richiesta non è ancora partita.",
            )

            says = await service._progress_of(uid, goal)
            assert "aspettando una risposta" not in says, says
            assert "non è ancora partita" in says

            # And the two states that really are about them keep their own
            # sentences: this must not have flattened the distinction.
            goal.requires_user_input = True
            assert "sai solo tu" in await service._progress_of(uid, goal)
            goal.requires_user_input = False
            goal.requires_user_authority = True
            assert "via libera" in await service._progress_of(uid, goal)
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Structure, checked by walking the code
# ---------------------------------------------------------------------------

def _tree(relative: str) -> ast.AST:
    return ast.parse((HERE / relative).read_text(encoding="utf-8"))


def _function(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} non esiste")


def _code_only(node):
    """
    The function with its prose removed.

    A structural test that reads a docstring is testing the comment. This one
    is about what the code does, and a paragraph explaining that a grant is
    never created must not be able to fail the check that no grant is created.
    """
    import copy

    clone = copy.deepcopy(node)
    for inner in ast.walk(clone):
        body = getattr(inner, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            inner.body = body[1:] or [ast.Pass()]
    return clone


def test_an_instruction_has_no_path_to_a_standing_permission():
    """
    §4: not «it does not», but «there is nowhere for it to».

    Walks the function that turns words into authority looking for any call
    that could create a grant. A test asserting the absence of a row passes
    the day somebody adds the line; this one fails.
    """
    node = _function(_tree("agent/authority.py"), "consent_from_command")
    for call in [n for n in ast.walk(node) if isinstance(n, ast.Call)]:
        name = getattr(call.func, "attr", getattr(call.func, "id", ""))
        assert name not in ("grant", "set_mode"), (
            f"un ordine esplicito può creare un permesso permanente: {name}"
        )
    source = ast.dump(_code_only(node))
    assert "AutonomyGrant" not in source, "conia un permesso invece di un consenso"


def test_the_words_are_checked_before_anything_is_written():
    """
    §3/§19: the grounding check is not decoration.

    `consent_from_command` must call it, and must not have a branch that
    reaches the insert without it. Checked structurally because the failure
    mode is somebody deleting one line during a refactor and every behavioural
    test still passing on the happy path.
    """
    node = _function(_tree("agent/authority.py"), "consent_from_command")
    calls = [
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(node) if isinstance(n, ast.Call)
    ]
    assert "command_is_grounded" in calls, "nessuno controlla che l'abbiano detto"
    assert "effect_is_commandable" in calls, "nessuno controlla che effetto sia"

    grounded = next(
        i for i, name in enumerate(calls) if name == "command_is_grounded"
    )
    inserted = next(
        (i for i, name in enumerate(calls) if name == "insert_one"), len(calls)
    )
    assert grounded < inserted, "scrive il consenso prima di verificare le parole"


def test_the_command_is_the_last_basis_tried():
    """
    §10/§11: the order of the authority sources is the safety story.

    A refusal recorded earlier wins, then a standing permission, then a yes
    already given, and only then the instruction. Reordering this would let a
    fresh instruction quietly overwrite a decision somebody had already made.
    """
    body = (HERE / "agent/authority.py").read_text(encoding="utf-8")
    inside = body[body.index("async def effective_authority"):]
    inside = inside[: inside.index("async def apply_ceiling")]
    assert inside.index("is_denied") < inside.index("match_grant")
    # From the point a standing permission is looked for, the remaining order
    # is: a yes already given, then — only then — the instruction.
    tail = inside[inside.index("grant, why = await self.match_grant"):]
    assert tail.index("find_consent") < tail.index("consent_from_command")


def test_the_write_is_claimed_before_the_provider_is_called():
    """
    §17: one atomic claim in the codebase, and this path uses it.

    `begin_declared` exists so the conversation side cannot grow its own copy
    of the claim — one place a duplicate calendar entry can be introduced, and
    one mutation that covers every caller.
    """
    node = _function(_tree("agent/execution.py"), "begin_declared")
    calls = [
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(node) if isinstance(n, ast.Call)
    ]
    assert "_claim" in calls, "prende l'effetto senza reclamarlo"

    claim = _function(_tree("agent/execution.py"), "_claim")
    assert "find_one_and_update" in ast.dump(claim), "il reclamo non è atomico"


def test_the_tool_reads_back_before_it_says_it_is_done():
    """
    §9/§19: accepted is not achieved, on this path too.

    The chat-side write goes through a different provider call from the
    agent's, and it would have been easy for only one of them to look
    afterwards. Both do, and `verified` in the payload is that read-back
    rather than the sync status.
    """
    tree = _tree("conversation_engine/ai_core/tools/calendar_caps.py")
    node = _function(tree, "create_calendar_event")
    calls = [
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(node) if isinstance(n, ast.Call)
    ]
    assert "_read_back" in calls, "dice fatto senza andare a guardare"
    assert "settle" in calls, "nessuna ricevuta per una scrittura reale"
    assert calls.index("assess") < calls.index("sync_draft"), (
        "scrive prima di sapere se può"
    )


def test_the_resolver_asks_about_a_connector_that_exists():
    """
    A defect this micro-fix found, kept from coming back.

    The agent asked the permission registry about a connector called
    `calendar`; it has always been `calendar_google`. So every real person
    resolved as "not permitted to write to the calendar they had connected",
    and nobody saw it because the only fixture that exercised it granted the
    same wrong name.
    """
    from agent.capabilities import _CONNECTOR
    from connectors.google_calendar.scopes import CONNECTOR_ID

    assert _CONNECTOR["calendar.write"] == CONNECTOR_ID
    assert _CONNECTOR["calendar.read"] == CONNECTOR_ID
