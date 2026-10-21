"""Offline capture contract: synthetic owners, bounded geometry, atomic Mongo semantics.

The collection substitute models unique keys and compare-and-swap only; it is
not evidence of an on-device RoomPlan scan or a production Mongo deployment.
"""
from __future__ import annotations

import asyncio
import copy
import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import FastAPI, Header, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from house_scans.models import (
    CreateHouseScan, HouseCapture, MAX_CAPTURE_BYTES, MAX_PATCH_BYTES, UpdateHouseScan,
)
from house_scans.service import HouseScanError, HouseScanService


def transform(x=0.0, y=0.0, z=0.0, angle=0.0):
    c, s = math.cos(angle), math.sin(angle)
    return [c, 0.0, -s, 0.0, 0.0, 1.0, 0.0, 0.0, s, 0.0, c, 0.0, x, y, z, 1.0]


def surface(item_id="wall-a", x=4.0, y=2.8, z=0.0, matrix=None):
    return {"id": item_id, "dimensions": {"x": x, "y": y, "z": z},
            "transform": matrix or transform(), "confidence": "high"}


def capture(capture_id="capture-fixture-1"):
    return {
        "schema_version": 1, "capture_id": capture_id, "source": "apple_roomplan",
        "captured_at": "2026-10-21T14:00:00+02:00",
        "rooms": [{
            "id": "room-one", "name": "Soggiorno",
            "walls": [
                surface("wall-a", matrix=transform(0, 1.4, -1.5)),
                surface("wall-b", x=3, matrix=transform(2, 1.4, 0, math.pi / 2)),
                surface("wall-c", matrix=transform(0, 1.4, 1.5, math.pi)),
                surface("wall-d", x=3, matrix=transform(-2, 1.4, 0, -math.pi / 2)),
            ],
            "doors": [], "windows": [], "openings": [],
            "floors": [surface("floor-one", x=4, y=0, z=3)], "objects": [],
        }],
    }


def request_body(capture_id="capture-fixture-1"):
    return {"title": "Casa di prova", "capture": capture(capture_id)}


class DuplicateKeyError(Exception):
    code = 11000


class Cursor:
    def __init__(self, records, projection):
        self.records = records
        self.projection = projection
        self.offset = 0

    def sort(self, fields):
        for field, direction in reversed(fields):
            self.records.sort(key=lambda item: item[field], reverse=direction < 0)
        return self

    def skip(self, offset):
        self.offset = offset
        return self

    async def to_list(self, length):
        items = self.records[self.offset:self.offset + length]
        if self.projection:
            items = [{k: v for k, v in item.items() if self.projection.get(k)} for item in items]
        return copy.deepcopy(items)


class Collection:
    def __init__(self):
        self.records = {}
        self.indexes = []
        self.queries = []
        self.lose_update_race = False
        self.lose_delete_race = False

    @staticmethod
    def matches(record, query):
        return all(record.get(key) == value for key, value in query.items())

    async def create_index(self, fields, **options):
        self.indexes.append((fields, options))
        return options.get("name", "index")

    async def find_one(self, query):
        self.queries.append(copy.deepcopy(query))
        return next((copy.deepcopy(item) for item in self.records.values()
                     if self.matches(item, query)), None)

    def find(self, query, projection=None):
        self.queries.append(copy.deepcopy(query))
        return Cursor([copy.deepcopy(item) for item in self.records.values()
                       if self.matches(item, query)], projection)

    async def insert_one(self, record):
        # Let concurrent requests both reach insertion before enforcing uniqueness.
        await asyncio.sleep(0)
        if any(item["id"] == record["id"] or
               (item["user_id"], item["capture_id"]) == (record["user_id"], record["capture_id"])
               for item in self.records.values()):
            raise DuplicateKeyError()
        self.records[record["id"]] = copy.deepcopy(record)
        return SimpleNamespace(inserted_id=record["id"])

    async def update_one(self, query, update):
        self.queries.append(copy.deepcopy(query))
        if self.lose_update_race:
            return SimpleNamespace(matched_count=0)
        for key, item in self.records.items():
            if self.matches(item, query):
                self.records[key] = {**item, **copy.deepcopy(update["$set"])}
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)

    async def delete_one(self, query):
        self.queries.append(copy.deepcopy(query))
        if self.lose_delete_race:
            return SimpleNamespace(deleted_count=0)
        for key, item in list(self.records.items()):
            if self.matches(item, query):
                del self.records[key]
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


def make_service():
    database = SimpleNamespace(house_scans=Collection())
    return HouseScanService(database), database


@pytest_asyncio.fixture
async def http_scans(monkeypatch):
    service, database = make_service()
    dependencies = ModuleType("deps")

    async def auth(authorization: str | None = Header(None)):
        if authorization not in ("Bearer synthetic-alice", "Bearer synthetic-bob"):
            raise HTTPException(401, "Accesso richiesto")
        return {"user_id": authorization.removeprefix("Bearer synthetic-")}

    dependencies.db = database
    dependencies.get_current_user = auth
    monkeypatch.setitem(sys.modules, "deps", dependencies)
    path = Path(__file__).resolve().parents[1] / "routers/house_scans.py"
    spec = importlib.util.spec_from_file_location("house_scan_http_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_service", lambda: service)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    # A single-loop ASGI client exercises the real routing/dependency pipeline
    # without TestClient's cross-thread portal or an external socket server.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://synthetic-test") as client:
        yield client, database


def headers(owner="alice"):
    return {"Authorization": f"Bearer synthetic-{owner}"}


BASE = "/api/house-scans"


@pytest.mark.parametrize("method,path", [
    ("GET", ""), ("POST", ""), ("GET", "/" + "a" * 32),
    ("PATCH", "/" + "a" * 32), ("DELETE", "/" + "a" * 32 + "?revision=1"),
])
@pytest.mark.asyncio
async def test_every_route_requires_bearer_auth_before_reading_input(http_scans, method, path):
    client, database = http_scans
    response = (await client.request(method, BASE + path, content=b"malformed unauthenticated body"))
    assert response.status_code == 401
    assert database.house_scans.records == {}


@pytest.mark.asyncio
async def test_http_create_reread_private_list_and_owner_isolation(http_scans):
    client, database = http_scans
    created = (await client.post(BASE, json=request_body(), headers=headers()))
    assert created.status_code == 201, created.text
    assert created.headers["cache-control"] == "private, no-store"
    saved = created.json()["scan"]
    assert created.json()["created"] is True
    assert saved["revision"] == 1
    assert saved["room_count"] == 1 and saved["wall_count"] == 4
    assert saved["captured_at"] == "2026-10-21T12:00:00Z"
    assert saved["provenance"]["original_measurements"] == "scan_estimates"
    assert saved["provenance"]["source_attestation"] == "client_reported"
    assert not {"user_id", "_id", "capture_sha256"}.intersection(saved)
    assert (await client.get(BASE + "/" + saved["id"], headers=headers())).json()["scan"] == saved
    summary = (await client.get(BASE, headers=headers())).json()["scans"][0]
    assert "capture" not in summary and "room_labels" not in summary
    assert (await client.get(BASE, headers=headers("bob"))).json()["scans"] == []
    path = BASE + "/" + saved["id"]
    assert (await client.get(path, headers=headers("bob"))).status_code == 404
    assert (await client.patch(path, json={"revision": 1, "title": "Intruso"}, headers=headers("bob"))).status_code == 404
    assert (await client.delete(path + "?revision=1", headers=headers("bob"))).status_code == 404
    assert all("user_id" in query for query in database.house_scans.queries)


@pytest.mark.asyncio
async def test_http_same_capture_is_owner_scoped_and_retry_does_not_overwrite(http_scans):
    client, _ = http_scans
    alice = (await client.post(BASE, json=request_body(), headers=headers())).json()["scan"]
    bob = (await client.post(BASE, json=request_body(), headers=headers("bob"))).json()["scan"]
    assert alice["id"] != bob["id"]
    path = BASE + "/" + alice["id"]
    (await client.patch(path, json={"revision": 1, "title": "Casa rinominata"}, headers=headers()))
    retry = (await client.post(BASE, json=request_body(), headers=headers()))
    assert retry.status_code == 200 and retry.json()["created"] is False
    assert retry.json()["scan"]["title"] == "Casa rinominata"
    assert retry.json()["scan"]["revision"] == 2
    different = request_body()
    different["capture"]["rooms"][0]["walls"][0]["dimensions"]["x"] = 4.4
    assert (await client.post(BASE, json=different, headers=headers())).status_code == 409
    assert len((await client.get(BASE, headers=headers())).json()["scans"]) == 1


@pytest.mark.asyncio
async def test_http_room_label_verified_measurement_and_clear_preserve_original_capture(http_scans):
    client, database = http_scans
    original = (await client.post(BASE, json=request_body(), headers=headers())).json()["scan"]
    path = BASE + "/" + original["id"]
    change = {"revision": 1, "room_labels": [{"room_id": "room-one", "name": "  Salone  "}],
              "wall_measurements": [{"room_id": "room-one", "wall_id": "wall-a", "length_m": 4.12}]}
    response = (await client.patch(path, json=change, headers=headers()))
    assert response.status_code == 200, response.text
    changed = response.json()["scan"]
    assert changed["capture"] == original["capture"]
    assert changed["room_labels"] == [{"room_id": "room-one", "name": "Salone"}]
    assert changed["wall_measurements"][0]["length_m"] == 4.12
    assert changed["wall_measurements"][0]["source"] == "user_verified"
    assert changed["wall_measurements"][0]["verified_at"]
    assert changed["verified_wall_count"] == 1
    assert (await client.patch(path, json=change, headers=headers())).status_code == 409
    clear = {"revision": 2, "room_labels": [{"room_id": "room-one", "name": "Soggiorno"}],
             "wall_measurements": [{"room_id": "room-one", "wall_id": "wall-a", "length_m": None}]}
    cleared = (await client.patch(path, json=clear, headers=headers())).json()["scan"]
    assert cleared["wall_measurements"] == [] and cleared["room_labels"] == []
    assert cleared["verified_wall_count"] == 0 and cleared["revision"] == 3
    assert cleared["capture"] == original["capture"]
    assert database.house_scans.records[original["id"]]["capture"] == original["capture"]


@pytest.mark.asyncio
async def test_http_invalid_edit_references_are_atomic_and_raw_geometry_cannot_be_patched(http_scans):
    client, _ = http_scans
    original = (await client.post(BASE, json=request_body(), headers=headers())).json()["scan"]
    path = BASE + "/" + original["id"]
    bad = {"revision": 1, "title": "Must not save",
           "wall_measurements": [{"room_id": "other-room", "wall_id": "wall-a", "length_m": 5}]}
    assert (await client.patch(path, json=bad, headers=headers())).status_code == 422
    assert (await client.patch(path, json={"revision": 1, "capture": capture()}, headers=headers())).status_code == 422
    assert (await client.get(path, headers=headers())).json()["scan"] == original


@pytest.mark.asyncio
async def test_http_delete_requires_current_revision_and_affects_only_owner(http_scans):
    client, _ = http_scans
    alice = (await client.post(BASE, json=request_body(), headers=headers())).json()["scan"]
    bob = (await client.post(BASE, json=request_body(), headers=headers("bob"))).json()["scan"]
    path = BASE + "/" + alice["id"]
    assert (await client.delete(path, headers=headers())).status_code == 422
    assert (await client.delete(path + "?revision=2", headers=headers())).status_code == 409
    assert (await client.delete(path + "?revision=1", headers=headers())).json() == {"deleted": True}
    assert (await client.get(path, headers=headers())).status_code == 404
    assert (await client.get(BASE + "/" + bob["id"], headers=headers("bob"))).status_code == 200


@pytest.mark.parametrize("payload", [
    b'{"title":"one","title":"two"}', b'{"capture":NaN}', b'{"capture":Infinity}',
    b'{"capture":-Infinity}', b'{"broken"', b'\xff', b'[' * 2000 + b']' * 2000,
], ids=["duplicate-key", "nan", "positive-infinity", "negative-infinity", "broken-json", "invalid-utf8", "too-deep"])
@pytest.mark.asyncio
async def test_http_rejects_invalid_ambiguous_or_deep_json(http_scans, payload):
    client, database = http_scans
    response = (await client.post(BASE, content=payload,
                           headers={**headers(), "Content-Type": "application/json"}))
    assert response.status_code == 422
    assert database.house_scans.records == {}


@pytest.mark.asyncio
async def test_http_rejects_raw_images_remote_urls_and_compressed_bodies(http_scans):
    client, database = http_scans
    assert (await client.post(BASE, content=b"fake-image", headers={**headers(), "Content-Type": "image/jpeg"})).status_code == 415
    assert (await client.post(BASE, json={**request_body(), "url": "https://example.invalid/plan"}, headers=headers())).status_code == 422
    assert (await client.post(BASE, json={**request_body(), "user_id": "bob"}, headers=headers())).status_code == 422
    assert (await client.post(BASE, json=request_body(), headers={**headers(), "Content-Encoding": "gzip"})).status_code == 415
    assert database.house_scans.records == {}


@pytest.mark.asyncio
async def test_http_size_cap_works_even_when_advertised_length_is_small(http_scans):
    client, database = http_scans
    response = (await client.post(BASE, content=b" " * (MAX_CAPTURE_BYTES + 1),
                           headers={**headers(), "Content-Type": "application/json", "Content-Length": "1"}))
    assert response.status_code == 413
    assert database.house_scans.records == {}
    saved = (await client.post(BASE, json=request_body(), headers=headers())).json()["scan"]
    response = (await client.patch(BASE + "/" + saved["id"], content=b" " * (MAX_PATCH_BYTES + 1),
                            headers={**headers(), "Content-Type": "application/json"}))
    assert response.status_code == 413
    assert database.house_scans.records[saved["id"]]["revision"] == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -1, 101, True, "4.0"])
def test_geometry_requires_finite_numeric_bounded_dimensions(value):
    data = capture()
    data["rooms"][0]["walls"][0]["dimensions"]["x"] = value
    with pytest.raises(ValidationError):
        HouseCapture.model_validate(data)


@pytest.mark.parametrize("matrix", [
    [0.0] * 16, transform()[:-1], transform() + [0.0],
    [2.0] + transform()[1:], [-1.0] + transform()[1:],
    transform(x=1001), transform(x=float("nan")), transform(x="2"),
    transform()[:15] + [0.0],
])
def test_geometry_rejects_invalid_or_scaled_transforms(matrix):
    data = capture()
    data["rooms"][0]["walls"][0]["transform"] = matrix
    with pytest.raises(ValidationError):
        HouseCapture.model_validate(data)


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"schema_version": "1"}, {"source": "magicplan"},
    {"capture_id": "../../other-owner"}, {"capture_id": "$set"},
    {"captured_at": 1_700_000_000}, {"captured_at": "2026-10-21T12:00:00"},
    {"captured_at": "0001-01-01T00:00:00+14:00"},
    {"captured_at": "9999-12-31T23:59:59-14:00"},
    {"user_id": "bob"}, {"raw_image": "data:image/png;base64,abc"},
])
def test_capture_schema_rejects_forged_or_ambiguous_fields(change):
    with pytest.raises(ValidationError):
        HouseCapture.model_validate({**capture(), **change})


def test_ids_are_unique_within_room_but_shared_wall_ids_across_rooms_are_allowed():
    data = capture()
    room = copy.deepcopy(data["rooms"][0])
    data["rooms"].append(room)
    with pytest.raises(ValidationError):
        HouseCapture.model_validate(data)
    room["id"] = "room-two"
    assert len(HouseCapture.model_validate(data).rooms) == 2
    room["walls"][1]["id"] = room["walls"][0]["id"]
    with pytest.raises(ValidationError):
        HouseCapture.model_validate(data)


def test_room_and_total_element_caps():
    data = capture()
    data["rooms"] = [{**copy.deepcopy(data["rooms"][0]), "id": f"room-{i}"} for i in range(51)]
    with pytest.raises(ValidationError):
        HouseCapture.model_validate(data)
    data["rooms"] = data["rooms"][:11]
    for room in data["rooms"]:
        room["objects"] = [{**surface(f"object-{i}", x=1, y=1, z=1), "category": "chair"}
                           for i in range(200)]
    with pytest.raises(ValidationError, match="2000"):
        HouseCapture.model_validate(data)


def test_patch_validates_verified_lengths_and_does_not_accept_duplicate_edits():
    for length in (0, -1, 101, float("nan"), True, "4.5"):
        with pytest.raises(ValidationError):
            UpdateHouseScan.model_validate({"revision": 1, "wall_measurements": [
                {"room_id": "room-one", "wall_id": "wall-a", "length_m": length}]})
    for body in ({"revision": True, "title": "Casa"}, {"revision": 1},
                 {"revision": 1, "title": None}, {"revision": 1, "title": "\n"},
                 {"revision": 1, "room_labels": [{"room_id": "room-one", "name": "A"}] * 2}):
        with pytest.raises(ValidationError):
            UpdateHouseScan.model_validate(body)


@pytest.mark.asyncio
async def test_concurrent_retry_uses_unique_owner_capture_index_and_survives_service_recreation():
    service, database = make_service()
    body = CreateHouseScan.model_validate(request_body())
    results = await asyncio.gather(service.create("alice", body), service.create("alice", body))
    assert sorted(created for _, created in results) == [False, True]
    assert results[0][0]["id"] == results[1][0]["id"]
    assert len(database.house_scans.records) == 1
    assert ([("user_id", 1), ("capture_id", 1)],
            {"unique": True, "name": "house_scan_owner_capture"}) in database.house_scans.indexes
    restarted = HouseScanService(database)
    assert await restarted.get("alice", results[0][0]["id"]) == results[0][0]


@pytest.mark.asyncio
async def test_concurrent_different_capture_with_same_key_is_not_silently_accepted():
    service, database = make_service()
    first = CreateHouseScan.model_validate(request_body())
    altered = request_body()
    altered["capture"]["rooms"][0]["walls"][0]["dimensions"]["x"] = 4.3
    second = CreateHouseScan.model_validate(altered)
    results = await asyncio.gather(service.create("alice", first), service.create("alice", second),
                                   return_exceptions=True)
    assert sum(isinstance(result, HouseScanError) and result.status == 409 for result in results) == 1
    assert len(database.house_scans.records) == 1


@pytest.mark.asyncio
async def test_update_and_delete_cas_reject_a_race_after_initial_read():
    service, database = make_service()
    original, _ = await service.create("alice", CreateHouseScan.model_validate(request_body()))
    database.house_scans.lose_update_race = True
    with pytest.raises(HouseScanError) as changed:
        await service.update("alice", original["id"], UpdateHouseScan(revision=1, title="Changed"))
    assert changed.value.status == 409
    assert await service.get("alice", original["id"]) == original
    database.house_scans.lose_delete_race = True
    with pytest.raises(HouseScanError) as deleted:
        await service.delete("alice", original["id"], 1)
    assert deleted.value.status == 409
    assert await service.get("alice", original["id"]) == original


@pytest.mark.asyncio
async def test_list_is_paginated_newest_first_without_private_geometry():
    service, _ = make_service()
    saved = []
    for number in range(4):
        item, _ = await service.create("alice", CreateHouseScan.model_validate(request_body(f"capture-{number}")))
        saved.append(item)
    await service.update("alice", saved[0]["id"], UpdateHouseScan(revision=1, title="Latest"))
    first = await service.list_scans("alice", limit=2)
    assert first["has_more"] is True and first["next_offset"] == 2
    assert first["scans"][0]["title"] == "Latest"
    second = await service.list_scans("alice", limit=2, offset=2)
    assert second["has_more"] is False and second["next_offset"] is None
    summaries = first["scans"] + second["scans"]
    assert {row["id"] for row in summaries} == {row["id"] for row in saved}
    assert all("capture" not in row and "user_id" not in row for row in summaries)
