"""ORA modular routers. Each domain owns its own router file."""
from connectors.apple_calendar import apple_calendar_router
from connectors.google_calendar import google_calendar_router

from . import (
    admin,
    auth,
    auto_link as auto_link_router,
    behavior as behavior_router,
    behavior_shadow as behavior_shadow_router,
    connectors as connectors_router,
    context as context_router,
    daily as daily_router,
    decisions as decisions_router,
    ingestion as ingestion_router,
    knowledge as knowledge_router,
    legacy_tasks,
    life_graph as life_graph_router,
    memory as memory_router,
    permissions as permissions_router,
)

ALL_ROUTERS = [
    auth.router,
    decisions_router.router,
    legacy_tasks.router,
    life_graph_router.router,
    knowledge_router.router,
    auto_link_router.router,
    context_router.router,
    admin.router,
    memory_router.router,
    permissions_router.router,
    connectors_router.router,
    ingestion_router.router,
    google_calendar_router,
    apple_calendar_router,
    daily_router.router,
    behavior_router.router,
    behavior_shadow_router.router,
]
