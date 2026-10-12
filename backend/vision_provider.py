"""Bounded Vision transport. Route health is process-local, never image/user data.

A provider outage, empty/truncated JSON or schema error is NOT a failure to see
an object. Only a well-formed negative identification can say that.
"""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import time
import httpx

log = logging.getLogger("ora.vision.provider")
DETECTION_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "recognized": {"type": "BOOLEAN"},
        "canonical_key": {"type": "STRING"},
        "object_name": {"type": "STRING"},
        "confidence": {"type": "STRING", "enum": ["high", "medium", "low"]},
        "bbox": {"type": "ARRAY", "items": {"type": "NUMBER"}, "minItems": 4, "maxItems": 4},
        "safe_to_generate": {"type": "BOOLEAN"},
        "uncertainty": {"type": "STRING"},
    },
    "required": ["recognized", "canonical_key", "object_name", "confidence", "bbox", "safe_to_generate", "uncertainty"],
}
MESSAGES = {
    "provider_timeout": "Il servizio visivo non ha risposto in tempo. Non dipende dall'oggetto: riprova fra poco.",
    "provider_billing": "Il servizio visivo non è disponibile per un problema di credito o fatturazione del collegamento AI.",
    "provider_access": "Il collegamento al servizio visivo non è autorizzato o il modello non è disponibile.",
    "provider_busy": "Il servizio visivo è momentaneamente occupato. Riprova fra poco.",
    "provider_unavailable": "Il servizio visivo non è momentaneamente disponibile. La fotocamera resta aperta.",
    "invalid_model_response": "Il servizio visivo ha restituito una risposta incompleta. Riprova: non è un errore della tua inquadratura.",
}
class VisionProviderError(RuntimeError):
    def __init__(self, code="provider_unavailable"):
        self.code = code if code in MESSAGES else "provider_unavailable"
        super().__init__(MESSAGES[self.code])

class RouteHealth:
    """Small expiring map keyed by a one-way credential digest, never raw keys."""
    def __init__(self):
        self.blocked = {}
        self.preferred = None
        self.preferred_until = 0.0
    def pair(self, model, key):
        return model, hashlib.sha256(key.encode()).hexdigest()
    def ready(self, model, key):
        now = time.monotonic()
        pair = self.pair(model, key)
        return self.blocked.get(pair, (0, ""))[0] <= now and self.blocked.get(("*", pair[1]), (0, ""))[0] <= now
    def failure(self, model, key, code, seconds, whole_key=False):
        now = time.monotonic()
        self.blocked = {k:v for k,v in self.blocked.items() if v[0]>now}
        if len(self.blocked)>32: self.blocked.clear()
        pair = self.pair(model,key)
        self.blocked[("*",pair[1]) if whole_key else pair] = (now+seconds,code)
    def success(self, model, key):
        self.preferred = self.pair(model,key)
        self.preferred_until = time.monotonic()+600
    def sort(self, pairs):
        preferred = self.preferred if self.preferred_until>time.monotonic() else None
        return sorted(pairs,key=lambda p: self.pair(*p)!=preferred)
    def unavailable_code(self, pairs):
        codes = []
        for model,key in pairs:
            p=self.pair(model,key)
            codes.extend(self.blocked[k][1] for k in (p,("*",p[1])) if k in self.blocked)
        return "provider_billing" if codes and all(c=="provider_billing" for c in codes) else "provider_unavailable"

_health = RouteHealth()

def configured_routes():
    keys=list(dict.fromkeys(os.environ.get(k,"").strip() for k in ("GEMINI_API_KEY","GEMINI2_API_KEY") if os.environ.get(k,"").strip()))
    # Existing successful alias first; do not require a more expensive model.
    names=os.environ.get("ORA_VISION_MODELS","gemini-flash-lite-latest,gemini-2.5-flash").split(",")
    models=list(dict.fromkeys(m.strip() for m in names if re.fullmatch(r"[a-zA-Z0-9._-]+",m.strip())))[:2]
    return [(m,k) for m in models for k in keys[:2]]

def parse_response(data):
    candidates=data.get("candidates",[]) if isinstance(data,dict) else []
    if not candidates or not isinstance(candidates[0],dict): raise VisionProviderError("invalid_model_response")
    candidate=candidates[0]
    if candidate.get("finishReason") not in (None,"STOP"): raise VisionProviderError("invalid_model_response")
    content=candidate.get("content")
    if not isinstance(content,dict) or not isinstance(content.get("parts"),list):
        raise VisionProviderError("invalid_model_response")
    parts=content["parts"]
    text="".join(p.get("text","") for p in parts if isinstance(p,dict) and isinstance(p.get("text",""),str) and not p.get("thought"))
    try:
        value=json.loads(text)
    except (TypeError,ValueError): raise VisionProviderError("invalid_model_response") from None
    if not isinstance(value,dict): raise VisionProviderError("invalid_model_response")
    return value

async def ask_json(system: str, prompt: str, image: bytes | None=None):
    routes=configured_routes()
    if not routes: raise VisionProviderError("provider_access")
    content=[{"text":prompt}]
    if image is not None: content.append({"inline_data":{"mime_type":"image/jpeg","data":base64.b64encode(image).decode("ascii")}})
    generation={"temperature":0.1,"responseMimeType":"application/json","maxOutputTokens":6000}
    if image is not None: generation["responseSchema"]=DETECTION_SCHEMA
    payload={"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":content}],"generationConfig":generation}
    deadline=time.monotonic()+21
    failure=None
    async with httpx.AsyncClient(timeout=18) as client:
        for model,key in _health.sort(routes):
            if not _health.ready(model,key): continue
            remaining=deadline-time.monotonic()
            if remaining<=.1: raise VisionProviderError("provider_timeout")
            try:
                response=await asyncio.wait_for(client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/"+model+":generateContent",
                    headers={"x-goog-api-key":key},json=payload),timeout=remaining)
                status=response.status_code
                if status!=200:
                    code=("provider_billing" if status==402 else "provider_access" if status in (401,403,404) else "provider_busy" if status==429 else "provider_unavailable")
                    cooldown=600 if status in (401,402,403,404) else 30 if status==429 else 10
                    _health.failure(model,key,code,cooldown,whole_key=status in (401,402))
                    log.warning("vision_provider outcome=%s status=%s model=%s",code,status,model)
                    failure=VisionProviderError(code)
                    continue
                value=parse_response(response.json())
                _health.success(model,key)
                log.info("vision_provider outcome=ok model=%s",model)
                return value
            except (asyncio.TimeoutError,httpx.TimeoutException):
                _health.failure(model,key,"provider_timeout",10)
                failure=VisionProviderError("provider_timeout")
            except httpx.HTTPError:
                failure=VisionProviderError("provider_unavailable")
            except (ValueError,VisionProviderError):
                failure=VisionProviderError("invalid_model_response")
    raise failure or VisionProviderError(_health.unavailable_code(routes))
