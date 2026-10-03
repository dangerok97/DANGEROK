"""A repeated spot wakes ORA without opening Vita, under explicit consent."""

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _loop_harness


def test_current_fix_counts_and_review_is_bounded_by_days_and_consent(monkeypatch):
    from ambient.service import AmbientService
    from places.models import Coordinates, PlaceCandidate, PresenceObservation
    from places.service import PlacesService

    consent = True
    calls = []
    old = PresenceObservation(user_id="u", coordinates=Coordinates(latitude=41, longitude=12),
                              candidate_id="same", observed_at="2026-09-27T12:00:00+00:00")
    current = PresenceObservation(user_id="u", coordinates=old.coordinates,
                                  candidate_id="same", observed_at="2026-09-28T12:00:00+00:00")
    candidate = PlaceCandidate(id="same", user_id="u", centroid=old.coordinates, distinct_days=1)

    class Users:
        async def find_one(self, query, projection):
            assert query == {"user_id": "u"}
            return {"preferences": {"place_monitoring_enabled": consent}}

    class DB:
        users = Users()

    async def observations(uid):
        return [old]

    async def save(value):
        return value

    async def schedule(self, owner_id, **kwargs):
        calls.append((owner_id, kwargs))
        return SimpleNamespace(id="wake")

    async def check():
        nonlocal consent
        service = PlacesService(DB())
        monkeypatch.setattr(service.repo, "recent_observations", observations)
        monkeypatch.setattr(service.repo, "save_candidate", save)
        monkeypatch.setattr(AmbientService, "schedule", schedule)
        assert await service._distinct_days("u", candidate, current) == 2
        candidate.distinct_days = 3

        consent = False
        await service._schedule_candidate_review("u", candidate)
        assert calls == [] and candidate.review_requested_days == 0
        consent = True
        await service._schedule_candidate_review("u", candidate)
        assert len(calls) == 1
        assert calls[0][1]["source_ref"] == "place_candidate:same"
        assert candidate.review_requested_days == 3
        await service._schedule_candidate_review("u", candidate)
        assert len(calls) == 1
        candidate.distinct_days = 6
        await service._schedule_candidate_review("u", candidate)
        assert len(calls) == 2

    _loop_harness.run(check())


def test_background_review_rechecks_consent_before_asking(monkeypatch):
    from ambient.models import AmbientWake
    from ambient.runtime import _handle
    from places.service import PlacesService

    enabled = False
    asked = []

    class Users:
        async def find_one(self, query, projection):
            return {"preferences": {"place_monitoring_enabled": enabled}}

    class DB:
        users = Users()

    async def review(self, owner_id, *, candidate_id, **kwargs):
        asked.append((owner_id, candidate_id))
        return []

    async def check():
        nonlocal enabled
        monkeypatch.setattr(PlacesService, "review_candidates", review)
        wake = AmbientWake(owner_id="u", reason="ambient_review", source_ref="place_candidate:same")
        quiet = await _handle(DB(), wake)
        assert quiet.result == "monitoring_off" and asked == []
        enabled = True
        done = await _handle(DB(), wake)
        assert done.result == "place_questions:0"
        assert asked == [("u", "same")]

    _loop_harness.run(check())


def test_known_place_transition_wakes_ordinary_opportunity_reasoning(monkeypatch):
    from opportunities.discovery import OpportunityDiscovery
    from places.service import PlacesService

    notes = []

    class Users:
        async def find_one(self, query, projection):
            return {"preferences": {"place_monitoring_enabled": True}}

    class DB:
        users = Users()

    async def note(self, owner_id, **kwargs):
        notes.append((owner_id, kwargs))
        return {"outcome": "accepted", "reason": ""}

    async def check():
        monkeypatch.setattr(OpportunityDiscovery, "note", note)
        service = PlacesService(DB())
        await service._note_presence_transitions(
            "u",
            {"entered": ["home", "work"], "returned": ["work"], "exited": ["gym"]},
        )
        assert [(row[1]["kind"], row[1]["entity_ref"]) for row in notes] == [
            ("presence.entered", "place:home"),
            ("presence.returned", "place:work"),
            ("presence.exited", "place:gym"),
        ]
        assert all(row[1]["source"] == "places" for row in notes)

    _loop_harness.run(check())


def test_known_place_transition_respects_monitoring_consent(monkeypatch):
    from opportunities.discovery import OpportunityDiscovery
    from places.service import PlacesService

    notes = []

    class Users:
        async def find_one(self, query, projection):
            return {"preferences": {"place_monitoring_enabled": False}}

    class DB:
        users = Users()

    async def note(self, owner_id, **kwargs):
        notes.append((owner_id, kwargs))

    async def check():
        monkeypatch.setattr(OpportunityDiscovery, "note", note)
        service = PlacesService(DB())
        await service._note_presence_transitions("u", {"entered": ["home"]})
        assert notes == []

    _loop_harness.run(check())
