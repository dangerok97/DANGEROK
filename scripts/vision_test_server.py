"""CI ONLY: serves the real Expo export and real catalog with synthetic auth/vision.
Not imported by server.py or deployed as a service. No external provider calls.
"""
import asyncio
import io
from PIL import Image
import importlib.util
import os
from pathlib import Path
import sys
import types

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from motor.motor_asyncio import AsyncIOMotorClient
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
url = os.environ.get("VISION_TEST_MONGO_URL", "mongodb://127.0.0.1:27017")
if not url.startswith("mongodb://127.0.0.1:"):
    raise RuntimeError("Browser harness only accepts the local disposable CI Mongo")
client = AsyncIOMotorClient(url, tz_aware=True)
database = client.ora_vision_browser_test
USER = {"user_id":"vision-test-alice","email":"vision-test@example.invalid","name":"Vision QA",
        "provider":"password","identity_confirmed":True,"knowledge_tutorial_version":1}

async def current_user(authorization: str | None = Header(None)):
    if authorization != "Bearer vision-test-alice":
        raise HTTPException(401,"Not signed in to the test harness")
    return USER

fake = types.ModuleType("deps"); fake.db = database; fake.get_current_user = current_user
sys.modules["deps"] = fake
import vision_xray
from vision_catalog import CatalogService
vision_xray._service = CatalogService(database)
vision_xray.can_see = lambda: True

async def fixture_recognition(system, prompt, image=None):
    if image is None:
        raise RuntimeError("The browser suite does not exercise real generation")
    box = [146,406,854,578]
    with Image.open(io.BytesIO(image)) as frame:
        frame = frame.convert("RGB"); frame.thumbnail((160,160))
        # Magenta region marker belongs ONLY to this synthetic camera fixture.
        # Production recognition always goes to the real visual provider.
        r,g,b = frame.getpixel((frame.width//2,frame.height//2))
        if r > 180 and g < 95 and b > 75:
            region = "full_body" if b > 165 else "face" if b > 120 else "hand"
            await asyncio.sleep(.18)
            return {"recognized":True,"canonical_key":"human_anatomy",
                    "object_name":"Zona corporea simulata nel test",
                    "confidence":"high","bbox":[90,220,920,800],
                    "body_region":region,"safe_to_generate":False,"uncertainty":""}
        points = [(x,y) for y in range(frame.height) for x in range(frame.width)
                  if (lambda rgb: rgb[0]<85 and rgb[1]<110 and rgb[2]<125)(frame.getpixel((x,y)))]
        if points:
            x0=min(x for x,y in points); y0=min(y for x,y in points)
            x1=max(x for x,y in points)+1; y1=max(y for x,y in points)+1
            box=[y0/frame.height*1000,x0/frame.width*1000,y1/frame.height*1000,x1/frame.width*1000]
    await asyncio.sleep(1.1)
    return {"recognized":True,"canonical_key":"remote_control","object_name":"Telecomando (riconoscimento simulato nel test)",
            "confidence":"high","bbox":box,"safe_to_generate":True,"uncertainty":""}
vision_xray.ask_json = fixture_recognition

app = FastAPI()
app.include_router(vision_xray.router, prefix="/api")

@app.get("/api/auth/me")
async def me(user=Depends(current_user)): return user

@app.post("/api/auth/login")
async def login(): return {"token":"vision-test-alice","user":USER}

@app.get("/api/health")
async def health(): return {"ok":True,"test_harness":True}

@app.get("/api/{path:path}")
async def harmless_test_reads(path: str, user=Depends(current_user)):
    return {"ok":True,"completed":True,"status":"completed","user":user,"items":[],"preferences":{}}

@app.post("/api/{path:path}")
async def harmless_test_writes(path: str, user=Depends(current_user)):
    return {"ok":True}

DIST = (ROOT / "frontend" / "dist-vision").resolve()
@app.get("/{path:path}")
async def static(path: str):
    target = (DIST / path).resolve()
    if not target.is_relative_to(DIST): raise HTTPException(404)
    if target.is_file(): return FileResponse(target)
    if target.with_suffix(".html").is_file(): return FileResponse(target.with_suffix(".html"))
    if (target / "index.html").is_file(): return FileResponse(target / "index.html")
    return FileResponse(DIST / "index.html")

if __name__ == "__main__":
    uvicorn.run(app,host="127.0.0.1",port=8765)
