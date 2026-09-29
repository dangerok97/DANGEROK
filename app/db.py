from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def crea_engine(url: str):
    if url.startswith("sqlite"):
        return create_engine(url, future=True, connect_args={"check_same_thread": False})
    # Postgres su hosting gratuito (es. Neon): il database si sospende da solo e i collegamenti vengono chiusi.
    # pool_pre_ping ripristina il collegamento; prepare_threshold=None evita problemi con i pooler di connessioni.
    return create_engine(url, future=True, pool_pre_ping=True, pool_recycle=240,
                         connect_args={"prepare_threshold": None})


def crea_sessionmaker(engine):
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False, class_=Session)
