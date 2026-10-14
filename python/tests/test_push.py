"""Consentimento push, SSRF, isolamento e entregas deduplicadas sem rede externa."""

import asyncio
import base64
import socket
from app.core import push_delivery
from app.core.config import settings


def subscription():
    encode = lambda value: base64.urlsafe_b64encode(value).rstrip(b"=").decode()
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/teste-isolado-123456",
        "keys": {"p256dh": encode(b"\x04" + b"1" * 64), "auth": encode(b"2" * 16)},
    }


def configure(monkeypatch):
    monkeypatch.setattr(settings, "VAPID_PRIVATE_KEY", "3" * 43)
    monkeypatch.setattr(settings, "VAPID_PUBLIC_KEY", "4" * 87)
    monkeypatch.setattr(settings, "VAPID_SUBJECT", "mailto:test@example.com")


def test_push_fails_closed_without_configuration(ambiente, autenticar):
    c, db = ambiente
    autenticar(c, "uc1", "candidato")
    assert c.get("/push/configuracao").json()["disponivel"] is False
    assert c.post("/push/assinaturas", json=subscription()).status_code == 503
    assert db.execute("SELECT COUNT(*) FROM Push_Assinaturas").fetchone()[0] == 0


def test_push_allowlist_private_dns_and_user_isolation(
    ambiente, autenticar, monkeypatch
):
    c, db = ambiente
    configure(monkeypatch)
    autenticar(c, "uc1", "candidato")
    data = subscription()
    assert (
        c.post(
            "/push/assinaturas",
            json={**data, "endpoint": "https://fcm.googleapis.com:invalid/teste"},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/push/assinaturas",
            json={**data, "endpoint": "https://127.0.0.1/metadata/service"},
        ).status_code
        == 400
    )
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    assert c.post("/push/assinaturas", json=data).status_code == 400
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    assert c.post("/push/assinaturas", json=data).status_code == 201
    autenticar(c, "uc2", "candidato")
    assert c.post("/push/assinaturas", json=data).status_code == 409
    assert c.delete("/push/assinaturas").status_code == 200
    assert (
        db.execute(
            "SELECT Ativa FROM Push_Assinaturas WHERE ID_Usuarios='uc1'"
        ).fetchone()[0]
        == 1
    )


def test_push_delivery_once_and_generic_payload(ambiente, autenticar, monkeypatch):
    c, db = ambiente
    configure(monkeypatch)
    autenticar(c, "uc1", "candidato")
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    assert c.post("/push/assinaturas", json=subscription()).status_code == 201
    db.execute(
        "INSERT INTO Notificacoes(ID_Notificacoes,ID_Usuarios,Titulo,Mensagem,Tipo) VALUES ('push1','uc1','Conteúdo privado','Não enviar no push','teste')"
    )
    db.commit()
    calls = []
    monkeypatch.setattr(
        push_delivery, "enviar_push", lambda data: calls.append(data) or 201
    )
    asyncio.run(push_delivery.processar_push())
    db.commit()
    asyncio.run(push_delivery.processar_push())
    assert len(calls) == 1
    assert db.execute("SELECT Estado FROM Push_Entregas").fetchone()[0] == "enviado"
