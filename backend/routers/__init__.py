"""ORA modular routers. Each domain owns its own router file."""
from action_engine import action_engine_router, study_plans_router, travel_projects_router
from connectors.apple_calendar import apple_calendar_router
from connectors.google_calendar import google_calendar_router
from documents import documents_router
from goal_engine import goal_engine_router
from home import router as home_router
from intent_engine import intent_engine_router
from llm.router import router as llm_router
from proactive_engine import router as proactive_engine_router
from conversation_engine import conversation_engine_router
from semantic_engine.router import semantic_engine_router
from ai_life_strategist.router import router as strategist_router
from life_setup.router import router as life_setup_router
from life_objects import life_objects_router
from life_map import life_map_router
from life_memory import life_memory_router

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
    life_os as life_os_router,
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
    documents_router,
    home_router,
    intent_engine_router,
    action_engine_router,
    study_plans_router,
    travel_projects_router,
    goal_engine_router,
    proactive_engine_router,
    conversation_engine_router,
    semantic_engine_router,
    strategist_router,
    life_setup_router,
    life_objects_router,
    life_map_router,
    life_memory_router,
    life_os_router.router,
    llm_router,
]

# Foreground location + presence (V2.7.1)
try:
    from location.router import router as location_router

    ALL_ROUTERS.append(location_router)
except Exception:
    pass

# Contextual card visuals (PX1.2)
try:
    from visuals.router import router as visuals_router

    ALL_ROUTERS.append(visuals_router)
except Exception:
    pass
