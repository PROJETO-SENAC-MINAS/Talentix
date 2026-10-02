"""Controles de conta: TOTP, tokens de e-mail e proteção de dados sensíveis."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def criptografar_segredo(valor: str) -> str:
    return _fernet().encrypt(valor.encode("utf-8")).decode("ascii")


def descriptografar_segredo(valor: str) -> str | None:
    try:
        return _fernet().decrypt(valor.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def gerar_segredo_totp() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _totp(secret: str, counter: int, digits: int = 6) -> str:
    padding = "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(secret + padding, casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def validar_totp(secret: str, codigo: str, agora: int | None = None) -> bool:
    if not codigo or not codigo.isdigit() or len(codigo) != 6:
        return False
    timestamp = int(agora if agora is not None else time.time())
    counter = timestamp // 30
    return any(hmac.compare_digest(_totp(secret, counter + drift), codigo) for drift in (-1, 0, 1))


def otpauth_uri(secret: str, email: str) -> str:
    label = quote(f"Talentix:{email}")
    issuer = quote("Talentix")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"


_email_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="talentix-email")


def gerar_token_email(id_usuario: str, email: str, finalidade: str) -> str:
    return _email_serializer.dumps({"id_usuario": id_usuario, "email": email, "finalidade": finalidade})


def validar_token_email(token: str, finalidade: str, max_age: int = 3600) -> dict | None:
    try:
        payload = _email_serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if payload.get("finalidade") != finalidade:
        return None
    if not isinstance(payload.get("id_usuario"), str) or not isinstance(payload.get("email"), str):
        return None
    return payload
