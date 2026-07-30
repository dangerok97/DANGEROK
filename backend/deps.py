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
from motor.motor_asyncio import AsyncIOMotorClient

from decision_engine import DecisionService
from life_graph import LifeGraphService
from knowledge import KnowledgeService
from auto_link import AutoLinkService
from context_assembler import ContextAssemblerService

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
EMERGENT_LLM_KEY = os.environ["EMERGENT_LLM_KEY"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGO = "HS256"
JWT_EXPIRY_DAYS = 30

DEMO_EMAILS = frozenset({"demo@ora.app"})

# --- Mongo -----------------------------------------------------------
client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

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
