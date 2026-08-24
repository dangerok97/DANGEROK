"""ORA contextual visuals — style lock, privacy boundary, stable identity.

The image generation *call* is not exercised here: what matters, and what can
regress silently, is everything around it — that the style never varies, that
no identifier ever reaches a provider, that the same card asks for the same
image forever, and that no domain routing creeps into the subject.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from visuals import (
    ORA_CONTEXTUAL_VISUAL_STYLE_V1,
    VISUAL_STYLE_VERSION,
    VisualDescriptor,
    build_descriptor,
    sanitize_subject,
    visual_key,
)

STYLE_SRC = Path(__file__).resolve().parents[1] / "visuals" / "style.py"


def test_no_identifier_survives_sanitisation():
    cases = [
        ("scrivi a mario.rossi@gmail.com", "mario.rossi@gmail.com"),
        ("chiama il +39 333 1234567", "1234567"),
        ("IBAN IT60X0542811101000000123456", "IT60X0542811101000000123456"),
        ("codice fiscale RSSMRA85M01H501Z", "RSSMRA85M01H501Z"),
        ("bolletta da €1.250,00", "1.250"),
        ("Via Giuseppe Garibaldi 42", "Garibaldi"),
        ("cena con Marco Bianchi", "Marco Bianchi"),
        ("vedi https://drive.google.com/file/d/abc", "drive.google.com"),
        ("pratica numero 998877665", "998877665"),
    ]
    for raw, secret in cases:
        out = sanitize_subject(raw)
        assert secret.lower() not in out.lower(), f"{secret!r} survived in {out!r}"


def test_prompt_always_carries_the_style_and_never_an_identifier():
    d = build_descriptor(
        title="Cena con Marco Bianchi",
        summary="via Roma 12, spesa €80, conferma a marco@example.com",
    )
    prompt = d.prompt()
    assert ORA_CONTEXTUAL_VISUAL_STYLE_V1 in prompt
    for secret in ("Marco Bianchi", "via Roma", "marco@example.com", "80"):
        assert secret not in prompt


def test_visual_key_is_stable_and_semantic():
    a = build_descriptor(title="Organizzare una piccola mostra", summary="definire luogo")
    again = build_descriptor(title="Organizzare una piccola mostra", summary="definire luogo")
    assert visual_key(entity_ref="s:1", descriptor=a) == visual_key(entity_ref="s:1", descriptor=again)
    # Scoped to the entity, so two cards never share one picture by accident.
    assert visual_key(entity_ref="s:1", descriptor=a) != visual_key(entity_ref="s:2", descriptor=a)
    # A materially different card earns a new image.
    changed = build_descriptor(title="Organizzare una grande retrospettiva", summary="definire luogo")
    assert visual_key(entity_ref="s:1", descriptor=a) != visual_key(entity_ref="s:1", descriptor=changed)
    # A new style version regenerates rather than mixing two looks on screen.
    bumped = VisualDescriptor(subject=a.subject, style_version="ora_style_v2")
    assert visual_key(entity_ref="s:1", descriptor=a) != visual_key(entity_ref="s:1", descriptor=bumped)


def test_key_never_depends_on_the_clock():
    src = STYLE_SRC.read_text(encoding="utf-8")
    fn = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "visual_key"
    )
    body = ast.unparse(fn)
    for forbidden in ("now(", "time(", "utcnow", "uuid", "random"):
        assert forbidden not in body, f"visual_key must be deterministic; found {forbidden}"


def test_no_domain_routing_in_subject_logic():
    src = STYLE_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)

    # The style constant is a photographic description ("studio lighting",
    # "botanical") and must not be mistaken for a domain branch.
    code = re.sub(r'"""[\s\S]*?"""', "", src)
    code = re.sub(r"^\s*#.*$", "", code, flags=re.M)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                code = code.replace(node.value.value, " ")

    for term in ("viaggio", "travel", "casa", "house", "mostra", "esame", "suitcase", "keys"):
        assert term.lower() not in code.lower(), f"domain routing leaked: {term}"

    for fn in (n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name in ("build_descriptor", "sanitize_subject")):
        for node in ast.walk(fn):
            assert not (isinstance(node, ast.Dict) and node.keys), \
                f"{fn.name} maps content words to subjects — that is a domain router"


def test_empty_input_still_produces_a_usable_prompt():
    d = build_descriptor()
    assert "Subject:" in d.prompt()
    assert d.style_version == VISUAL_STYLE_VERSION
