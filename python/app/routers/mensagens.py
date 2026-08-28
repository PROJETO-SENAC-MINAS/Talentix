"""
CRUD de Mensagens diretas entre usuários, opcionalmente contextualizadas
por uma candidatura.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual
from app.core.notificar import notificar_usuario
from app.core.email_service import email_nova_mensagem

router = APIRouter(prefix="/mensagens", tags=["Mensagens"])


class MensagemCreate(BaseModel):
    id_destinatario: str
    conteudo: str
    id_candidatura: str | None = None


@router.post("", status_code=201)
async def enviar_mensagem(dados: MensagemCreate, sessao: dict = Depends(usuario_atual)):
    id_msg = novo_uuid()
    await execute(
        """INSERT INTO Mensagens (ID_Mensagens, ID_Remetente, ID_Destinatario, ID_Candidaturas, Conteudo)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_msg, sessao["id_usuario"], dados.id_destinatario, dados.id_candidatura, dados.conteudo),
    )

    remetente = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    nome_remetente = remetente["Nome"] if remetente else "Alguém"
    await notificar_usuario(
        id_usuario=dados.id_destinatario,
        titulo="Nova mensagem recebida",
        mensagem=f"Você recebeu uma nova mensagem de {nome_remetente}.",
        tipo="mensagem",
        enviar_email_fn=lambda email: email_nova_mensagem(email, nome_remetente),
    )

    return await fetch_one("SELECT * FROM Mensagens WHERE ID_Mensagens=%s", (id_msg,))


@router.get("/conversas/{id_outro_usuario}")
async def obter_conversa(id_outro_usuario: str, sessao: dict = Depends(usuario_atual)):
    """Retorna a conversa (todas as mensagens) entre o usuário logado e outro usuário."""
    return await fetch_all(
        """SELECT * FROM Mensagens
           WHERE (ID_Remetente=%s AND ID_Destinatario=%s) OR (ID_Remetente=%s AND ID_Destinatario=%s)
           ORDER BY EnviadaEm ASC""",
        (sessao["id_usuario"], id_outro_usuario, id_outro_usuario, sessao["id_usuario"]),
    )


@router.get("")
async def listar_minhas_mensagens(apenas_nao_lidas: bool = False, sessao: dict = Depends(usuario_atual)):
    query = "SELECT * FROM Mensagens WHERE ID_Destinatario=%s"
    params: list = [sessao["id_usuario"]]
    if apenas_nao_lidas:
        query += " AND Lida=0"
    query += " ORDER BY EnviadaEm DESC"
    return await fetch_all(query, tuple(params))


@router.patch("/{id_mensagem}/marcar-lida")
async def marcar_mensagem_lida(id_mensagem: str, sessao: dict = Depends(usuario_atual)):
    mensagem = await fetch_one("SELECT * FROM Mensagens WHERE ID_Mensagens=%s", (id_mensagem,))
    if not mensagem:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada.")
    if mensagem["ID_Destinatario"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute("UPDATE Mensagens SET Lida=1 WHERE ID_Mensagens=%s", (id_mensagem,))
    return {"mensagem": "Mensagem marcada como lida."}


@router.delete("/{id_mensagem}")
async def excluir_mensagem(id_mensagem: str, sessao: dict = Depends(usuario_atual)):
    mensagem = await fetch_one("SELECT * FROM Mensagens WHERE ID_Mensagens=%s", (id_mensagem,))
    if not mensagem:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada.")
    if sessao["id_usuario"] not in (mensagem["ID_Remetente"], mensagem["ID_Destinatario"]):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute("DELETE FROM Mensagens WHERE ID_Mensagens=%s", (id_mensagem,))
    return {"mensagem": "Mensagem excluída."}