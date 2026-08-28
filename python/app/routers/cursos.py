"""
CRUD de Cursos (catálogo) e Recomendações de Curso para candidatos.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.notificar import notificar_usuario
from app.core.email_service import email_recomendacao_curso

router = APIRouter(tags=["Cursos"])

_STATUS_NA_FILA = 1
_STATUS_CONCLUIDO = 3


# ==================== CURSOS (catálogo) ====================

class CursoCreate(BaseModel):
    titulo: str
    descricao: str | None = None
    plataforma: str | None = None
    url: str | None = None
    nivel: str | None = None
    categoria: str | None = None
    carga_horaria: int | None = None


@router.post("/cursos", status_code=201)
async def criar_curso(dados: CursoCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    id_curso = novo_uuid()
    await execute(
        """INSERT INTO Cursos (ID_Cursos, Titulo, Descricao, Plataforma, Url, Nivel, Categoria, CargaHoraria)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_curso, dados.titulo, dados.descricao, dados.plataforma, dados.url,
         dados.nivel, dados.categoria, dados.carga_horaria),
    )
    return await fetch_one("SELECT * FROM Cursos WHERE ID_Cursos=%s", (id_curso,))


@router.get("/cursos")
async def listar_cursos(categoria: str | None = None, nivel: str | None = None):
    query = "SELECT * FROM Cursos WHERE Ativo=1"
    params: list = []
    if categoria:
        query += " AND Categoria=%s"
        params.append(categoria)
    if nivel:
        query += " AND Nivel=%s"
        params.append(nivel)
    query += " ORDER BY Titulo"
    return await fetch_all(query, tuple(params))


@router.get("/cursos/{id_curso}")
async def obter_curso(id_curso: str):
    curso = await fetch_one("SELECT * FROM Cursos WHERE ID_Cursos=%s AND Ativo=1", (id_curso,))
    if not curso:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Curso não encontrado.")
    return curso


@router.put("/cursos/{id_curso}")
async def atualizar_curso(id_curso: str, dados: CursoCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    await execute(
        """UPDATE Cursos SET Titulo=%s, Descricao=%s, Plataforma=%s, Url=%s, Nivel=%s, Categoria=%s, CargaHoraria=%s
           WHERE ID_Cursos=%s""",
        (dados.titulo, dados.descricao, dados.plataforma, dados.url, dados.nivel,
         dados.categoria, dados.carga_horaria, id_curso),
    )
    return await fetch_one("SELECT * FROM Cursos WHERE ID_Cursos=%s", (id_curso,))


@router.delete("/cursos/{id_curso}")
async def desativar_curso(id_curso: str, sessao: dict = Depends(exigir_tipo("administrador"))):
    await execute("UPDATE Cursos SET Ativo=0 WHERE ID_Cursos=%s", (id_curso,))
    return {"mensagem": "Curso desativado."}


# ==================== RECOMENDAÇÕES DE CURSO ====================

class RecomendacaoCursoCreate(BaseModel):
    id_candidato: str
    id_curso: str
    motivo: str | None = None
    prioridade: int | None = None


@router.post("/recomendacoes-curso", status_code=201)
async def criar_recomendacao_curso(dados: RecomendacaoCursoCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    id_rec = novo_uuid()
    await execute(
        """INSERT INTO Recomendacoes_Curso
               (ID_Recomendacoes_Curso, ID_Candidatos, ID_Cursos, ID_Status_Processamento_IA, Motivo, Prioridade)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (id_rec, dados.id_candidato, dados.id_curso, _STATUS_CONCLUIDO, dados.motivo, dados.prioridade),
    )

    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (dados.id_candidato,))
    curso = await fetch_one("SELECT Titulo FROM Cursos WHERE ID_Cursos=%s", (dados.id_curso,))
    if candidato and curso:
        candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (candidato["ID_Usuarios"],))
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Candidato"
        await notificar_usuario(
            id_usuario=candidato["ID_Usuarios"],
            titulo="Nova recomendação de curso",
            mensagem=f"Recomendamos o curso '{curso['Titulo']}' para você.",
            tipo="curso",
            enviar_email_fn=lambda email: email_recomendacao_curso(
                email, nome_candidato, curso["Titulo"], dados.motivo
            ),
        )

    return await fetch_one("SELECT * FROM Recomendacoes_Curso WHERE ID_Recomendacoes_Curso=%s", (id_rec,))


@router.get("/candidatos/{id_candidato}/recomendacoes-curso")
async def listar_recomendacoes_curso(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    return await fetch_all(
        """SELECT rc.*, c.Titulo, c.Plataforma, c.Url
           FROM Recomendacoes_Curso rc
           JOIN Cursos c ON c.ID_Cursos = rc.ID_Cursos
           WHERE rc.ID_Candidatos=%s ORDER BY rc.Prioridade DESC""",
        (id_candidato,),
    )


@router.patch("/recomendacoes-curso/{id_recomendacao}/concluir")
async def concluir_recomendacao_curso(id_recomendacao: str, sessao: dict = Depends(usuario_atual)):
    await execute(
        "UPDATE Recomendacoes_Curso SET Concluida=1 WHERE ID_Recomendacoes_Curso=%s", (id_recomendacao,)
    )
    return {"mensagem": "Recomendação marcada como concluída."}