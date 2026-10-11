"""One-shot QA transport fallback for PUBLIC test photographs only.
Never send private camera images through a public image cache.
Source attribution remains the original Wikimedia Commons file and author.
"""
import io
import urllib.parse
import httpx
from PIL import Image, ImageOps
import vision_production_smoke as smoke


def public_picture(client, source):
    origin = source["url"]
    urls = [origin,
            "https://wsrv.nl/?" + urllib.parse.urlencode({"url": origin, "w": 960, "output": "jpg"}),
            "https://images.weserv.nl/?" + urllib.parse.urlencode({"url": origin, "w": 960, "output": "jpg"})]
    for url in urls:
        try:
            response = client.get(url, follow_redirects=True, timeout=25,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ORA-Public-Image-QA/1.0)"})
            if response.status_code != 200:
                smoke.record("public_photo_transport", photo_name=source["name"], host=urllib.parse.urlparse(url).hostname, status=response.status_code)
                continue
            with Image.open(io.BytesIO(response.content)) as image:
                clean = ImageOps.exif_transpose(image).convert("RGB")
                clean.thumbnail((960,960))
                out = io.BytesIO(); clean.save(out,"JPEG",quality=80)
            data = out.getvalue()
            (smoke.OUT/(source["name"]+"-source.jpg")).write_bytes(data)
            smoke.record("public_photo_loaded", photo_name=source["name"], host=urllib.parse.urlparse(url).hostname,
                         width=clean.width, height=clean.height, original_source=source["page"])
            return data
        except (httpx.HTTPError, OSError, ValueError):
            continue
    raise RuntimeError("Public test photo unavailable from the source and public cache")

smoke.picture = public_picture
if __name__ == "__main__":
    try:
        smoke.main()
    except Exception as exc:
        smoke.REPORT["completed"] = False
        smoke.record("smoke_failed", error_type=type(exc).__name__, message=str(exc)[:350])
        raise SystemExit(1)
