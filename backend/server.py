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


@api.get("/health")
async def health():
    """Minimal non-sensitive health check for local / CI verification."""
    import os
    from llm import llm_status

    db_ok = False
    try:
        await client.admin.command("ping")
        db_ok = True
    except Exception:
        db_ok = False

    llm = llm_status()
    google_oauth = all(
        (os.environ.get(k) or "").strip()
        for k in (
            "GOOGLE_OAUTH_CLIENT_ID",
            "GOOGLE_OAUTH_CLIENT_SECRET",
            "GOOGLE_OAUTH_REDIRECT_URI",
        )
    )
    return {
        "app": "ORA",
        "status": "ok" if db_ok else "degraded",
        "environment": os.environ.get("ENVIRONMENT", "development"),
        "database": {"ok": db_ok, "name": os.environ.get("DB_NAME", "")},
        "llm": {
            "provider": llm.get("provider"),
            "configured": bool(llm.get("configured")),
            "model": llm.get("model"),
            "preferred": llm.get("preferred"),
            "priority": ["gemini", "openai", "ollama", "emergent"],
        },
        "integrations": {
            "google_oauth_configured": google_oauth,
            "emergent_google_auth": os.environ.get("EMERGENT_GOOGLE_AUTH", "0").lower()
            in ("1", "true", "yes"),
        },
    }


# Mount every domain router under /api.
for r in ALL_ROUTERS:
    api.include_router(r)


@app.on_event("startup")
async def startup():
    # Users
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    # Social identities (Google / Apple / password)
    from social_auth import ensure_identity_indexes, migrate_password_identities
    await ensure_identity_indexes(db)
    await migrate_password_identities(db)
    # Document intelligence worker + indexes
    from documents.intelligence.worker import start_worker
    from deps import get_intelligence_service
    await get_intelligence_service().ensure_ready()
    start_worker()
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

    # Action Center (Iteration 11)
    await db.decision_action_history.create_index("id", unique=True)
    await db.decision_action_history.create_index([("user_id", 1), ("decision_id", 1), ("timestamp", 1)])
    await db.decision_action_history.create_index([("user_id", 1), ("timestamp", -1)])

    # Behavioral Intelligence (Iteration 15)
    try:
        from behavioral_intelligence import BehavioralIntelligenceService
        bhv = BehavioralIntelligenceService(db)
        await bhv.ensure_ready()
        logger.info("Behavioral Intelligence indexes ready")
    except Exception:
        logger.exception("Behavioral Intelligence bootstrap failed (non-fatal)")

    # Behavior-Aware Shadow (Iteration 17) — always ensure indexes so
    # activating BEHAVIOR_SHADOW_MODE at runtime is safe. The shadow
    # service itself is idle unless BOTH flags are enabled.
    try:
        from behavior_aware_decisions import BehaviorShadowService
        _shadow = BehaviorShadowService(db)
        await _shadow.ensure_ready()
        logger.info("Behavior-Aware Shadow indexes ready")
    except Exception:
        logger.exception("Behavior-Aware Shadow bootstrap failed (non-fatal)")

    # Documents (Iteration 19) — indexes for the new module.
    try:
        from deps import get_document_service
        await get_document_service().ensure_ready()
        logger.info("Documents indexes ready")
    except Exception:
        logger.exception("Documents bootstrap failed (non-fatal)")

    # Home V2 intelligence dashboard
    try:
        from home.service import HomeService
        await HomeService(db).ensure_indexes()
        logger.info("Home V2 indexes ready")
    except Exception:
        logger.exception("Home V2 bootstrap failed (non-fatal)")

    # Action Engine — guided priority flows
    try:
        from action_engine import ActionEngineService
        from deps import decisions as _decisions, knowledge as _knowledge, life_graph as _life_graph
        await ActionEngineService(
            db, life_graph=_life_graph, knowledge=_knowledge, decisions=_decisions,
        ).ensure_indexes()
        logger.info("Action Engine indexes ready")
    except Exception:
        logger.exception("Action Engine bootstrap failed (non-fatal)")

    # Goal Engine — shadow identity/lifecycle (no Home UX yet)
    try:
        from goal_engine import GoalService
        from deps import knowledge as _kn_ge, life_graph as _lg_ge
        await GoalService(db, life_graph=_lg_ge, knowledge=_kn_ge).ensure_indexes()
        logger.info("Goal Engine indexes ready")
    except Exception:
        logger.exception("Goal Engine bootstrap failed (non-fatal)")

    # Proactive Engine — IF/WHEN/HOW/WHY intervene (Home "ORA TI CONSIGLIA")
    try:
        from proactive_engine import ProactiveEngineService
        await ProactiveEngineService(db).ensure_indexes()
        logger.info("Proactive Engine indexes ready")
    except Exception:
        logger.exception("Proactive Engine bootstrap failed (non-fatal)")

    # Conversation Engine — entry orchestrator (NOT a chatbot)
    try:
        from conversation_engine import ConversationEngineService
        from deps import decisions as _dec_ce, knowledge as _kn_ce, life_graph as _lg_ce
        await ConversationEngineService(
            db, life_graph=_lg_ce, knowledge=_kn_ce, decisions=_dec_ce,
        ).ensure_indexes()
        logger.info("Conversation Engine indexes ready")
    except Exception:
        logger.exception("Conversation Engine bootstrap failed (non-fatal)")

    # Life Setup + AI Life Strategist — first-launch conversation (NOT a wizard)
    try:
        from life_setup import get_life_setup_service
        from deps import knowledge as _kn_ls, life_graph as _lg_ls
        svc = get_life_setup_service(db)
        svc.life_graph = _lg_ls
        svc.knowledge = _kn_ls
        await svc.ensure_indexes()
        logger.info("Life Setup indexes ready")
    except Exception:
        logger.exception("Life Setup bootstrap failed (non-fatal)")

    # Life Object Engine — core identity (shadow writes; Home UX unchanged)
    try:
        from life_objects import LifeObjectService
        from deps import knowledge as _kn_lo, life_graph as _lg_lo
        await LifeObjectService(db, life_graph=_lg_lo, knowledge=_kn_lo).ensure_indexes()
        logger.info("Life Object Engine indexes ready")
    except Exception:
        logger.exception("Life Object Engine bootstrap failed (non-fatal)")

    # Life Map — Contesti cognition foundation (deterministic + optional Gemini)
    try:
        from life_map.service import get_life_map_service
        await get_life_map_service(db).ensure_indexes()
        logger.info("Life Map indexes ready")
    except Exception:
        logger.exception("Life Map bootstrap failed (non-fatal)")

    # Life Memory — Memoria durable learned facts (deterministic + optional Gemini)
    try:
        from life_memory.service import get_life_memory_service
        from life_memory.clarify import get_clarification_service
        await get_life_memory_service(db).ensure_indexes()
        await get_clarification_service(db).ensure_indexes()
        logger.info("Life Memory indexes ready")
    except Exception:
        logger.exception("Life Memory bootstrap failed (non-fatal)")

    # Life OS — generic plans & artifacts (AI Core execution layer)
    try:
        from life_os.service import LifeOsService
        await LifeOsService(db).ensure_indexes()
        logger.info("Life OS indexes ready")
    except Exception:
        logger.exception("Life OS bootstrap failed (non-fatal)")

    # AI Core ContextFile — session evidence refs (Documents V2 holds blobs)
    try:
        from situations.service import SituationService

        await SituationService(db).ensure_indexes()
        logger.info("Situation indexes ready")
    except Exception:
        logger.exception("Situation indexes failed (non-fatal)")

    # AI Core ContextFile — session evidence refs (Documents V2 holds blobs)
    try:
        from conversation_engine.ai_core.files.service import ContextFileService

        await ContextFileService(db).ensure_indexes()
        logger.info("Life OS context file indexes ready")
    except Exception:
        logger.exception("ContextFile indexes failed (non-fatal)")

    # Location signals + presence (V2.7.1 — short TTL raw GPS)
    try:
        from location.service import LocationService

        await LocationService(db).ensure_indexes()
        logger.info("Location indexes ready")
    except Exception:
        logger.exception("Location indexes failed (non-fatal)")

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
        "knowledge, auto_link, context_assembler, permissions, connectors, "
        "home_v2, action_engine, goal_engine, proactive_engine, conversation_engine."
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


# --- Behavioral middleware (Iteration 15) ----------------------------
# Purely observational: fires idempotent "first_app_open_today" and
# "manual_refresh" events into the behavioral timeline. Never blocks the
# request, never touches other modules. All failures are swallowed so a
# behavioral hiccup can never break the API.
import jwt as _pyjwt  # noqa: E402
from deps import JWT_SECRET as _JWT_SECRET, JWT_ALGO as _JWT_ALGO  # noqa: E402
from behavioral_intelligence import BehavioralIntelligenceService as _BhvSvc  # noqa: E402

_bhv_singleton: _BhvSvc | None = None


def _bhv() -> _BhvSvc:
    global _bhv_singleton
    if _bhv_singleton is None:
        _bhv_singleton = _BhvSvc(db)
    return _bhv_singleton


def _user_id_from_request(headers) -> str | None:
    auth = headers.get("authorization") or headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    tok = auth.split(" ", 1)[1].strip()
    try:
        payload = _pyjwt.decode(tok, _JWT_SECRET, algorithms=[_JWT_ALGO])
        return payload.get("user_id")
    except Exception:
        return None


@app.middleware("http")
async def behavioral_observer_middleware(request, call_next):
    # Never block the response — do all work AFTER call_next.
    response = await call_next(request)
    try:
        path = request.url.path
        if not path.startswith("/api/") or "/behavior" in path:
            return response
        if request.method != "GET":
            return response
        uid = _user_id_from_request(request.headers)
        if not uid:
            return response
        svc = _bhv()
        # Refresh: any GET on decisions/top or daily/today is treated as a refresh
        if path.endswith("/decisions/top") or path.endswith("/daily/today"):
            await svc.observers.record_manual_refresh(uid)
        # First open today: idempotent per (uid, UTC date)
        await svc.observers.record_app_open_if_needed(uid)
    except Exception:
        # Behavioral engine is purely observational — never break requests.
        logger.debug("behavioral middleware swallowed exception", exc_info=True)
    return response

