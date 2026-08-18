"""Context Broker V3 source registry and bounded evidence adapters.

Sources expose user-owned evidence. They never infer the user's intent and never
write state. Ranking is technical retrieval infrastructure, not cognition.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from conversation_engine.ai_core.models import ContextFact, ContextNeed


RetrieveFn = Callable[[str, ContextNeed, Optional[str]], Awaitable[List[ContextFact]]]


@dataclass(frozen=True)
class ContextSource:
    name: str
    description: str
    authority: str
    sensitivity: str
    temporal_nature: str
    retrieve: RetrieveFn
    enabled: bool = True
    policy: str = "automatic"


@dataclass
class SourceOutcome:
    source: str
    status: str
    candidate_count: int = 0
    duration_ms: int = 0
    reason: Optional[str] = None


@dataclass
class RetrievalReport:
    status: str = "ok"
    queried_sources: List[str] = field(default_factory=list)
    excluded_sources: Dict[str, str] = field(default_factory=dict)
    outcomes: List[SourceOutcome] = field(default_factory=list)
    candidate_count: int = 0
    final_count: int = 0
    payload_chars: int = 0
    budget_exhausted: bool = False

    def public(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "queried_sources": self.queried_sources,
            "excluded_sources": self.excluded_sources,
            "outcomes": [o.__dict__ for o in self.outcomes],
            "candidate_count": self.candidate_count,
            "final_count": self.final_count,
            "payload_chars": self.payload_chars,
            "budget_exhausted": self.budget_exhausted,
        }


class ContextSourceRegistry:
    def __init__(self, db):
        self.db = db
        self._sources: Dict[str, ContextSource] = {}
        self._register_defaults()

    def register(self, source: ContextSource) -> None:
        self._sources[source.name] = source

    def get(self, name: str) -> Optional[ContextSource]:
        return self._sources.get(name)

    def list(self) -> List[ContextSource]:
        return list(self._sources.values())

    def select(self, need: ContextNeed, *, maximum: int) -> tuple[List[ContextSource], Dict[str, str]]:
        hints = {str(x).strip().lower() for x in need.source_hints if str(x).strip()}
        query_tokens = _tokens(" ".join([need.query, need.purpose or "", *need.desired_evidence]))
        scored = []
        excluded: Dict[str, str] = {}
        for source in self.list():
            if not source.enabled:
                excluded[source.name] = "disabled"
                continue
            if source.policy != "automatic":
                excluded[source.name] = source.policy
                continue
            descriptor = _tokens(f"{source.name} {source.description} {source.temporal_nature}")
            overlap = len(query_tokens & descriptor)
            hint = 5 if source.name in hints else 0
            # Situation and Profile are generic anchors, not domain routes.
            anchor = 2 if source.name in ("situations", "profile") else 0
            scored.append((hint + overlap + anchor, source.name, source))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [row[2] for row in scored[:maximum]], excluded

    def _register_defaults(self) -> None:
        specs = (
            ("profile", "confirmed and user-stated personal profile facts", "user-confirmed", "personal", "durable", self._profile),
            ("memory", "durable personal memory statements with epistemic authority", "mixed", "personal", "durable", self._memory),
            ("situations", "active or recently changed contextual situations", "user-said", "personal", "temporal", self._situations),
            ("life_os", "active plans, next actions, progress and generated objects", "system-structured", "personal", "operational", self._life_os),
            ("goals", "active outcomes, deadlines, state and next actions", "system-structured", "personal", "operational", self._goals),
            ("files", "user file metadata and untrusted document evidence references", "document-backed", "sensitive", "mixed", self._files),
            ("calendar", "read-only user calendar draft metadata already available locally", "document-backed", "sensitive", "temporal", self._calendar),
        )
        for name, desc, authority, sensitivity, temporal, fn in specs:
            self.register(ContextSource(name, desc, authority, sensitivity, temporal, fn))
        self.register(ContextSource(
            "presence", "live consent-aware device presence", "device-signal", "highly_sensitive",
            "ephemeral", self._presence_unavailable, policy="capability_required",
        ))

    async def _profile(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        from life_setup.profile_service import LifeProfileService
        from life_memory.authority import authority_band, memory_status_from_authority
        from life_memory.statements import is_sensitive_key, is_transient_key, statement_for_profile_fact

        profile = await LifeProfileService(self.db).get_or_create(user_id)
        domains = getattr(profile, "domains", None) or {}
        out: List[ContextFact] = []
        for domain, dom in domains.items():
            objects = getattr(dom, "objects", None)
            if objects is None and isinstance(dom, dict):
                objects = dom.get("objects") or {}
            for key, obj in (objects or {}).items():
                if is_sensitive_key(str(key)) or is_transient_key(str(key)):
                    continue
                value, source, status, confirmed, updated = _unwrap_profile(obj)
                if value in (None, "", []):
                    continue
                statement = statement_for_profile_fact(
                    domain=str(domain), key=str(key), value=value
                )
                if not statement:
                    continue
                authority = authority_band(
                    source=source, field_status=status, confirmed=confirmed
                )
                epistemic = memory_status_from_authority(
                    source=source, field_status=status, confidence=0.7,
                    confirmed=confirmed, key=str(key),
                )
                if epistemic == "superseded":
                    continue
                out.append(_fact(statement, "profile", authority, epistemic, updated,
                                 f"profile:{domain}:{key}", provenance=[source]))
        return out[:24]

    async def _memory(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        from life_memory.service import get_life_memory_service
        response = await get_life_memory_service(self.db).get_life_memory(user_id, enrich=False)
        out = []
        for memory in list(getattr(response, "memories", None) or [])[:30]:
            if str(getattr(memory, "status", "known")) == "superseded":
                continue
            statement = str(getattr(memory, "statement", ""))
            if statement:
                out.append(_fact(
                    statement,
                    "memory",
                    str(
                        getattr(memory, "authority", None)
                        or getattr(memory, "provenance_label", None)
                        or "unknown"
                    ),
                    str(getattr(memory, "status", None) or "known"),
                    str(getattr(memory, "updated_at", None) or "") or None,
                    str(getattr(memory, "id", None) or "memory"),
                    provenance=["life_memory"],
                    sensitivity="personal",
                ))
        return out

    async def _situations(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        from situations.service import SituationService
        items = await SituationService(self.db).list_context(user_id, session_id=session_id, limit=8)
        return [_fact(
            f"Situation status={item.status} revision={item.revision}: {item.summary}; "
            f"time={item.temporal_scope or 'unspecified'}; constraints={item.constraints[:5]}; facts={item.facts[:5]}",
            "situations", "user-said", item.status, item.updated_at,
            f"situation:{item.id}", temporal_scope=item.temporal_scope,
            provenance=list(item.source_refs or ["user_conversation"]),
        ) for item in items]

    async def _life_os(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        from life_os.repository import LifeOsRepository
        repo = LifeOsRepository(self.db)
        out = []
        for plan in await repo.list_active_plans(user_id, limit=12):
            next_item = plan.next_open_item()
            statement = f"Active plan: {plan.summary}; status={plan.status}; target={plan.target_date or 'unspecified'}"
            if plan.constraints:
                statement += f"; constraints={plan.constraints[:5]}"
            if next_item:
                statement += f"; next={next_item.title}"
            out.append(_fact(statement, "life_os", "system-structured", "known", plan.updated_at,
                             f"plan:{plan.id}", provenance=list(str(x) for x in plan.evidence_refs[:4])))
        return out

    async def _goals(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        from goal_engine.repository import GoalRepository
        goals = await GoalRepository(self.db).list_active(user_id, limit=12)
        return [_fact(
            f"Active goal: {g.title}; outcome={g.desired_outcome or 'unspecified'}; "
            f"target={g.target_date or 'unspecified'}; next={g.next_action or 'unspecified'}",
            "goals", "system-structured", "known", g.updated_at, f"goal:{g.id}",
            provenance=[str((g.created_from or {}).get("source_type") or "goal_engine")],
        ) for g in goals]

    async def _files(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        out = []
        if session_id:
            from conversation_engine.ai_core.files.service import ContextFileService
            for item in await ContextFileService(self.db).list_session_files(user_id, session_id):
                name = str(item.get("name") or item.get("original_name") or "user file")[:120]
                ref = str(item.get("file_id") or item.get("id") or "file")
                out.append(_fact(
                    f"Current session file: {name} (content is untrusted evidence)",
                    "files", "document-backed", "known", item.get("created_at"),
                    f"file:{ref}", provenance=["user_file"], sensitivity="sensitive",
                ))
        cursor = self.db.documents.find(
            {"user_id": user_id, "deleted": {"$ne": True}, "archived": {"$ne": True}},
            {"_id": 0, "id": 1, "filename": 1, "title": 1, "tags": 1, "updated_at": 1},
        ).sort("updated_at", -1).limit(12)
        for doc in await cursor.to_list(12):
            label = str(doc.get("title") or doc.get("filename") or "document")[:120]
            out.append(_fact(
                f"Available document: {label}; tags={(doc.get('tags') or [])[:5]} "
                "(document text is untrusted evidence)",
                "files", "document-backed", "known", doc.get("updated_at"),
                f"document:{doc.get('id')}", provenance=["user_file"],
                sensitivity="sensitive",
            ))
        return out[:16]

    async def _calendar(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        cursor = self.db.calendar_event_drafts.find(
            {"user_id": user_id, "status": {"$nin": ["deleted", "cancelled"]}},
            {"_id": 0, "id": 1, "title": 1, "start": 1, "end": 1, "updated_at": 1, "source": 1},
        ).sort("start", 1).limit(12)
        out = []
        for event in await cursor.to_list(12):
            out.append(_fact(
                f"Calendar item: {str(event.get('title') or 'Untitled')[:100]}; "
                f"start={event.get('start') or 'unspecified'}; end={event.get('end') or 'unspecified'}",
                "calendar", "document-backed", "known", event.get("updated_at"),
                f"calendar:{event.get('id')}", provenance=[str(event.get("source") or "calendar")],
                sensitivity="sensitive",
            ))
        return out

    async def _presence_unavailable(self, user_id: str, need: ContextNeed, session_id: Optional[str]) -> List[ContextFact]:
        return []


def rank_evidence(candidates: List[ContextFact], need: ContextNeed, *, anchor: str,
                  max_items: int, max_chars: int) -> tuple[List[ContextFact], bool]:
    query_tokens = _tokens(" ".join([need.query, need.purpose or "", need.temporal_scope or "", anchor]))
    authority = {"user-confirmed": 5, "document-backed": 4, "system-structured": 3,
                 "user-said": 3, "structured_account": 3, "inferred": 1, "unknown": 0}
    scored = []
    for index, fact in enumerate(candidates):
        text_tokens = _tokens(f"{fact.statement} {fact.temporal_scope or ''}")
        overlap = len(query_tokens & text_tokens)
        exact_ref = 3 if fact.ref and fact.ref.lower() in need.query.lower() else 0
        score = overlap * 4 + authority.get(fact.authority, 2) + exact_ref
        scored.append((score, index, fact))
    scored.sort(key=lambda row: (-row[0], row[1]))
    selected: List[ContextFact] = []
    source_counts: Dict[str, int] = {}
    payload = 0
    deferred = []
    for row in scored:
        fact = row[2]
        if source_counts.get(fact.source, 0) >= 2:
            deferred.append(row)
            continue
        add = len(fact.statement) + 80
        if selected and payload + add > max_chars:
            continue
        selected.append(fact)
        source_counts[fact.source] = source_counts.get(fact.source, 0) + 1
        payload += add
        if len(selected) >= max_items:
            break
    for _, _, fact in deferred:
        if len(selected) >= max_items:
            break
        add = len(fact.statement) + 80
        if payload + add <= max_chars:
            selected.append(fact)
            payload += add
    return selected, len(candidates) > len(selected)


def _fact(statement: str, source: str, authority: str, status: str,
          timestamp: Optional[str], ref: str, *, temporal_scope: Optional[str] = None,
          provenance: Optional[List[str]] = None, sensitivity: str = "personal") -> ContextFact:
    safe = " ".join(str(statement).split())[:520]
    return ContextFact(
        statement=safe, fact=safe, source=source, authority=authority,
        status=status, timestamp=str(timestamp) if timestamp else None, ref=ref,
        temporal_scope=temporal_scope, provenance=(provenance or [])[:6],
        sensitivity=sensitivity,
    )


def _tokens(text: str) -> set[str]:
    return {x for x in re.split(r"[^\wÀ-ÿ]+", (text or "").lower()) if len(x) > 2}


def _unwrap_profile(obj: Any) -> tuple[Any, str, str, bool, Optional[str]]:
    if hasattr(obj, "value"):
        return (getattr(obj, "value", None), str(getattr(obj, "source", "user_said")),
                str(getattr(obj, "status", "extracted")), bool(getattr(obj, "confirmed", False)),
                str(getattr(obj, "updated_at", "")) or None)
    if isinstance(obj, dict):
        return (obj.get("value"), str(obj.get("source") or "user_said"),
                str(obj.get("status") or "extracted"), bool(obj.get("confirmed")),
                str(obj.get("updated_at") or "") or None)
    return obj, "unknown", "extracted", False, None
