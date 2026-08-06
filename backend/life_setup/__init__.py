"""Life Setup — first-launch natural conversation + Life Profile persistence."""
from __future__ import annotations

from life_setup.service import LifeSetupService, life_setup_enabled, get_life_setup_service

__all__ = [
    "LifeSetupService",
    "life_setup_enabled",
    "get_life_setup_service",
]
