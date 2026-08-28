"""
CRUD de Avaliações (pós-processo seletivo) e Denúncias (moderação).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.notificar import notificar_usuario
from app.core.email_service import email_denuncia_recebida, email_denuncia_resolvida

router = APIRouter(tags=["Avaliações e Denúncias"])


# ==================== AVALIAÇÕES ====================

class AvaliacaoCreate(BaseModel):
    id_candidatura: str
    id_candidato: str | None = None
    id_empresa: str | None = None
    nota: int = Field(ge=1, le=5)
    comentario: str | None = None


@router.post("/avaliacoes", status_code=201)
async def criar_avaliacao(dados: AvaliacaoCreate, sessao: dict = Depends(usuario_atual)):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (dados.id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")

    id_avaliacao = novo_uuid()
    await execute(
        """INSERT INTO Avaliacoes (ID_Avaliacoes, ID_Avaliador, ID_Candidatos, ID_Empresas, ID_Candidaturas, Nota, Comentario)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (id_avaliacao, sessao["id_usuario"], dados.id_candidato, dados.id_empresa,
         dados.id_candidatura, dados.nota, dados.comentario),
    )
    return await fetch_one("SELECT * FROM Avaliacoes WHERE ID_Avaliacoes=%s", (id_avaliacao,))


@router.get("/avaliacoes")
async def listar_avaliacoes(id_candidato: str | None = None, id_empresa: str | None = None):
    query = "SELECT * FROM Avaliacoes WHERE 1=1"
    params: list = []
    if id_candidato:
        query += " AND ID_Candidatos=%s"
        params.append(id_candidato)
    if id_empresa:
        query += " AND ID_Empresas=%s"
        params.append(id_empresa)
    query += " ORDER BY CriadaEm DESC"
    return await fetch_all(query, tuple(params))


@router.delete("/avaliacoes/{id_avaliacao}")
async def excluir_avaliacao(id_avaliacao: str, sessao: dict = Depends(usuario_atual)):
    avaliacao = await fetch_one("SELECT * FROM Avaliacoes WHERE ID_Avaliacoes=%s", (id_avaliacao,))
    if not avaliacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Avaliação não encontrada.")
    if avaliacao["ID_Avaliador"] != sessao["id_usuario"] and sessao["tipo_usuario"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute("DELETE FROM Avaliacoes WHERE ID_Avaliacoes=%s", (id_avaliacao,))
    return {"mensagem": "Avaliação excluída."}


# ==================== DENÚNCIAS ====================

class DenunciaCreate(BaseModel):
    id_usuario_alvo: str | None = None
    id_vaga: str | None = None
    motivo: str
    descricao: str | None = None


@router.post("/denuncias", status_code=201)
async def criar_denuncia(dados: DenunciaCreate, sessao: dict = Depends(usuario_atual)):
    id_denuncia = novo_uuid()
    await execute(
        """INSERT INTO Denuncias (ID_Denuncias, ID_Denunciante, ID_Usuario_Alvo, ID_Vagas, ID_Status_Denuncia, Motivo, Descricao)
           VALUES (%s, %s, %s, %s, 1, %s, %s)""",
        (id_denuncia, sessao["id_usuario"], dados.id_usuario_alvo, dados.id_vaga, dados.motivo, dados.descricao),
    )

    # notifica todos os administradores ativos (in-app + e-mail)
    administradores = await fetch_all("SELECT ID_Usuarios FROM Administradores WHERE Ativo=1")
    for admin in administradores:
        await notificar_usuario(
            id_usuario=admin["ID_Usuarios"],
            titulo="Nova denúncia registrada",
            mensagem=f"Uma nova denúncia foi registrada: {dados.motivo}.",
            tipo="denuncia",
            enviar_email_fn=lambda email: email_denuncia_recebida(email, dados.motivo),
        )

    return await fetch_one("SELECT * FROM Denuncias WHERE ID_Denuncias=%s", (id_denuncia,))


@router.get("/denuncias")
async def listar_denuncias(sessao: dict = Depends(exigir_tipo("administrador"))):
    return await fetch_all("SELECT * FROM Denuncias ORDER BY CriadaEm DESC")


@router.get("/denuncias/minhas")
async def listar_minhas_denuncias(sessao: dict = Depends(usuario_atual)):
    return await fetch_all(
        "SELECT * FROM Denuncias WHERE ID_Denunciante=%s ORDER BY CriadaEm DESC", (sessao["id_usuario"],)
    )


class DenunciaResolucao(BaseModel):
    id_status_denuncia: int  # 3 = RESOLVIDA, 4 = REJEITADA


@router.patch("/denuncias/{id_denuncia}/resolver")
async def resolver_denuncia(
    id_denuncia: str, dados: DenunciaResolucao, sessao: dict = Depends(exigir_tipo("administrador"))
):
    admin = await fetch_one("SELECT ID_Administradores FROM Administradores WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if not admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrador não encontrado.")

    denuncia = await fetch_one("SELECT * FROM Denuncias WHERE ID_Denuncias=%s", (id_denuncia,))
    if not denuncia:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Denúncia não encontrada.")

    await execute(
        """UPDATE Denuncias SET ID_Status_Denuncia=%s, ID_Administradores=%s, ResolvidaEm=NOW()
           WHERE ID_Denuncias=%s""",
        (dados.id_status_denuncia, admin["ID_Administradores"], id_denuncia),
    )

    # notifica o denunciante sobre o resultado (in-app + e-mail)
    novo_status = await fetch_one(
        "SELECT Descricao FROM Status_Denuncia WHERE ID_Status_Denuncia=%s", (dados.id_status_denuncia,)
    )
    if novo_status:
        await notificar_usuario(
            id_usuario=denuncia["ID_Denunciante"],
            titulo="Sua denúncia foi analisada",
            mensagem=f"Sua denúncia sobre '{denuncia['Motivo']}' foi marcada como: {novo_status['Descricao']}.",
            tipo="denuncia",
            enviar_email_fn=lambda email: email_denuncia_resolvida(
                email, denuncia["Motivo"], novo_status["Descricao"]
            ),
        )

    return await fetch_one("SELECT * FROM Denuncias WHERE ID_Denuncias=%s", (id_denuncia,))