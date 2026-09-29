"""Password (Argon2), TOTP e cifratura dei dati sensibili a riposo (Fernet)."""
from __future__ import annotations

import base64
import hashlib
import json
import secrets

import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

_ph = PasswordHasher()


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hash_: str, pw: str) -> bool:
    try:
        return _ph.verify(hash_, pw)
    except (VerifyMismatchError, Exception):
        return False


def nuovo_segreto_totp() -> str:
    return pyotp.random_base32()


def uri_totp(segreto: str, nome: str = "utente", issuer: str = "Dangerok") -> str:
    return pyotp.TOTP(segreto).provisioning_uri(name=nome, issuer_name=issuer)


def verifica_totp(segreto: str, codice: str) -> bool:
    codice = (codice or "").replace(" ", "")
    return bool(codice.isdigit() and len(codice) == 6 and pyotp.TOTP(segreto).verify(codice, valid_window=1))


def nuova_chiave_fernet() -> str:
    return Fernet.generate_key().decode()


def nuovo_segreto_sessione() -> str:
    return secrets.token_urlsafe(48)


def _chiave_fernet(segreto: str) -> bytes:
    """Una chiave Fernet valida resta com'e' (compatibilita'); qualsiasi altra stringa lunga viene derivata."""
    try:
        Fernet(segreto.encode())
        return segreto.encode()
    except Exception:
        if len(segreto) < 24:
            raise RuntimeError("DATA_KEY troppo corta: servono almeno 24 caratteri casuali")
        return base64.urlsafe_b64encode(hashlib.sha256(("dangerok|" + segreto).encode()).digest())


class Cifratore:
    def __init__(self, chiave: str):
        self._f = Fernet(_chiave_fernet(chiave))

    def cifra_json(self, obj) -> str:
        return self._f.encrypt(json.dumps(obj, ensure_ascii=False).encode()).decode()

    def decifra_json(self, token: str):
        if not token:
            return {}
        try:
            return json.loads(self._f.decrypt(token.encode()).decode())
        except InvalidToken as e:  # chiave errata o dato alterato
            raise RuntimeError("Impossibile decifrare il dato: chiave errata o dato corrotto") from e

    def cifra_testo(self, s: str) -> str:
        return self._f.encrypt((s or "").encode()).decode()

    def decifra_testo(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode() if token else ""
