"""
Análises de IA e Recomendações de Vaga. Seguem o padrão de processamento
assíncrono: o endpoint de criação apenas enfileira (status_processamento = 'NA_FILA'),
e um worker externo (fora do escopo desta API) é responsável por processar e
atualizar o registro com o resultado via PATCH /processar.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.access import checar_acesso_analise, checar_dono_candidato
from app.core.service_auth import exigir_worker_ia
from app.core.notificar import notificar_usuario
from app.core.email_service import email_recomendacao_vaga

router = APIRouter(tags=["Inteligência Artificial"])

_STATUS_NA_FILA = 1
_STATUS_PROCESSANDO = 2
_STATUS_CONCLUIDO = 3
_STATUS_FALHOU = 4


# ==================== ANÁLISES DE IA ====================

class AnaliseIACreate(BaseModel):
    id_candidato: str
    id_vaga: str
    id_candidatura: str | None = None


@router.post("/analises-ia", status_code=201)
async def solicitar_analise_ia(dados: AnaliseIACreate, sessao: dict = Depends(usuario_atual)):
    await checar_acesso_analise(dados.id_candidato, dados.id_vaga, sessao)
    if dados.id_candidatura:
        candidatura = await fetch_one(
            """SELECT ID_Candidaturas FROM Candidaturas WHERE ID_Candidaturas=%s
               AND ID_Candidatos=%s AND ID_Vagas=%s AND Ativo=1""",
            (dados.id_candidatura, dados.id_candidato, dados.id_vaga),
        )
        if not candidatura:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Candidatura incompatível com candidato e vaga.")
    id_analise = novo_uuid()
    await execute(
        """INSERT INTO Analises_IA (ID_Analises_IA, ID_Candidatos, ID_Vagas, ID_Candidaturas, ID_Status_Processamento_IA)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_analise, dados.id_candidato, dados.id_vaga, dados.id_candidatura, _STATUS_NA_FILA),
    )
    return await fetch_one("SELECT * FROM Analises_IA WHERE ID_Analises_IA=%s", (id_analise,))


@router.get("/analises-ia")
async def listar_analises_ia(
    id_candidato: str | None = None,
    id_vaga: str | None = None,
    sessao: dict = Depends(exigir_tipo("candidato", "empresa", "administrador")),
):
    query = """SELECT a.* FROM Analises_IA a
               JOIN Candidatos c ON c.ID_Candidatos=a.ID_Candidatos AND c.Ativo=1
               JOIN Vagas v ON v.ID_Vagas=a.ID_Vagas
               JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas WHERE 1=1"""
    params: list = []
    if sessao["tipo_usuario"] == "candidato":
        query += " AND c.ID_Usuarios=%s"
        params.append(sessao["id_usuario"])
    elif sessao["tipo_usuario"] == "empresa":
        query += """ AND e.ID_Usuarios=%s AND e.Ativo=1 AND EXISTS (
            SELECT 1 FROM Candidaturas ca WHERE ca.ID_Candidatos=a.ID_Candidatos
            AND ca.ID_Vagas=a.ID_Vagas AND ca.Ativo=1)"""
        params.append(sessao["id_usuario"])
    if id_candidato:
        query += " AND a.ID_Candidatos=%s"
        params.append(id_candidato)
    if id_vaga:
        query += " AND a.ID_Vagas=%s"
        params.append(id_vaga)
    query += " ORDER BY a.CriadoEm DESC"
    return await fetch_all(query, tuple(params))


@router.get("/analises-ia/{id_analise}")
async def obter_analise_ia(id_analise: str, sessao: dict = Depends(usuario_atual)):
    analise = await fetch_one("SELECT * FROM Analises_IA WHERE ID_Analises_IA=%s", (id_analise,))
    if not analise:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    await checar_acesso_analise(analise["ID_Candidatos"], analise["ID_Vagas"], sessao)
    return analise


class AnaliseIAResultado(BaseModel):
    score_compatibilidade: int = Field(ge=0, le=100)
    pontos_fortes: str | None = None
    lacunas: str | None = None
    justificativa: str | None = None
    modelo_ia: str | None = None


@router.patch("/analises-ia/{id_analise}/processar", dependencies=[Depends(exigir_worker_ia)])
async def processar_analise_ia(id_analise: str, resultado: AnaliseIAResultado):
    """
    Endpoint chamado pelo worker/serviço de IA (processo assíncrono) para
    gravar o resultado final e marcar como concluído.
    """
    analise = await fetch_one("SELECT * FROM Analises_IA WHERE ID_Analises_IA=%s", (id_analise,))
    if not analise:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")

    await execute(
        """UPDATE Analises_IA SET ScoreCompatibilidade=%s, PontosFortes=%s, Lacunas=%s,
               Justificativa=%s, ModeloIA=%s, ID_Status_Processamento_IA=%s, AnalisadaEm=NOW()
           WHERE ID_Analises_IA=%s""",
        (resultado.score_compatibilidade, resultado.pontos_fortes, resultado.lacunas,
         resultado.justificativa, resultado.modelo_ia, _STATUS_CONCLUIDO, id_analise),
    )
    return await fetch_one("SELECT * FROM Analises_IA WHERE ID_Analises_IA=%s", (id_analise,))


@router.patch("/analises-ia/{id_analise}/falhar", dependencies=[Depends(exigir_worker_ia)])
async def marcar_analise_ia_falhou(id_analise: str):
    if not await fetch_one("SELECT ID_Analises_IA FROM Analises_IA WHERE ID_Analises_IA=%s", (id_analise,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análise não encontrada.")
    await execute(
        "UPDATE Analises_IA SET ID_Status_Processamento_IA=%s WHERE ID_Analises_IA=%s",
        (_STATUS_FALHOU, id_analise),
    )
    return {"mensagem": "Análise marcada como falha."}


# ==================== RECOMENDAÇÕES DE VAGA ====================

class RecomendacaoVagaCreate(BaseModel):
    id_candidato: str
    id_vaga: str


@router.post("/recomendacoes-vaga", status_code=201)
async def criar_recomendacao_vaga(dados: RecomendacaoVagaCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    id_rec = novo_uuid()
    await execute(
        """INSERT INTO Recomendacoes_Vaga (ID_Recomendacoes_Vaga, ID_Candidatos, ID_Vagas, ID_Status_Processamento_IA)
           VALUES (%s, %s, %s, %s)""",
        (id_rec, dados.id_candidato, dados.id_vaga, _STATUS_NA_FILA),
    )
    return await fetch_one("SELECT * FROM Recomendacoes_Vaga WHERE ID_Recomendacoes_Vaga=%s", (id_rec,))


@router.get("/candidatos/{id_candidato}/recomendacoes-vaga")
async def listar_recomendacoes_vaga(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    await checar_dono_candidato(id_candidato, sessao)
    return await fetch_all(
        """SELECT rv.*, v.Titulo, v.Localizacao
           FROM Recomendacoes_Vaga rv
           JOIN Vagas v ON v.ID_Vagas = rv.ID_Vagas
           WHERE rv.ID_Candidatos=%s AND rv.ID_Status_Processamento_IA=3
           ORDER BY rv.Score DESC""",
        (id_candidato,),
    )


class RecomendacaoVagaResultado(BaseModel):
    score: int = Field(ge=0, le=100)
    motivo: str | None = None


@router.patch("/recomendacoes-vaga/{id_recomendacao}/processar", dependencies=[Depends(exigir_worker_ia)])
async def processar_recomendacao_vaga(id_recomendacao: str, resultado: RecomendacaoVagaResultado):
    recomendacao = await fetch_one("SELECT * FROM Recomendacoes_Vaga WHERE ID_Recomendacoes_Vaga=%s", (id_recomendacao,))
    if not recomendacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recomendação não encontrada.")
    await execute(
        """UPDATE Recomendacoes_Vaga SET Score=%s, Motivo=%s, ID_Status_Processamento_IA=%s
           WHERE ID_Recomendacoes_Vaga=%s""",
        (resultado.score, resultado.motivo, _STATUS_CONCLUIDO, id_recomendacao),
    )

    recomendacao = await fetch_one("SELECT * FROM Recomendacoes_Vaga WHERE ID_Recomendacoes_Vaga=%s", (id_recomendacao,))
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (recomendacao["ID_Candidatos"],))
    vaga = await fetch_one("SELECT Titulo FROM Vagas WHERE ID_Vagas=%s", (recomendacao["ID_Vagas"],))
    if candidato and vaga:
        candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (candidato["ID_Usuarios"],))
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Candidato"
        await notificar_usuario(
            id_usuario=candidato["ID_Usuarios"],
            titulo="Nova vaga recomendada para você",
            mensagem=f"Encontramos a vaga '{vaga['Titulo']}' que combina com seu perfil.",
            tipo="recomendacao",
            enviar_email_fn=lambda email: email_recomendacao_vaga(
                email, nome_candidato, vaga["Titulo"], resultado.motivo
            ),
        )

    return recomendacao


@router.patch("/recomendacoes-vaga/{id_recomendacao}/marcar-visualizada")
async def marcar_recomendacao_visualizada(id_recomendacao: str, sessao: dict = Depends(usuario_atual)):
    recomendacao = await fetch_one("SELECT * FROM Recomendacoes_Vaga WHERE ID_Recomendacoes_Vaga=%s", (id_recomendacao,))
    if not recomendacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recomendação não encontrada.")
    await checar_dono_candidato(recomendacao["ID_Candidatos"], sessao)
    await execute(
        "UPDATE Recomendacoes_Vaga SET Visualizada=1 WHERE ID_Recomendacoes_Vaga=%s", (id_recomendacao,)
    )
    return {"mensagem": "Recomendação marcada como visualizada."}
