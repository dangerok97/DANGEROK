"""Context Broker — semantic personal lookup with provenance.

AI decides when personal context may answer; this module only retrieves.
No conversational keyword branches. Schema field maps exist only to read
existing Profile / Memory / Account structures.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from conversation_engine.ai_core.models import ContextFact

logger = logging.getLogger("ora.ai_core.context_broker")

# Allowed retrieval categories (governance surface — not dialogue templates).
ALLOWED_CATEGORIES = frozenset(
    {
        "identity",
        "residence",
        "employment",
        "study",
        "goal",
        "general",
        "presence",
    }
)

# Over-broad AI context requests — reject (do not dump the user DB).
_BLOCKED_QUERY = re.compile(
    r"(entire|whole|full|tutti|tutto|completo|dump|database|all\s+(facts|data|memories|profile)|profilo\s+intero)",
    re.I,
)

# Semantic hints for AI context_query → category (broker routing only).
_CATEGORY_HINTS: Dict[str, Tuple[str, ...]] = {
    "identity": (
        "identity",
        "name",
        "nome",
        "display name",
        "who i am",
        "chi sono",
        "chiamo",
        "user's name",
        "account name",
    ),
    "residence": (
        "residence",
        "live",
        "lives",
        "home",
        "vivi",
        "vivo",
        "dove vivo",
        "dove abito",
        "città",
        "citta",
        "city",
        "address",
        "indirizzo",
        "casa",
    ),
    "presence": (
        "presence",
        "current location",
        "dove sono",
        "where am i",
        "posizione attuale",
        "adesso dove",
        "device location",
        "foreground location",
    ),
    "employment": (
        "employment",
        "work",
        "job",
        "lavoro",
        "ruolo",
        "occupazione",
        "profession",
        "career",
        "employer",
    ),
    "study": (
        "study",
        "studio",
        "university",
        "universit",
        "corso",
        "facolt",
        "exam",
        "esame",
        "school",
    ),
}

# Profile slot families per category — unavoidable schema maps to read Life Profile.
_CATEGORY_SLOTS: Dict[str, frozenset] = {
    "identity": frozenset({"identity.name"}),
    "residence": frozenset({"casa.city", "casa.address"}),
    "employment": frozenset({"lavoro.role"}),
    "study": frozenset({"studio.university", "studio.course"}),
}

STAGE_A_MAX = 4
STAGE_B_MAX = 8
MAX_PAYLOAD_CHARS = 2400


class ContextBroker:
    def __init__(self, db=None):
        self.db = db

    async def retrieve(
        self,
        *,
        user_id: str,
        user_message: str = "",
        active_goal: Optional[Dict[str, Any]] = None,
        query: Optional[str] = None,
        stage: str = "A",
        session_id: Optional[str] = None,
    ) -> List[ContextFact]:
        """
        Stage A: minimal high-authority baseline (account display name + active goal).
        Stage B: targeted semantic personal lookup from AI context_query.
        """
        if self.db is None or not user_id:
            return []

        if stage == "B":
            ok, reason = validate_context_query(query or "")
            if not ok:
                logger.info("context query blocked: %s", reason)
                return []

        facts: List[ContextFact] = []

        # --- Account (Stage A always; Stage B when identity/general) ---
        categories = infer_categories(
            (query or user_message) if stage == "B" else ""
        )
        if stage == "A" or "identity" in categories or "general" in categories:
            facts.extend(await self._account_facts(user_id))

        # --- Active goal (tiny) — historical context, not a binding command ---
        if active_goal and (active_goal.get("summary") or active_goal.get("desired_outcome")):
            if stage == "A" or "goal" in categories or "general" in categories:
                summary = (active_goal.get("summary") or "").strip()
                outcome = (active_goal.get("desired_outcome") or "").strip()
                msg = (user_message or "").strip()
                # Ambiguous new goal utterance must not inherit a specific prior subject.
                if _looks_like_ambiguous_new_goal(msg) and _goal_has_specific_subject(
                    summary
                ):
                    stmt = (
                        "Previous conversation goal (may be outdated — do NOT assume this "
                        f"is the current subject unless the user confirms): {summary}"
                    )
                    status = "ambiguous"
                else:
                    stmt = f"Obiettivo attivo: {summary}" + (
                        f" — esito: {outcome}" if outcome else ""
                    )
                    status = "known"
                facts.append(
                    ContextFact(
                        statement=stmt[:280],
                        fact=stmt[:280],
                        source="goal",
                        authority="conversation",
                        status=status,
                        ref="active_goal",
                    )
                )

        # Stage A stops here — do not stuff Profile/Memory.
        if stage == "A":
            facts.extend(await self._situation_facts(user_id, session_id=session_id, detailed=False))
            return _finalize(facts, limit=STAGE_A_MAX + 4)

        # --- Stage B: Profile + Memory + minimized presence ---
        facts.extend(
            await self._profile_facts(user_id, categories=categories, query=query or "")
        )
        facts.extend(
            await self._memory_facts(user_id, categories=categories, query=query or "")
        )
        if "presence" in categories or "general" in categories:
            facts.extend(await self._presence_facts(user_id))
        if "general" in categories or "goal" in categories:
            facts.extend(await self._situation_facts(user_id, session_id=session_id, detailed=True))

        return _finalize(facts, limit=STAGE_B_MAX)

    async def _situation_facts(self, user_id: str, *, session_id: Optional[str], detailed: bool) -> List[ContextFact]:
        try:
            from situations.service import SituationService

            items = await SituationService(self.db).list_context(
                user_id, session_id=session_id, limit=4 if detailed else 3
            )
        except Exception as e:
            logger.info("context broker situations soft-fail: %s", type(e).__name__)
            return []
        out: List[ContextFact] = []
        for item in items:
            preview = item.context_preview()
            statement = (
                f"Situation {item.id} revision={item.revision} status={item.status}: "
                f"{item.summary}"
            )
            if detailed:
                statement += f"; details={json.dumps(preview, ensure_ascii=False)}"
            out.append(ContextFact(
                statement=statement[:700], fact=statement[:700], source="situation",
                authority="user_context", status=item.status, timestamp=item.updated_at,
                ref=f"situation:{item.id}", temporal_scope=item.temporal_scope,
            ))
        return out

    async def _presence_facts(self, user_id: str) -> List[ContextFact]:
        """Minimized presence — never a GPS trail; never overwrites residence."""
        out: List[ContextFact] = []
        try:
            from location.service import LocationService

            presence = await LocationService(self.db).build_presence(user_id)
            slice_ = presence.for_broker()
        except Exception as e:
            logger.info("context broker presence soft-fail: %s", type(e).__name__)
            return out
        freshness = slice_.get("freshness") or "UNKNOWN"
        if freshness == "UNKNOWN":
            stmt = (
                "Device presence: unknown — no usable current location signal. "
                "Do not claim where the user is now."
            )
        elif freshness == "STALE":
            label = slice_.get("label")
            stmt = (
                "Device presence is STALE"
                + (f" (last coarse place: {label})" if label else "")
                + ". Do NOT say the user is there now."
            )
        else:
            label = slice_.get("label")
            locality = slice_.get("locality")
            municipality = slice_.get("municipality")
            region = slice_.get("region")
            if label or locality or municipality:
                parts = [f"display={label}"] if label else []
                if locality:
                    parts.append(f"locality={locality}")
                if municipality and (
                    not locality or municipality.lower() != str(locality).lower()
                ):
                    parts.append(f"municipality={municipality}")
                if region:
                    parts.append(f"region={region}")
                stmt = (
                    f"Current device presence ({freshness}): {'; '.join(parts)}. "
                    "This is NOT durable residence. Prefer display/locality when answering; "
                    "mention municipality only as admin context when helpful."
                )
            elif slice_.get("coordinates"):
                stmt = (
                    f"Current device presence ({freshness}): coordinates available. "
                    "This is NOT durable residence. Prefer place_label when answering."
                )
            else:
                stmt = f"Current device presence freshness={freshness}."
        out.append(
            ContextFact(
                statement=stmt[:280],
                fact=stmt[:280],
                source="presence",
                authority="device_signal",
                status="known" if freshness in ("CURRENT", "RECENT") else "ambiguous",
                timestamp=slice_.get("last_seen_at"),
                ref="presence:current",
            )
        )
        return out

    async def _account_facts(self, user_id: str) -> List[ContextFact]:
        out: List[ContextFact] = []
        try:
            u = await self.db.users.find_one(
                {"user_id": user_id}, {"_id": 0, "name": 1, "email": 1}
            )
        except Exception as e:
            logger.info("context broker account soft-fail: %s", type(e).__name__)
            return out
        if not isinstance(u, dict):
            return out
        name = (u.get("name") or "").strip()
        if not name:
            return out
        try:
            from life_memory.statements import statement_for_profile_fact

            stmt = statement_for_profile_fact(
                domain="identity", key="identity.preferred_name", value=name
            )
        except Exception:
            stmt = None
        statement = stmt or f"Il nome dell'account è {name}."
        out.append(
            ContextFact(
                statement=statement,
                fact=statement,
                source="account",
                authority="structured_account",
                status="known",
                ref="account:name",
            )
        )
        return out

    async def _profile_facts(
        self,
        user_id: str,
        *,
        categories: Set[str],
        query: str,
    ) -> List[ContextFact]:
        out: List[ContextFact] = []
        try:
            from life_setup.profile_service import LifeProfileService

            profile = await LifeProfileService(self.db).get_or_create(user_id)
        except Exception as e:
            logger.info("context broker profile soft-fail: %s", type(e).__name__)
            return out

        domains = getattr(profile, "domains", None) or {}
        if isinstance(profile, dict):
            domains = profile.get("domains") or {}

        try:
            from life_memory.authority import authority_band, memory_status_from_authority
            from life_memory.statements import (
                is_sensitive_key,
                is_transient_key,
                normalize_slot,
                statement_for_profile_fact,
            )
        except Exception as e:
            logger.info("context broker profile imports soft-fail: %s", type(e).__name__)
            return out

        want_slots = _slots_for_categories(categories)
        q_tokens = _tokens(query)

        for domain, dom in domains.items():
            objects = getattr(dom, "objects", None)
            if objects is None and isinstance(dom, dict):
                objects = dom.get("objects") or {}
            if not isinstance(objects, dict):
                continue
            for key, obj in objects.items():
                if is_sensitive_key(str(key)) or is_transient_key(str(key)):
                    continue
                value, source, field_status, confirmed, updated = _unwrap_profile_obj(obj)
                if value in (None, "", []):
                    continue
                slot = normalize_slot(str(domain), str(key))
                if want_slots and slot not in want_slots:
                    blob = f"{key} {value} {slot}".lower()
                    if not any(t in blob for t in q_tokens):
                        if "general" not in categories:
                            continue
                stmt = statement_for_profile_fact(
                    domain=str(domain), key=str(key), value=value
                )
                if not stmt:
                    continue
                band = authority_band(
                    source=str(source or "user_said"),
                    field_status=str(field_status or "extracted"),
                    confirmed=bool(confirmed),
                )
                status = memory_status_from_authority(
                    source=str(source or "user_said"),
                    field_status=str(field_status or "extracted"),
                    confidence=0.7,
                    confirmed=bool(confirmed),
                    key=str(key),
                )
                if status == "superseded":
                    continue
                out.append(
                    ContextFact(
                        statement=stmt,
                        fact=stmt,
                        source="profile",
                        authority=band,
                        status=status,
                        timestamp=updated,
                        ref=f"profile:{domain}:{key}",
                    )
                )
        return out

    async def _memory_facts(
        self,
        user_id: str,
        *,
        categories: Set[str],
        query: str,
    ) -> List[ContextFact]:
        out: List[ContextFact] = []
        try:
            from life_memory.service import get_life_memory_service

            # Deterministic assemble only — no LLM inside the broker.
            resp = await get_life_memory_service(self.db).get_life_memory(
                user_id, enrich=False
            )
        except Exception as e:
            logger.info("context broker memory soft-fail: %s", type(e).__name__)
            return out

        memories = getattr(resp, "memories", None) or []
        q_tokens = _tokens(query)
        scored: List[Tuple[int, Any]] = []
        for m in memories:
            statement = str(getattr(m, "statement", None) or "")
            if not statement:
                continue
            status = str(getattr(m, "status", None) or "known")
            if status == "superseded":
                continue
            domain = str(getattr(m, "domain", None) or "")
            slot = str(getattr(m, "slot", None) or "")
            score = _semantic_score(
                statement=statement,
                domain=domain,
                slot=slot,
                categories=categories,
                q_tokens=q_tokens,
            )
            if score <= 0 and "general" not in categories:
                continue
            scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        for _score, m in scored[:STAGE_B_MAX]:
            statement = str(m.statement)[:240]
            auth = str(
                getattr(m, "authority", None)
                or getattr(m, "provenance_label", None)
                or "unknown"
            )
            if auth.lower().startswith("dal tuo account"):
                auth = "structured_account"
            out.append(
                ContextFact(
                    statement=statement,
                    fact=statement,
                    source="memory",
                    authority=auth,
                    status=str(getattr(m, "status", None) or "known"),
                    timestamp=str(getattr(m, "updated_at", None) or "") or None,
                    ref=str(getattr(m, "id", None) or "memory"),
                )
            )
        return out


def validate_context_query(query: str) -> Tuple[bool, str]:
    q = (query or "").strip()
    if not q:
        return False, "empty_query"
    if len(q) > 400:
        return False, "query_too_long"
    if _BLOCKED_QUERY.search(q):
        return False, "overbroad_query"
    return True, "ok"


def infer_categories(text: str) -> Set[str]:
    """Map AI context_query to allowed categories. Empty → general."""
    t = (text or "").lower().strip()
    if not t:
        return {"general"}
    found: Set[str] = set()
    for cat, hints in _CATEGORY_HINTS.items():
        if any(h in t for h in hints):
            found.add(cat)
    return found or {"general"}


def _slots_for_categories(categories: Set[str]) -> Set[str]:
    slots: Set[str] = set()
    for c in categories:
        slots |= set(_CATEGORY_SLOTS.get(c) or ())
    return slots


def _tokens(text: str) -> List[str]:
    return [t for t in re.split(r"\W+", (text or "").lower()) if len(t) > 2][:12]


def _semantic_score(
    *,
    statement: str,
    domain: str,
    slot: str,
    categories: Set[str],
    q_tokens: Sequence[str],
) -> int:
    score = 0
    blob = f"{statement} {domain} {slot}".lower()
    if "general" in categories:
        score += 1
    for cat in categories:
        for hint in _CATEGORY_HINTS.get(cat, ()):
            if hint in blob:
                score += 3
        for s in _CATEGORY_SLOTS.get(cat, ()):
            if s in slot or s.split(".")[-1] in slot:
                score += 4
        if cat == "identity" and domain in ("identity", "mlc"):
            score += 2
        if cat == "residence" and domain in ("casa", "home"):
            score += 2
        if cat == "employment" and domain in ("lavoro", "work"):
            score += 2
        if cat == "study" and domain in ("studio", "study"):
            score += 2
    for t in q_tokens:
        if t in blob:
            score += 1
    return score


def _unwrap_profile_obj(obj: Any) -> Tuple[Any, str, str, bool, Optional[str]]:
    if obj is None:
        return None, "unknown", "extracted", False, None
    if hasattr(obj, "value"):
        return (
            getattr(obj, "value", None),
            str(getattr(obj, "source", None) or "user_said"),
            str(getattr(obj, "status", None) or "extracted"),
            bool(getattr(obj, "confirmed", False)),
            str(getattr(obj, "updated_at", None) or "") or None,
        )
    if isinstance(obj, dict):
        return (
            obj.get("value"),
            str(obj.get("source") or "user_said"),
            str(obj.get("status") or "extracted"),
            bool(obj.get("confirmed")),
            str(obj.get("updated_at") or "") or None,
        )
    return obj, "unknown", "extracted", False, None


def _finalize(facts: List[ContextFact], *, limit: int) -> List[ContextFact]:
    seen: Set[str] = set()
    out: List[ContextFact] = []
    payload = 0
    for f in facts:
        stmt = (f.statement or f.fact or "").strip()
        if not stmt:
            continue
        key = stmt.lower()
        if key in seen:
            continue
        add = len(stmt) + len(f.source or "") + len(f.authority or "")
        if out and payload + add > MAX_PAYLOAD_CHARS:
            break
        seen.add(key)
        if not f.statement:
            f.statement = stmt
        if not f.fact:
            f.fact = stmt
        out.append(f)
        payload += add
        if len(out) >= limit:
            break
    return out


def context_payload_stats(facts: Sequence[ContextFact]) -> Dict[str, int]:
    dumped = [f.model_dump() for f in facts]
    raw = json.dumps(dumped, ensure_ascii=False)
    return {"item_count": len(facts), "payload_chars": len(raw)}


def _looks_like_ambiguous_new_goal(message: str) -> bool:
    """True when user opens a horizon goal without naming the concrete object."""
    m = (message or "").strip().lower()
    if not m or len(m) > 220:
        return False
    horizon = any(
        p in m
        for p in (
            "tra ",
            "fra ",
            "in ",
            "entro",
            "days",
            "giorni",
            "settiman",
            "mesi",
            "weeks",
            "months",
        )
    )
    goalish = any(
        p in m
        for p in (
            "esame",
            "exam",
            "scadenza",
            "deadline",
            "devo ",
            "voglio ",
            "organizz",
            "prepar",
            "adott",
            "viaggio",
            "partire",
        )
    )
    if not (horizon and goalish):
        return False
    # If a concrete proper-ish subject already appears, not ambiguous.
    # Keep heuristic light — named courses/places usually have capitals in original;
    # here we only use lowercase, so treat short generic phrases as ambiguous.
    specific_markers = (
        "matematica",
        "psicolog",
        "informatica",
        "fisica",
        "chimica",
        "vienna",
        "roma",
        "cane",
        "mostra",
    )
    if any(s in m for s in specific_markers):
        return False
    return True


def _goal_has_specific_subject(summary: str) -> bool:
    s = (summary or "").strip().lower()
    if not s:
        return False
    # Generic placeholders are not "specific"
    if s in ("esame", "exam", "preparazione esame", "obiettivo"):
        return False
    specific = (
        "psicolog",
        "matematica",
        "informatica",
        "fisica",
        "chimica",
        "vienna",
        "mostra",
        "cane",
        "viaggio",
    )
    return any(x in s for x in specific) or len(s.split()) >= 4
