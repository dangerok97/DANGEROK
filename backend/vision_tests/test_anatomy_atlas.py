"""Person recognition is a routed atlas, never a shared anatomical record."""
import httpx
import pytest
from fastapi import FastAPI
from test_catalog import api_module, database, jpeg
from vision_catalog import MODELS, JOBS


@pytest.mark.asyncio
async def test_person_detection_returns_generic_anatomy_without_generating_or_saving(api_module, monkeypatch, database):
    monkeypatch.setattr(api_module, "can_see", lambda: True)
    seen = []
    async def observe(*args, **kwargs):
        seen.append(1)
        return {"recognized": True, "canonical_key": "human_anatomy",
                "object_name": "Persona", "confidence": "high",
                "bbox": [100, 200, 900, 700], "safe_to_generate": False}
    monkeypatch.setattr(api_module, "ask_json", observe)
    async def no_generation(*args, **kwargs):
        raise AssertionError("A photographed person must never enter model generation")
    monkeypatch.setattr(api_module, "generate_family", no_generation)
    app = FastAPI()
    app.include_router(api_module.router, prefix="/api")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/vision-xray/scan",
            json={"mime_type": "image/jpeg", "image_base64": jpeg(), "allow_generation": True},
            headers={"Authorization": "Bearer vision-test-alice"})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "anatomy"
        assert data["identification"]["canonical_key"] == "human_anatomy"
        assert "gender" not in str(data).lower()
        assert "sex" not in str(data).lower()
        assert "manifest" not in data
    assert seen
    assert await database[JOBS].count_documents({}) == 0
    assert await database[MODELS].count_documents({"canonical_key":"human_anatomy"}) == 0
