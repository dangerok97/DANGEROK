"""Cutout worker contract tests using synthetic model output, no AI weights/download."""
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

PATH = Path(__file__).resolve().parents[1] / "backend/cutout_worker.py"
spec = importlib.util.spec_from_file_location("ora_private_cutout_test_worker", PATH)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

def _sample_jpeg():
    buf = io.BytesIO()
    Image.new("RGB",(400,350),(220,230,240)).save(buf,format="JPEG")
    return buf.getvalue()

def test_private_worker_contract_and_one_model_inference(monkeypatch):
    monkeypatch.setenv("ORA_CUTOUT_TOKEN","studio-private-synthetic-token-long-enough")
    calls = []
    class FakeModel:
        def get_inputs(self):
            return [SimpleNamespace(name="input")]
        def run(self, outputs, feed):
            calls.append(feed)
            y,x = np.ogrid[:320,:320]
            p = np.exp(-((y-160)**2/(90*90)+(x-160)**2/(75*75))*3).astype(np.float32)
            return [p[None,None,...]]
    monkeypatch.setattr(worker,"_load_session",lambda:FakeModel())
    with TestClient(worker.app) as client:
        raw=_sample_jpeg()
        assert client.post("/cutout",data=raw,headers={"content-type":"image/jpeg"}).status_code==401
        assert client.post("/cutout",data=raw,headers={
            "content-type":"image/jpeg","X-Ora-Cutout-Token":"wrong"
        }).status_code==401
        resp = client.post("/cutout",content=raw,headers={
            "content-type":"image/jpeg","X-Ora-Cutout-Token":"studio-private-synthetic-token-long-enough"
        })
        assert resp.status_code==200, resp.text
        assert resp.headers["content-type"]=="image/png"
        assert resp.headers["cache-control"]=="no-store"
        with Image.open(io.BytesIO(resp.content)) as img:
            assert img.format=="PNG" and img.mode=="RGBA" and img.size==(576,576)
            extrema=img.getchannel("A").getextrema()
            assert extrema[0] == 0 and extrema[1] > 200
        assert len(calls)==1
        assert calls[0]["input"].shape == (1,3,320,320)

def test_worker_rejects_large_or_non_jpeg(monkeypatch):
    monkeypatch.setenv("ORA_CUTOUT_TOKEN","studio-private-synthetic-token-long-enough")
    with TestClient(worker.app) as client:
        h={"X-Ora-Cutout-Token":"studio-private-synthetic-token-long-enough"}
        assert client.post("/cutout",content=b"x"*700_000,
                           headers={**h,"content-type":"image/jpeg"}).status_code==413
        assert client.post("/cutout",content=b"<svg/>",
                           headers={**h,"content-type":"image/svg+xml"}).status_code==415
