"""
CRUD de Notificações. Só o próprio usuário (ou admin) pode ler/marcar como lida.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo

router = APIRouter(prefix="/notificacoes", tags=["Notificações"])


class NotificacaoCreate(BaseModel):
    id_usuario: str
    titulo: str
    mensagem: str
    tipo: str | None = None


@router.post("", status_code=201)
async def criar_notificacao(dados: NotificacaoCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    """Criação manual/administrativa. Em geral notificações são geradas por triggers internos do sistema."""
    id_notif = novo_uuid()
    await execute(
        """INSERT INTO Notificacoes (ID_Notificacoes, ID_Usuarios, Titulo, Mensagem, Tipo)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_notif, dados.id_usuario, dados.titulo, dados.mensagem, dados.tipo),
    )
    return await fetch_one("SELECT * FROM Notificacoes WHERE ID_Notificacoes=%s", (id_notif,))


@router.get("")
async def listar_minhas_notificacoes(apenas_nao_lidas: bool = False, sessao: dict = Depends(usuario_atual)):
    query = "SELECT * FROM Notificacoes WHERE ID_Usuarios=%s"
    params: list = [sessao["id_usuario"]]
    if apenas_nao_lidas:
        query += " AND Lida=0"
    query += " ORDER BY CriadaEm DESC"
    return await fetch_all(query, tuple(params))


@router.patch("/{id_notificacao}/marcar-lida")
async def marcar_notificacao_lida(id_notificacao: str, sessao: dict = Depends(usuario_atual)):
    notificacao = await fetch_one("SELECT * FROM Notificacoes WHERE ID_Notificacoes=%s", (id_notificacao,))
    if not notificacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificação não encontrada.")
    if notificacao["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute("UPDATE Notificacoes SET Lida=1 WHERE ID_Notificacoes=%s", (id_notificacao,))
    return {"mensagem": "Notificação marcada como lida."}


@router.patch("/marcar-todas-lidas")
async def marcar_todas_lidas(sessao: dict = Depends(usuario_atual)):
    await execute("UPDATE Notificacoes SET Lida=1 WHERE ID_Usuarios=%s AND Lida=0", (sessao["id_usuario"],))
    return {"mensagem": "Todas as notificações foram marcadas como lidas."}


@router.delete("/{id_notificacao}")
async def excluir_notificacao(id_notificacao: str, sessao: dict = Depends(usuario_atual)):
    notificacao = await fetch_one("SELECT * FROM Notificacoes WHERE ID_Notificacoes=%s", (id_notificacao,))
    if not notificacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Notificação não encontrada.")
    if notificacao["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute("DELETE FROM Notificacoes WHERE ID_Notificacoes=%s", (id_notificacao,))
    return {"mensagem": "Notificação excluída."}