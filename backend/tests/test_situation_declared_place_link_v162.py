"""Situation place identity recovery: exact, owner-scoped and fail-closed."""
import pytest

from situations.declared_place_link import restore_owned_place_reference
from situations.models import SituationUpdate


class Cursor:
    def __init__(self, rows):
        self.rows, self.max_rows = rows, 1000

    def limit(self, n):
        self.max_rows = n
        return self

    async def to_list(self, length):
        return self.rows[:min(self.max_rows, length)]


class PlaceCollection:
    def __init__(self, rows):
        self.rows, self.queries = rows, []

    def find(self, criteria, projection):
        self.queries.append((criteria, projection))
        return Cursor([r for r in self.rows if r["user_id"] == criteria["user_id"]
                       and r.get("state") != "dismissed"])


class Db:
    def __init__(self, rows):
        self.life_places = PlaceCollection(rows)


def place(id="t", *, owner="a", label="Tarquinia", state="active"):
    return dict(id=id, user_id=owner, label=label, state=state)


def declaration(**kwargs):
    return SituationUpdate(operation="create", summary="Caso in corso",
                           location_label="Tarquinia", **kwargs)


@pytest.mark.asyncio
async def test_owned_unique_name_recovers_canonical_reference():
    db, original = Db([place(), place("foreign", owner="b")]), declaration()
    out = await restore_owned_place_reference(
        db, owner_id="a", user_message="Ho appena steso i panni a Tarquinia.", update=original)
    assert out is not original and out.linked_object_refs == ["place:t"]
    assert original.linked_object_refs == []
    assert out.summary == original.summary and out.location_label == original.location_label
    assert db.life_places.queries[0][0]["user_id"] == "a"


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["A Milano", "Luogo non indicato", "Tarquiniazzata"])
async def test_unmentioned_or_partial_label_does_not_link(message):
    u = declaration()
    assert await restore_owned_place_reference(
        Db([place()]), owner_id="a", user_message=message, update=u) is u


@pytest.mark.asyncio
async def test_ambiguous_duplicates_are_not_assumed():
    u = declaration()
    assert await restore_owned_place_reference(
        Db([place("1"), place("2")]), owner_id="a",
        user_message="A Tarquinia", update=u) is u


@pytest.mark.asyncio
async def test_other_owner_and_dismissed_place_are_rejected():
    u = declaration()
    assert await restore_owned_place_reference(
        Db([place("foreign", owner="b"), place(state="dismissed")]),
        owner_id="a", user_message="A Tarquinia", update=u) is u


@pytest.mark.asyncio
async def test_already_declared_ref_cannot_be_overwritten():
    u = declaration(linked_object_refs=["place:chosen"])
    assert await restore_owned_place_reference(
        Db([place()]), owner_id="a", user_message="A Tarquinia", update=u) is u


@pytest.mark.asyncio
async def test_unrelated_operation_or_inferred_source_stays_intact():
    for u in (SituationUpdate(operation="update", situation_id="sit_1",
                              location_label="Tarquinia"),
              declaration(source="inferred")):
        assert await restore_owned_place_reference(
            Db([place()]), owner_id="a", user_message="A Tarquinia", update=u) is u


@pytest.mark.asyncio
async def test_partial_owner_inventory_is_not_enough():
    u = declaration()
    db = Db([place()] + [place(str(n), label=f"Altro {n}") for n in range(100)])
    assert await restore_owned_place_reference(
        db, owner_id="a", user_message="A Tarquinia", update=u) is u


@pytest.mark.asyncio
async def test_read_failure_is_nonblocking():
    class Broken:
        @property
        def life_places(self):
            raise RuntimeError("offline")
    u = declaration()
    assert await restore_owned_place_reference(
        Broken(), owner_id="a", user_message="A Tarquinia", update=u) is u
