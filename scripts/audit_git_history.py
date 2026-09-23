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
    ("env_file", re.compile(r"(^|/)\.env($|\.)", re.I)),
    ("credential_json", re.compile(r"(^|/)(?:credentials|token)\.json$", re.I)),
    ("secret_directory", re.compile(r"(^|/)(?:secrets|oauth-keys)/", re.I)),
    ("key_file", re.compile(r"\.(?:p8|p12|key)$", re.I)),
    ("pem_file", re.compile(r"\.pem$", re.I)),
)
DOCUMENT_STORAGE = re.compile(r"(^|/)backend/data/documents(?:/|$)", re.I)

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

    for line in raw.splitlines():
        sha, sep, path = line.partition(" ")
        if not sep:
            continue
        sha_paths[sha].add(path)

    path_findings: set[tuple[str, str, str]] = set()
    document_blob_shas: set[str] = set()

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

        # Paths are evaluated only for actual file blobs. Directory/tree
        # objects made the first version report the same storage hierarchy
        # hundreds of times and leaked opaque user-scoped path fragments.
        for path in paths:
            if DOCUMENT_STORAGE.search(path):
                document_blob_shas.add(sha)
                continue
            for kind, rx in SENSITIVE_PATHS:
                if not rx.search(path):
                    continue
                if path.endswith(".env.example"):
                    continue
                path_findings.add((kind, path, sha[:12]))

        if size > MAX_BLOB_BYTES or b"\x00" in data[:8192]:
            continue

        lowered = data.lower()
        for kind, rx in CONTENT_PATTERNS.items():
            if not rx.search(data):
                continue
            # Historical telephone tests intentionally used a PEM-shaped
            # not-a-real-key fixture. It is demonstrably synthetic (commit
            # c0cd44b); do not turn a known fixture into a security incident.
            if kind == "private_key_pem" and b"not-a-real-key" in lowered:
                continue
            if kind == "openai_style_key" and any(m in lowered for m in PLACEHOLDER_MARKERS):
                continue
            shown = sorted(paths)[:3] or ["<unknown-path>"]
            for path in shown:
                content_findings.add((kind, path, sha[:12]))

    proc.stdin.close()
    proc.wait(timeout=10)

    findings = sorted(path_findings | content_findings)
    total = len(findings) + (1 if document_blob_shas else 0)
    if total:
        print(
            "FULL_HISTORY_SECRET_AUDIT=FAIL "
            f"categories={total} historical_document_blobs={len(document_blob_shas)}"
        )
        if document_blob_shas:
            print(
                "- historical_document_storage: backend/data/documents "
                f"contains {len(document_blob_shas)} unique historical file blobs "
                "(paths and contents intentionally hidden)"
            )
        for kind, path, sha12 in findings[:50]:
            print(f"- {kind}: {path} @ {sha12}")
        if len(findings) > 50:
            print(f"- additional_non_document_findings: {len(findings) - 50}")
        print("Matched values and document paths are intentionally never printed.")
        return 1

    print(
        "FULL_HISTORY_SECRET_AUDIT=PASS "
        f"historical_objects={len(sha_paths)} "
        "historical_document_blobs=0 high_confidence_secret_patterns=0 sensitive_paths=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
