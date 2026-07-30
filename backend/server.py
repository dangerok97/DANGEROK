"""
ORA - Life Operating System - Backend
FastAPI + MongoDB + Emergent LLM (GPT-5.2) + Emergent Google OAuth + JWT
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
from typing import List, Optional
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage

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
# SCORING
# ============================================================
def compute_score(t: dict) -> float:
    time_factor = max(0, 10 - min(t.get("time_required_min", 15) / 15, 10))
    energy_factor = max(0, 10 - t.get("energy", 3))
    score = (
        t.get("urgency", 5) * 2.2
        + t.get("importance", 5) * 1.8
        + t.get("risk", 3) * 1.4
        + t.get("economic_impact", 3) * 1.0
        + t.get("personal_impact", 5) * 1.2
        + time_factor * 0.6
        + energy_factor * 0.5
    )
    return round(score, 2)


# ============================================================
# SEED
# ============================================================
async def seed_priorities(user_id: str):
    existing = await db.tasks.count_documents({"user_id": user_id})
    if existing > 0:
        return
    now = datetime.now(timezone.utc)
    seeds = [
        {
            "title": "Esci tra 25 minuti.",
            "context": "Il traffico sta aumentando sul tuo tragitto.",
            "urgency": 9, "importance": 8, "risk": 6, "time_required_min": 2,
            "energy": 1, "economic_impact": 2, "personal_impact": 7,
            "kind": "travel",
            "metadata": {"destination": "Ufficio", "eta_min": 25},
        },
        {
            "title": "La bolletta luce scade tra 3 giorni.",
            "context": "€ 87,40 · Enel Energia",
            "urgency": 8, "importance": 7, "risk": 7, "time_required_min": 5,
            "energy": 1, "economic_impact": 6, "personal_impact": 5,
            "kind": "bill",
            "metadata": {"amount": 87.40, "provider": "Enel", "due_days": 3},
        },
        {
            "title": "Marco aspetta ancora una tua risposta.",
            "context": "Messaggio ricevuto 2 giorni fa.",
            "urgency": 6, "importance": 6, "risk": 3, "time_required_min": 3,
            "energy": 2, "economic_impact": 1, "personal_impact": 8,
            "kind": "message",
            "metadata": {"contact": "Marco", "channel": "WhatsApp"},
        },
        {
            "title": "Hai dormito poco negli ultimi giorni.",
            "context": "Media 5h 20min · consigliato 7h+",
            "urgency": 4, "importance": 8, "risk": 6, "time_required_min": 10,
            "energy": 2, "economic_impact": 1, "personal_impact": 9,
            "kind": "health",
            "metadata": {"avg_sleep_hours": 5.3},
        },
        {
            "title": "Hai risparmiato 220 € questo mese.",
            "context": "+18% rispetto al mese scorso. Ottimo lavoro.",
            "urgency": 2, "importance": 4, "risk": 1, "time_required_min": 1,
            "energy": 1, "economic_impact": 5, "personal_impact": 6,
            "kind": "finance",
            "metadata": {"saved_eur": 220, "delta_pct": 18},
        },
    ]
    docs = []
    for s in seeds:
        s.update({
            "id": f"task_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "status": "open",
            "created_at": now.isoformat(),
        })
        s["score"] = compute_score(s)
        docs.append(s)
    await db.tasks.insert_many(docs)


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
    await seed_priorities(user["user_id"])
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@api.post("/auth/login", response_model=AuthOut)
async def login(body: LoginIn):
    user = await db.users.find_one({"email": body.email}, {"_id": 0})
    if not user or not user.get("password_hash"):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Credenziali non valide")
    await seed_priorities(user["user_id"])
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@api.post("/auth/google-session", response_model=AuthOut)
async def google_session(body: GoogleSessionIn):
    """Exchange Emergent session_token (from Google OAuth) for our JWT."""
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
    await seed_priorities(user["user_id"])
    return AuthOut(token=make_jwt(user["user_id"]), user=user_to_out(user))


@api.get("/auth/me", response_model=UserOut)
async def me(user=Depends(get_current_user)):
    return user_to_out(user)


@api.post("/auth/logout")
async def logout(user=Depends(get_current_user)):
    return {"ok": True}


# ============================================================
# ROUTES: TASKS / PRIORITIES
# ============================================================
def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@api.get("/priorities")
async def get_priorities(user=Depends(get_current_user)):
    cursor = db.tasks.find(
        {"user_id": user["user_id"], "status": "open"}, {"_id": 0}
    ).sort("score", -1).limit(5)
    tasks = await cursor.to_list(length=5)
    return {"items": tasks}


@api.get("/tasks")
async def list_tasks(user=Depends(get_current_user)):
    cursor = db.tasks.find({"user_id": user["user_id"]}, {"_id": 0}).sort("score", -1)
    tasks = await cursor.to_list(length=200)
    return {"items": tasks}


@api.post("/tasks")
async def create_task(body: TaskIn, user=Depends(get_current_user)):
    doc = body.model_dump()
    doc.update({
        "id": f"task_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    doc["score"] = compute_score(doc)
    await db.tasks.insert_one(doc)
    return _clean(doc)


@api.post("/tasks/{task_id}/dismiss")
async def dismiss_task(task_id: str, user=Depends(get_current_user)):
    res = await db.tasks.update_one(
        {"id": task_id, "user_id": user["user_id"]},
        {"$set": {"status": "dismissed"}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return {"ok": True}


@api.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, user=Depends(get_current_user)):
    res = await db.tasks.update_one(
        {"id": task_id, "user_id": user["user_id"]},
        {"$set": {"status": "resolved", "resolved_at": datetime.now(timezone.utc).isoformat()}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task non trovato")
    return {"ok": True}


@api.post("/tasks/{task_id}/resolve")
async def resolve_task(task_id: str, user=Depends(get_current_user)):
    task = await db.tasks.find_one({"id": task_id, "user_id": user["user_id"]}, {"_id": 0})
    if not task:
        raise HTTPException(status_code=404, detail="Task non trovato")

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
        f"Situazione: {task['title']}\n"
        f"Contesto: {task.get('context') or '-'}\n"
        f"Tipo: {task.get('kind')}\n"
        f"Dati: {task.get('metadata') or {}}"
    )
    try:
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"resolve-{task_id}",
            system_message=system,
        ).with_model("openai", "gpt-5.2")
        result = await chat.send_message(UserMessage(text=prompt))
        solution = result if isinstance(result, str) else str(result)
    except Exception as e:
        logger.exception("AI resolve failed")
        raise HTTPException(status_code=502, detail=f"AI non disponibile: {e}")

    await db.tasks.update_one(
        {"id": task_id, "user_id": user["user_id"]},
        {"$set": {"last_resolution": solution, "last_resolved_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"solution": solution, "task_id": task_id}


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
    await db.tasks.create_index([("user_id", 1), ("status", 1), ("score", -1)])
    await db.memories.create_index([("user_id", 1), ("created_at", -1)])
    logger.info("ORA backend ready.")


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
