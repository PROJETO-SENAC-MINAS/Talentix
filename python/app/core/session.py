"""
Sessão baseada em cookie assinado (não armazenamos sessão no servidor;
o cookie carrega o payload assinado, então não pode ser adulterado
pelo cliente sem invalidar a assinatura).
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, Response
from app.core.config import settings
from hashlib import sha256

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="talentix-session")


def criar_cookie_sessao(response: Response, id_usuario: str, tipo_usuario: str, senha_hash: str = "") -> None:
    """Cria o cookie de sessão assinado após login bem-sucedido."""
    payload = {"id_usuario": id_usuario, "tipo_usuario": tipo_usuario,
               "auth_tag": sha256(senha_hash.encode()).hexdigest()}
    token = _serializer.dumps(payload)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )


def destruir_cookie_sessao(response: Response) -> None:
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )


def ler_sessao(request: Request) -> dict | None:
    """Lê e valida o cookie de sessão da requisição. Retorna None se inválido/ausente."""
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = _serializer.loads(token, max_age=settings.SESSION_MAX_AGE_SECONDS)
        return payload if isinstance(payload, dict) and isinstance(payload.get("id_usuario"), str) else None
    except (BadSignature, SignatureExpired):
        return None
