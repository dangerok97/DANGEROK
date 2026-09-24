"""
V3.10 — moving an appointment is not adding one.

    SPOSTARE NON È CREARE.
    A SECOND EVENT IS NOT A MOVE.

What happened: the person said "visita dentistica spostata all'11 settembre
anziché il 10". ORA created a second event on the 11th, left the 10th exactly
where it was, and said "ho aggiornato la data". Three separate failures in one
sentence — the wrong tool, a calendar with two appointments where there should
be one, and a report of something that did not happen.

The write path had the right machinery all along: `update_calendar_event`
patches ORA's own draft and pushes to the *same* Google event, never touching
`google_event_id`. Nothing forced it to be used, and nothing stopped a
creation from being described as a move.

So: the create path refuses when it is about to add a second commitment with
the same name at a different time, and hands back the ref to update instead;
and both paths say plainly, in the payload, which of the two things happened.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)
ROME = ZoneInfo("Europe/Rome")


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _clean(db, uid):
    for coll in ("calendar_event_drafts", "ingestion_events", "connector_instances",
                 "permission_consents", "permission_audit", "agent_receipts",
                 "action_intents", "authority_consents"):
        await db[coll].delete_many({"user_id": uid})
        await db[coll].delete_many({"owner_id": uid})


def _when(days=1, hour=10):
    return (datetime.now(ROME) + timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


async def _draft(db, uid, *, draft_id, title, when, handle="ev_google_1"):
    """One commitment ORA already manages, already on Google."""
    await db.calendar_event_drafts.insert_one({
        "id": draft_id, "user_id": uid, "title": title,
        "start_datetime": when.isoformat(),
        "end_datetime": (when + timedelta(hours=1)).isoformat(),
        "timezone": "Europe/Rome", "all_day": False,
        "status": "confirmed", "sync_status": "synced",
        "google_event_id": handle, "provider": "google",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Not creating a second one
# ---------------------------------------------------------------------------

def test_creating_the_same_commitment_at_a_new_time_is_refused():
    """
    §2: the refusal that would have prevented the bug outright.

    Same name, different time, within a fortnight: that is somebody moving an
    appointment, and adding a second one leaves them with two forever. The
    tool refuses and hands back the ref to update — it does not choose for
    the model, it removes the option of choosing wrongly by accident.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_dieci",
                         title="Visita dentistica", when=_when(4, 10))

            obs = await calendar_caps.create_calendar_event(
                {"title": "Visita dentistica",
                 "start_datetime": _when(5, 10).isoformat(),
                 "timezone": "Europe/Rome"},
                {"user_id": uid, "db": db},
            )

            assert obs.status == "rejected"
            assert obs.payload["failure_kind"] == "looks_like_a_move"
            assert obs.payload["existing"]["calendar_ref"].endswith("ced_dieci")
            assert "update_calendar_event" in obs.payload["reason"]

            # And nothing was written: no second draft, no second event.
            assert await db.calendar_event_drafts.count_documents(
                {"user_id": uid}
            ) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_two_genuinely_different_commitments_are_not_refused():
    """
    The guard must not stop a person having two appointments.

    Different names are different things, and a system that refused to add
    "Dentista" because "Visita dentistica" exists would be unusable in a
    different, quieter way.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_uno",
                         title="Visita dentistica", when=_when(4, 10))
            twin = await calendar_caps._already_have_one(
                db, uid, title="Riunione di lavoro",
                start=_when(5, 10).isoformat(),
            )
            assert twin is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_appointment_at_the_same_time_is_the_one_already_there():
    """
    Non e' uno spostamento, ed e' quello di prima: sono due cose diverse.

    Qui c'era scritto che dello stesso nome alla stessa ora si occupava
    l'idempotenza del percorso di scrittura, e non era vero fino in fondo.
    Quella riconosce lo stesso atto dall'impronta dei suoi parametri — e fra
    i parametri c'e' la fine. Su una vita vera la stessa frase detta due
    volte a nove minuti di distanza ha prodotto due impegni identici, uno che
    finiva alle 19:15 e uno alle 19:30: nessuno aveva chiesto una durata,
    l'aveva scelta chi rispondeva, diversa le due volte.

    Quindi lo stesso nome che comincia alla stessa ora torna, marcato per
    quello che e': non un impegno da spostare, ma quello che c'e' gia'.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            when = _when(4, 10)
            await _draft(db, uid, draft_id="ced_uno",
                         title="Visita dentistica", when=when)
            twin = await calendar_caps._already_have_one(
                db, uid, title="Visita dentistica", start=when.isoformat(),
            )
            assert twin is not None, (
                "lo stesso impegno chiesto due volte torna a essere due"
            )
            assert twin["id"] == "ced_uno"
            assert twin.get("_starts_at_the_same_time") is True, (
                "il chiamante lo tratterebbe come uno spostamento"
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_cancelled_commitment_does_not_block_a_new_one():
    """Something they cancelled is not something they are moving."""
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_morto",
                         title="Visita dentistica", when=_when(4, 10))
            await db.calendar_event_drafts.update_one(
                {"id": "ced_morto"}, {"$set": {"status": "cancelled"}},
            )
            twin = await calendar_caps._already_have_one(
                db, uid, title="Visita dentistica",
                start=_when(5, 10).isoformat(),
            )
            assert twin is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_an_appointment_far_away_is_not_the_same_appointment():
    """
    §2: the window is what keeps this a guard rather than a ban.

    A dentist visit next week and one in three months are two appointments.
    Refusing the second would be the guard deciding something it cannot know.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_vicino",
                         title="Visita dentistica", when=_when(2, 10))
            twin = await calendar_caps._already_have_one(
                db, uid, title="Visita dentistica",
                start=_when(120, 10).isoformat(),
            )
            assert twin is None
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_the_same_name_written_differently_is_the_same_name():
    """Case, accents and punctuation are spelling, not meaning."""
    from conversation_engine.ai_core.tools.calendar_caps import _same_thing

    assert _same_thing("Visita  Dentìstica!") == _same_thing("visita dentistica")
    assert _same_thing("VISITA DENTISTICA") == _same_thing("Visita dentistica")
    # And two genuinely different names stay different: this is equality of
    # strings, never similarity.
    assert _same_thing("Visita dentistica") != _same_thing("Dentista")


def test_a_person_who_really_wants_two_can_have_two():
    """
    §2: a refusal the model can act on, not a wall.

    The guard is about accidents. Somebody who genuinely wants a second
    appointment with the same name says so, and the second call goes through.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_uno",
                         title="Visita dentistica", when=_when(4, 10))

            obs = await calendar_caps.create_calendar_event(
                {"title": "Visita dentistica",
                 "start_datetime": _when(5, 10).isoformat(),
                 "timezone": "Europe/Rome", "create_anyway": True},
                {"user_id": uid, "db": db},
            )
            # It got past the guard: whatever it says next is about consent
            # or the connector, never about a duplicate.
            assert obs.payload.get("failure_kind") != "looks_like_a_move"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# Saying what happened
# ---------------------------------------------------------------------------

def test_a_creation_can_never_be_described_as_a_move():
    """
    §6: the sentence "ho aggiornato la data" must be impossible after a create.

    This is the failure the person actually saw. The tool now states, in the
    payload the model reads, which of the two things it did — and the two
    words are not interchangeable.
    """
    import ast

    source = (HERE / "conversation_engine/ai_core/tools/calendar_caps.py").read_text(
        encoding="utf-8",
    )
    tree = ast.parse(source)

    def payload_of(name: str) -> str:
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == name
        )
        return ast.unparse(fn)

    created = payload_of("create_calendar_event")
    assert "'operation': 'created'" in created or '"operation": "created"' in created
    assert "'moved_anything': False" in created
    assert "'say_it_as': 'aggiunto'" in created

    updated = payload_of("update_calendar_event")
    # An update is described as a move only after the requested new slot is
    # verified on the same provider event. Merely getting a 200/read-back is
    # not enough.
    assert "moved_anything" in updated and "moved_as_asked" in updated
    assert "'spostato'" in updated
    assert "provider_identity_preserved" in updated
    assert "readback_mismatch" in updated


def test_the_prompt_tells_the_model_which_tool_moves_something():
    """
    §1: the tool choice is where the bug was, so that is where the rule goes.

    Not a slogan: the two sentences name the tools, name the failure mode
    ("the person would end up with two"), and forbid describing a creation as
    an update.
    """
    prompt = (HERE / "conversation_engine/ai_core/prompt.py").read_text(encoding="utf-8")

    assert "Moving something is not adding something" in prompt
    assert "update_calendar_event with its calendar_ref" in prompt
    assert "operation: created" in prompt and "operation: updated" in prompt
    assert "not go and check" in prompt

    registry = (HERE / "conversation_engine/ai_core/tools/registry.py").read_text(
        encoding="utf-8",
    )
    assert "Never use it to move or reschedule" in registry
    assert "create_anyway" in registry


def test_rescheduling_keeps_the_same_event_on_the_provider():
    """
    §2: modify must not become create at the connector level either.

    `reschedule_draft` patches ORA's own draft and pushes to the same Google
    event; `google_event_id` is never in the patch. Checked structurally
    because a refactor that "re-created for reliability" would produce
    exactly the duplicate this whole file is about.
    """
    import ast

    source = (HERE / "documents/intelligence/google_sync.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "reschedule_draft"
    )
    body = ast.unparse(fn)

    assert "_update_existing" in body, "lo spostamento non passa dall'update"
    assert "create_event" not in body, "lo spostamento crea un evento"

    # Il manico non deve essere una CHIAVE della patch. Leggerlo per decidere
    # lo stato di sincronizzazione e' un'altra cosa, e va benissimo.
    for node in ast.walk(fn):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            target = ast.unparse(node)
            assert "google_event_id" not in target, (
                f"il manico dell'evento viene riscritto: {target}"
            )
    # E i campi ammessi in una riprogrammazione non lo comprendono.
    allowed = (HERE / "documents/intelligence/google_sync.py").read_text(
        encoding="utf-8",
    )
    fields = allowed.split("_RESCHEDULE_ALLOWED_FIELDS")[1].split(")")[0]
    assert "google_event_id" not in fields


def test_moving_an_appointment_leaves_exactly_one():
    """
    §4/§7: the end state a person can check — old slot empty, new slot full.

    Driven through ORA's own reschedule path with a fake provider, so what is
    asserted is the state of the world afterwards rather than the shape of a
    call.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from documents.intelligence.google_sync import GoogleCalendarSyncService

            when = _when(4, 10)
            moved_to = _when(5, 10)
            await _draft(db, uid, draft_id="ced_uno", title="Visita dentistica",
                         when=when, handle="ev_google_1")

            pushed = {}

            class Gcal:
                """Il minimo che il percorso di riprogrammazione chiede."""

                async def list_instances(self, user_id):
                    return [{"id": "inst_test", "status": "connected",
                             "metadata": {"default_calendar_id": "primary"},
                             "secret_reference": "ref"}]

                async def _get_access_token(self, *, user_id, instance):
                    return "token"

            service = GoogleCalendarSyncService(db=db, google_calendar_service=Gcal())

            async def push(*, user_id, draft, access, calendar_id, **kw):
                pushed["handle"] = draft.get("google_event_id")
                pushed["start"] = draft.get("start_datetime")
                return {**draft, "sync_status": "synced"}

            service._update_existing = push

            out = await service.reschedule_draft(
                user_id=uid, draft_id="ced_uno",
                fields={"start_datetime": moved_to.isoformat()},
            )

            # One draft, at the new time, on the same provider event.
            drafts = await db.calendar_event_drafts.find(
                {"user_id": uid}, {"_id": 0}
            ).to_list(10)
            assert len(drafts) == 1, "lo spostamento ha lasciato due impegni"
            assert drafts[0]["start_datetime"] == moved_to.isoformat()
            assert drafts[0]["google_event_id"] == "ev_google_1"
            assert pushed["handle"] == "ev_google_1", "ha scritto su un altro evento"
            assert pushed["start"] == moved_to.isoformat()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())



# ---------------------------------------------------------------------------
# The real bug, reproduced
# ---------------------------------------------------------------------------

def test_the_real_bug_a_move_with_a_different_title_is_refused():
    """
    The exact sequence that produced two dentist appointments.

        "Visita dentistica QA ORA", 10 settembre
        person: "sposta la visita dentistica all'11 settembre"
        model:  create_calendar_event(title="Visita dentista", 11 settembre)

    The title guard cannot catch this — the two strings genuinely differ —
    and neither can a prompt, because a prompt is advice. What catches it is
    the person's own sentence, read from where it arrived: they asked to move
    something, so creating is not an available way to answer them.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_dieci",
                         title="Visita dentistica QA ORA", when=_when(4, 10),
                         handle="ev_google_1")

            obs = await calendar_caps.create_calendar_event(
                {"title": "Visita dentista",
                 "start_datetime": _when(5, 10).isoformat(),
                 "timezone": "Europe/Rome",
                 # The model declared nothing at all — exactly as it did.
                 "user_authority": {"requested_by_user": True,
                                    "user_words": "sposta la visita dentistica"}},
                {"user_id": uid, "db": db,
                 "user_message": "sposta la visita dentistica all'11 settembre"},
            )

            assert obs.status == "rejected"
            assert obs.payload["failure_kind"] == "modify_requires_update"
            assert "update_calendar_event" in obs.payload["reason"]
            assert obs.payload["why_we_think_so"] == (
                "la persona ha chiesto di spostare qualcosa"
            )
            # Nothing was written: still one commitment, still on the 10th.
            drafts = await db.calendar_event_drafts.find(
                {"user_id": uid}, {"_id": 0}
            ).to_list(10)
            assert len(drafts) == 1
            assert drafts[0]["start_datetime"] == _when(4, 10).isoformat()
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_declared_modify_is_refused_even_with_a_brand_new_title():
    """
    §: the model's own declaration closes the door before anything is written.

    When it knows it is moving something, saying so is enough — no title
    comparison, no reading of anybody's sentence.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            obs = await calendar_caps.create_calendar_event(
                {"title": "Qualcosa di completamente diverso",
                 "start_datetime": _when(5, 10).isoformat(),
                 "timezone": "Europe/Rome",
                 "operation_intent": "modify"},
                {"user_id": uid, "db": db, "user_message": "facciamolo venerdì"},
            )
            assert obs.status == "rejected"
            assert obs.payload["failure_kind"] == "modify_requires_update"
            assert obs.payload["why_we_think_so"] == "il modello lo ha dichiarato"
            assert await db.calendar_event_drafts.count_documents({"user_id": uid}) == 0
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_create_anyway_cannot_turn_a_move_into_a_creation():
    """
    §: the escape hatch is for duplicates, never for a move.

    Otherwise the guard is decorative: a model that hits the refusal would
    learn to set the flag and carry on, and the person would end up with the
    two appointments the guard exists to prevent.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_dieci",
                         title="Visita dentistica", when=_when(4, 10))

            for arguments in (
                {"operation_intent": "modify", "create_anyway": True},
                {"create_anyway": True},
            ):
                obs = await calendar_caps.create_calendar_event(
                    {"title": "Visita dentista",
                     "start_datetime": _when(5, 10).isoformat(),
                     "timezone": "Europe/Rome", **arguments},
                    {"user_id": uid, "db": db,
                     "user_message": "sposta la visita all'11"},
                )
                assert obs.status == "rejected", arguments
                assert obs.payload["failure_kind"] == "modify_requires_update"
            assert await db.calendar_event_drafts.count_documents({"user_id": uid}) == 1
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_genuinely_new_appointment_is_still_created():
    """
    The guard must not make ORA unable to add anything.

    Somebody asking for a new commitment says so, and nothing about their
    sentence or the model's declaration reads as a move — so the create path
    runs exactly as before.
    """
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            obs = await calendar_caps.create_calendar_event(
                {"title": "Cena con Marco",
                 "start_datetime": _when(3, 20).isoformat(),
                 "timezone": "Europe/Rome", "operation_intent": "new"},
                {"user_id": uid, "db": db,
                 "user_message": "segnami una cena con Marco venerdì alle 20"},
            )
            # It got past both guards; what it says next is about consent or
            # the connector, never about a move or a duplicate.
            assert obs.payload.get("failure_kind") not in (
                "modify_requires_update", "looks_like_a_move",
            )
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_a_move_is_only_confirmed_when_the_old_slot_is_empty():
    """
    §6: "l'ho spostato" is a claim about two slots, and both are checked.

    Same provider event, now at the requested time — so the time it used to
    be at no longer holds it. If the read-back disagrees, the payload says
    the slots were not confirmed and the model has nothing to claim.
    """
    from conversation_engine.ai_core.tools.calendar_caps import _is_at

    wanted = _when(5, 16)
    # What Google hands back after a successful move, in its own offset.
    assert _is_at(
        {"start": {"dateTime": wanted.astimezone(timezone.utc).isoformat()}},
        wanted.isoformat(),
    ), "lo stesso istante scritto in UTC non viene riconosciuto"
    # Still at the old time: not moved.
    assert not _is_at(
        {"start": {"dateTime": _when(4, 10).isoformat()}}, wanted.isoformat(),
    )
    # Nothing came back: nothing is confirmed.
    assert not _is_at({}, wanted.isoformat())
    assert not _is_at({"start": {"dateTime": wanted.isoformat()}}, None)



def test_direct_move_cannot_use_a_ref_for_a_different_named_event():
    from conversation_engine.ai_core.tools.calendar_caps import (
        _direct_move_targets_selected_title,
    )
    spoken = "Sposta TEST ORA — continuazione alle 20:00"
    assert _direct_move_targets_selected_title("TEST ORA — continuazione", spoken)
    assert not _direct_move_targets_selected_title("TEST ORA — riunione di lavoro", spoken)


def test_update_timezone_cannot_silently_turn_20_into_22():
    from conversation_engine.ai_core.tools.calendar_caps import (
        _canonical_update_datetime,
    )
    assert _canonical_update_datetime(
        "2026-09-30T20:00:00Z", "Europe/Rome"
    ) is None
    assert _canonical_update_datetime(
        "2026-09-30T20:00:00", "Europe/Rome"
    ).endswith("+02:00")
    assert _canonical_update_datetime(
        "2026-09-30T20:00:00+02:00", "Europe/Rome"
    ).endswith("+02:00")


def test_update_only_claims_success_when_readback_matches_requested_effect():
    source = (HERE / "conversation_engine/ai_core/tools/calendar_caps.py").read_text(
        encoding="utf-8",
    )
    fn = source.split("async def update_calendar_event", 1)[1].split(
        "async def cancel_calendar_event", 1
    )[0]
    assert 'status="ok" if moved_as_asked else "partial"' in fn
    assert 'observed=moved_as_asked' in fn
    assert '"readback_mismatch"' in fn



def test_exact_title_resolution_finds_one_google_imported_event():
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps
            when = _when(6, 19)
            await db.ingestion_events.insert_one({
                "id": "ing_exact_1",
                "user_id": uid,
                "connector_id": "calendar_google",
                "source_status": "active",
                "external_id": "g_exact_1",
                "normalized_payload": {
                    "title": {"value": "TEST ORA — continuazione"},
                    "starts_at": {"value": when.isoformat()},
                    "ends_at": {"value": (when + timedelta(minutes=45)).isoformat()},
                    "timezone": {"value": "Europe/Rome"},
                    "status": {"value": "confirmed"},
                },
            })

            got = await calendar_caps._exact_named_calendar_ref(
                db, uid, "TEST ORA — continuazione",
                now=datetime.now(ROME),
            )
            assert got["status"] == "ok", got
            assert got["match"]["calendar_ref"] == "calendar:google:ing_exact_1"
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())


def test_exact_title_resolution_never_guesses_between_duplicates():
    async def body():
        client, db = await _db()
        uid = f"mv_{uuid.uuid4().hex[:8]}"
        try:
            from conversation_engine.ai_core.tools import calendar_caps

            await _draft(db, uid, draft_id="ced_a", title="Prova", when=_when(3, 10))
            await _draft(db, uid, draft_id="ced_b", title="Prova", when=_when(4, 10),
                         handle="ev_google_2")
            got = await calendar_caps._exact_named_calendar_ref(
                db, uid, "Prova", now=datetime.now(ROME),
            )
            assert got["status"] == "ambiguous"
            assert len(got["matches"]) == 2
        finally:
            await _clean(db, uid)
            client.close()

    _run(body())
