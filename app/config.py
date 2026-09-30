from __future__ import annotations

import os
from dataclasses import dataclass


def normalizza_database_url(url: str) -> str:
    """I provider forniscono 'postgres://' o 'postgresql://': SQLAlchemy con psycopg vuole 'postgresql+psycopg://'."""
    for prefisso in ("postgres://", "postgresql://"):
        if url.startswith(prefisso):
            return "postgresql+psycopg://" + url[len(prefisso):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    data_key: str            # chiave Fernet per cifrare i dati sensibili a riposo
    session_secret: str
    https_only: bool
    anthropic_model: str
    setup_token: str = ""
    session_max_age: int = 8 * 3600
    max_login_failures: int = 5
    lock_minutes: int = 15
    chat_asincrona: bool = False        # la chat elabora in background e la pagina si aggiorna da sola (evita i timeout del proxy)
    istruttoria_auto: bool = False      # istruttoria normativa automatica (ricerche su fonti aperte senza che l'AI le chieda)

    @staticmethod
    def load() -> "Settings":
        def need(name: str) -> str:
            v = os.environ.get(name, "")
            if not v:
                raise RuntimeError(f"Variabile d'ambiente mancante: {name} (vedi .env.example)")
            return v

        return Settings(
            database_url=normalizza_database_url(os.environ.get("DATABASE_URL", "sqlite:///./dangerok.db")),
            data_key=need("DATA_KEY"),
            session_secret=need("SESSION_SECRET"),
            https_only=os.environ.get("HTTPS_ONLY", "1") != "0",
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
            setup_token=os.environ.get("SETUP_TOKEN", ""),
            istruttoria_auto=os.environ.get("ISTRUTTORIA_AUTO", "1") != "0",
            chat_asincrona=os.environ.get("CHAT_ASINCRONA", "1") != "0",
        )
