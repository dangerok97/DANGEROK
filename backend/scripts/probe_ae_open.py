"""Probe Action Engine open against local :8000."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"


def post(path, body, token=None):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    email = f"probe_{int(time.time())}@example.com"
    st, reg = post("/api/auth/register", {"email": email, "password": "TestPass123!", "name": "Probe"})
    print("register", st, reg if isinstance(reg, dict) else str(reg)[:400])
    token = reg.get("token") if isinstance(reg, dict) else None
    assert token, "no token"

    st2, dec = post(
        "/api/decisions",
        {
            "title": "Esame Probe",
            "category": "study",
            "urgency": 8,
            "importance": 9,
            "deadline": "2026-08-20T00:00:00+00:00",
        },
        token,
    )
    print("decision", st2, dec if isinstance(dec, dict) else str(dec)[:200])

    req = urllib.request.Request(API + "/api/home", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        home = json.loads(r.read().decode())
    focus = home.get("primary_focus") or {}
    print("focus", focus.get("title"), focus.get("type"), focus.get("source_type"))
    print(
        "actions",
        [(a.get("id"), a.get("kind"), a.get("label")) for a in focus.get("actions") or []],
    )

    st3, opened = post("/api/action-engine/open", {"home_item": focus, "force_new": True}, token)
    print("open", st3)
    print(opened if isinstance(opened, dict) else str(opened)[:800])

    try:
        with urllib.request.urlopen(urllib.request.Request(API + "/openapi.json"), timeout=10) as r:
            paths = list(json.loads(r.read().decode()).get("paths", {}).keys())
            print("ae_paths", [p for p in paths if "action" in p][:30])
    except Exception as e:
        print("openapi err", e)


if __name__ == "__main__":
    main()
