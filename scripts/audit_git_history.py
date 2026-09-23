#!/usr/bin/env python3
"""Read-only full-history secret audit.

The repository is public, so checking only HEAD is not enough: a deleted
credential is still downloadable from an old commit. This scanner walks every
reachable historical blob but never prints matched values. Output is limited
to finding kind, historical path and object SHA.

No network, no repository secrets and no third-party dependency are used.
"""
from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import PurePosixPath

MAX_BLOB_BYTES = 2_000_000

SENSITIVE_PATHS = (
    re.compile(r"(^|/)\.env($|\.)", re.I),
    re.compile(r"(^|/)(?:credentials|token)\.json$", re.I),
    re.compile(r"(^|/)backend/data/", re.I),
    re.compile(r"(^|/)(?:secrets|oauth-keys)/", re.I),
    re.compile(r"\.(?:p8|p12|key)$", re.I),
    re.compile(r"\.pem$", re.I),
)

# Deliberately high-confidence signatures only. Generic words such as
# "API_KEY" appear legitimately in source and documentation.
CONTENT_PATTERNS = {
    "private_key_pem": re.compile(
        rb"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"
    ),
    "google_api_key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "openai_style_key": re.compile(rb"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "github_token": re.compile(
        rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"
    ),
    "mongodb_uri_with_password": re.compile(
        rb"mongodb(?:\+srv)?://[^\s:/]+:[^\s@/]+@"
    ),
}

# Example/documentation placeholders are not credentials. We only use this
# to suppress the common fake OpenAI-style strings, never PEM or URI hits.
PLACEHOLDER_MARKERS = (
    b"example",
    b"placeholder",
    b"changeme",
    b"not-for-prod",
    b"dummy",
    b"xxxxxxxx",
)


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def main() -> int:
    raw = git("rev-list", "--objects", "--all").decode("utf-8", "replace")
    sha_paths: dict[str, set[str]] = collections.defaultdict(set)
    path_findings: set[tuple[str, str, str]] = set()

    for line in raw.splitlines():
        sha, sep, path = line.partition(" ")
        if not sep:
            continue
        sha_paths[sha].add(path)
        for rx in SENSITIVE_PATHS:
            if rx.search(path):
                # .env.example is intentionally tracked.
                if path.endswith(".env.example"):
                    continue
                path_findings.add(("sensitive_historical_path", path, sha[:12]))

    proc = subprocess.Popen(
        ["git", "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert proc.stdin is not None and proc.stdout is not None

    content_findings: set[tuple[str, str, str]] = set()
    for sha, paths in sha_paths.items():
        proc.stdin.write((sha + "\n").encode())
        proc.stdin.flush()
        header = proc.stdout.readline().decode("ascii", "replace").strip()
        parts = header.split()
        if len(parts) < 3:
            continue
        size = int(parts[2])
        # --batch emits a body for every object type. Always consume it before
        # deciding whether to scan it, otherwise the next header read starts
        # in the middle of a tree/commit body and the stream loses alignment.
        data = proc.stdout.read(size)
        proc.stdout.read(1)  # batch record terminator
        if parts[1] != "blob":
            continue
        if size > MAX_BLOB_BYTES or b"\x00" in data[:8192]:
            continue

        lowered = data.lower()
        for kind, rx in CONTENT_PATTERNS.items():
            if not rx.search(data):
                continue
            if kind == "openai_style_key" and any(m in lowered for m in PLACEHOLDER_MARKERS):
                continue
            shown = sorted(paths)[:3] or ["<unknown-path>"]
            for path in shown:
                content_findings.add((kind, path, sha[:12]))

    proc.stdin.close()
    proc.wait(timeout=10)

    findings = sorted(path_findings | content_findings)
    if findings:
        print(f"FULL_HISTORY_SECRET_AUDIT=FAIL findings={len(findings)}")
        for kind, path, sha12 in findings:
            print(f"- {kind}: {path} @ {sha12}")
        print("Matched values are intentionally never printed.")
        return 1

    print(
        "FULL_HISTORY_SECRET_AUDIT=PASS "
        f"historical_objects={len(sha_paths)} "
        "high_confidence_secret_patterns=0 sensitive_paths=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
