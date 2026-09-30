"""
CRUD de Mensagens diretas entre usuários, opcionalmente contextualizadas
por uma candidatura.
"""
from app.core.routes import AtomicRouter as APIRouter

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual
from app.core.access import checar_empresa
from app.routers.candidaturas import _checar_acesso_candidatura
from app.core.notificar import notificar_usuario
from app.core.email_service import email_nova_mensagem

router = APIRouter(prefix="/mensagens", tags=["Mensagens"])


class MensagemCreate(BaseModel):
    id_destinatario: str
    conteudo: str = Field(min_length=1, max_length=10000)
    id_candidatura: str | None = None


@router.post("", status_code=201)
async def enviar_mensagem(dados: MensagemCreate, sessao: dict = Depends(usuario_atual)):
    if not await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1", (dados.id_destinatario,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destinatário não encontrado.")
    if dados.id_candidatura:
        candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s AND Ativo=1", (dados.id_candidatura,))
        if not candidatura:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
        await _checar_acesso_candidatura(candidatura, sessao)
        candidato = await fetch_one("SELECT ID_Usuarios FROM Candidatos WHERE ID_Candidatos=%s AND Ativo=1", (candidatura["ID_Candidatos"],))
        vaga = await fetch_one("SELECT ID_Empresas FROM Vagas WHERE ID_Vagas=%s", (candidatura["ID_Vagas"],))
        empresa = await fetch_one("SELECT ID_Usuarios FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (vaga["ID_Empresas"],))
        recrutador = await fetch_one("SELECT ID_Usuarios FROM Recrutadores WHERE ID_Usuarios=%s AND ID_Empresas=%s AND Ativo=1",
                                   (dados.id_destinatario, vaga["ID_Empresas"]))
        participantes = {candidato["ID_Usuarios"] if candidato else None, empresa["ID_Usuarios"] if empresa else None}
        if dados.id_destinatario not in participantes and not recrutador:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Destinatário não participa desta candidatura.")
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
        """SELECT m.*, r.Nome AS NomeRemetente, d.Nome AS NomeDestinatario FROM Mensagens m
           JOIN Usuarios r ON r.ID_Usuarios=m.ID_Remetente JOIN Usuarios d ON d.ID_Usuarios=m.ID_Destinatario
           WHERE (ID_Remetente=%s AND ID_Destinatario=%s) OR (ID_Remetente=%s AND ID_Destinatario=%s)
           ORDER BY EnviadaEm ASC""",
        (sessao["id_usuario"], id_outro_usuario, id_outro_usuario, sessao["id_usuario"]),
    )


@router.get("")
async def listar_minhas_mensagens(apenas_nao_lidas: bool = False, sessao: dict = Depends(usuario_atual)):
    query = """SELECT m.*, r.Nome AS NomeRemetente FROM Mensagens m
               JOIN Usuarios r ON r.ID_Usuarios=m.ID_Remetente WHERE ID_Destinatario=%s"""
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
