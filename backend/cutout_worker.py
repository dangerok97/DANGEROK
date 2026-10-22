"""Private, authenticated ORA apparel cutout worker (U2NetP ONNX, Apache-2.0).

Runs as a separate Railway service. No logging or storage of source images;
model weights are pinned and checked, no runtime internet dependency.
"""
import asyncio
import hashlib
import hmac
import io
import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

MODEL_SHA256 = "309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8"
MODEL_PATH = Path(os.environ.get("ORA_CUTOUT_MODEL_PATH", "/opt/ora-cutout/u2netp.onnx"))
MAX_INPUT = 675_000
MAX_PIXELS = 16_000_000
MAX_OUTPUT = 550_000
STUDIO_EDGE = 576
app = FastAPI(title="ORA private cutout", docs_url=None, redoc_url=None, openapi_url=None)
_session = None
_semaphore = asyncio.Semaphore(1)

def _load_session():
    global _session
    if _session is None:
        if hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest() != MODEL_SHA256:
            raise RuntimeError("Unverified segmentation model")
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.inter_op_num_threads = 1
        _session = ort.InferenceSession(str(MODEL_PATH), sess_options=opts,
                                       providers=["CPUExecutionProvider"])
    return _session

def _make_cutout(source: bytes) -> bytes:
    if not source or len(source) > MAX_INPUT:
        raise ValueError("image_size")
    try:
        with Image.open(io.BytesIO(source), formats=["JPEG"]) as opened:
            if opened.width * opened.height > MAX_PIXELS:
                raise ValueError("too_many_pixels")
            image = ImageOps.exif_transpose(opened).convert("RGB")
            image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("image_invalid") from exc

    model = _load_session()
    resized = image.resize((320,320), Image.Resampling.LANCZOS)
    rgb = np.asarray(resized, dtype=np.float32)
    rgb /= max(float(rgb.max()), 1e-6)
    mean = np.asarray([0.485,0.456,0.406], dtype=np.float32)
    std = np.asarray([0.229,0.224,0.225], dtype=np.float32)
    tensor = np.transpose((rgb-mean)/std, (2,0,1))[None,...].astype(np.float32)
    prediction = model.run(None, {model.get_inputs()[0].name:tensor})[0][0,0]
    lo, hi = float(prediction.min()), float(prediction.max())
    if hi-lo < 0.01:
        raise ValueError("uncertain_mask")
    alpha = Image.fromarray(np.uint8(np.clip((prediction-lo)/(hi-lo),0,1)*255), "L")
    alpha = alpha.resize(image.size, Image.Resampling.LANCZOS)
    a = np.asarray(alpha)
    foreground = a >= 100
    coverage = float(foreground.mean())
    if coverage < 0.04 or coverage > 0.91:
        raise ValueError("untrustworthy_mask")
    ys, xs = np.where(foreground)
    if (xs.min() < 3 and xs.max() > image.width-4 and
        ys.min() < 3 and ys.max() > image.height-4):
        raise ValueError("full_frame_background")

    transparent = image.convert("RGBA")
    transparent.putalpha(alpha)
    bbox = alpha.point(lambda v: 255 if v >= 28 else 0).getbbox()
    if not bbox:
        raise ValueError("empty_foreground")
    garment = transparent.crop(bbox)
    garment.thumbnail((int(STUDIO_EDGE*0.87), int(STUDIO_EDGE*0.87)),
                      Image.Resampling.LANCZOS)
    studio = Image.new("RGBA", (STUDIO_EDGE,STUDIO_EDGE), (255,255,255,0))
    studio.alpha_composite(garment, ((STUDIO_EDGE-garment.width)//2,
                                   (STUDIO_EDGE-garment.height)//2))
    out = io.BytesIO()
    studio.save(out, format="PNG", optimize=True)
    if out.tell() > MAX_OUTPUT:
        raise ValueError("output_too_large")
    return out.getvalue()

@app.get("/healthz")
async def health():
    return {"status":"ok", "private":True, "model":"u2netp"}

@app.post("/cutout")
async def cutout(request:Request, x_ora_cutout_token: str | None = Header(None)):
    secret = os.environ.get("ORA_CUTOUT_TOKEN","")
    if len(secret) < 32 or not x_ora_cutout_token or not hmac.compare_digest(
        secret, x_ora_cutout_token
    ):
        raise HTTPException(401, "Accesso vietato")
    if request.headers.get("content-type","").split(";")[0].lower() != "image/jpeg":
        raise HTTPException(415, "JPEG atteso")
    raw = bytearray()
    try:
        async for part in request.stream():
            if len(raw)+len(part) > MAX_INPUT:
                raise HTTPException(413, "Immagine troppo grande")
            raw.extend(part)
        try:
            await asyncio.wait_for(_semaphore.acquire(), timeout=3)
        except asyncio.TimeoutError:
            raise HTTPException(503, "Elaboratore occupato") from None
        try:
            # Hold the semaphore until the thread ends, including if HTTP times
            # out upstream; do not launch multiple unbounded ONNX inferences.
            try:
                processed = await run_in_threadpool(_make_cutout, bytes(raw))
            except ValueError:
                raise HTTPException(422, "Ritaglio non affidabile") from None
        finally:
            _semaphore.release()
        return Response(content=processed, media_type="image/png",
                        headers={"Cache-Control":"no-store"})
    finally:
        raw.clear()
