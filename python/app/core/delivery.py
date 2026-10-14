"""Outbox de texto: preferências e deduplicação antes de efeitos externos."""

from html import escape
from app.core.security import novo_uuid
from app.db.database import fetch_one, execute


async def enfileirar_email(usuario, assunto, corpo, chave):
    u = await fetch_one(
        "SELECT EmailConfirmadoEm,Ativo FROM Usuarios WHERE ID_Usuarios=%s", (usuario,)
    )
    p = await fetch_one(
        "SELECT EmailAtivo FROM Preferencias_Notificacao WHERE ID_Usuarios=%s",
        (usuario,),
    )
    if (
        not u
        or not u["Ativo"]
        or not u["EmailConfirmadoEm"]
        or not p
        or not p["EmailAtivo"]
    ):
        return False
    if await fetch_one("SELECT ID_Email FROM Outbox_Email WHERE Chave=%s", (chave,)):
        return True
    await execute(
        "INSERT INTO Outbox_Email(ID_Email,ID_Usuarios,Assunto,Corpo,Chave) VALUES (%s,%s,%s,%s,%s)",
        (
            novo_uuid(),
            usuario,
            assunto.replace("\r", "").replace("\n", " ")[:200],
            corpo[:10000],
            chave,
        ),
    )
    return True


def corpo_email(texto):
    return (
        "<p>"
        + escape(texto).replace("\n", "<br>")
        + "</p><p>Gerencie suas preferências no Talentix.</p>"
    )
