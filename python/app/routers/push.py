"""Web Push com consentimento e destinos restritos aos serviços dos navegadores."""

import asyncio, base64
from hashlib import sha256
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.config import settings
from app.core.ssrf import validar_url_saida
from app.core.security import novo_uuid
from app.core.audit import registrar_auditoria
from app.db.database import fetch_one, execute

router = AtomicRouter(prefix="/push", tags=["Notificações push"])


def configurado():
    return bool(
        settings.VAPID_PRIVATE_KEY
        and settings.VAPID_PUBLIC_KEY
        and settings.VAPID_SUBJECT
    )


def validar_endpoint(endpoint):
    try:
        parsed = urlsplit(endpoint)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(422, "Endpoint push inválido.") from exc
    allowed = {
        "fcm.googleapis.com",
        "updates.push.services.mozilla.com",
        "web.push.apple.com",
    }
    if host.endswith(".notify.windows.com") and len(host.split(".")) == 4:
        allowed.add(host)
    if port not in {None, 443} or parsed.fragment:
        raise HTTPException(422, "Endpoint push inválido.")
    return validar_url_saida(endpoint, allowed)


def chave_bytes(value, length):
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
        if len(decoded) != length:
            raise ValueError()
        return decoded
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, "Chave de assinatura push inválida.") from exc


@router.get("/configuracao")
async def configuracao(s=Depends(usuario_atual)):
    return {
        "disponivel": configurado(),
        "chave_publica": settings.VAPID_PUBLIC_KEY if configurado() else None,
    }


class Keys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p256dh: str = Field(min_length=80, max_length=100)
    auth: str = Field(min_length=20, max_length=30, repr=False)


class Subscription(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(min_length=20, max_length=2048, repr=False)
    keys: Keys
    expirationTime: int | None = None


@router.post("/assinaturas", status_code=201)
async def assinar(d: Subscription, request: Request, s=Depends(usuario_atual)):
    if not configurado():
        raise HTTPException(
            503, "Notificações do navegador indisponíveis neste ambiente."
        )
    if chave_bytes(d.keys.p256dh, 65)[0] != 4:
        raise HTTPException(422, "Chave pública inválida.")
    chave_bytes(d.keys.auth, 16)
    await asyncio.to_thread(validar_endpoint, d.endpoint)
    key = sha256(d.endpoint.encode()).hexdigest()
    await fetch_one(
        "SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s FOR UPDATE",
        (s["id_usuario"],),
    )
    old = await fetch_one(
        "SELECT ID_Usuarios FROM Push_Assinaturas WHERE ID_Assinatura=%s FOR UPDATE",
        (key,),
    )
    if old and old["ID_Usuarios"] != s["id_usuario"]:
        raise HTTPException(
            409, "Reative a inscrição do navegador antes de vinculá-la a outra conta."
        )
    if old:
        await execute(
            "UPDATE Push_Assinaturas SET Dados=%s,Ativa=1 WHERE ID_Assinatura=%s",
            (d.model_dump_json(), key),
        )
    else:
        await execute(
            "INSERT INTO Push_Assinaturas(ID_Assinatura,ID_Usuarios,Dados) VALUES (%s,%s,%s)",
            (key, s["id_usuario"], d.model_dump_json()),
        )
    await execute(
        "INSERT INTO Privacidade_Consentimentos(ID_Consentimento,ID_Usuarios,Finalidade,Autorizado,VersaoPolitica) VALUES (%s,%s,%s,1,%s)",
        (novo_uuid(), s["id_usuario"], "notificacoes_push", "2026-10-v1"),
    )
    await registrar_auditoria(
        request, "push.ativar", "Push_Assinaturas", s["id_usuario"], key
    )
    return {"id": key, "mensagem": "Notificações ativadas neste navegador."}


@router.delete("/assinaturas")
async def cancelar(request: Request, s=Depends(usuario_atual)):
    await execute(
        "UPDATE Push_Assinaturas SET Ativa=0 WHERE ID_Usuarios=%s", (s["id_usuario"],)
    )
    await execute(
        "INSERT INTO Privacidade_Consentimentos(ID_Consentimento,ID_Usuarios,Finalidade,Autorizado,VersaoPolitica) VALUES (%s,%s,%s,0,%s)",
        (novo_uuid(), s["id_usuario"], "notificacoes_push", "2026-10-v1"),
    )
    await registrar_auditoria(
        request, "push.desativar", "Push_Assinaturas", s["id_usuario"]
    )
    return {"mensagem": "Notificações push desativadas para sua conta."}
