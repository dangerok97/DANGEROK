"""
Two more Google capabilities, configured — and kept out of the repository.

Places (New) resolves an address somebody typed. Maps JavaScript draws a map
in a browser. They are not the same kind of secret and are not treated as one:

- The Places key opens a large surface and stays server-side. It must never
  reach a bundle, a tracked file or a log.
- The Maps key is a browser key by definition — it ships in the page and
  anybody can read it. Its safety is the restriction set on it in Google
  Cloud, not secrecy. What still must not happen is it living in the repo.

Nothing in this file contains a key, and one of the tests exists to make sure
nothing anywhere else does either.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import _loop_harness  # tests/_loop_harness.py: the one place a loop is chosen

HERE = Path(_BACKEND)
FRONTEND = HERE.parent / "frontend"
REPO = HERE.parent

# What a Google API key looks like, not any particular one.
GOOGLE_KEY = re.compile(r"AIzaSy[0-9A-Za-z_\-]{25,}")


def _run(coro):
    return _loop_harness.run(coro)


# ---------------------------------------------------------------------------
# Configuration, read from the environment and nowhere else
# ---------------------------------------------------------------------------

def test_places_reports_whether_it_is_configured_rather_than_guessing():
    from places import lookup

    caps = lookup.capabilities()
    assert set(caps) == {"places_available", "places_provider", "why_unavailable"}

    if caps["places_available"]:
        assert caps["places_provider"] == "google_places_new"
        assert caps["why_unavailable"] is None
    else:
        assert caps["places_provider"] is None
        assert "PLACES_API_KEY" in caps["why_unavailable"]


def test_the_places_key_is_read_from_the_environment_only():
    source = (HERE / "places" / "lookup.py").read_text(encoding="utf-8")
    assert 'KEY_ENV = "PLACES_API_KEY"' in source
    assert "os.environ.get(KEY_ENV)" in source
    assert not GOOGLE_KEY.search(source), "una chiave è finita nel sorgente"


def test_without_a_key_places_says_so_instead_of_returning_no_results(monkeypatch):
    """
    An empty list would tell somebody their address does not exist. The truth
    is that nobody asked.
    """
    from places import lookup

    monkeypatch.setenv("PLACES_API_KEY", "")

    async def ask():
        return await lookup.suggest("Via Roma 1, Padova")

    result = _run(ask())
    assert result["available"] is False
    assert "suggestions" not in result
    assert "PLACES_API_KEY" in result["why_unavailable"]


def test_a_query_too_short_to_mean_anything_is_not_a_billed_request(monkeypatch):
    from places import lookup

    monkeypatch.setenv("PLACES_API_KEY", "not-a-real-key-and-never-sent")

    async def ask():
        return await lookup.suggest("Vi")

    result = _run(ask())
    assert result["too_short"] is True
    assert result["suggestions"] == []


# ---------------------------------------------------------------------------
# The two keys are different kinds of thing
# ---------------------------------------------------------------------------

def test_the_maps_key_is_the_only_one_the_browser_ever_sees():
    config = (FRONTEND / "src" / "config" / "maps.ts").read_text(encoding="utf-8")

    assert "EXPO_PUBLIC_MAPS_WEB_KEY" in config
    assert not GOOGLE_KEY.search(config), "una chiave è finita nel sorgente"

    # The server-side keys must not be reachable from a bundle at all.
    for server_only in ("PLACES_API_KEY", "ROUTING_API_KEY"):
        assert server_only not in config, f"{server_only} è esposta al browser"

    for relative in ("src", "app"):
        for path in (FRONTEND / relative).rglob("*.ts*"):
            if "node_modules" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert "PLACES_API_KEY" not in text, f"{path.name} nomina la chiave server-side"


def test_no_map_is_offered_when_there_is_no_key_to_draw_it_with():
    config = (FRONTEND / "src" / "config" / "maps.ts").read_text(encoding="utf-8")
    # A script tag with an empty key leaves a grey box and a console error;
    # a caller told "unavailable" can say something useful instead.
    assert "if (!apiKey) return null;" in config
    assert "available: false" in config


# ---------------------------------------------------------------------------
# Nothing reached the repository
# ---------------------------------------------------------------------------

def test_no_google_key_is_tracked_anywhere_in_the_repository():
    """
    Asks git, not the filesystem: what matters is what would be pushed.
    """
    listed = subprocess.run(
        ["git", "grep", "-lI", "-E", r"AIzaSy[0-9A-Za-z_\-]{25,}", "--", "."],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    offenders = [line for line in listed.stdout.splitlines() if line.strip()]
    assert not offenders, f"chiavi in file tracciati: {offenders}"


def test_no_google_key_is_waiting_in_the_working_tree_either():
    """
    Tracked-and-modified plus untracked-not-ignored: everything a careless
    `git add -A` would sweep up.
    """
    listed = subprocess.run(
        ["git", "ls-files", "-mo", "--exclude-standard"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    offenders = []
    for name in listed.stdout.splitlines():
        if not name.strip() or "node_modules" in name or "__pycache__" in name:
            continue
        path = REPO / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if GOOGLE_KEY.search(text):
            offenders.append(name)
    assert not offenders, f"chiavi in file committabili: {offenders}"


def test_the_env_files_that_hold_keys_are_ignored_by_git():
    for relative in (".env", "backend/.env", "frontend/.env"):
        path = REPO / relative
        if not path.exists():
            continue
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", relative],
            cwd=str(REPO),
            capture_output=True,
        )
        assert ignored.returncode == 0, f"{relative} NON è ignorato da git"


def test_documentation_names_the_variables_and_never_their_values():
    for doc in (REPO / "docs").glob("*.md"):
        text = doc.read_text(encoding="utf-8", errors="ignore")
        assert not GOOGLE_KEY.search(text), f"{doc.name} contiene una chiave"
