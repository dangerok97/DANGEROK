"""
V3.6 — where a person's life happens, and who is allowed to say what it means.

The thing being tested is a boundary. A device can notice that somebody keeps
returning to the same coordinates; that is arithmetic and the code does it.
What that place *is* — a gym, a hospital, a mother's flat — is not in the
coordinates, and every path that could turn a count into a claim is closed
here on purpose.

    GPS OBSERVES. AI UNDERSTANDS. USER CONFIRMS.

So the model is stubbed where it is asked to judge, and what is asserted is
that the code neither judged for it nor let it skip the person.
"""

from __future__ import annotations

import ast
import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

os.environ.setdefault("CALENDAR_PROVIDER_MODE", "fake")
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBNAME = os.environ.get("DB_NAME", "ora_test")
HERE = Path(_BACKEND)

# Padova, roughly. Two points a street apart and one across the city.
PADOVA = (45.4064, 11.8768)
NEXT_DOOR = (45.4065, 11.8769)
ACROSS_TOWN = (45.4180, 11.8900)


def _run(coro):
    return _loop_harness.run(coro)


async def _db():
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO)
    return client, client[DBNAME]


async def _service(db):
    from places.service import PlacesService

    return PlacesService(db)


class FakeModel:
    """The model, saying what a test needs it to say."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    async def __call__(self, system, user):
        self.calls += 1
        return self.answers.pop(0) if self.answers else None


def _install(monkeypatch, model):
    import places.reasoning as reasoning

    monkeypatch.setattr(reasoning, "_ask_model", model)


# ---------------------------------------------------------------------------
# A place is something a person said
# ---------------------------------------------------------------------------

def test_a_place_belongs_to_one_person_and_survives_the_session():
    async def body():
        client, db = await _db()
        mine = f"u_pl_{uuid.uuid4().hex[:8]}"
        theirs = f"u_pl_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            saved = await service.save_place(
                mine,
                label="Casa",
                role="home",
                coordinates=Coordinates(latitude=PADOVA[0], longitude=PADOVA[1]),
                locality="Padova",
            )

            # A fresh service, as a later session would build.
            again = await _service(db)
            assert [p.id for p in await again.list_places(mine)] == [saved.id]
            assert await again.get_place(mine, saved.id) is not None

            # And nobody else's.
            assert await again.list_places(theirs) == []
            assert await again.get_place(theirs, saved.id) is None
        finally:
            for uid in (mine, theirs):
                await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_home_and_work_are_singular_because_a_person_has_one_of_each():
    """
    Moving house does not give somebody two homes. The previous one stops
    being the answer rather than competing with the new one — and it is not
    deleted, because it is still a real place they knew.
    """
    async def body():
        client, db = await _db()
        uid = f"u_pl_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            old = await service.save_place(uid, label="Casa vecchia", role="home")
            new = await service.save_place(uid, label="Casa nuova", role="home")

            homes = [
                p
                for p in await service.list_places(uid)
                if p.role == "home" and p.role_confirmed_by_user
            ]
            assert [p.id for p in homes] == [new.id]
            still_there = await service.get_place(uid, old.id)
            assert still_there is not None and still_there.label == "Casa vecchia"
        finally:
            await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_role_is_never_written_unless_somebody_said_so():
    async def body():
        client, db = await _db()
        uid = f"u_pl_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            place = await service.save_place(uid, label="Palestra", role="other")
            assert place.role == "other"
            assert place.role_confirmed_by_user is False, (
                "un luogo senza ruolo dichiarato risulta confermato"
            )
        finally:
            await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# An observation is not a fact
# ---------------------------------------------------------------------------

def test_returning_to_a_spot_makes_a_candidate_and_nothing_more():
    """
    The heart of it. Eleven sightings is eleven sightings: no place appears, no
    name is invented, and the count sits there waiting for a person.
    """
    async def body():
        client, db = await _db()
        uid = f"u_ob_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for _ in range(11):
                await service.record_observation(
                    uid, latitude=PADOVA[0], longitude=PADOVA[1], accuracy_meters=20
                )

            assert await service.list_places(uid) == [], "un'osservazione è diventata un luogo"
            candidates = await service.repo.list_candidates(uid)
            assert len(candidates) == 1
            assert candidates[0].observation_count == 11
            assert candidates[0].outcome == "pending"
            assert candidates[0].became_place_id is None
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_the_same_street_is_one_candidate_and_the_next_town_is_another():
    async def body():
        client, db = await _db()
        uid = f"u_ob_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            await service.record_observation(uid, latitude=NEXT_DOOR[0], longitude=NEXT_DOOR[1])
            await service.record_observation(uid, latitude=ACROSS_TOWN[0], longitude=ACROSS_TOWN[1])

            candidates = await service.repo.list_candidates(uid)
            assert len(candidates) == 2, [c.observation_count for c in candidates]
            assert sorted(c.observation_count for c in candidates) == [1, 2]
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_sighting_at_a_place_they_already_named_is_not_a_new_candidate():
    async def body():
        client, db = await _db()
        uid = f"u_ob_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            home = await service.save_place(
                uid,
                label="Casa",
                role="home",
                coordinates=Coordinates(latitude=PADOVA[0], longitude=PADOVA[1]),
            )
            result = await service.record_observation(
                uid, latitude=NEXT_DOOR[0], longitude=NEXT_DOOR[1]
            )
            assert result["at_known_place"] == home.id
            assert await service.repo.list_candidates(uid) == []
        finally:
            await db.life_places.delete_many({"user_id": uid})
            await db.presence_observations.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_fix_too_vague_to_place_is_not_recorded_as_evidence():
    async def body():
        client, db = await _db()
        uid = f"u_ob_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            result = await service.record_observation(
                uid, latitude=PADOVA[0], longitude=PADOVA[1], accuracy_meters=5000
            )
            assert result["recorded"] is False
            assert result["reason"] == "accuracy_too_low"
            assert await service.repo.list_candidates(uid) == []
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_nothing_in_the_code_decides_what_a_place_is(monkeypatch):
    """
    Structural, because this is the rule that would be easiest to break by
    accident. No threshold promotes a candidate, and no domain word appears in
    the logic that handles them.
    """
    banned = ("palestra", "gym", "ufficio", "office", "supermerc", "hospital",
              "ospedale", "school", "scuola", "ristorante", "restaurant")
    for name in ("service.py", "geometry.py", "models.py", "repository.py"):
        source = (HERE / "places" / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    source = source.replace(doc, "")
        code = "\n".join(
            line for line in source.splitlines() if not line.strip().startswith("#")
        )
        low = code.lower()
        for word in banned:
            assert word not in low, f"{name} conosce un dominio: {word!r}"

    # And no counter that turns evidence into a place on its own.
    service = (HERE / "places" / "service.py").read_text(encoding="utf-8")
    for shape in ("observation_count >", "observation_count >=", "times_seen >", "visits >"):
        assert shape not in service, f"una soglia promuove un candidato: {shape}"


# ---------------------------------------------------------------------------
# The model decides whether to ask. The person decides what it is.
# ---------------------------------------------------------------------------

def test_the_model_is_shown_measurements_and_no_verdict(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_rv_{uuid.uuid4().hex[:8]}"
        seen = {}

        async def capture(system, user):
            seen["system"] = system
            seen["user"] = user
            return {"ask_about": []}

        try:
            service = await _service(db)
            for _ in range(6):
                await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            _install(monkeypatch, capture)
            await service.review_candidates(uid)

            assert "times_seen" in seen["user"]
            assert "distinct_days" in seen["user"]
            # No word in the payload proposes a meaning.
            for word in ("gym", "palestra", "significant", "importance", "score"):
                assert word not in seen["user"].lower(), f"il payload suggerisce: {word}"
            assert "Never name a place" in seen["system"]
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_staying_quiet_is_a_valid_answer_and_changes_nothing(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_rv_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for _ in range(4):
                await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            _install(monkeypatch, FakeModel([{"ask_about": []}]))

            assert await service.review_candidates(uid) == []
            candidate = (await service.repo.list_candidates(uid))[0]
            assert candidate.outcome == "pending"
            assert candidate.question_id is None
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_question_worth_asking_becomes_an_ordinary_open_question(monkeypatch):
    """§7: no second question engine. It waits where every other question waits."""
    async def body():
        client, db = await _db()
        uid = f"u_rv_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for _ in range(5):
                await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            candidate = (await service.repo.list_candidates(uid))[0]
            _install(
                monkeypatch,
                FakeModel([
                    {
                        "ask_about": [
                            {
                                "candidate_id": candidate.id,
                                "question": "Che posto è?",
                                "why": "ci passi spesso",
                            }
                        ]
                    }
                ]),
            )
            raised = await service.review_candidates(uid)
            assert len(raised) == 1 and raised[0]["question"] == "Che posto è?"

            from waiting.repository import OpenQuestionRepository

            questions = await OpenQuestionRepository(db).list_open(uid)
            mine = [q for q in questions if q.get("context_label") == "Luoghi"]
            assert len(mine) == 1
            assert mine[0]["dedupe_key"] == f"place_candidate:{candidate.id}"
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            await db.open_questions.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_reference_to_a_candidate_that_does_not_exist_is_dropped(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_rv_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            _install(
                monkeypatch,
                FakeModel([
                    {"ask_about": [{"candidate_id": "pcd_inventato", "question": "Che posto è?"}]}
                ]),
            )
            assert await service.review_candidates(uid) == []
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_only_a_persons_answer_turns_a_candidate_into_a_place(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_cf_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for _ in range(5):
                await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            candidate = (await service.repo.list_candidates(uid))[0]

            _install(
                monkeypatch,
                FakeModel([{"decision": "name", "label": "La palestra", "role": "other"}]),
            )
            result = await service.answer_candidate(uid, candidate.id, "è la palestra")

            assert result["outcome"] == "confirmed"
            places = await service.list_places(uid)
            assert len(places) == 1
            # Their words, kept.
            assert places[0].label == "La palestra"
            assert places[0].source == "confirmed_candidate"
            assert places[0].from_candidate_id == candidate.id
            assert places[0].coordinates is not None
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_person_can_say_stop_asking_about_this_one(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_cf_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            candidate = (await service.repo.list_candidates(uid))[0]

            _install(monkeypatch, FakeModel([{"decision": "mute", "label": "", "role": "other"}]))
            result = await service.answer_candidate(uid, candidate.id, "non chiedermelo più")
            # Sprint 2 split two answers that were one word: "dismissed" is
            # not this time, "suppressed" is never ask me about this again.
            assert result["outcome"] == "suppressed"
            assert await service.list_places(uid) == []

            # And it is not raised again.
            _install(monkeypatch, FakeModel([{"ask_about": []}]))
            assert await service.review_candidates(uid) == []
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_an_answer_nobody_can_read_creates_nothing(monkeypatch):
    async def body():
        client, db = await _db()
        uid = f"u_cf_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            candidate = (await service.repo.list_candidates(uid))[0]
            _install(monkeypatch, FakeModel([{"decision": "unclear"}]))
            result = await service.answer_candidate(uid, candidate.id, "mah")
            assert result["ok"] is False
            assert await service.list_places(uid) == []
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


# ---------------------------------------------------------------------------
# "Portami a lavoro"
# ---------------------------------------------------------------------------

def test_a_destination_resolves_to_the_place_they_confirmed():
    async def body():
        client, db = await _db()
        uid = f"u_nv_{uuid.uuid4().hex[:8]}"
        try:
            from places.models import Coordinates

            service = await _service(db)
            work = await service.save_place(
                uid,
                label="Ufficio Zona Industriale",
                role="work",
                coordinates=Coordinates(latitude=ACROSS_TOWN[0], longitude=ACROSS_TOWN[1]),
            )
            await service.save_place(uid, label="Casa", role="home")

            # By the role they confirmed, and by the name they gave it.
            assert (await service.resolve_destination(uid, "lavoro")).place.id == work.id
            by_name = await service.resolve_destination(uid, "Ufficio Zona Industriale")
            assert by_name.place.id == work.id
        finally:
            await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_a_name_that_matches_nothing_is_a_question_not_a_guess():
    async def body():
        client, db = await _db()
        uid = f"u_nv_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await service.save_place(uid, label="Ufficio", role="work")
            resolution = await service.resolve_destination(uid, "Uffici")

            assert resolution.resolved is False, "una quasi-corrispondenza ha risolto"
            assert resolution.reason
            assert resolution.candidates, "non offre nemmeno le alternative"
        finally:
            await db.life_places.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_nothing_resolves_a_destination_by_approximate_spelling():
    """
    Structural. Being asked which place is a much smaller cost than being
    taken to the wrong one.
    """
    source = (HERE / "places" / "service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                source = source.replace(doc, "")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    for cheat in ("startswith", "endswith", "difflib", "levenshtein", "fuzz", "in p.label"):
        assert cheat not in code, f"la destinazione si risolve per somiglianza: {cheat}"


def test_navigation_hands_off_and_never_assumes_the_app():
    from places.navigation import handoff, navigation_url

    plan = handoff(latitude=ACROSS_TOWN[0], longitude=ACROSS_TOWN[1], label="Ufficio")
    assert plan["needs_choice"] is True, "un'app è stata scelta al posto della persona"
    ids = {o["id"] for o in plan["options"]}
    assert {"google_maps", "apple_maps", "waze"} <= ids

    chosen = handoff(
        latitude=ACROSS_TOWN[0],
        longitude=ACROSS_TOWN[1],
        label="Ufficio",
        preferred_app="waze",
    )
    assert chosen["needs_choice"] is False and chosen["app"] == "waze"
    assert "waze.com" in chosen["url"]

    # Coordinates, not a name: a name can land on the wrong branch.
    url = navigation_url("google_maps", latitude=45.5, longitude=11.9)
    assert "destination=45.5%2C11.9" in url

    # And nothing offered that cannot open.
    android = handoff(latitude=45.5, longitude=11.9, platform="android")
    assert "apple_maps" not in {o["id"] for o in android["options"]}


def test_the_capabilities_exist_and_none_of_them_decides_anything():
    from conversation_engine.ai_core.tools.registry import ToolRegistry

    registry = ToolRegistry()
    for name in (
        "list_life_places",
        "get_life_place",
        "save_life_place",
        "record_location_observation",
        "open_navigation",
    ):
        assert name in registry._tools, f"capability mancante: {name}"

    spec = registry._tools["open_navigation"]
    assert "not when they asked" in spec.description, (
        "la descrizione non distingue andare dal chiedere quanto ci vuole"
    )
    save = registry._tools["save_life_place"]
    assert "Never label a place for them" in save.description


def test_the_prompt_separates_asking_from_going():
    """§12: the difference has to be reasoned, not pattern-matched."""
    prompt = (HERE / "conversation_engine" / "ai_core" / "prompt.py").read_text(encoding="utf-8")
    assert "Portami a lavoro" in prompt
    assert "Quanto ci metto" in prompt
    assert "do not treat" in prompt and "as a trigger" in prompt


def test_a_place_question_is_not_work_by_itself(monkeypatch):
    """
    V3.3's rule still holds here: noticing something is not a task. A place
    ORA is curious about must not appear as work waiting to be done.
    """
    async def body():
        client, db = await _db()
        uid = f"u_wk_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            for _ in range(6):
                await service.record_observation(uid, latitude=PADOVA[0], longitude=PADOVA[1])
            candidate = (await service.repo.list_candidates(uid))[0]
            _install(
                monkeypatch,
                FakeModel([
                    {"ask_about": [{"candidate_id": candidate.id, "question": "Che posto è?"}]}
                ]),
            )
            await service.review_candidates(uid)

            for collection in ("attention_items", "work_items", "action_center_items"):
                if collection in await db.list_collection_names():
                    assert await db[collection].count_documents({"user_id": uid}) == 0, (
                        f"un luogo osservato è diventato lavoro in {collection}"
                    )
        finally:
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            await db.open_questions.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_turning_location_off_can_actually_erase_what_was_seen():
    """Named places are theirs and stay. What the device noticed does not."""
    async def body():
        client, db = await _db()
        uid = f"u_pv_{uuid.uuid4().hex[:8]}"
        try:
            service = await _service(db)
            await service.save_place(uid, label="Casa", role="home")
            for _ in range(3):
                await service.record_observation(uid, latitude=ACROSS_TOWN[0], longitude=ACROSS_TOWN[1])

            erased = await service.forget_observations(uid)
            assert erased["observations_deleted"] >= 3
            assert erased["candidates_deleted"] >= 1
            assert await service.repo.list_candidates(uid) == []
            assert [p.label for p in await service.list_places(uid)] == ["Casa"]
        finally:
            await db.life_places.delete_many({"user_id": uid})
            await db.presence_observations.delete_many({"user_id": uid})
            await db.place_candidates.delete_many({"user_id": uid})
            client.close()

    _run(body())


def test_what_leaves_the_server_for_a_screen_is_not_a_coordinate_list():
    from places.models import Coordinates, LifePlace

    place = LifePlace(
        user_id="u",
        label="Casa",
        role="home",
        role_confirmed_by_user=True,
        coordinates=Coordinates(latitude=45.4064, longitude=11.8768),
    )
    public = place.public()
    assert public["has_coordinates"] is True
    assert "coordinates" not in public and "latitude" not in public
    assert "latitude" not in place.for_ai()


def test_geometry_only_answers_questions_that_have_right_answers():
    from places.geometry import distance_meters, same_place
    from places.models import Coordinates

    here = Coordinates(latitude=PADOVA[0], longitude=PADOVA[1])
    door = Coordinates(latitude=NEXT_DOOR[0], longitude=NEXT_DOOR[1])
    far = Coordinates(latitude=ACROSS_TOWN[0], longitude=ACROSS_TOWN[1])

    assert distance_meters(here, here) == pytest.approx(0.0, abs=0.001)
    assert distance_meters(here, door) < 30
    assert 1000 < distance_meters(here, far) < 3000
    assert same_place(here, door) is True
    assert same_place(here, far) is False
