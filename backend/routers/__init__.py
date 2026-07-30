"""ORA modular routers. Each domain owns its own router file."""
from . import (
    auth,
    decisions as decisions_router,
    legacy_tasks,
    life_graph as life_graph_router,
    knowledge as knowledge_router,
    auto_link as auto_link_router,
    context as context_router,
    admin,
    memory as memory_router,
    permissions as permissions_router,
    connectors as connectors_router,
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
]
