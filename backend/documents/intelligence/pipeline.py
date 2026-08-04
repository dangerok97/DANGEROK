"""Pipeline states and phase records for intelligent documents."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

PIPELINE_VERSION = "intel-docs-1.0"

PIPELINE_STATES = (
    "uploaded",
    "queued",
    "extracting",
    "classifying",
    "analyzing",
    "action_required",
    "completed",
    "failed",
    "needs_review",
)

# UI-friendly Italian labels
STATE_LABELS_IT = {
    "uploaded": "Documento caricato",
    "queued": "In coda per l'analisi",
    "extracting": "Estrazione del testo",
    "classifying": "Identificazione del contenuto",
    "analyzing": "Creazione delle informazioni utili",
    "action_required": "Serve una verifica",
    "completed": "Analisi completata",
    "failed": "Analisi non riuscita",
    "needs_review": "Serve una verifica",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PipelineState:
    @staticmethod
    def initial() -> dict[str, Any]:
        return {
            "pipeline_status": "uploaded",
            "pipeline_status_label": STATE_LABELS_IT["uploaded"],
            "pipeline_version": PIPELINE_VERSION,
            "pipeline_attempts": 0,
            "pipeline_error": None,
            "pipeline_provider": None,
            "pipeline_started_at": None,
            "pipeline_finished_at": None,
            "pipeline_duration_ms": None,
            "pipeline_phases": [],
            "pipeline_updated_at": _now(),
        }

    @staticmethod
    def set_status(
        doc: dict[str, Any],
        status: str,
        *,
        error: Optional[str] = None,
        provider: Optional[str] = None,
        phase_extra: Optional[dict] = None,
    ) -> dict[str, Any]:
        if status not in PIPELINE_STATES:
            raise ValueError(f"invalid pipeline status: {status}")
        now = _now()
        phases = list(doc.get("pipeline_phases") or [])
        phase = {
            "status": status,
            "at": now,
            "error": error,
            "provider": provider,
        }
        if phase_extra:
            phase.update(phase_extra)
        phases.append(phase)
        # keep last 40 phases
        phases = phases[-40:]
        updates: dict[str, Any] = {
            "pipeline_status": status,
            "pipeline_status_label": STATE_LABELS_IT.get(status, status),
            "pipeline_version": PIPELINE_VERSION,
            "pipeline_error": error,
            "pipeline_phases": phases,
            "pipeline_updated_at": now,
        }
        if provider is not None:
            updates["pipeline_provider"] = provider
        if status == "queued":
            updates["pipeline_attempts"] = int(doc.get("pipeline_attempts") or 0) + 1
            updates["pipeline_started_at"] = now
            updates["pipeline_finished_at"] = None
        if status in ("completed", "failed", "needs_review", "action_required"):
            updates["pipeline_finished_at"] = now
            started = doc.get("pipeline_started_at") or updates.get("pipeline_started_at")
            if started:
                try:
                    t0 = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(now.replace("Z", "+00:00"))
                    updates["pipeline_duration_ms"] = int((t1 - t0).total_seconds() * 1000)
                except Exception:
                    pass
        return updates
