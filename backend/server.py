"""
ORA — Life Operating System — Backend entry point.

Kept intentionally THIN: only bootstrap, middleware, startup / shutdown
and router wiring. Every domain lives in `routers/<domain>.py`. Business
logic sits in dedicated packages: `decision_engine/`, `life_graph/`,
`knowledge/`, `auto_link/`, `context_assembler/`, `permissions/`,
`connectors/`.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, FastAPI
from starlette.middleware.cors import CORSMiddleware

from deps import client, db, get_permissions_service
from routers import ALL_ROUTERS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ora")


app = FastAPI(title="ORA API")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"app": "ORA", "status": "ok"}


# Mount every domain router under /api.
for r in ALL_ROUTERS:
    api.include_router(r)


@app.on_event("startup")
async def startup():
    # Users
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    # Legacy tasks (kept).
    await db.tasks.create_index([("user_id", 1), ("status", 1), ("score", -1)])
    # Decisions
    await db.decisions.create_index([("user_id", 1), ("status", 1)])
    await db.decisions.create_index("id", unique=True)
    await db.decisions.create_index([("user_id", 1), ("node_ids", 1)])
    # Life Graph
    await db.life_nodes.create_index("id", unique=True)
    await db.life_nodes.create_index([("user_id", 1), ("status", 1), ("type", 1)])
    await db.life_edges.create_index("id", unique=True)
    await db.life_edges.create_index([("user_id", 1), ("from_node", 1)])
    await db.life_edges.create_index([("user_id", 1), ("to_node", 1)])
    # Knowledge Layer
    await db.node_knowledge.create_index([("user_id", 1), ("node_id", 1)], unique=True)
    await db.node_knowledge.create_index("id", unique=True, sparse=True)
    # Auto-Link
    await db.link_proposals.create_index("id", unique=True)
    await db.link_proposals.create_index([("user_id", 1), ("decision_id", 1), ("node_id", 1), ("status", 1)])
    await db.link_proposals.create_index([("user_id", 1), ("status", 1), ("created_at", -1)])
    # Context Assembler
    await db.context_snapshots.create_index("id", unique=True)
    await db.context_snapshots.create_index([("user_id", 1), ("decision_id", 1), ("status", 1), ("generated_at", -1)])
    await db.context_snapshots.create_index([("user_id", 1), ("decision_id", 1), ("context_hash", 1)])
    # Memory
    await db.memories.create_index([("user_id", 1), ("created_at", -1)])

    # Permissions
    await db.permission_consents.create_index(
        [("user_id", 1), ("capability_id", 1), ("connector_id", 1), ("connector_instance_id", 1)],
        unique=True,
        name="uniq_user_cap_conn_instance",
    )
    await db.permission_consents.create_index([("user_id", 1), ("status", 1)])
    await db.permission_consents.create_index("id", unique=True)
    await db.permission_capability_meta.create_index("id", unique=True)
    await db.permission_audit.create_index([("user_id", 1), ("timestamp", -1)])
    await db.permission_audit.create_index("event_id", unique=True)
    await db.permission_audit.create_index([("connector_id", 1), ("timestamp", -1)])
    await db.permission_audit.create_index([("capability_id", 1), ("timestamp", -1)])

    # Ingestion + Connectors + Vault (Iteration 9)
    await db.ingestion_events.create_index("id", unique=True)
    await db.ingestion_events.create_index(
        [("user_id", 1), ("connector_instance_id", 1), ("external_id", 1), ("ingested_at", -1)],
        name="idx_ing_user_instance_ext",
    )
    await db.ingestion_events.create_index([("user_id", 1), ("ingestion_status", 1), ("ingested_at", -1)])
    await db.ingestion_events.create_index([("user_id", 1), ("connector_id", 1), ("ingested_at", -1)])
    await db.connector_instances.create_index("id", unique=True)
    await db.connector_instances.create_index(
        [("user_id", 1), ("connector_id", 1), ("provider_account_id_hash", 1)],
        unique=True, name="uniq_user_conn_account",
    )
    await db.connector_instances.create_index([("user_id", 1), ("status", 1)])
    await db.secret_vault.create_index("id", unique=True)
    await db.secret_vault.create_index([("user_id", 1), ("purpose", 1)])
    await db.google_oauth_sessions.create_index("state", unique=True)
    await db.google_oauth_sessions.create_index([("user_id", 1), ("created_at", -1)])
    await db.google_oauth_sessions.create_index("expires_at")
    await db.data_revocation_plans.create_index([("user_id", 1), ("connector_instance_id", 1)])

    # Sync capability registry to Mongo (idempotent, structural fields are
    # overwritten from code; ops metadata is preserved).
    try:
        perms = get_permissions_service()
        sync_res = await perms.sync_registry()
        logger.info("Permissions registry synced: %s", sync_res)
    except Exception:
        logger.exception("Permissions registry sync failed")

    logger.info(
        "ORA backend ready. Modules online: decision_engine, life_graph, "
        "knowledge, auto_link, context_assembler, permissions, connectors."
    )


@app.on_event("shutdown")
async def shutdown():
    client.close()


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
