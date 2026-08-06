"""ORA Life Object Engine — canonical model of user reality (shadow mode).

Life Objects hold canonical truth. Conversation, Goal, Documents, Brain,
Proactive, Home, Travel, Study keep existing as satellites that read/write
objects. Home UX stays Goal-aware until LIFE_OBJECT_HOME_UI_ENABLED (default OFF).
"""
from life_objects.models import LifeObject, LifeObjectCreateBody, LifeObjectPatchBody
from life_objects.router import router as life_objects_router
from life_objects.service import (
    LifeObjectService,
    get_life_object_service,
    life_object_engine_enabled,
    life_object_home_ui_enabled,
)
from life_objects.shadow import (
    shadow_attach_goal,
    shadow_upsert_from_document,
    shadow_upsert_from_study,
    shadow_upsert_from_travel,
)

__all__ = [
    "LifeObject",
    "LifeObjectCreateBody",
    "LifeObjectPatchBody",
    "LifeObjectService",
    "get_life_object_service",
    "life_object_engine_enabled",
    "life_object_home_ui_enabled",
    "life_objects_router",
    "shadow_upsert_from_document",
    "shadow_attach_goal",
    "shadow_upsert_from_travel",
    "shadow_upsert_from_study",
]
