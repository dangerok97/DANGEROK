"""Deterministic Life Map assemble — structured data → presentation + evidence.

Mirrors Contesti FE Prompt 5 mapping. No Gemini. No invented domains.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from ai_life_strategist.models import DOMAIN_LABELS_IT

from life_map.identity import (
    SituationCandidate,
    temporal_anchor_day,
    temporal_anchor_range,
)
from life_map.models import (
    EvidenceRef,
    PresentationArea,
    PresentationSituation,
)

HIDDEN_DOMAINS = frozenset({"mlc", "doc"})
LIVE_STATUSES = frozenset({"active", "paused"})
DOMAIN_ORDER = [
    "lavoro",
    "studio",
    "casa",
    "auto",
    "famiglia",
    "salute",
    "finanze",
    "viaggi",
    "animali",
    "assicurazioni",
    "abbonamenti",
    "internet",
    "documenti",
    "servizi",
]
IDENTITY_KEYS: Dict[str, List[str]] = {
    "lavoro": ["lavoro.ruolo", "ruolo"],
    "studio": ["studio.universita", "universita"],
    "casa": ["casa.citta", "citta"],
    "auto": ["auto.modello", "modello"],
    "famiglia": ["famiglia.nucleo", "nucleo"],
}


def _present(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


def _human_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        t = value.strip()
        if not t:
            return None
        if t.islower() and "_" in t and t.replace("_", "").isalnum():
            return None
        return t
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _parse_date(iso: Optional[str]) -> Optional[date]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(iso[:10])
        except Exception:
            return None


def _fmt_it(d: date) -> str:
    months = [
        "",
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ]
    return f"{d.day} {months[d.month]}"


def _days_until(iso: Optional[str], today: Optional[date] = None) -> Optional[int]:
    d = _parse_date(iso)
    if not d:
        return None
    t = today or date.today()
    return (d - t).days


def _date_range(start: Optional[str], end: Optional[str]) -> Optional[str]:
    a = _parse_date(start)
    b = _parse_date(end)
    if a and b:
        return f"{_fmt_it(a)} – {_fmt_it(b)}"
    if a:
        return f"Dal {_fmt_it(a)}"
    if b:
        return f"Fino al {_fmt_it(b)}"
    return None


def _travel_phase(phase: Optional[str], days: Optional[int]) -> Optional[str]:
    p = (phase or "").lower()
    if p == "during":
        return "In corso"
    if p == "departure_day":
        return "Partenza oggi"
    if p == "welcome_back":
        return "Di ritorno"
    if p == "days_until":
        if isinstance(days, int) and days >= 0:
            if days == 0:
                return "Partenza oggi"
            if days == 1:
                return "Partenza domani"
            return f"Partenza tra {days} giorni"
        return "In arrivo"
    if p == "upcoming":
        return "In arrivo"
    return None


def _study_temporal(exam_date: Optional[str], today: Optional[date] = None) -> Optional[str]:
    n = _days_until(exam_date, today)
    if n is None:
        d = _parse_date(exam_date)
        return f"Esame il {_fmt_it(d)}" if d else None
    if n < 0:
        return None
    if n == 0:
        return "Esame oggi"
    if n == 1:
        return "Esame domani"
    return f"Esame tra {n} giorni"


def _identity_for_domain(domain: str, objects: Dict[str, Any]) -> Optional[str]:
    for key in IDENTITY_KEYS.get(domain, []):
        obj = objects.get(key) or {}
        human = _human_string(obj.get("value") if isinstance(obj, dict) else obj)
        if human:
            return human
    for key, obj in objects.items():
        if key.endswith(".active") or key in ("active",) or key.endswith(".owned") or key.endswith(".purchased"):
            continue
        val = obj.get("value") if isinstance(obj, dict) else obj
        human = _human_string(val)
        if human and len(human) <= 80:
            return human
    return None


def assemble_life_map(
    *,
    profile: Optional[Dict[str, Any]],
    study_plans: Optional[List[Dict[str, Any]]],
    travel_projects: Optional[List[Dict[str, Any]]],
    today: Optional[date] = None,
    life_os_plans: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[
    List[PresentationArea],
    List[PresentationSituation],
    List[EvidenceRef],
    str,
    List[SituationCandidate],
]:
    evidence: List[EvidenceRef] = []
    areas: List[PresentationArea] = []
    situations: List[PresentationSituation] = []
    candidates: List[SituationCandidate] = []
    today = today or date.today()

    domains = (profile or {}).get("domains") or {}
    for domain_key, dom in domains.items():
        key = str(domain_key or "").lower().strip()
        if not key or key in HIDDEN_DOMAINS:
            continue
        title = DOMAIN_LABELS_IT.get(key)
        if not title:
            continue
        objects = (dom or {}).get("objects") or {}
        if not isinstance(objects, dict):
            continue
        known = False
        for fact_key, obj in objects.items():
            val = obj.get("value") if isinstance(obj, dict) else obj
            if not _present(val):
                continue
            known = True
            # Skip boolean-only evidence noise for Gemini pack (still counts as known area)
            human = _human_string(val)
            if human:
                eid = f"profile:{key}:{fact_key}"
                evidence.append(
                    EvidenceRef(
                        id=eid,
                        kind="life_profile_fact",
                        label=f"{title} · {fact_key}",
                        summary=human[:120],
                    )
                )
        if not known:
            continue
        # Boolean-only domain: still show area (Prompt 5 parity) with synthetic evidence id
        if not any(e.id.startswith(f"profile:{key}:") for e in evidence):
            eid = f"profile:{key}:_present"
            evidence.append(
                EvidenceRef(
                    id=eid,
                    kind="life_profile_fact",
                    label=title,
                    summary="ambito presente nel profilo",
                )
            )
        identity = _identity_for_domain(key, objects)
        areas.append(
            PresentationArea(
                id=f"area:{key}",
                domain=key,
                title=title,
                identity=identity,
            )
        )

    order = {d: i for i, d in enumerate(DOMAIN_ORDER)}
    areas.sort(key=lambda a: (order.get(a.domain, 1000), a.title))

    # DEV presentation trace: why study/life_os rows are shown or hidden
    import os as _os

    _dev_trace = (_os.environ.get("LIFE_MAP_TRACE") or _os.environ.get("DEV") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    presentation_trace: List[Dict[str, Any]] = []

    for plan in study_plans or []:
        status = str(plan.get("status") or "").lower()
        if status not in LIVE_STATUSES:
            if _dev_trace:
                presentation_trace.append({
                    "source": "study_plan",
                    "id": plan.get("id"),
                    "shown": False,
                    "reason": f"status:{status}",
                })
            continue
        title = (plan.get("exam_name") or plan.get("subject") or "").strip()
        if not title:
            continue
        n = _days_until(plan.get("exam_date"), today)
        sessions = plan.get("sessions") or []
        open_today = any(
            (s.get("starts_at") or "")[:10] == today.isoformat()
            and (s.get("status") or "") in ("planned", "in_progress")
            for s in sessions
        )
        # Past exam, or exam-day with no remaining sessions → hide from Contesti
        # (non-destructive; legacy row remains in DB)
        if n is not None and n < 0:
            if _dev_trace:
                presentation_trace.append({
                    "source": "study_plan",
                    "id": plan.get("id"),
                    "shown": False,
                    "reason": "EXPIRED_STALE",
                    "relation": "HISTORICAL",
                })
            continue
        if n == 0 and not open_today:
            if _dev_trace:
                presentation_trace.append({
                    "source": "study_plan",
                    "id": plan.get("id"),
                    "shown": False,
                    "reason": "EXPIRED_STALE_exam_day_no_session",
                    "relation": "HISTORICAL",
                })
            continue
        pid = str(plan.get("id") or "")
        if not pid:
            continue
        temporal = _study_temporal(plan.get("exam_date"), today)
        if _dev_trace:
            presentation_trace.append({
                "source": "study_plan",
                "id": pid,
                "shown": True,
                "reason": "ACTIVE_OR_UPCOMING",
                "relation": "DISTINCT",
            })
        subject = plan.get("subject")
        summary = subject if subject and subject != title else None
        sid = f"study:{pid}"
        entity = (plan.get("subject") or plan.get("exam_name") or title).strip()
        lineage: List[str] = []
        sp = plan.get("source_priority_id")
        if sp:
            lineage.append(f"home_item:{sp}")
        lo = plan.get("life_object_id")
        lo_ids = [str(lo)] if lo else []
        evidence.append(
            EvidenceRef(
                id=sid,
                kind="study_plan",
                label=title,
                summary=(temporal or title)[:120],
            )
        )
        situations.append(
            PresentationSituation(
                id=sid,
                kind="study",
                title=title,
                temporal=temporal,
                summary=summary,
                href=f"/study-plan/{pid}",
            )
        )
        candidates.append(
            SituationCandidate(
                candidate_id=sid,
                kind="study",
                title=title,
                temporal=temporal,
                summary=summary,
                href=f"/study-plan/{pid}",
                source_type="study_plan",
                source_id=pid,
                lineage_refs=lineage,
                entity_raw=entity,
                temporal_anchor=temporal_anchor_day(plan.get("exam_date")),
                updated_at=plan.get("updated_at"),
                evidence_refs=[sid],
                life_object_ids=lo_ids,
            )
        )

    for project in travel_projects or []:
        status = str(project.get("status") or "").lower()
        if status not in LIVE_STATUSES:
            continue
        title = (project.get("title") or project.get("destination") or "").strip()
        if not title:
            continue
        tid = str(project.get("id") or "")
        if not tid:
            continue
        range_s = _date_range(project.get("start_date"), project.get("end_date"))
        days = project.get("days_until")
        days_i = int(days) if isinstance(days, (int, float)) else None
        phase_s = _travel_phase(project.get("phase"), days_i)
        dest = project.get("destination")
        if range_s and phase_s:
            summary = phase_s
        elif dest and dest != title:
            summary = str(dest)
        else:
            summary = phase_s
        sid = f"travel:{tid}"
        entity = (project.get("destination") or project.get("title") or title).strip()
        lineage = []
        sp = project.get("source_priority_id")
        if sp:
            lineage.append(f"home_item:{sp}")
        lo = project.get("life_object_id")
        lo_ids = [str(lo)] if lo else []
        evidence.append(
            EvidenceRef(
                id=sid,
                kind="travel_project",
                label=title,
                summary=(range_s or phase_s or title)[:120],
            )
        )
        situations.append(
            PresentationSituation(
                id=sid,
                kind="travel",
                title=title,
                temporal=range_s or phase_s,
                summary=summary,
                href=f"/travel-project/{tid}",
            )
        )
        candidates.append(
            SituationCandidate(
                candidate_id=sid,
                kind="travel",
                title=title,
                temporal=range_s or phase_s,
                summary=summary,
                href=f"/travel-project/{tid}",
                source_type="travel_project",
                source_id=tid,
                lineage_refs=lineage,
                entity_raw=entity,
                temporal_anchor=temporal_anchor_range(
                    project.get("start_date"), project.get("end_date")
                ),
                updated_at=project.get("updated_at"),
                evidence_refs=[sid],
                life_object_ids=lo_ids,
            )
        )

    for plan in life_os_plans or []:
        status = str(plan.get("status") or "").lower()
        if status not in LIVE_STATUSES:
            continue
        title = (plan.get("summary") or "").strip()
        if not title:
            continue
        pid = str(plan.get("id") or "")
        if not pid:
            continue
        target = (plan.get("target_date") or "")[:10]
        temporal = None
        if target:
            try:
                td = datetime.fromisoformat(target).date()
                days = (td - today).days
                temporal = f"tra {days}g" if days >= 0 else "scadenza"
            except Exception:
                temporal = target
        next_title = None
        for it in sorted(
            plan.get("items") or [],
            key=lambda x: (x.get("order") or 0, x.get("due_date") or ""),
        ):
            if it.get("status") in ("not_started", "in_progress", None, ""):
                next_title = (it.get("title") or "").strip() or None
                break
        sid = f"life_os:{pid}"
        sess = plan.get("conversation_session_id")
        href = f"/goal-workspace/{pid}" if pid else (f"/ora/{sess}" if sess else None)
        evidence.append(
            EvidenceRef(
                id=sid,
                kind="life_os_plan",
                label=title,
                summary=(next_title or plan.get("desired_outcome") or title)[:120],
            )
        )
        situations.append(
            PresentationSituation(
                id=sid,
                kind="life_os",
                title=title,
                temporal=temporal,
                summary=next_title or plan.get("desired_outcome") or "",
                href=href,
            )
        )
        candidates.append(
            SituationCandidate(
                candidate_id=sid,
                kind="life_os",
                title=title,
                temporal=temporal,
                summary=next_title or "",
                href=href,
                source_type="life_os_plan",
                source_id=pid,
                lineage_refs=[],
                entity_raw=title,
                temporal_anchor=temporal_anchor_day(target) if target else None,
                updated_at=plan.get("updated_at"),
                evidence_refs=[sid],
                life_object_ids=[],
            )
        )

    situations.sort(key=lambda s: (0 if s.temporal else 1, s.title))

    # Fingerprint from evidence + candidate identity signals (not presentation noise)
    fp_payload = {
        "areas": [a.model_dump() for a in areas],
        "candidates": [
            {
                "id": c.candidate_id,
                "source": f"{c.source_type}:{c.source_id}",
                "entity": c.entity_raw,
                "anchor": c.temporal_anchor,
                "lineage": c.lineage_refs,
                "updated_at": c.updated_at,
            }
            for c in candidates
        ],
        "evidence": [e.model_dump() for e in evidence],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fp_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:24]

    if _dev_trace and presentation_trace:
        import logging

        logging.getLogger("ora.life_map").info(
            "life_map presentation_trace count=%s sample=%s",
            len(presentation_trace),
            presentation_trace[:12],
        )

    return areas, situations, evidence, fingerprint, candidates
