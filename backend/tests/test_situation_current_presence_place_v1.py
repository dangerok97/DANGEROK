"""A just-started activity takes the place label of the current authorized position.

Production 23/10/2026: "Ho appena steso i panni" read weather at the current
position, but the Situation was stored without a place and a later review asked
the person for the locality. Synthetic data only.
"""
from datetime import datetime, timedelta, timezone

import pytest

from situations.declared_place_link import attach_current_presence_label
from situations.models import SituationUpdate

NOW = datetime(2026, 10, 23, 8, 55, tzinfo=timezone.utc)


def create(**extra):
    base = dict(operation="create", summary="Attività sintetica appena iniziata",
                started_at=(NOW - timedelta(minutes=1)).isoformat())
    base.update(extra)
    return SituationUpdate(**base)


def at(label):
    async def where(owner):
        return (42.0, 11.0, label) if label is not None else None
    return where


@pytest.mark.asyncio
async def test_just_started_activity_gets_current_locality():
    out = await attach_current_presence_label(object(), owner_id="u", update=create(), now=NOW, where=at("Località sintetica"))
    assert out.location_label == "Località sintetica"


@pytest.mark.asyncio
@pytest.mark.parametrize("update", [
    create(location_label="Altrove"),                                   # the person said where
    create(linked_object_refs=["place:p1"]),                            # a saved place is linked
    create(started_at=(NOW - timedelta(minutes=40)).isoformat()),       # not just started
    create(started_at=None),                                            # start unknown
    SituationUpdate(operation="update", situation_id="s", expected_revision=1,
                    started_at=(NOW - timedelta(minutes=1)).isoformat()),  # not a creation
])
async def test_rule_does_not_apply(update):
    out = await attach_current_presence_label(object(), owner_id="u", update=update, now=NOW, where=at("Località sintetica"))
    assert out is update


@pytest.mark.asyncio
@pytest.mark.parametrize("where", [at(None), at("")])
async def test_no_consent_stale_or_unnamed_position_changes_nothing(where):
    update = create()
    assert await attach_current_presence_label(object(), owner_id="u", update=update, now=NOW, where=where) is update


@pytest.mark.asyncio
async def test_position_failure_never_blocks_the_situation():
    async def broken(owner):
        raise RuntimeError("provider down")
    update = create()
    assert await attach_current_presence_label(object(), owner_id="u", update=update, now=NOW, where=broken) is update
