"""User-facing WhatsApp text renderer.

AI Core uses the same conversation for web and WhatsApp. The LLM can sometimes
emit a serialized, language-keyed answer (e.g. "{'it': 'Ciao\n...'}").
Never send the serialized container, Python escape sequences, or malformed
Markdown to WhatsApp. This module has no database or network side effects.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any


_LOCALE_KEYS = ("it", "it-IT", "it_IT")
_MAX_ENCODED_MESSAGE = 20_000
_BAD_REPLY = (
    "Ho preparato una risposta, ma non sono riuscito a visualizzarla "
    "correttamente. Puoi ripetere la domanda?"
)


def _italian_value(data: Any) -> str | None:
    """Accept only explicit Italian string fields, never repr(data)."""
    if not isinstance(data, dict):
        return None
    for key in _LOCALE_KEYS:
        value = data.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("text"), str):
            return value["text"]
    return None


def _decode_reply(value: Any) -> tuple[str, bool]:
    """Return text and whether it came from an explicit locale wrapper."""
    if isinstance(value, dict):
        localized = _italian_value(value)
        return (localized if localized is not None else _BAD_REPLY), True
    if not isinstance(value, str):
        return "", False
    raw = value.strip()
    if not raw:
        return "", False
    if len(raw) <= _MAX_ENCODED_MESSAGE and raw.startswith("{") and raw.endswith("}"):
        for decoder in (json.loads, ast.literal_eval):
            try:
                decoded = decoder(raw)
            except (ValueError, SyntaxError, TypeError, RecursionError, MemoryError):
                continue
            localized = _italian_value(decoded)
            if localized is not None:
                return localized, True
            # A structured message without an Italian field should not be
            # guessed or translated by the bridge.
            if isinstance(decoded, dict) and any(
                k in decoded for k in ("it", "it-IT", "it_IT")
            ):
                return _BAD_REPLY, True
    if re.match(r"^\{\s*['\"]it(?:-IT|_IT)?['\"]\s*:", raw):
        # Malformed locale containers must never be shown as Python code.
        return _BAD_REPLY, True
    return raw, False


def _tidy_whatsapp_emphasis(text: str) -> str:
    """Convert common Markdown emphasis to WhatsApp's single-star syntax.

    Valid *paired* WhatsApp emphasis is kept. A missing closing/opening star
    is removed rather than showing an orphaned formatting character.
    """
    text = re.sub(r"\*\*([^\n*]{1,400})\*\*", r"*\1*", text)
    text = re.sub(r"(?<!\*)\*\*([^\n*]{1,400})\*(?!\*)", r"*\1*", text)
    text = re.sub(r"(?<!\*)\*([^\n*]{1,400})\*\*(?!\*)", r"*\1*", text)

    def clean_line(line: str) -> str:
        # Asterisks used as arithmetic operators or in backtick code are not
        # typography; removing them would change the factual content.
        if "`" in line or re.search(r"\b\d+\s*\*\s*\d+\b", line):
            return line
        if "*" not in line or line.count("*") % 2 == 0:
            return line
        # Retain only already paired emphasis. Orphan asterisks do not
        # improve WhatsApp formatting and should not be visible to the user.
        valid = list(re.finditer(r"\*[^*\n]{1,400}\*", line))
        if not valid:
            return line.replace("*", "")
        parts: list[str] = []
        offset = 0
        for match in valid:
            parts.append(line[offset:match.start()].replace("*", ""))
            parts.append(match.group(0))
            offset = match.end()
        parts.append(line[offset:].replace("*", ""))
        return "".join(parts)

    return "\n".join(clean_line(line) for line in text.split("\n"))


def render_whatsapp_answer(value: Any) -> str:
    """Render only human-readable Italian text; never a language-map repr."""
    text, from_locale = _decode_reply(value)
    if not text:
        return ""
    # Newlines are real line breaks in a WhatsApp message, not Python escapes.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u2028", "\n")
    if from_locale and "\\n" in text and "\n" not in text:
        # A double-serialized locale string may contain literal backslash-n.
        # This is limited to decoded locale data so code/path messages remain
        # unchanged in ordinary chat.
        text = text.replace("\\r\\n", "\n").replace("\\n", "\n")
    text = _tidy_whatsapp_emphasis(text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()
