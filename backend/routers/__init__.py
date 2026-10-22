""""ORA modular routers. Each domain owns its own router file."""
from action_engine import action_engine_router, study_plans_router, travel_projects_router
from connectors.apple_calendar import apple_calendar_router
from connectors.bank.router import router as bank_router
from lifesearch.router import router as lifesearch_router
from connectors.gmail.router import router as gmail_router
from connectors.google_calendar import google_calendar_router
from documents import documents_router
from energy_offers.router import router as energy_offers_router
from goal_engine import goal_engine_router
from home import router as home_router
from intent_engine import intent_engine_router
from llm.router import router as llm_router
from proactive_engine import proactive_engine_router
from conversation_engine import conversation_engine_router
from semantic_engine.router import semantic_engine_router
from ai_life_strategist.router import router as strategist_router
from life_profile.router import router as life_profile_router
from life_setup.router import router as life_setup_router
from life_objects import life_objects_router
from life_map import life_map_router
from life_memory import life_memory_router
from activity import activity_router
from agenda.router import router as agenda_router
from weather_router import router as weather_router
from accommodation.router import router as accommodation_router

from . import (
    admin, auth, auto_link as auto_link_router, behavior as behavior_router,
    behavior_shadow as behavior_shadow_router, calendar_events as calendar_events_router,
    connectors as connectors_router, context as context_router, daily as daily_router,
    financial as financial_router, decisions as decisions_router, ingestion as ingestion_router,
    knowledge as knowledge_router, legacy_tasks, life_graph as life_graph_router,
    life_os as life_os_router, memory as memory_router, permissions as permissions_router,
)

ALL_ROUTERS = [
    auth.router, agenda_router, weather_router, accommodation_router,
    decisions_router.router, legacy_tasks.router, life_graph_router.router,
    knowledge_router.router, auto_link_router.router, context_router.router,
    admin.router, memory_router.router, permissions_router.router, connectors_router.router,
    ingestion_router.router, google_calendar_router, gmail_router, apple_calendar_router,
    bank_router, daily_router.router, financial_router.router, lifesearch_router,
    behavior_router.router, behavior_shadow_router.router, calendar_events_router.router,
    documents_router, energy_offers_router, home_router, intent_engine_router,
    action_engine_router, study_plans_router, travel_projects_router, goal_engine_router,
    proactive_engine_router, conversation_engine_router, semantic_engine_router,
    strategist_router, life_profile_router, life_setup_router, life_objects_router,
    life_map_router, activity_router, life_memory_router, life_os_router.router, llm_router,
]

# Optional domain routers remain isolated so optional dependencies cannot break bootstrap.
def _append_optional(module: str, attribute: str, package: bool = False):
    try:
        if package:
            mod = __import__(module, fromlist=[attribute])
            ALL_ROUTERS.append(getattr(mod, attribute))
        else:
            mod = __import__(module, fromlist=["router"])
            ALL_ROUTERS.append(getattr(mod, attribute))
    except Exception:
        pass

_append_optional("contacts.router", "router")
_append_optional("location.router", "router")
_append_optional("places.router", "router")
_append_optional("opportunities.router", "router")
_append_optional("delivery.router", "router")
_append_optional("ambient.router", "router")
_append_optional("agent.router", "router")
_append_optional("connected.router", "router")
_append_optional("visuals.router", "router")
_append_optional("waiting.router", "router")
_append_optional("voice.router", "router")
_append_optional("telephone.router", "router")
_append_optional("autonomy.router", "router")
_append_optional("preparation.router", "router")

from vision_xray import router as vision_xray_router
ALL_ROUTERS.append(vision_xray_router)
from whatsapp.router import router as whatsapp_router
ALL_ROUTERS.append(whatsapp_router)
from .loyalty_wallet import router as loyalty_wallet_router
ALL_ROUTERS.append(loyalty_wallet_router)
from wardrobe.router import router as wardrobe_router
ALL_ROUTERS.append(wardrobe_router)
from .house_scans import router as house_scans_router
ALL_ROUTERS.append(house_scans_router)
from recipes.router import router as recipes_router
ALL_ROUTERS.append(recipes_router)

# Weekly meal planner and generated shopping list, sharing recipe ownership.
from cooking_planner.router import router as cooking_planner_router
ALL_ROUTERS.append(cooking_planner_router)
