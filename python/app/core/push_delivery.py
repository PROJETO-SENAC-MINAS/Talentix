"""Entrega genérica, sem PII, redirecionamento ou destino arbitrário."""

import asyncio, json
from datetime import datetime, timezone, timedelta
import requests
from pywebpush import webpush, WebPushException
from app.core.config import settings
from app.routers.push import configurado, validar_endpoint
from app.db.database import fetch_one, fetch_all, execute, transaction


class NoRedirectSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs["allow_redirects"] = False
        kwargs["timeout"] = 10
        return super().request(method, url, **kwargs)


def enviar_push(data):
    validar_endpoint(data["endpoint"])
    with NoRedirectSession() as session:
        session.trust_env = False
        result = webpush(
            subscription_info=data,
            data='{"atualizacao":true}',
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            requests_session=session,
            timeout=10,
            ttl=3600,
        )
        return result.status_code


async def processar_push():
    if not configurado():
        return
    candidates = await fetch_all("""SELECT s.ID_Assinatura,n.ID_Notificacoes FROM Push_Assinaturas s
        JOIN Usuarios u ON u.ID_Usuarios=s.ID_Usuarios AND u.Ativo=1
        JOIN Notificacoes n ON n.ID_Usuarios=s.ID_Usuarios AND n.CriadaEm>=s.CriadoEm AND n.Lida=0
        WHERE s.Ativa=1 AND NOT EXISTS(SELECT 1 FROM Push_Entregas p WHERE p.ID_Assinatura=s.ID_Assinatura AND p.ID_Notificacoes=n.ID_Notificacoes)
        ORDER BY n.CriadaEm LIMIT 100""")
    for item in candidates:
        async with transaction():
            sub = await fetch_one(
                "SELECT Ativa FROM Push_Assinaturas WHERE ID_Assinatura=%s FOR UPDATE",
                (item["ID_Assinatura"],),
            )
            if not sub or not sub["Ativa"]:
                continue
            if not await fetch_one(
                "SELECT ID_Assinatura FROM Push_Entregas WHERE ID_Assinatura=%s AND ID_Notificacoes=%s",
                (item["ID_Assinatura"], item["ID_Notificacoes"]),
            ):
                await execute(
                    "INSERT INTO Push_Entregas(ID_Assinatura,ID_Notificacoes) VALUES (%s,%s)",
                    (item["ID_Assinatura"], item["ID_Notificacoes"]),
                )
    for _ in range(20):
        async with transaction():
            row = await fetch_one("""SELECT p.*,s.Dados,s.Ativa,u.Ativo AS UsuarioAtivo FROM Push_Entregas p
                JOIN Push_Assinaturas s ON s.ID_Assinatura=p.ID_Assinatura JOIN Usuarios u ON u.ID_Usuarios=s.ID_Usuarios
                WHERE p.Estado IN ('pendente','processando') AND p.Tentativas<3 AND p.ProximaEm<=NOW() LIMIT 1 FOR UPDATE SKIP LOCKED""")
            if not row:
                break
            attempt = row["Tentativas"] + 1
            lease = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
                seconds=90
            )
            await execute(
                "UPDATE Push_Entregas SET Estado='processando',Tentativas=%s,ProximaEm=%s WHERE ID_Assinatura=%s AND ID_Notificacoes=%s",
                (attempt, lease, row["ID_Assinatura"], row["ID_Notificacoes"]),
            )
        state = "ignorado"
        status = None
        if row["Ativa"] and row["UsuarioAtivo"]:
            try:
                data = (
                    json.loads(row["Dados"])
                    if isinstance(row["Dados"], str)
                    else row["Dados"]
                )
                status = await asyncio.to_thread(enviar_push, data)
                state = (
                    "enviado"
                    if status in {200, 201, 202}
                    else (
                        "falhou" if status in {404, 410} or attempt >= 3 else "pendente"
                    )
                )
            except WebPushException as exc:
                status = exc.response.status_code if exc.response is not None else None
                state = "falhou" if status in {404, 410} or attempt >= 3 else "pendente"
            except Exception:
                state = "falhou" if attempt >= 3 else "pendente"
        if status in {404, 410}:
            await execute(
                "UPDATE Push_Assinaturas SET Ativa=0 WHERE ID_Assinatura=%s",
                (row["ID_Assinatura"],),
            )
        await execute(
            "UPDATE Push_Entregas SET Estado=%s,ProximaEm=%s WHERE ID_Assinatura=%s AND ID_Notificacoes=%s AND Tentativas=%s",
            (
                state,
                datetime.now(timezone.utc).replace(tzinfo=None)
                + timedelta(minutes=2**attempt),
                row["ID_Assinatura"],
                row["ID_Notificacoes"],
                attempt,
            ),
        )
