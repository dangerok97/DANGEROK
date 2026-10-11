"""One-shot deployed check. Real auth/API/AI; public photo as synthetic camera.
Does not create new shared models or touch any existing user's account/data.
"""
import base64
import io
import json
from pathlib import Path
import secrets
import time
import uuid
from urllib.parse import urlencode

import httpx
from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright, expect

API = "https://ora-backend-production-aa56.up.railway.app"
WEB = "https://ora-web-production-fb67.up.railway.app"
OUT = Path(".vision-hold-deployed")
OUT.mkdir(exist_ok=True)
REPORT = {"provider_mocked":False, "auth_mocked":False, "physical_phone_camera_tested":False,
          "camera_input":"Public-domain photograph in synthetic live video", "checks":[],
          "source":"https://commons.wikimedia.org/wiki/File:First_Generation_Remote_Control.JPG"}


def record(check, **values):
    REPORT["checks"].append({"check":check, **values})
    (OUT / "report.json").write_text(json.dumps(REPORT, ensure_ascii=False, indent=2))
    print(json.dumps({"check":check, **values}, ensure_ascii=False), flush=True)


def response_json(response):
    if response.status_code >= 400:
        raise RuntimeError("HTTP " + str(response.status_code) + " at " + response.url.path)
    return response.json()


def main():
    origin = "https://upload.wikimedia.org/wikipedia/commons/3/37/First_Generation_Remote_Control.JPG"
    with httpx.Client(timeout=50) as client:
        source = client.get("https://wsrv.nl/?" + urlencode({"url":origin, "w":960, "output":"jpg"}), follow_redirects=True)
        source.raise_for_status()
        with Image.open(io.BytesIO(source.content)) as image:
            clean = ImageOps.exif_transpose(image).convert("RGB"); clean.thumbnail((960,960))
            out = io.BytesIO(); clean.save(out,"JPEG",quality=80)
        encoded = base64.b64encode(out.getvalue()).decode()
        # One QA account, no credentials in artifacts or logs.
        credentials = {"email":"ora-vision-qa-" + uuid.uuid4().hex + "@example.com",
                       "password":secrets.token_urlsafe(32), "first_name":"Collaudo", "last_name":"Vision", "tutorial_seen":True}
        token = response_json(client.post(API + "/api/auth/register", json=credentials))["token"]
        headers = {"Authorization":"Bearer " + token}
        policy = response_json(client.get(API + "/api/vision-xray/available", headers=headers))
        assert policy.get("catalog_policy") == "automatic_generic_shared", "New backend policy not deployed"
        assert policy.get("exploration_mode") == "hold_after_acquisition"
        record("deployed_policy", catalog_policy=policy["catalog_policy"], exploration_mode=policy["exploration_mode"])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = browser.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True)
            context.add_init_script("localStorage.setItem('ora_auth_token'," + json.dumps(json.dumps(token)) + ");")
            context.add_init_script("""(() => {
const state={blank:false,openings:0,stream:null};window.__visionHoldQA=state;
const src='data:image/jpeg;base64,""" + encoded + """';
const getUserMedia=async()=>{
state.openings++;const image=new Image();image.src=src;await image.decode();
const c=document.createElement('canvas');c.width=800;c.height=Math.round(800*image.height/image.width);
const ctx=c.getContext('2d');let n=0;
const draw=()=>{if(state.blank){ctx.fillStyle='#867e74';ctx.fillRect(0,0,c.width,c.height);}else ctx.drawImage(image,0,0,c.width,c.height);ctx.fillStyle='#79bbc5';ctx.fillRect(5,c.height-9,++n%60,4);};
draw();setInterval(draw,40);state.stream=c.captureStream(24);return state.stream;
};Object.defineProperty(navigator,'mediaDevices',{configurable:true,get:()=>({getUserMedia})});
})();""")
            page = context.new_page()
            scans = []
            def request_seen(request):
                if request.url.endswith("/api/vision-xray/scan"):
                    body = request.post_data_json
                    scans.append({"has_contribute_flag":"contribute" in body})
            page.on("request", request_seen)
            try:
                page.goto(WEB + "/vision-xray", wait_until="domcontentloaded")
                expect(page.get_by_test_id("vision-open-camera")).to_be_visible(timeout=60000)
                expect(page.get_by_role("checkbox")).to_have_count(0)
                expect(page.get_by_test_id("vision-catalog-policy")).to_contain_text("automaticamente")
                page.get_by_test_id("vision-open-camera").click()
                canvas = page.get_by_test_id("vision-scene")
                expect(canvas).to_have_attribute("data-part-count","8",timeout=55000)
                expect(canvas).to_have_attribute("data-scene-state","held")
                page.get_by_test_id("vision-part-pcb").click()
                video = page.get_by_test_id("vision-camera-video")
                before = video.evaluate("v=>v.currentTime")
                page.evaluate("window.__visionHoldQA.blank=true")
                page.wait_for_timeout(17000)
                expect(canvas).to_have_attribute("data-part-count","8")
                expect(canvas).to_have_attribute("data-selected-part","pcb")
                expect(page.get_by_test_id("vision-status")).to_contain_text("Schema fissato")
                assert len(scans) == 1 and not scans[0]["has_contribute_flag"]
                after = video.evaluate("v=>({time:v.currentTime,paused:v.paused,tracks:v.srcObject.getTracks().map(t=>t.readyState)})")
                assert after["time"] > before + 10 and not after["paused"] and after["tracks"] == ["live"]
                page.get_by_test_id("vision-part-battery_a").click()
                expect(page.get_by_test_id("vision-part-detail")).to_contain_text("Prima pila")
                page.get_by_test_id("vision-toggle-explode").click()
                expect(page.get_by_test_id("vision-toggle-explode")).to_have_text("Scomponi")
                page.get_by_test_id("vision-toggle-explode").click()
                page.wait_for_timeout(600)
                close = page.get_by_test_id("vision-close-model")
                expect(close).to_be_visible()
                box = close.bounding_box()
                assert box["width"] >= 44 and box["height"] >= 44
                page.screenshot(path=str(OUT / "ORA_Vision_schema_fissato_X_mobile.png"),full_page=True)
                record("held_after_object_disappears", seconds_without_object=17, parts=8, scans_before_dismissal=len(scans),
                       selected_part="battery_a", camera_live=True, x_width=box["width"], x_height=box["height"])
                page.evaluate("window.__visionHoldQA.blank=false")
                close.click()
                deadline = time.monotonic() + 10
                while len(scans) < 2 and time.monotonic() < deadline:
                    page.wait_for_timeout(100)
                assert len(scans) == 2
                expect(canvas).to_have_attribute("data-part-count","8",timeout=55000)
                assert page.evaluate("window.__visionHoldQA.openings") == 1
                assert video.evaluate("v=>v.srcObject.getTracks()[0].readyState") == "live"
                record("x_restarts_scan", scans_after_x=len(scans), camera_openings=1, parts=8)
                page.get_by_test_id("vision-stop-camera").click()
                assert page.evaluate("window.__visionHoldQA.stream.getTracks().every(t=>t.readyState==='ended')")
                record("stop_camera", tracks_ended=True)
                REPORT["completed"] = True
                record("complete", success=True)
            except Exception:
                page.screenshot(path=str(OUT / "failure.png"),full_page=True)
                raise
            finally:
                browser.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        REPORT["completed"] = False
        record("failed", error_type=type(exc).__name__, message=str(exc)[:350])
        raise SystemExit(1)
