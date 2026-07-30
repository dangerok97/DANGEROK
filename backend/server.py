"""
ORA - Life Operating System - Backend
FastAPI + MongoDB + Emergent LLM (GPT-5.2) + Emergent Google OAuth + JWT

The reasoning core is in `decision_engine/`. This file stays thin: it wires
HTTP → service, and handles auth.
"""
from fastapi import FastAPI, APIRouter, HTTPException, Header, Depends
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import bcrypt
import jwt as pyjwt
import httpx
from pathlib import Path
from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage

from decision_engine import DecisionService
from decision_engine.service import build_seed_decisions
from life_graph import LifeGraphService, NODE_TYPES, RELATION_TYPES

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGO = "HS256"
JWT_EXPIRY_DAYS = 30

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]
decisions = DecisionService(db)
life_graph = LifeGraphService(db)

app = FastAPI(title="ORA API")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ora")


# ============================================================
# MODELS
# ============================================================
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionIn(BaseModel):
    session_token: str


class UserOut(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    provider: str


class AuthOut(BaseModel):
    token: str
    user: UserOut


class DecisionIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = "generic"
    urgency: int = 5
    importance: int = 5
    risk: int = 3
    time_required_min: int = 15
    place: Optional[str] = None
    people: Optional[List[str]] = None
    energy: int = 3
    economic_impact: int = 3
    personal_impact: int = 5
    starts_at: Optional[str] = None
    deadline: Optional[str] = None
    linked_to: Optional[List[str]] = None
    metadata: Optional[dict] = None


# Legacy task input (kept for backward compatibility).
class TaskIn(BaseModel):
    title: str
    context: Optional[str] = None
    urgency: int = 5
    importance: int = 5
    risk: int = 3
    time_required_min: int = 15
    place: Optional[str] = None
    energy: int = 3
    economic_impact: int = 3
    personal_impact: int = 5
    kind: Optional[str] = "generic"
    metadata: Optional[dict] = None


class MemoryIn(BaseModel):
    content: str
    tags: Optional[List[str]] = None


class MemoryAskIn(BaseModel):
    question: str


# --- Life Graph ---
class NodeIn(BaseModel):
    type: str = "generic"
    label: str
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None


class NodePatch(BaseModel):
    type: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


class EdgeIn(BaseModel):
    from_node: str
    to_node: str
    type: str = "related_to"
    directed: bool = False
    attributes: Optional[Dict[str, Any]] = None


class DecisionNodesLinkIn(BaseModel):
    node_ids: List[str]


# ============================================================
# AUTH HELPERS
# ============================================================
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def make_jwt(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRY_DAYS),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
        user_id = payload.get("sub")
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def upsert_user(email: str, name: Optional[str], picture: Optional[str], provider: str, password_hash: Optional[str] = None) -> dict:
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        updates = {}
        if name and not existing.get("name"):
            updates["name"] = name
        if picture and not existing.get("picture"):
            updates["picture"] = picture
        provs = set(existing.get("providers", [existing.get("provider", provider)]))
        provs.add(provider)
        updates["providers"] = list(provs)
        if password_hash and not existing.get("password_hash"):
            updates["password_hash"] = password_hash
        if updates:
            await db.users.update_one({"user_id": existing["user_id"]}, {"$set": updates})
            existing.update(updates)
        return existing
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    doc = {
        "user_id": user_id,
        "email": email,
        "name": name,
        "picture": picture,
        "provider": provider,
        "providers": [provider],
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    return doc


def user_to_out(u: dict) -> UserOut:
    return UserOut(
        user_id=u["user_id"],
        email=u["email"],
        name=u.get("name"),
        picture=u.get("picture"),
        provider=u.get("provider", "email"),
    )


# ============================================================
# SEED / MIGRATE FOR A USER
# ============================================================
async def prepare_user_decisions(user_id: str):
    """Called after any successful auth. Idempotent:
       1) Migrate legacy tasks → decisions (once).
       2) If user still has zero decisions, seed the rich starter set.
    """
    try:
        await decisions.migrate_user_tasks(user_id)
    except Exception:
        logger.exception("Legacy task migration failed for %s", user_id)

    count = await db.decisions.count_documents({"user_id": user_id})
    if count == 0:
        seeds = build_seed_decisions(user_id)
        if seeds:
            await db.decisions.insert_many(seeds)


# ============================================================
# LEGACY-COMPAT: decision → task-shape
# ============================================================
def decision_as_task(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a task-shaped dict for old clients (frontend v1).
    Retains `id`, adds `reason` and `kind` fields."""
    return {
        "id": d.get("id"),
        "user_id": d.get("user_id"),
        "title": d.get("title"),
        "context": d.get("description"),
        "urgency": d.get("urgency"),
        "importance": d.get("importance"),
        "risk": d.get("risk"),
        "time_required_min": d.get("time_required_min"),
        "energy": d.get("energy"),
        "economic_impact": d.get("economic_impact"),
        "personal_impact": d.get("personal_impact"),
        "kind": d.get("category"),
        "metadata": d.get("metadata"),
        "score": d.get("score"),
        "reason": d.get("reason"),
        "reason_tags": d.get("reason_tags"),
        "status": d.get("status"),
        "created_at": d.get("created_at"),
        "starts_at": d.get("starts_at"),
        "deadline": d.get("deadline"),
    }


# ============================================================
# ROUTES: AUTH
# ============================================================
@api.get("/")
async def root():
    return {"app": "ORA", "status": "ok"}


@api.post("/auth/register", response_model=AuthOut)
async def register(body: RegisterIn):
    existing = await db.users.find_one({"email": body.email}, {"_id": 0})
    if existing and existing.get("password_hash"):
        raise HTTPException(status_code=409, detail="Email già registrata")
    user = await upsert_user(
        email=body.email,
        name=body.name,
        picture=None,
        provider="email",
        password_hash=hash_password(body.password),
    )
    await prepare_user_decisions(user["user_id"])
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@api.post("/auth/login", response_model=AuthOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    await prepare_user_decisions(user["user_id"])
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@api.post("/auth/google-session", response_model=AuthOut)
async def google_session(body: GoogleSessionIn):
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": body.session_token},
        )
        if r.status_code != 200:
            raise HTTPException(status_code=401, detail="Google auth failed")
        data = r.json()
    user = await upsert_user(
        email=data["email"],
        name=data.get("name"),
        picture=data.get("picture"),
        provider="google",
    )
    await prepare_user_decisions(user["user_id"])
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@api.get("/auth/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return user_to_out(user)


@api.post("/auth/logout")
async def logout(user=Depends(get_current_user)):
    return {"ok": True}


# ============================================================
# ROUTES: DECISIONS (new canonical API)
# ============================================================
@api.get("/decisions")
async def list_decisions(user=Depends(get_current_user)):
    """All ranked decisions (any status)."""
    items = await decisions.ranked(user["user_id"])
    # Merge in non-open ones (unranked) at the end.
    all_docs = await decisions.list_all(user["user_id"])
    ranked_ids = {d["id"] for d in items}
    tail = [d for d in all_docs if d["id"] not in ranked_ids]
    return {"items": items + tail}


@api.get("/decisions/top")
async def top_decisions(limit: int = 3, user=Depends(get_current_user)):
    limit = max(1, min(limit, 20))
    items = await decisions.top(user["user_id"], limit=limit)
    return {"items": items}


@api.get("/decisions/{decision_id}")
async def get_decision(decision_id: str, user=Depends(get_current_user)):
    d = await decisions.get(user["user_id"], decision_id)
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return d


@api.post("/decisions")
async def create_decision(body: DecisionIn, user=Depends(get_current_user)):
    doc = await decisions.create(user["user_id"], body.model_dump(), origin="user")
    return doc


@api.post("/decisions/{decision_id}/dismiss")
async def dismiss_decision(decision_id: str, user=Depends(get_current_user)):
    ok = await decisions.dismiss(user["user_id"], decision_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return {"ok": True}


@api.post("/decisions/{decision_id}/complete")
async def complete_decision(decision_id: str, user=Depends(get_current_user)):
    ok = await decisions.complete(user["user_id"], decision_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return {"ok": True}


@api.post("/decisions/{decision_id}/resolve")
async def resolve_decision(decision_id: str, user=Depends(get_current_user)):
    d = await decisions.get(user["user_id"], decision_id)
    if not d:
        raise HTTPException(status_code=404, detail="Decision non trovata")

    system = (
        "Sei ORA, un sistema operativo della vita quotidiana. "
        "Il tuo compito è ridurre il carico mentale dell'utente. "
        "Data una situazione, proponi UNA soluzione concreta, immediata, azionabile. "
        "Rispondi SEMPRE in italiano. Formato risposta:\n"
        "1) Una frase che dice esattamente cosa fare adesso (max 15 parole).\n"
        "2) 2-3 passi pratici, numerati, senza fronzoli.\n"
        "3) Se serve, un'app da aprire (es: Google Maps, WhatsApp, home banking).\n"
        "Nessun preambolo. Nessuna scusa. Nessuna domanda. Sii diretto."
    )
    prompt = (
        f"Situazione: {d['title']}\n"
        f"Contesto: {d.get('description') or '-'}\n"
        f"Categoria: {d.get('category')}\n"
        f"Deadline: {d.get('deadline') or '-'}\n"
        f"Inizio: {d.get('starts_at') or '-'}\n"
        f"Persone: {', '.join(d.get('people') or []) or '-'}\n"
        f"Dati: {d.get('metadata') or {}}"
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"resolve-{decision_id}",
            system_message=system,
        ).with_model("openai", "gpt-5.2")
        result = await chat.send_message(UserMessage(text=prompt))
        solution = result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.exception("AI resolve failed")
        raise HTTPException(status_code=502, detail=f"AI non disponibile: {e}")

    await decisions.attach_resolution(user["user_id"], decision_id, solution)
    return {"solution": solution, "decision_id": decision_id, "task_id": decision_id}


# ============================================================
# ROUTES: LEGACY /tasks + /priorities (backward compatible)
# ============================================================
@api.get("/priorities")
async def get_priorities(limit: int = 3, user=Depends(get_current_user)):
    """Top decisions in the legacy task-shape (Home v1 uses this)."""
    limit = max(1, min(limit, 20))
    ranked = await decisions.top(user["user_id"], limit=limit)
    return {"items": [decision_as_task(d) for d in ranked]}


@api.get("/tasks")
async def list_tasks(user=Depends(get_current_user)):
    ranked = await decisions.ranked(user["user_id"])
    all_docs = await decisions.list_all(user["user_id"])
    ranked_ids = {d["id"] for d in ranked}
    tail = [d for d in all_docs if d["id"] not in ranked_ids]
    return {"items": [decision_as_task(d) for d in ranked + tail]}


@api.post("/tasks")
async def create_task_legacy(body: TaskIn, user=Depends(get_current_user)):
    payload = body.model_dump()
    payload["description"] = payload.pop("context", None)
    payload["category"] = payload.pop("kind", "generic")
    doc = await decisions.create(user["user_id"], payload, origin="user:legacy_task")
    return decision_as_task(doc)


@api.post("/tasks/{task_id}/dismiss")
async def dismiss_task_legacy(task_id: str, user=Depends(get_current_user)):
    ok = await decisions.dismiss(user["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return {"ok": True}


@api.post("/tasks/{task_id}/complete")
async def complete_task_legacy(task_id: str, user=Depends(get_current_user)):
    ok = await decisions.complete(user["user_id"], task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return {"ok": True}


@api.post("/tasks/{task_id}/resolve")
async def resolve_task_legacy(task_id: str, user=Depends(get_current_user)):
    # Delegate to the new endpoint.
    return await resolve_decision(task_id, user)


# ============================================================
# ROUTES: LIFE GRAPH (new, isolated module)
# ============================================================
@api.get("/life-graph/vocabulary")
async def life_graph_vocabulary():
    """Public list of supported node types and relation types."""
    return {
        "node_types": sorted(NODE_TYPES),
        "relation_types": sorted(RELATION_TYPES),
    }


@api.post("/life-graph/seed")
async def life_graph_seed(user=Depends(get_current_user)):
    return await life_graph.seed_demo(user["user_id"])


# --- nodes ---
@api.post("/life-graph/nodes")
async def create_node(body: NodeIn, user=Depends(get_current_user)):
    return await life_graph.create_node(
        user["user_id"],
        type=body.type,
        label=body.label,
        description=body.description,
        attributes=body.attributes,
    )


@api.get("/life-graph/nodes")
async def list_nodes(type: Optional[str] = None, include_archived: bool = False, user=Depends(get_current_user)):
    items = await life_graph.list_nodes(user["user_id"], node_type=type, include_archived=include_archived)
    return {"items": items}


@api.get("/life-graph/nodes/{node_id}")
async def get_node(node_id: str, user=Depends(get_current_user)):
    node = await life_graph.get_node(user["user_id"], node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return node


@api.patch("/life-graph/nodes/{node_id}")
async def patch_node(node_id: str, body: NodePatch, user=Depends(get_current_user)):
    node = await life_graph.update_node(user["user_id"], node_id, body.model_dump(exclude_none=True))
    if not node:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return node


@api.delete("/life-graph/nodes/{node_id}")
async def delete_node(node_id: str, user=Depends(get_current_user)):
    ok = await life_graph.archive_node(user["user_id"], node_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return {"ok": True}


@api.get("/life-graph/nodes/{node_id}/graph")
async def node_graph(node_id: str, depth: int = 2, user=Depends(get_current_user)):
    sub = await life_graph.neighborhood(user["user_id"], node_id, depth=depth)
    if sub["root"] is None:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    return sub


@api.get("/life-graph/nodes/{node_id}/decisions")
async def node_decisions(node_id: str, user=Depends(get_current_user)):
    node = await life_graph.get_node(user["user_id"], node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Nodo non trovato")
    items = await life_graph.decisions_for_node(user["user_id"], node_id)
    return {"items": items}


# --- edges ---
@api.post("/life-graph/edges")
async def create_edge(body: EdgeIn, user=Depends(get_current_user)):
    try:
        return await life_graph.create_edge(
            user["user_id"],
            from_node=body.from_node,
            to_node=body.to_node,
            type=body.type,
            directed=body.directed,
            attributes=body.attributes,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api.get("/life-graph/edges")
async def list_edges(node_id: Optional[str] = None, user=Depends(get_current_user)):
    items = await life_graph.list_edges(user["user_id"], node_id=node_id)
    return {"items": items}


@api.delete("/life-graph/edges/{edge_id}")
async def delete_edge(edge_id: str, user=Depends(get_current_user)):
    ok = await life_graph.delete_edge(user["user_id"], edge_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Edge non trovato")
    return {"ok": True}


# --- decision <-> node ---
@api.post("/life-graph/decisions/{decision_id}/nodes")
async def link_decision_to_nodes(decision_id: str, body: DecisionNodesLinkIn, user=Depends(get_current_user)):
    try:
        updated = await life_graph.link_decision(user["user_id"], decision_id, body.node_ids)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return updated


@api.delete("/life-graph/decisions/{decision_id}/nodes/{node_id}")
async def unlink_decision_from_node(decision_id: str, node_id: str, user=Depends(get_current_user)):
    updated = await life_graph.unlink_decision(user["user_id"], decision_id, node_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Decision non trovata")
    return updated


# ============================================================
# ROUTES: MEMORY
# ============================================================
@api.post("/memory")
async def add_memory(body: MemoryIn, user=Depends(get_current_user)):
    doc = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "content": body.content,
        "tags": body.tags or [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.memories.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api.get("/memory")
async def list_memory(user=Depends(get_current_user)):
    cursor = db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    items = await cursor.to_list(length=500)
    return {"items": items}


@api.post("/memory/ask")
async def ask_memory(body: MemoryAskIn, user=Depends(get_current_user)):
    cursor = db.memories.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).limit(200)
    items = await cursor.to_list(length=200)

    if not items:
        return {
            "answer": "Non ho ancora nulla salvato nella tua memoria. Aggiungi qualcosa dalla scheda Aggiungi e ti risponderò all'istante.",
            "sources": [],
        }

    context_block = "\n".join([f"- ({m.get('created_at','')[:10]}) {m['content']}" for m in items])
    system = (
        "Sei la memoria personale di ORA. "
        "Rispondi SOLO usando le informazioni fornite nel contesto. "
        "Se la risposta non è presente, dì onestamente: 'Non risulta nella tua memoria.' "
        "Rispondi in italiano, breve e diretto. Max 2 frasi."
    )
    prompt = f"Contesto (memoria dell'utente):\n{context_block}\n\nDomanda: {body.question}"
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"mem-{user['user_id']}",
            system_message=system,
        ).with_model("openai", "gpt-5.2")
        result = await chat.send_message(UserMessage(text=prompt))
        answer = result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.exception("AI memory failed")
        raise HTTPException(status_code=502, detail=f"AI non disponibile: {e}")

    return {"answer": answer, "sources": items[:5]}


# ============================================================
# STARTUP
# ============================================================
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("user_id", unique=True)
    # Legacy tasks index (kept).
    await db.tasks.create_index([("user_id", 1), ("status", 1), ("score", -1)])
    # Decisions indexes.
    await db.decisions.create_index([("user_id", 1), ("status", 1)])
    await db.decisions.create_index("id", unique=True)
    await db.decisions.create_index([("user_id", 1), ("node_ids", 1)])
    # Life Graph indexes.
    await db.life_nodes.create_index("id", unique=True)
    await db.life_nodes.create_index([("user_id", 1), ("status", 1), ("type", 1)])
    await db.life_edges.create_index("id", unique=True)
    await db.life_edges.create_index([("user_id", 1), ("from_node", 1)])
    await db.life_edges.create_index([("user_id", 1), ("to_node", 1)])
    await db.memories.create_index([("user_id", 1), ("created_at", -1)])
    logger.info("ORA backend ready. Decision Engine + Life Graph online.")


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
