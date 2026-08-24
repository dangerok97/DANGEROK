"""ORA contextual visual style — what every generated card image must look like.

Two things live here and nothing else: the **style lock** (which never varies)
and the **descriptor** (which is the only thing that does).

    style  →  constant, versioned, product identity
    subject →  derived per card, from a bounded, sanitised summary

The subject changes. The ORA style does not. That is what makes a wall of
generated images read as one product rather than a stock library.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Optional

# Bump when the look itself changes. It is part of the visual key, so a new
# version regenerates images rather than silently mixing two styles on screen.
# v2: the look moved from photographic to stylised — v1 images would sit beside
# v2 ones as obvious strangers, so they must not survive the change.
VISUAL_STYLE_VERSION = "ora_contextual_visual_style_v3"

# The look, stated as an illustration brief rather than a photography brief.
#
# v2 still opened with "editorial still life", and that phrase pulls image
# models straight toward a studio photograph no matter how many negatives
# follow it. v3 leads with the medium — digital illustration, matte clay
# render — because the first words carry the most weight, and only then
# describes the mood.
ORA_CONTEXTUAL_VISUAL_STYLE_V1 = (
    "A digital illustration. Stylised 3D artwork with a soft matte clay-render "
    "finish, like a carefully art-directed editorial illustration. "
    "Simplified, gently rounded geometric forms with smooth matte surfaces and "
    "no fine surface detail. "
    "Warm refined palette: ivory, cream, beige, sand and soft neutral tones. "
    "Even diffused studio-soft lighting, delicate soft shadows, no harsh "
    "contrast. Clean minimal composition, only a few clearly readable objects, "
    "generous empty space, calm and premium. "
    "Rendered artwork, NOT a photograph. "
    "Strictly avoid: photography, photorealism, photorealistic rendering, "
    "real-world photo, stock photo, snapshot, documentary realism, camera "
    "capture, film grain, lens blur, bokeh, depth-of-field, reflections, "
    "realistic fabric or wood or skin texture, hyper-detailed materials, "
    "cluttered scenes, text, lettering, captions, logos, watermarks, user "
    "interface elements, charts, people, faces, hands, neon colours, cartoon "
    "mascots. "
    # Stated last and on its own, because a subject like "contracts and
    # receipts" invites the model to label the objects and a prohibition buried
    # inside a long avoid-list does not survive that pull. Recency is leverage.
    "ABSOLUTELY NO TEXT OF ANY KIND anywhere in the image: no words, no labels "
    "on objects, no letters, no numbers, no handwriting, no signage. Objects "
    "must be completely blank and unlabelled."
)

# What the picture must communicate. Kept as an instruction to the model, never
# as a lookup table in the code: ORA must not hold its own private opinion that
# an exhibition means a camera.
SEMANTIC_DIRECTIVE = (
    "The image must make the PRIMARY SEMANTIC CONCEPT of the card immediately "
    "recognisable at first glance. Choose a small set of concrete objects that "
    "are strongly and unmistakably associated with that specific meaning, and "
    "make the main subject the clear focal point of the composition. "
    "Do not fall back on generic workspace, desk, notebook, laptop, coffee or "
    "productivity imagery unless those are themselves the primary subject of "
    "the card."
)

# Aspect the hero media slot expects. Kept here so the generator and the layout
# cannot drift apart.
VISUAL_ASPECT = "4:3"

MAX_SUBJECT_CHARS = 120


# --- privacy -----------------------------------------------------------------
#
# The descriptor is the ONLY user-derived text that ever leaves ORA for an
# image provider. It carries the gist of a card and nothing that identifies a
# person, a place they live, or anything about their money or health. Anything
# matching these is removed before the request is built — the sanitiser is not
# a nicety, it is the boundary.

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE = re.compile(r"(?:(?<=\s)|^)(?:\+?\d[\d\s().-]{6,}\d)(?=\s|$)")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_CF = re.compile(r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.I)  # codice fiscale
_LONG_NUM = re.compile(r"\b\d{5,}\b")
_MONEY = re.compile(r"[€$£]\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:€|eur|euro|usd)\b", re.I)
_URL = re.compile(r"https?://\S+|www\.\S+")
_ADDRESS = re.compile(
    r"\b(?:via|viale|piazza|corso|vicolo|largo|strada|str\.|street|avenue|ave\.|road|rd\.)\s+[^\s,;.]+"
    r"(?:\s+[^\s,;.]+)?\s*,?\s*\d*",
    re.I,
)
# A capitalised pair reads as a person's full name far more often than not.
_FULL_NAME = re.compile(r"\b[A-Z][a-zà-ÿ]{2,}\s+[A-Z][a-zà-ÿ]{2,}\b")

_REDACTIONS = (_URL, _EMAIL, _IBAN, _CF, _MONEY, _PHONE, _ADDRESS, _FULL_NAME, _LONG_NUM)


def sanitize_subject(raw: Optional[str]) -> str:
    """Reduce a card's text to a safe, generic subject phrase.

    Removes contact details, identifiers, money, addresses, links and personal
    names, collapses what is left, and truncates. The result is meant to be
    dull: "a small photography exhibition" rather than anything that could
    identify whose it is.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    for pattern in _REDACTIONS:
        text = pattern.sub(" ", text)
    text = re.sub(r"[^\w\s\-àèéìòùÀÈÉÌÒÙ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_SUBJECT_CHARS].strip()


@dataclass(frozen=True)
class VisualDescriptor:
    """Everything the provider is allowed to know about one card."""

    subject: str
    style_version: str = VISUAL_STYLE_VERSION

    def prompt(self) -> str:
        subject = self.subject or "a calm arrangement of simple everyday objects"
        # Style, then what the picture must communicate, then the subject —
        # in that order, because the first two never vary and the third always
        # does.
        return "\n\n".join((
            ORA_CONTEXTUAL_VISUAL_STYLE_V1,
            SEMANTIC_DIRECTIVE,
            f"Subject: {subject}.",
        ))


def build_descriptor(*, title: Optional[str] = None, summary: Optional[str] = None) -> VisualDescriptor:
    """Build the descriptor from a card's own words, sanitised.

    Deliberately no branching on meaning: there is no mapping from "travel" to
    a suitcase or from "house" to keys anywhere in ORA. The model receives a
    neutral phrase and decides the subject itself, which is what keeps this
    general-purpose instead of a hidden domain router.
    """
    parts = [sanitize_subject(title), sanitize_subject(summary)]
    subject = " ".join(p for p in parts if p).strip()
    return VisualDescriptor(subject=subject[:MAX_SUBJECT_CHARS])


def visual_key(*, entity_ref: str, descriptor: VisualDescriptor) -> str:
    """Stable identity of one generated image.

    Derived from *what the picture is of* — the entity it belongs to plus the
    semantic descriptor and the style version — and never from the clock. The
    same card asks for the same key forever, which is what makes caching real
    and stops Home from paying for a new image on every render. A material
    change to the card changes the descriptor, and therefore the key, and
    therefore earns a new picture.
    """
    basis = f"{entity_ref}|{descriptor.style_version}|{descriptor.subject}"
    return "vis_" + hashlib.sha256(basis.encode()).hexdigest()[:24]


__all__ = [
    "ORA_CONTEXTUAL_VISUAL_STYLE_V1",
    "SEMANTIC_DIRECTIVE",
    "VISUAL_STYLE_VERSION",
    "VISUAL_ASPECT",
    "VisualDescriptor",
    "build_descriptor",
    "sanitize_subject",
    "visual_key",
]
