"""AI Life Strategist policy — what AI may and may not do."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# AI may: reason, suggest, propose, link, extract, explain, choose next Q.
AI_MAY = frozenset({
    "reason",
    "suggest",
    "propose",
    "link",
    "extract",
    "explain",
    "choose_next_question",
    "recommend_document",
    "propose_shadow_goal",
    "propose_calendar_draft",
})

# AI may NOT: delete, modify confirmed, irreversible actions without consent.
AI_MAY_NOT = frozenset({
    "delete_data",
    "overwrite_confirmed",
    "create_irreversible_calendar",
    "send_email",
    "send_whatsapp",
    "open_banking_transfer",
    "request_password",
    "request_pin",
    "request_otp",
    "request_bank_credentials",
})

PRIVACY_REFUSAL_PATTERNS = [
    (re.compile(r"\b(password|passwd|pwd)\b", re.I), "password"),
    (re.compile(r"\b(pin|codice\s*pin)\b", re.I), "pin"),
    (re.compile(r"\b(otp|one[-\s]?time|codice\s*(di\s*)?verifica|2fa)\b", re.I), "otp"),
    (
        re.compile(
            r"\b(iban|carta\s*di\s*credito|cvv|coordinate\s*bancarie|"
            r"credenziali\s*bancarie|password\s*home\s*banking|"
            r"accesso\s*conto)\b",
            re.I,
        ),
        "bank_credentials",
    ),
]

PRIVACY_REFUSAL_MESSAGE = (
    "Non ti chiederò mai password, PIN, OTP o credenziali bancarie. "
    "Puoi caricare un documento rilevante o raccontarmi solo ciò che ti senti di condividere."
)


def is_allowed_action(action: str) -> bool:
    return action in AI_MAY and action not in AI_MAY_NOT


def assert_allowed(action: str) -> None:
    if action in AI_MAY_NOT or action not in AI_MAY:
        raise PermissionError(f"AI Life Strategist policy forbids action: {action}")


def detect_privacy_sensitive_request(text: str) -> Optional[str]:
    """If the *assistant* were about to ask for secrets — detect in proposed Q."""
    t = text or ""
    for pat, kind in PRIVACY_REFUSAL_PATTERNS:
        if pat.search(t):
            return kind
    return None


def user_text_is_credential_dump(text: str) -> bool:
    """User pasted something that looks like credentials — do not store raw."""
    t = (text or "").strip()
    if not t:
        return False
    if re.search(r"(?i)\b(password|pin|otp|cvv)\s*[:=]", t):
        return True
    if re.search(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", t):  # card-like
        return True
    return False


def sanitize_known_facts(facts: Dict[str, Any]) -> Dict[str, Any]:
    """Strip secrets from context before any LLM / cache."""
    blocked = {
        "password", "pin", "otp", "cvv", "iban", "card_number",
        "bank_password", "token", "secret", "api_key",
    }
    out: Dict[str, Any] = {}
    for k, v in (facts or {}).items():
        lk = str(k).lower()
        if any(b in lk for b in blocked):
            continue
        if isinstance(v, str) and user_text_is_credential_dump(v):
            continue
        out[k] = v
    return out


def filter_unsafe_plan_fields(question: str, reason: str, benefit: str) -> Tuple[str, str, str, bool]:
    """Rewrite plan text if it violates privacy. Returns (q, reason, benefit, refused)."""
    kind = detect_privacy_sensitive_request(question) or detect_privacy_sensitive_request(reason)
    if not kind:
        return question, reason, benefit, False
    safe_q = (
        "Preferisci caricare un documento utile (es. contratto o bolletta) "
        "oppure saltare questo punto per ora?"
    )
    safe_reason = PRIVACY_REFUSAL_MESSAGE
    safe_benefit = (
        "ORA può aiutarti senza credenziali sensibili — "
        "bastano documenti o informazioni generali che scegli tu."
    )
    return safe_q, safe_reason, safe_benefit, True


def consent_required_for(action: str) -> bool:
    return action in {
        "create_irreversible_calendar",
        "overwrite_confirmed",
        "delete_data",
    }
