"""Source adapters for Home V2. Each must never raise out of gather_all."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Tuple

from home.models import ConnectionWarning, HomeItem

from .action_engine_adapter import load_action_engine_items
from .activities import load_activities
from .brain import load_brain_signals
from .conversation_adapter import load_conversation_items
from .life_setup import load_life_setup_items
from .life_os_plan import load_life_os_plans
from .decisions_adapter import load_decisions
from .document_actions import load_document_actions
from .documents import load_documents
from .event_candidates import load_event_candidates
from .google_calendar import load_google_calendar_events, google_connection_state
from .internal_calendar import load_internal_calendar
from .reminders import load_reminders
from .study import load_study_state
from .travel import load_travel_state

logger = logging.getLogger("ora.home.adapters")

AdapterFn = Callable[..., Any]


async def _safe(
    name: str,
    coro,
) -> Tuple[List[HomeItem], List[ConnectionWarning]]:
    try:
        result = await coro
        if isinstance(result, tuple):
            items, warnings = result
            return list(items or []), list(warnings or [])
        return list(result or []), []
    except Exception as e:
        logger.warning("home adapter %s failed: %s", name, type(e).__name__)
        return [], [ConnectionWarning(
            code=f"source_error_{name}",
            message=f"Fonte {name} temporaneamente non disponibile",
            severity="warning",
        )]


async def gather_all(db, user_id: str) -> Tuple[List[HomeItem], List[ConnectionWarning], Dict[str, Any]]:
    """Collect from all sources; one failure never blocks Home."""
    gcal_state_task = asyncio.create_task(google_connection_state(db, user_id))

    results = await asyncio.gather(
        _safe("google_calendar", load_google_calendar_events(db, user_id)),
        _safe("internal_calendar", load_internal_calendar(db, user_id)),
        _safe("documents", load_documents(db, user_id)),
        _safe("event_candidates", load_event_candidates(db, user_id)),
        _safe("document_actions", load_document_actions(db, user_id)),
        _safe("study", load_study_state(db, user_id)),
        _safe("travel", load_travel_state(db, user_id)),
        _safe("activities", load_activities(db, user_id)),
        _safe("reminders", load_reminders(db, user_id)),
        _safe("decisions", load_decisions(db, user_id)),
        _safe("brain", load_brain_signals(db, user_id)),
        _safe("action_engine", load_action_engine_items(db, user_id)),
        _safe("conversation", load_conversation_items(db, user_id)),
        _safe("life_setup", load_life_setup_items(db, user_id)),
        _safe("life_os_plan", load_life_os_plans(db, user_id)),
    )

    items: List[HomeItem] = []
    warnings: List[ConnectionWarning] = []
    for its, warns in results:
        items.extend(its)
        warnings.extend(warns)

    try:
        gcal = await gcal_state_task
    except Exception:
        gcal = {"connected": False, "instance": None}

    if not gcal.get("connected"):
        warnings.append(ConnectionWarning(
            code="google_calendar_disconnected",
            message="Collega Google Calendar per arricchire le priorità",
            severity="info",
            dismissible=True,
        ))

    return items, warnings, gcal
