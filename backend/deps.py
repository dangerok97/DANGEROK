"""
Shared application state and dependencies.

server.py should stay thin (bootstrap only). All service instances, DB
handles, and auth helpers are exposed from here so each domain router
can `from deps import ...` without pulling business logic into the entry
point.
"""
from __future__ import annotations

import os
import uuid
import bcrypt
import jwt as pyjwt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
import mongo

from decision_engine import DecisionService
from life_graph import LifeGraphService
from knowledge import KnowledgeService
from auto_link import AutoLinkService
from context_assembler import ContextAssemblerService

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


def _require_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"Variabile d'ambiente obbligatoria mancante: {name}. "
            f"Copia backend/.env.example in backend/.env e compilala."
        )
    return value


MONGO_URL = _require_env("MONGO_URL")
DB_NAME = _require_env("DB_NAME")
JWT_SECRET = _require_env("JWT_SECRET")
# Deprecated alias — LLM uses llm.provider; kept for any legacy imports.
EMERGENT_LLM_KEY = (os.environ.get("EMERGENT_LLM_KEY") or "").strip()
JWT_ALGO = "HS256"
JWT_EXPIRY_DAYS = 30

DEMO_EMAILS = frozenset({"demo@ora.app"})

# --- Mongo -----------------------------------------------------------
# `client` and `db` stay exactly what every caller already imports: one
# module-level name each, imported once, held by services built at import
# time. What changed is what they point at.
#
# A Motor client binds itself to an event loop on its first await and keeps
# that binding for good, so a client built here — at import, outside any loop
# — belonged to whichever loop touched it first. Anything else running later
# on a different loop got "Future attached to a different loop", and closing
# it in shutdown left the process without a usable client at all.
#
# These handles resolve to the client owned by the loop that is running right
# now (see mongo.py). No caller changes, no client per request: within one
# loop it is built once and reused, pool included.
mongo.configure(MONGO_URL, DB_NAME)


class _Database:
    """`deps.db`, forwarding to the database of the running loop."""

    def __getattr__(self, name: str):
        return getattr(mongo.database(), name)

    def __getitem__(self, name: str):
        return mongo.database()[name]

    def __repr__(self) -> str:
        return f"<deps.db {DB_NAME!r}>"


class _Client:
    """`deps.client`, forwarding to the client of the running loop."""

    def __getattr__(self, name: str):
        return getattr(mongo.client(), name)

    def __getitem__(self, name: str):
        return mongo.client()[name]

    def close(self) -> None:
        """Close this loop's client. A later startup builds a fresh one."""
        mongo.close()

    def __repr__(self) -> str:
        return "<deps.client>"


client = _Client()
db = _Database()

# --- Services --------------------------------------------------------
decisions = DecisionService(db)
life_graph = LifeGraphService(db)
knowledge = KnowledgeService(db)
auto_link = AutoLinkService(db, life_graph)
context_asm = ContextAssemblerService(db)

# Lazily-imported to avoid circular refs at bootstrap time.
_permissions_service = None
_connectors_service = None
_ingestion_service = None
_google_calendar_service = None
_apple_calendar_service = None
_token_vault = None
_daily_summary_service = None
_explanation_service = None
_action_center_service = None


def get_permissions_service():
    global _permissions_service
    if _permissions_service is None:
        from permissions import PermissionService
        _permissions_service = PermissionService(db)
    return _permissions_service


def get_connectors_service():
    global _connectors_service
    if _connectors_service is None:
        from connectors import ConnectorService
        _connectors_service = ConnectorService(db, permissions=get_permissions_service())
    return _connectors_service


def get_token_vault():
    global _token_vault
    if _token_vault is None:
        from security import build_token_vault
        _token_vault = build_token_vault(db)
    return _token_vault


def get_ingestion_service():
    global _ingestion_service
    if _ingestion_service is None:
        from ingestion import IngestionService
        _ingestion_service = IngestionService(
            db,
            life_graph=life_graph,
            knowledge=knowledge,
            decisions=decisions,
            auto_link=auto_link,
        )
    return _ingestion_service


def get_google_calendar_service():
    global _google_calendar_service
    if _google_calendar_service is None:
        from connectors.google_calendar import GoogleCalendarService
        _google_calendar_service = GoogleCalendarService(
            db=db,
            permissions=get_permissions_service(),
            ingestion=get_ingestion_service(),
            vault=get_token_vault(),
        )
    return _google_calendar_service


def get_apple_calendar_service():
    global _apple_calendar_service
    if _apple_calendar_service is None:
        from connectors.apple_calendar import AppleCalendarService
        _apple_calendar_service = AppleCalendarService(
            db=db,
            permissions=get_permissions_service(),
            ingestion=get_ingestion_service(),
        )
    return _apple_calendar_service


_document_service = None


def get_document_service():
    global _document_service
    if _document_service is None:
        from documents import DocumentService, build_default_storage
        _document_service = DocumentService(
            db=db,
            storage=build_default_storage(),
            life_graph=life_graph,
            knowledge=knowledge,
        )
    return _document_service


_intelligence_service = None


def get_intelligence_service():
    global _intelligence_service
    if _intelligence_service is None:
        from documents.intelligence.service import IntelligenceService
        _intelligence_service = IntelligenceService(db, get_document_service())
    return _intelligence_service


def get_daily_summary_service():
    global _daily_summary_service
    if _daily_summary_service is None:
        from daily_intelligence import DailySummaryService
        _daily_summary_service = DailySummaryService(db)
    return _daily_summary_service


def get_explanation_service():
    global _explanation_service
    if _explanation_service is None:
        from explainability import ExplanationService
        _explanation_service = ExplanationService(
            db,
            life_graph=life_graph,
            context_asm=context_asm,
            decisions=decisions,
            daily=get_daily_summary_service(),
        )
    return _explanation_service


def get_action_center_service():
    global _action_center_service
    if _action_center_service is None:
        from action_center import ActionCenterService
        _action_center_service = ActionCenterService(db)
    return _action_center_service


# --- Auth helpers ----------------------------------------------------
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


async def upsert_user(
    email: str,
    name: Optional[str],
    picture: Optional[str],
    provider: str,
    password_hash: Optional[str] = None,
) -> dict:
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
