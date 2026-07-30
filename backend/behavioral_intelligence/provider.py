"""BehaviorProfileProvider — Context Assembler integration.

Gated by env flag ``BEHAVIOR_PROFILE_ENABLED``. When disabled (default),
this provider is a no-op:

* returns no signals
* leaves ``context_hash`` unchanged
* NEVER queries the DB

When enabled it can be plugged into the ContextAssemblerService's
provider chain. For iteration 15 the flag stays OFF; the class exists
only to prove the wiring is ready for future iterations.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .service import BehavioralIntelligenceService


def _flag_on() -> bool:
    return os.environ.get("BEHAVIOR_PROFILE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


class BehaviorProfileProvider:
    """Read-only context provider. Never mutates DB, never persists signals."""

    provider_id = "behavior_profile_provider"
    provider_version = "v1.0"

    def __init__(self, service: BehavioralIntelligenceService):
        self._service = service

    @property
    def enabled(self) -> bool:
        return _flag_on()

    async def signals(self, user_id: str) -> List[Dict[str, Any]]:
        """Return a (possibly empty) list of context signals.

        When the flag is OFF (default) this returns an empty list so the
        Context Assembler produces the exact same snapshot / hash as before
        this iteration. This guarantees no regressions on other modules.
        """
        if not self.enabled:
            return []

        # Enabled path: expose non-invasive summary tags. No PII, no titles.
        profile = await self._service.get_profile(user_id, persist=False)
        return [
            {
                "kind": "behavior_profile",
                "provider": self.provider_id,
                "version": self.provider_version,
                "confidence": profile.confidence.value,
                "sample_size": profile.sample_size,
                "attributes": {
                    "planning_style": profile.planning_style.value,
                    "completion_style": profile.completion_style.value,
                    "activity_level": profile.activity_level.value,
                    "calendar_usage": profile.calendar_usage.value,
                    "consistency": profile.consistency.value,
                    "procrastination_index": profile.procrastination_index,
                    "avg_completion_minutes": profile.average_completion_time_minutes,
                    "avg_postpone_minutes": profile.average_postpone_time_minutes,
                    "completion_rate": profile.decision_completion_rate,
                    "postpone_rate": profile.decision_postpone_rate,
                },
            }
        ]
