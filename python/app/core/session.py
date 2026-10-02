"""Sessões assinadas com suporte a registro e revogação no servidor."""
from hashlib import sha256
import uuid

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="talentix-session")


def novo_id_sessao() -> str:
    return str(uuid.uuid4())


def criar_cookie_sessao(
    response: Response,
    id_usuario: str,
    tipo_usuario: str,
    senha_hash: str = "",
    modo_usuario: bool = False,
    id_sessao: str | None = None,
) -> None:
    payload = {
        "id_usuario": id_usuario,
        "tipo_usuario": tipo_usuario,
        "modo_usuario": bool(modo_usuario),
        "auth_tag": sha256(senha_hash.encode()).hexdigest(),
    }
    if id_sessao:
        payload["id_sessao"] = id_sessao
    token = _serializer.dumps(payload)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )


def destruir_cookie_sessao(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
    )


def ler_sessao(request: Request) -> dict | None:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = _serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
        return payload if isinstance(payload, dict) and isinstance(payload.get("id_usuario"), str) else None
    except (BadSignature, SignatureExpired):
        return None
