"""Read-only, owner-scoped stars. No new memory store, LLM call or progress writes."""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json

from life_memory.assemble import MemoryCandidate
from life_memory.identity import resolve_memory_candidates
from life_memory.statements import normalize_slot, statement_for_profile_fact
from life_profile.areas import all_areas, area_for_domain
from life_profile.objectives import objectives_for_area
from life_profile.human import appartiene_all_area, come_si_chiama, come_si_dice_il_fatto, come_si_dice_il_valore
from life_profile.service import LifeProfileService, _PROVENANCE_LABEL
from life_setup.profile_service import LifeProfileService as ProfileStore

# Presentation only: the existing eight hubs remain stable for work telemetry.
DOMAIN_HUB = {"casa": "home", "abbonamenti": "home", "servizi": "home",
              "lavoro": "calendar", "studio": "calendar", "auto": "places",
              "viaggi": "places", "famiglia": "people", "animali": "people",
              "patrimonio": "finances", "finanze": "finances", "assicurazioni": "finances",
              "documenti": "documents", "doc": "documents", "telephone": "calls"}
HIDDEN_PARTS = {"password", "secret", "token", "pipeline", "analysis_version", "provider", "model"}


def stable_id(key: str) -> str:
    return "star_" + hashlib.sha256(key.encode()).hexdigest()[:24]


def display_value(value) -> str:
    if isinstance(value, bool):
        return "Sì" if value else "No"
    if isinstance(value, list):
        return ", ".join(display_value(v) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k.replace('_', ' ')}: {display_value(v)}" for k, v in value.items())
    return str(value)


async def knowledge_map(db, user_id: str) -> dict:
    profile = await ProfileStore(db).get(user_id)
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "first_name": 1,
        "last_name": 1, "name": 1, "identity_confirmed_at": 1, "created_at": 1}) or {}
    progress = await LifeProfileService(db).completeness(user_id)
    catalogue = {o.ref: o for a in all_areas() for o in objectives_for_area(a)}
    grouped = defaultdict(list)
    explicit_identity = bool(user.get("first_name") and user.get("last_name") and user.get("identity_confirmed_at"))
    stars = []
    for field, label in (("first_name", "Nome"), ("last_name", "Cognome")) if explicit_identity else (("name", "Nome del profilo"),):
        if user.get(field):
            stars.append({"id": stable_id("account:" + field), "area": "memory", "branch_id": None,
                "title": label, "statement": str(user[field]), "status": "known",
                "provenance": "Confermato da te" if explicit_identity else "Dal tuo account",
                "updated_at": user.get("identity_confirmed_at") or user.get("created_at")})
    for domain, part in (profile.domains.items() if profile else []):
        for key, obj in part.objects.items():
            if obj.status in ("suggested", "rejected") or obj.value is None or obj.value == "" or obj.value == [] or obj.value == {}:
                continue
            if any(piece in key.lower().replace(".", "_").split("_") for piece in HIDDEN_PARTS):
                continue
            slot = normalize_slot(domain, key)
            if slot == "identity.name" and stars:
                continue  # Account identity is not counted twice.
            known = obj.confirmed or obj.status in ("confirmed", "corrected") or obj.source in ("user_said", "user_confirmed", "system")
            objective = catalogue.get(key)
            label = come_si_chiama(key, objective.label if objective else key.split(".")[-1].replace("_", " ").capitalize())
            statement = come_si_dice_il_fatto(key, come_si_dice_il_valore(obj.value)) or statement_for_profile_fact(domain=domain, key=key, value=obj.value)
            if not statement:
                statement = f"{label}: {display_value(obj.value)}"
            owning_area = next((a for a in all_areas() if appartiene_all_area(key, a.id)), None)
            display_domain = owning_area.domains[0] if owning_area else slot.split(".")[0] if slot.split(".")[0] in DOMAIN_HUB else domain
            grouped[slot].append(MemoryCandidate(
                candidate_id=f"profile:{domain}:{key}", kind="fact", statement=statement,
                domain=display_domain, group_label=label, slot=slot,
                status="known" if known else "likely",
                authority="user_confirmed" if obj.confirmed else "user_stated" if known else "ai_inferred",
                source_refs=[f"life_profile:{domain}:{key}"],
                provenance_label=_PROVENANCE_LABEL.get(obj.source, "Dal tuo profilo"),
                updated_at=obj.updated_at, learned_at=obj.confirmed_at or obj.updated_at,
                value_norm=json.dumps(obj.value, sort_keys=True, ensure_ascii=False),
                source_priority=10 if obj.confirmed or obj.status in ("confirmed", "corrected") else 20 if known else 50,
            ))
    # Resolve aliases and contradictions using the same authority rules as Memory.
    # Partition by semantic slot so adding many notes never creates an N² scan.
    for slot, candidates in grouped.items():
        memories, _, _ = resolve_memory_candidates(candidates)
        for memory in memories:
            if memory.status not in ("known", "likely"):
                continue
            domain = memory.domain or ""
            vita = area_for_domain(domain)
            stars.append({"id": stable_id("profile:" + slot), "area": DOMAIN_HUB.get(domain, "memory"),
                "branch_id": vita.id if vita else None, "title": memory.group_label,
                "statement": memory.statement, "status": memory.status,
                "provenance": memory.provenance_label, "updated_at": memory.updated_at})
    now = datetime.now(timezone.utc)
    notes = await db.memories.find({"user_id": user_id, "status": {"$nin": ["forgotten", "superseded", "rejected", "expired"]}}, {"_id": 0}).to_list(None)
    for note in notes:
        expiry = note.get("expires_at") or (note.get("temporal_scope") or {}).get("ends_at")
        if expiry:
            try:
                deadline = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
                if deadline.replace(tzinfo=deadline.tzinfo or timezone.utc) <= now:
                    continue
            except ValueError:
                continue
        statement = note.get("statement") or note.get("content")
        note_id = note.get("id") or note.get("memory_id")
        if not statement or not note_id or note.get("status", "active") not in ("active", "known") or note.get("authority") == "device":
            continue
        domain = note.get("domain") or ""
        vita = area_for_domain(domain)
        stars.append({"id": stable_id("memory:" + str(note_id)), "area": DOMAIN_HUB.get(domain, "memory"),
            "branch_id": vita.id if vita else None, "title": "Ricordo", "statement": str(statement),
            "status": "likely" if note.get("epistemic_status") in ("inferred", "tentative") else "known", "provenance": "Salvato in memoria",
            "updated_at": note.get("updated_at") or note.get("created_at")})
    stars.sort(key=lambda s: s["id"])
    area_domains = {a.id: a.domains[0] for a in all_areas()}
    branches = [{**a.model_dump(), "area": DOMAIN_HUB.get(area_domains[a.area_id], "memory"),
                 "star_count": sum(s["branch_id"] == a.area_id for s in stars),
                 "complete": a.percent >= 100 and a.known_count > 0} for a in progress.areas]
    result = {"stars": stars, "count": len(stars), "known_count": sum(s["status"] == "known" for s in stars),
              "percent": progress.percent, "branches": branches}
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()[:24]
    return result
