"""Explicit, one-shot production smoke; no user account/data or provider secrets.

Creates two isolated synthetic QA accounts through real registration. Tests the
real deployed API/auth/catalog/provider. Browser camera input is a public photo
played as a synthetic MediaStream, NOT evidence of a physical iPhone camera.
Only private generated schematics are permitted. Never writes a shared AI model.
Credentials live only in this process and are never included in artifacts.
"""
from __future__ import annotations
import base64
import io
import json
import os
from pathlib import Path
import secrets
import time
import uuid

import httpx
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright, expect

API = "https://ora-backend-production-aa56.up.railway.app"
WEB = "https://ora-web-production-fb67.up.railway.app"
OUT = Path(".vision-production-evidence")
OUT.mkdir(exist_ok=True)
REPORT = {"api":API, "web":WEB, "checks":[], "camera_source":"public photo in a synthetic video stream",
          "physical_phone_camera_tested":False, "provider_mocked":False, "auth_mocked":False}
SOURCES = [
    {"name":"remote", "url":"https://upload.wikimedia.org/wikipedia/commons/3/37/First_Generation_Remote_Control.JPG",
     "page":"https://commons.wikimedia.org/wiki/File:First_Generation_Remote_Control.JPG", "author":"Webwires", "license":"Public domain"},
    {"name":"stapler", "url":"https://upload.wikimedia.org/wikipedia/commons/1/14/Stapler_image.jpg",
     "page":"https://commons.wikimedia.org/wiki/File:Stapler_image.jpg", "author":"Janakiraman janaki", "license":"CC BY-SA 4.0"},
]
REPORT["photo_sources"] = SOURCES


def record(name, **values):
    row={"check":name, **values}; REPORT["checks"].append(row)
    print(json.dumps(row,ensure_ascii=False),flush=True)
    (OUT/"report.json").write_text(json.dumps(REPORT,ensure_ascii=False,indent=2))


def require(response):
    if response.status_code >= 400:
        # No request bodies, emails, auth headers or tokens in exceptions.
        raise RuntimeError(f"API failed: HTTP {response.status_code} at {response.url.path}")
    return response.json()


def picture(client, source):
    response=client.get(source["url"],follow_redirects=True,headers={"User-Agent":"ORA-Vision-QA/1.0 (one-shot image recognition verification)"})
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as image:
        clean=ImageOps.exif_transpose(image).convert("RGB");clean.thumbnail((960,960))
        output=io.BytesIO();clean.save(output,"JPEG",quality=80)
    data=output.getvalue()
    (OUT/(source["name"]+"-source.jpg")).write_bytes(data)
    return data


def register(client):
    credentials={"email":"ora-vision-qa-"+uuid.uuid4().hex+"@example.com",
                 "password":secrets.token_urlsafe(32),"first_name":"Collaudo","last_name":"Vision","tutorial_seen":True}
    auth=require(client.post(API+"/api/auth/register",json=credentials))
    return credentials, auth["token"]


def scan(client, token, photo, label, generate=False):
    started=time.monotonic()
    response=client.post(API+"/api/vision-xray/scan",headers={"Authorization":"Bearer "+token},json={
        "mime_type":"image/jpeg","image_base64":base64.b64encode(photo).decode(),
        "frame_id":"qa-"+label,"allow_generation":generate,"contribute":False,
    })
    value=require(response)
    record(label, http_status=response.status_code, elapsed_seconds=round(time.monotonic()-started,2),
           status=value.get("status"),cache_hit=value.get("cache_hit"),generation_used=value.get("generation_used"),
           family=(value.get("manifest") or {}).get("canonical_key"),
           version_id=value.get("version_id"),parts=len((value.get("manifest") or {}).get("parts",[])),
           reason=value.get("reason"))
    return value


def main():
    with httpx.Client(timeout=60) as client:
        # Wait for the explicitly authorized deployment in this same work session.
        # A finite check, not a persistent monitor.
        for _ in range(90):
            probe=client.get(API+"/api/vision-xray/catalog")
            if probe.status_code==401: break
            time.sleep(10)
        else: raise RuntimeError("New catalog route was not deployed within 15 minutes")
        record("protected_catalog",unauthenticated_status=probe.status_code)
        credentials,token=register(client)
        second_credentials,second_token=register(client)
        headers={"Authorization":"Bearer "+token}
        first=require(client.get(API+"/api/vision-xray/catalog",headers=headers))
        remote=next(x for x in first["models"] if x["canonical_key"]=="remote_control")
        model=require(client.get(API+"/api/vision-xray/catalog/"+remote["model_id"],headers=headers))
        assert len(model["manifest"]["parts"])==8 and model["cache_hit"]
        other=require(client.get(API+"/api/vision-xray/catalog/"+remote["model_id"],headers={"Authorization":"Bearer "+second_token}))
        assert other["version_id"]==model["version_id"]
        record("shared_seed_reused_between_accounts",catalog_count=len(first["models"]),version_id=model["version_id"],parts=8)
        remote_photo=picture(client,SOURCES[0])
        recognized=scan(client,token,remote_photo,"real_ai_remote",False)
        assert recognized.get("status")=="family" and recognized.get("cache_hit") and not recognized.get("generation_used"), "Real provider did not resolve remote to catalogue"
        assert recognized["manifest"]["canonical_key"]=="remote_control"

        # Actual deployed frontend + real token/API/recognizer; synthetic video input.
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=["--no-sandbox"])
            context=browser.new_context(viewport={"width":390,"height":844},is_mobile=True,has_touch=True)
            context.add_init_script("localStorage.setItem('ora_auth_token',"+json.dumps(json.dumps(token))+");")
            encoded=base64.b64encode(remote_photo).decode()
            context.add_init_script("""(() => {
const src='data:image/jpeg;base64,"""+encoded+"""';
Object.defineProperty(navigator.mediaDevices,'getUserMedia',{configurable:true,value:async()=>{
const image=new Image();image.src=src;await image.decode();
const c=document.createElement('canvas');c.width=800;c.height=Math.round(800*image.height/image.width);
const ctx=c.getContext('2d');let n=0;
const draw=()=>{ctx.drawImage(image,0,0,c.width,c.height);ctx.fillStyle='#6ebfba';ctx.fillRect(5,c.height-9,++n%60,4);};
draw();const timer=setInterval(draw,40);const stream=c.captureStream(24);
window.__visionQATrack=stream;return stream;
}});
})();""")
            page=context.new_page();page.goto(WEB+"/vision-xray",wait_until="domcontentloaded")
            expect(page.get_by_test_id("vision-open-camera")).to_be_visible(timeout=60000)
            page.get_by_test_id("vision-open-camera").click()
            expect(page.get_by_test_id("vision-scene")).to_have_attribute("data-part-count","8",timeout=65000)
            v=page.get_by_test_id("vision-camera-video")
            before=v.evaluate("v=>v.currentTime");page.wait_for_timeout(800)
            after=v.evaluate("v=>({time:v.currentTime,paused:v.paused,tracks:v.srcObject.getTracks().map(t=>t.readyState)})")
            assert after["time"]>before+.3 and not after["paused"] and after["tracks"]==["live"]
            page.get_by_test_id("vision-part-pcb").click()
            expect(page.get_by_test_id("vision-part-detail")).to_contain_text("Scheda elettronica")
            page.screenshot(path=str(OUT/"ora-vision-deployed-mobile.png"),full_page=True)
            record("deployed_browser_live_video",parts=8,selected="pcb",video_seconds_advanced=round(after["time"]-before,2),track_state="live")
            page.get_by_test_id("vision-stop-camera").click()
            assert page.evaluate("window.__visionQATrack.getTracks().every(t=>t.readyState==='ended')")
            record("deployed_browser_camera_stop",all_tracks_ended=True)
            page.set_viewport_size({"width":1440,"height":1000})
            page.get_by_test_id("vision-catalog-toggle").click();page.get_by_test_id("vision-catalog-remote_control").click()
            expect(page.get_by_test_id("vision-scene")).to_have_attribute("data-part-count","8")
            page.wait_for_timeout(700);page.screenshot(path=str(OUT/"ora-vision-deployed-desktop.png"),full_page=True)
            browser.close()

        # Unknown-object generation is checked privately, never added to the shared catalogue by QA.
        staple_photo=picture(client,SOURCES[1])
        created=scan(client,token,staple_photo,"real_ai_new_object",True)
        if created.get("status")=="family" and created.get("generation_used"):
            assert not created["shared"] and created["manifest"]["evidence_level"]=="illustrative"
            isolation=client.get(API+"/api/vision-xray/catalog/"+created["model_id"],headers={"Authorization":"Bearer "+second_token})
            assert isolation.status_code==404
            renewed=require(client.post(API+"/api/auth/login",json={"email":credentials["email"],"password":credentials["password"]}))["token"]
            again=scan(client,renewed,staple_photo,"real_ai_new_object_reused_in_new_session",True)
            assert again.get("cache_hit") and not again.get("generation_used") and again["version_id"]==created["version_id"]
            record("private_generated_reuse",same_version=True,other_account_status=404)
        else:
            record("new_object_generation_not_proven",status=created.get("status"),reason=created.get("reason"))
        REPORT["completed"]=True
        record("smoke_complete",success=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        REPORT["completed"]=False
        record("smoke_failed",error_type=type(exc).__name__,message=str(exc)[:350])
        raise SystemExit(1)
