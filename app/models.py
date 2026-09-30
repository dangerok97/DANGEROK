from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class Utente(Base):
    """Un solo utente ammesso: nessuna registrazione pubblica."""
    __tablename__ = "utente"
    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_cifrato: Mapped[str] = mapped_column(Text)
    tentativi_falliti: Mapped[int] = mapped_column(Integer, default=0)
    bloccato_fino: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Pratica(Base):
    """Il titolo e' un codice interno: i dati del soggetto stanno solo nel blocco cifrato."""
    __tablename__ = "pratica"
    id: Mapped[int] = mapped_column(primary_key=True)
    codice: Mapped[str] = mapped_column(String(30), unique=True)
    tipo: Mapped[str] = mapped_column(String(12))              # controllo | verifica
    tipologia: Mapped[str] = mapped_column(String(40), default="generica")
    creata_il: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    dati_cifrati: Mapped[str] = mapped_column(Text, default="")  # soggetto, scheda, verbalizzanti

    fasi: Mapped[list["FasePratica"]] = relationship(back_populates="pratica", cascade="all, delete-orphan")
    atti: Mapped[list["Atto"]] = relationship(back_populates="pratica", cascade="all, delete-orphan",
                                              order_by="Atto.id")


class FasePratica(Base):
    __tablename__ = "fase_pratica"
    id: Mapped[int] = mapped_column(primary_key=True)
    pratica_id: Mapped[int] = mapped_column(ForeignKey("pratica.id"))
    chiave: Mapped[str] = mapped_column(String(40))
    stato: Mapped[str] = mapped_column(String(16), default="da_fare")  # da_fare|in_corso|completata|non_applicabile
    motivo_cifrato: Mapped[str] = mapped_column(Text, default="")      # motivazione se non applicabile
    pratica: Mapped[Pratica] = relationship(back_populates="fasi")


class Atto(Base):
    __tablename__ = "atto"
    id: Mapped[int] = mapped_column(primary_key=True)
    pratica_id: Mapped[int] = mapped_column(ForeignKey("pratica.id"))
    tipo: Mapped[str] = mapped_column(String(10))               # PVOC | PVV | PVC | CNR | INVITO
    fase: Mapped[str] = mapped_column(String(40), default="")
    giornata: Mapped[str] = mapped_column(String(10), default="")
    contenuto_cifrato: Mapped[str] = mapped_column(Text, default="")
    generato_da_ai: Mapped[int] = mapped_column(Integer, default=0)
    creato_il: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    pratica: Mapped[Pratica] = relationship(back_populates="atti")


class LogAI(Base):
    """Registro di cio' che e' uscito verso l'AI: SOLO il testo gia' pseudonimizzato."""
    __tablename__ = "log_ai"
    id: Mapped[int] = mapped_column(primary_key=True)
    pratica_id: Mapped[int] = mapped_column(Integer)
    quando: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    sezione: Mapped[str] = mapped_column(String(60))
    modello: Mapped[str] = mapped_column(String(40), default="")
    testo_inviato: Mapped[str] = mapped_column(Text)
    esito: Mapped[str] = mapped_column(String(20), default="ok")


class FonteNormativa(Base):
    """Istantanea di una fonte consultata dall'AI: URL, data di consultazione ed estratto citato.
    Serve a rendere riproducibile e verificabile ogni affermazione normativa."""
    __tablename__ = "fonte_normativa"
    id: Mapped[int] = mapped_column(primary_key=True)
    pratica_id: Mapped[int] = mapped_column(Integer)
    quesito: Mapped[str] = mapped_column(Text)
    periodo: Mapped[str] = mapped_column(String(40), default="")
    url: Mapped[str] = mapped_column(String(600))
    titolo: Mapped[str] = mapped_column(String(300), default="")
    estratto: Mapped[str] = mapped_column(Text, default="")
    dominio: Mapped[str] = mapped_column(String(120), default="")
    ufficiale: Mapped[int] = mapped_column(Integer, default=0)
    consultata_il: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Impostazione(Base):
    """Impostazioni dell'utente (es. dati del Reparto per gli atti), cifrate."""
    __tablename__ = "impostazione"
    chiave: Mapped[str] = mapped_column(String(40), primary_key=True)
    valore_cifrato: Mapped[str] = mapped_column(Text, default="")


class MessaggioChat(Base):
    """Conversazione con l'assistente: il testo e' cifrato a riposo (contiene i dati reali, non i segnaposto)."""
    __tablename__ = "messaggio_chat"
    id: Mapped[int] = mapped_column(primary_key=True)
    pratica_id: Mapped[int] = mapped_column(ForeignKey("pratica.id"))
    ruolo: Mapped[str] = mapped_column(String(10))               # user | assistant
    contenuto_cifrato: Mapped[str] = mapped_column(Text, default="")
    creato_il: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentoPratica(Base):
    """Documento acquisito nel fascicolo: si conserva il testo estratto (cifrato), non il file originale."""
    __tablename__ = "documento_pratica"
    id: Mapped[int] = mapped_column(primary_key=True)
    pratica_id: Mapped[int] = mapped_column(ForeignKey("pratica.id"))
    nome_cifrato: Mapped[str] = mapped_column(Text, default="")
    tipo: Mapped[str] = mapped_column(String(16), default="testo")   # xml_fattura | testo | csv | docx | pdf
    testo_cifrato: Mapped[str] = mapped_column(Text, default="")
    caratteri: Mapped[int] = mapped_column(Integer, default=0)
    creato_il: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
