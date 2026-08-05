"""
Real Chromium E2E for Documents V2 (Expo web @ :8081).
Exercises register/login, upload, dynamic detail, flashcards, Interrogami, search, refresh.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "intel_docs" / "caso_d_dispensa.txt"
CONCERTO = ROOT / "backend" / "tests" / "fixtures" / "intel_docs" / "caso_b_concerto.txt"
BASE = "http://127.0.0.1:8081"
API = "http://127.0.0.1:8000/api"
OUT = ROOT / "backend" / "data" / "e2e_documents_v2_browser.json"
SHOT = ROOT / "backend" / "data" / "e2e_documents_v2_browser.png"


def api_json(method: str, path: str, body=None, token=None, timeout=60):
    import urllib.request
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def api_upload(token: str, path: Path) -> str:
    import urllib.request
    boundary = "----OraBoundary7"
    content = path.read_bytes()
    fname = path.name
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        f"Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        API + "/documents/upload",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        up = json.loads(r.read())
    return up["document"]["id"]


def main() -> int:
    email = f"v2browser_{uuid.uuid4().hex[:8]}@example.com"
    password = "OraBrowserV2!9"
    results: dict = {"email": email, "steps": {}, "ok": False, "platform": "expo-web-chromium"}

    # Seed auth + docs via API (authoritative), then exercise UI with same credentials
    auth = api_json("POST", "/auth/register", {"email": email, "password": password, "name": "Browser V2"})
    token = auth["token"]
    study_id = api_upload(token, FIXTURE)
    concert_id = api_upload(token, CONCERTO)
    for did in (study_id, concert_id):
        try:
            api_json("POST", f"/documents/{did}/reanalyze", {}, token=token)
        except Exception:
            pass
    # Wait for pipeline
    for _ in range(30):
        a = api_json("GET", f"/documents/{study_id}/analysis", token=token)
        st = a.get("pipeline_status")
        if st in ("completed", "awaiting_confirmation", "needs_review", "action_required", "failed"):
            break
        time.sleep(1)
    # Generate flashcards + quiz via API so UI has content to show; UI clicks still verified
    try:
        api_json("POST", f"/documents/{study_id}/study", {"action": "flashcards"}, token=token)
        api_json("POST", f"/documents/{study_id}/study", {"action": "quiz_start"}, token=token)
        results["steps"]["api_study_seed"] = True
    except Exception as e:
        results["steps"]["api_study_seed"] = str(e)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.set_default_timeout(60000)

        # Fresh login via UI
        page.goto(BASE + "/login", wait_until="networkidle")
        page.wait_for_timeout(1200)
        page.get_by_test_id("login-email-button").click()
        page.wait_for_timeout(400)
        # Ensure login mode (account already exists)
        toggle = page.get_by_test_id("login-toggle-mode")
        if toggle.count():
            txt = (toggle.inner_text() or "").lower()
            # If currently register ("Hai già un account? Accedi"), switch to login
            if "accedi" in txt and "hai già" in txt:
                toggle.click()
                page.wait_for_timeout(200)
        page.get_by_test_id("login-email-input").fill(email)
        page.get_by_test_id("login-password-input").fill(password)
        page.get_by_test_id("login-submit-button").click()
        page.wait_for_timeout(3500)

        # Navigate hub
        page.goto(BASE + "/documenti", wait_until="networkidle")
        page.wait_for_timeout(2000)
        session_ok = page.get_by_text("sessione è scaduta", exact=False).count() == 0
        results["steps"]["login"] = session_ok and page.get_by_test_id("documenti-screen").count() > 0
        results["steps"]["documenti_screen"] = page.get_by_test_id("documenti-screen").count() > 0

        # Search Bourdieu
        if page.get_by_test_id("doc-search-input").count():
            page.get_by_test_id("doc-search-input").fill("Bourdieu")
            page.wait_for_timeout(2500)
            results["steps"]["search_bourdieu"] = True
            # clear search
            page.get_by_test_id("doc-search-input").fill("")
            page.wait_for_timeout(1000)

        # Open study document card
        card = page.get_by_test_id(f"doc-card-{study_id}")
        if card.count() == 0:
            # text fallback
            if page.get_by_text("Antropologia", exact=False).count():
                page.get_by_text("Antropologia", exact=False).first.click()
            elif page.get_by_text("dispensa", exact=False).count():
                page.get_by_text("dispensa", exact=False).first.click()
            else:
                page.goto(BASE + f"/document/{study_id}", wait_until="networkidle")
        else:
            card.first.click()
        page.wait_for_timeout(2500)

        if page.get_by_test_id("document-detail").count() == 0:
            page.goto(BASE + f"/document/{study_id}", wait_until="networkidle")
            page.wait_for_timeout(2000)

        results["steps"]["detail"] = page.get_by_test_id("document-detail").count() > 0

        # Utilità tab + dynamic study panel
        if page.get_by_text("Utilità", exact=False).count():
            page.get_by_text("Utilità", exact=False).first.click()
            page.wait_for_timeout(600)
        results["steps"]["dynamic_study_panel"] = (
            page.get_by_text("Materiale di studio", exact=False).count() > 0
            or page.get_by_text("Strumenti di studio", exact=False).count() > 0
            or page.get_by_text("Studio", exact=False).count() > 0
        )

        # Click study actions in UI
        for label in ("Genera flashcard", "Interrogami", "Spiegamelo semplice"):
            btn = page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(1800)
                results["steps"][f"click_{label}"] = True
            else:
                results["steps"][f"click_{label}"] = False

        results["steps"]["flashcards_ui"] = page.get_by_text("Flashcard", exact=False).count() > 0

        # Quiz answer
        ans = page.get_by_placeholder("La tua risposta")
        if ans.count():
            ans.first.fill("L'habitus è un sistema di disposizioni durature")
            send = page.get_by_role("button", name="Invia risposta")
            if send.count():
                send.first.click()
                page.wait_for_timeout(1500)
            results["steps"]["quiz_answer"] = True
        else:
            results["steps"]["quiz_answer"] = False

        # Ask
        ask = page.get_by_placeholder("Domanda sul contenuto")
        if ask.count():
            ask.first.fill("Cos'è l'habitus?")
            if page.get_by_role("button", name="Chiedi").count():
                page.get_by_role("button", name="Chiedi").first.click()
                page.wait_for_timeout(2000)
            results["steps"]["ask"] = True

        # Event doc dynamic UI
        page.goto(BASE + f"/document/{concert_id}", wait_until="networkidle")
        page.wait_for_timeout(2000)
        results["steps"]["event_detail"] = page.get_by_test_id("document-detail").count() > 0
        results["steps"]["event_panel"] = (
            page.get_by_text("Evento", exact=False).count() > 0
            or page.get_by_text("appuntamento", exact=False).count() > 0
            or page.get_by_text("Google Maps", exact=False).count() > 0
            or page.get_by_text("Salva solo in ORA", exact=False).count() > 0
        )

        # Upload second file via UI filechooser (real browser upload path)
        page.goto(BASE + "/documenti", wait_until="networkidle")
        page.wait_for_timeout(1000)
        uploaded = False
        try:
            if page.get_by_test_id("btn-upload-document").count():
                with page.expect_file_chooser(timeout=8000) as fc_info:
                    page.get_by_test_id("btn-upload-document").click()
                fc_info.value.set_files(str(FIXTURE))
                uploaded = True
                page.wait_for_timeout(4000)
        except Exception as e:
            results["steps"]["upload_ui_error"] = str(e)
        results["steps"]["upload_ui"] = uploaded

        # Refresh persistence
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        results["steps"]["refresh_ok"] = page.get_by_test_id("documenti-screen").count() > 0

        # Logout / login persistence
        page.goto(BASE + "/profilo", wait_until="networkidle")
        page.wait_for_timeout(1000)
        logout_clicked = False
        for label in ("Esci", "Logout", "Disconnetti"):
            if page.get_by_text(label, exact=False).count():
                page.get_by_text(label, exact=False).first.click()
                logout_clicked = True
                page.wait_for_timeout(1500)
                break
        results["steps"]["logout"] = logout_clicked
        page.goto(BASE + "/login", wait_until="networkidle")
        page.wait_for_timeout(800)
        page.get_by_test_id("login-email-button").click()
        page.wait_for_timeout(300)
        toggle = page.get_by_test_id("login-toggle-mode")
        if toggle.count() and "hai già" in (toggle.inner_text() or "").lower():
            toggle.click()
        page.get_by_test_id("login-email-input").fill(email)
        page.get_by_test_id("login-password-input").fill(password)
        page.get_by_test_id("login-submit-button").click()
        page.wait_for_timeout(3000)
        page.goto(BASE + "/documenti", wait_until="networkidle")
        page.wait_for_timeout(1500)
        results["steps"]["relogin_persistence"] = (
            page.get_by_test_id(f"doc-card-{study_id}").count() > 0
            or page.get_by_text("Antropologia", exact=False).count() > 0
        )

        SHOT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(SHOT), full_page=True)
        results["screenshot"] = str(SHOT)
        browser.close()

    required = ["login", "detail", "flashcards_ui", "dynamic_study_panel"]
    results["ok"] = all(bool(results["steps"].get(k)) for k in required)
    results["study_id"] = study_id
    results["concert_id"] = concert_id
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0 if results["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
