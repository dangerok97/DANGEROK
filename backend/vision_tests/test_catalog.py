"""Standalone Vision tests: real disposable Mongo, deterministic provider fixtures.
No end-user account, provider key, production DB or production auth bypass.
Run with PYTHONPATH=backend pytest -c /dev/null backend/vision_tests -q.
"""
import asyncio
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import uuid

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image
from pydantic import ValidationError

from vision_catalog import CatalogService, CatalogLimit, Manifest, MODELS, VERSIONS, JOBS, seeds, now
from datetime import timedelta


@pytest_asyncio.fixture
async def database():
    url = os.environ.get("VISION_TEST_MONGO_URL", "mongodb://127.0.0.1:27017")
    name = "ora_vision_test_" + uuid.uuid4().hex
    client = AsyncIOMotorClient(url, serverSelectionTimeoutMS=5000, tz_aware=True)
    await client.admin.command("ping")
    try:
        yield client[name]
    finally:
        assert name.startswith("ora_vision_test_")
        await client.drop_database(name)
        client.close()


def generated_fixture(key="test_widget"):
    # A geometry fixture, NOT evidence about a physical stapler.
    data = seeds()[1].model_dump(mode="json")
    data["canonical_key"] = key
    data["title"] = "Oggetto di test"
    return data


@pytest.mark.parametrize("manifest", seeds(), ids=lambda m: m.canonical_key)
def test_seed_is_separable_and_explicitly_illustrative(manifest):
    assert Manifest.model_validate(manifest.model_dump()) == manifest
    assert manifest.evidence_level == "illustrative"
    assert len({p.key for p in manifest.parts}) == len(manifest.parts)
    assert any(p.assembled != p.exploded for p in manifest.parts)
    assert all(p.evidence == "typical" for p in manifest.parts)


@pytest.mark.parametrize("field,value", [("shape", "eval"), ("size", [0,2,3]),
    ("size", [float("nan"),2,3]), ("exploded", [9999,0,0]), ("evidence", "visible")])
def test_invalid_geometry_is_rejected(field, value):
    data = generated_fixture(); data["parts"][0][field] = value
    with pytest.raises(ValidationError): Manifest.model_validate(data)


def test_duplicate_parts_are_rejected():
    data = generated_fixture(); data["parts"][1]["key"] = data["parts"][0]["key"]
    with pytest.raises(ValidationError): Manifest.model_validate(data)


def test_cannot_upgrade_ai_evidence():
    data = generated_fixture(); data["evidence_level"] = "model_verified"
    with pytest.raises(ValidationError): Manifest.model_validate(data)


@pytest.mark.asyncio
async def test_seed_hit_never_calls_generator(database):
    service = CatalogService(database)
    async def forbidden(): raise AssertionError("A catalog hit generated again")
    one = await service.resolve(key="remote_control", title="", user_id="alice", generator=forbidden)
    two = await CatalogService(database).resolve(key="remote_control", title="", user_id="bob", generator=forbidden)
    assert one["version_id"] == two["version_id"]
    assert one["cache_hit"] and two["cache_hit"] and not two["generation_used"]
    assert await database[MODELS].count_documents({}) == len(seeds())
    assert await database[VERSIONS].count_documents({}) == len(seeds())
    assert await database[JOBS].count_documents({}) == 0


@pytest.mark.asyncio
async def test_generated_model_is_reused_without_second_generation(database):
    calls = 0
    async def generate():
        nonlocal calls
        calls += 1; return generated_fixture()
    first = await CatalogService(database).resolve(key="test_widget", title="", user_id="alice", generator=generate)
    second = await CatalogService(database).resolve(key="test_widget", title="", user_id="bob", generator=generate)
    assert calls == 1 and first["generation_used"] and second["cache_hit"]
    assert first["version_id"] == second["version_id"]
    assert first["shared"] and second["shared"]


@pytest.mark.asyncio
async def test_legacy_private_model_is_not_republished(database):
    service = CatalogService(database)
    await service.initialize()
    scope = service.private_scope("alice")
    first = await service._store(Manifest.model_validate(generated_fixture()), scope, "generated")
    await database[JOBS].insert_one({"_id":"legacy-private-job", "model_id":first["model_id"],
                                    "scope":scope, "state":"ready"})
    assert await service.find("test_widget", "bob") is None
    assert await service.read(first["model_id"], scope=service.private_scope("bob")) is None
    assert await service.job_result("legacy-private-job", "bob") is None
    await CatalogService(database).initialize()
    assert (await service.find("test_widget", "alice"))["shared"] is False
    assert await database[MODELS].count_documents({"canonical_key":"test_widget", "scope":"shared"}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_flag", [None, False, True])
async def test_generic_model_is_shared_automatically(database, legacy_flag):
    async def generate(): return generated_fixture()
    service = CatalogService(database)
    a = await service.resolve(key="test_widget", title="", user_id="alice", generator=generate, contribute=legacy_flag)
    b = await CatalogService(database).resolve(key="test_widget", title="", user_id="bob")
    assert a["shared"] and b["shared"] and b["cache_hit"]
    assert a["version_id"] == b["version_id"]
    assert b["manifest"]["evidence_level"] == "illustrative"


@pytest.mark.asyncio
async def test_concurrent_users_share_one_build(database):
    calls = 0
    async def generate():
        nonlocal calls
        calls += 1; await asyncio.sleep(.15); return generated_fixture()
    a, b = await asyncio.gather(*[CatalogService(database).resolve(key="test_widget", title="", user_id=u,
                                generator=generate) for u in ("alice", "bob")])
    assert calls == 1
    assert any(x["status"] == "family" for x in (a,b))
    assert await database[MODELS].count_documents({"canonical_key": "test_widget"}) == 1
    assert await database[JOBS].count_documents({"canonical_key": "test_widget"}) == 1


@pytest.mark.asyncio
async def test_generated_model_survives_a_new_python_process(database):
    async def generate(): return generated_fixture()
    first = await CatalogService(database).resolve(key="test_widget", title="", user_id="alice", generator=generate)
    script = '''import asyncio,json,os
from motor.motor_asyncio import AsyncIOMotorClient
from vision_catalog import CatalogService
async def main():
 c=AsyncIOMotorClient(os.environ["VISION_TEST_MONGO_URL"])
 value=await CatalogService(c[os.environ["VISION_TEST_DB"]]).find("test_widget","alice")
 print(json.dumps({"version_id":value["version_id"]}))
 c.close()
asyncio.run(main())
'''
    env = {**os.environ, "VISION_TEST_DB": database.name,
           "VISION_TEST_MONGO_URL": os.environ.get("VISION_TEST_MONGO_URL", "mongodb://127.0.0.1:27017")}
    process = await asyncio.to_thread(subprocess.run, [sys.executable,"-c",script], env=env,
                                      capture_output=True, text=True, check=True, timeout=15)
    assert json.loads(process.stdout)["version_id"] == first["version_id"]


@pytest.mark.asyncio
async def test_failed_generation_is_not_published(database):
    async def generate(): return {"parts": []}
    service = CatalogService(database)
    result = await service.resolve(key="test_widget", title="", user_id="alice", generator=generate)
    assert result["status"] == "unknown"
    assert await service.find("test_widget", "alice") is None
    assert await database[JOBS].count_documents({"state": "failed"}) == 1


@pytest.mark.asyncio
async def test_initializing_does_not_resurrect_retired_seed(database):
    service = CatalogService(database); await service.initialize()
    found = await service.find("remote_control", "alice")
    await database[MODELS].update_one({"_id": found["model_id"]}, {"$set": {"status": "retired"}})
    fresh = CatalogService(database); await fresh.initialize()
    assert await fresh.find("remote_control", "alice") is None
    assert len(await fresh.list_models("alice")) == len(seeds()) - 1


@pytest.mark.asyncio
async def test_expired_build_lease_is_recoverable(database):
    service = CatalogService(database); await service.initialize()
    scope = "shared"; model_id = service.model_id("test_widget", scope)
    from vision_catalog import digest
    job_id = "vxj_" + digest(model_id)
    await database[JOBS].insert_one({"_id":job_id,"scope":scope,"model_id":model_id,
        "canonical_key":"test_widget","state":"building","lease_until":now()-timedelta(seconds=2),
        "lease_token":"dead-process","attempts":1})
    async def generate(): return generated_fixture()
    result = await service.resolve(key="test_widget",title="",user_id="alice",generator=generate)
    assert result["status"] == "family"
    assert (await database[JOBS].find_one({"_id":job_id}))["attempts"] == 2


@pytest.mark.asyncio
async def test_stale_builder_cannot_publish(database):
    service = CatalogService(database)
    async def generate():
        await database[JOBS].update_one({"canonical_key":"test_widget"},{"$set":{"lease_token":"new-worker"}})
        return generated_fixture()
    result = await service.resolve(key="test_widget",title="",user_id="alice",generator=generate)
    assert result["status"] == "building"
    assert await service.find("test_widget","alice") is None


@pytest.mark.asyncio
async def test_quota_is_atomic_and_bounded(database):
    service = CatalogService(database); await service.initialize()
    await service.quota("alice","test",2,60); await service.quota("alice","test",2,60)
    with pytest.raises(CatalogLimit): await service.quota("alice","test",2,60)


@pytest_asyncio.fixture
async def api_module(database, monkeypatch):
    fake = types.ModuleType("deps"); fake.db = database
    async def user(authorization: str | None = Header(None)):
        if authorization not in ("Bearer vision-test-alice", "Bearer vision-test-bob"):
            raise HTTPException(401,"Missing test bearer")
        return {"user_id": authorization.removeprefix("Bearer vision-test-")}
    fake.get_current_user = user
    monkeypatch.setitem(sys.modules,"deps",fake)
    path = Path(__file__).resolve().parents[1]/"vision_xray.py"
    spec = importlib.util.spec_from_file_location("vision_under_test_"+uuid.uuid4().hex,path)
    module = importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name,None)


def jpeg():
    stream=io.BytesIO(); image=Image.new("RGB",(64,64),(120,90,50))
    exif=Image.Exif();exif[270]="private-metadata-never-persist"
    image.save(stream,"JPEG",exif=exif)
    return base64.b64encode(stream.getvalue()).decode()


def test_initial_families_are_distinct():
    assert len({seed.canonical_key for seed in seeds()}) == len(seeds())


@pytest.mark.asyncio
async def test_image_metadata_is_removed(api_module):
    blob=api_module.decode_photo("image/jpeg",jpeg())
    assert b"private-metadata-never-persist" not in blob
    with Image.open(io.BytesIO(blob)) as image: assert not image.getexif()
    with pytest.raises(HTTPException): api_module.decode_photo("image/png",jpeg())
    with pytest.raises(HTTPException): api_module.decode_photo("image/jpeg","invalid!!!!")


@pytest.mark.asyncio
async def test_bad_detection_box_is_not_treated_as_a_match(api_module):
    raw={"recognized":True,"confidence":"high","canonical_key":"remote_control","bbox":[0,0,float("nan"),1000]}
    assert api_module.normalize_identification(raw) is None
    raw["bbox"]=[100,200,900,600]
    assert api_module.normalize_identification(raw)["bbox"] == pytest.approx([.2,.1,.4,.8])


@pytest.mark.asyncio
async def test_router_returns_persisted_model_and_never_photo_bytes(api_module,monkeypatch,database):
    monkeypatch.setattr(api_module,"can_see",lambda:True)
    async def recognize(*args,**kwargs):
        return {"recognized":True,"canonical_key":"remote_control","object_name":"Telecomando","confidence":"high","bbox":[100,200,900,600],"safe_to_generate":True}
    monkeypatch.setattr(api_module,"ask_json",recognize)
    app=FastAPI();app.include_router(api_module.router,prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        assert (await client.get("/api/vision-xray/catalog")).status_code == 401
        body={"mime_type":"image/jpeg","image_base64":jpeg(),"frame_id":"frame-1","allow_generation":True}
        response=await client.post("/api/vision-xray/scan",json=body,headers={"Authorization":"Bearer vision-test-alice"})
        assert response.status_code == 200, response.text
        data=response.json();assert data["cache_hit"] and not data["generation_used"]
        assert data["frame_id"] == "frame-1" and len(data["manifest"]["parts"]) == 8
        assert response.headers["cache-control"] == "no-store"
    for name in (MODELS,VERSIONS,JOBS):
        docs=await database[name].find({}).to_list(100)
        serialized=json.dumps(docs,default=str)
        assert "image_base64" not in serialized and "private-metadata-never-persist" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_flag", [None, False, True])
async def test_api_shares_generic_recipe_without_client_opt_in(api_module, monkeypatch, database, legacy_flag):
    monkeypatch.setattr(api_module, "can_see", lambda: True)
    async def recognize(*args, **kwargs):
        return {"recognized":True, "canonical_key":"test_widget", "object_name":"Pinzatrice",
                "confidence":"high", "bbox":[100,200,900,600], "safe_to_generate":True}
    calls = []
    async def generate(key):
        calls.append(key)
        return generated_fixture(key)
    monkeypatch.setattr(api_module, "ask_json", recognize)
    monkeypatch.setattr(api_module, "generate_family", generate)
    app = FastAPI(); app.include_router(api_module.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = {"mime_type":"image/jpeg", "image_base64":jpeg(), "allow_generation":True}
        if legacy_flag is not None: body["contribute"] = legacy_flag
        response = await client.post("/api/vision-xray/scan", json=body,
                                     headers={"Authorization":"Bearer vision-test-alice"})
        assert response.status_code == 200, response.text
        first = response.json()
        assert first["shared"] is True and first["generation_used"] is True
        second = await client.get("/api/vision-xray/catalog/" + first["model_id"],
                                  headers={"Authorization":"Bearer vision-test-bob"})
        assert second.status_code == 200
        assert second.json()["version_id"] == first["version_id"]
        assert second.json()["cache_hit"] and not second.json()["generation_used"]
        available = await client.get("/api/vision-xray/available",
                                     headers={"Authorization":"Bearer vision-test-alice"})
        assert available.json()["catalog_policy"] == "automatic_generic_shared"
    assert calls == ["test_widget"]
    for collection in (MODELS, VERSIONS, JOBS):
        text = json.dumps(await database[collection].find({}).to_list(100), default=str)
        assert "image_base64" not in text and "private-metadata-never-persist" not in text


@pytest.mark.asyncio
async def test_uncertain_object_is_retried_with_central_crop(api_module, monkeypatch):
    seen = []
    async def mocked_ai(system, prompt, image=None):
        seen.append((system, image))
        if len(seen) == 1:
            return {"recognized": False, "confidence": "low"}
        return {"recognized": True, "confidence": "high",
                "canonical_key": "pedal_bin", "object_name": "Pattumiera con pedale",
                "bbox": [100, 200, 900, 800], "safe_to_generate": True}
    monkeypatch.setattr(api_module, "ask_json", mocked_ai)
    image = api_module.decode_photo("image/jpeg", jpeg())
    result = await api_module.recognize_with_recovery(image)
    assert result["canonical_key"] == "pedal_bin"
    assert result["recognition_method"] == "focused_second_pass"
    assert result["bbox"] == pytest.approx([.296, .22, .408, .56])
    assert len(seen) == 2
    assert seen[0][1] != seen[1][1]

@pytest.mark.asyncio
async def test_recovery_never_generates_from_unrecognized_image(api_module, monkeypatch):
    calls = []
    async def uncertain(system, prompt, image=None):
        calls.append(1)
        return {"recognized": False, "confidence": "low"}
    monkeypatch.setattr(api_module, "ask_json", uncertain)
    result = await api_module.recognize_with_recovery(api_module.decode_photo("image/jpeg", jpeg()))
    assert result is None and len(calls) == 2

@pytest.mark.asyncio
async def test_first_pass_success_does_not_use_extra_ai(api_module, monkeypatch):
    calls = []
    async def recognized(system, prompt, image=None):
        calls.append(1)
        return {"recognized": True, "confidence": "high", "canonical_key": "remote_control",
                "object_name": "Telecomando", "bbox": [100, 200, 900, 800],
                "safe_to_generate": True}
    monkeypatch.setattr(api_module, "ask_json", recognized)
    result = await api_module.recognize_with_recovery(api_module.decode_photo("image/jpeg", jpeg()))
    assert result["recognition_method"] == "primary" and len(calls) == 1
