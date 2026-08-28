"""
CRUD de Currículos (com upload de arquivo), Experiências e Formações.
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from datetime import date

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual
from app.core.upload import salvar_arquivo, remover_arquivo

router = APIRouter(tags=["Currículo"])


async def _checar_dono_candidato(id_candidato: str, sessao: dict) -> None:
    if sessao["tipo_usuario"] == "administrador":
        return
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (id_candidato,))
    if not candidato or candidato["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre este candidato.")


# ==================== CURRÍCULOS (arquivo) ====================

@router.post("/candidatos/{id_candidato}/curriculos", status_code=201, tags=["Currículos"])
async def enviar_curriculo(
    id_candidato: str,
    titulo: str = Form(...),
    principal: bool = Form(False),
    arquivo: UploadFile = File(...),
    sessao: dict = Depends(usuario_atual),
):
    await _checar_dono_candidato(id_candidato, sessao)
    info = await salvar_arquivo(arquivo, "curriculos")

    if principal:
        await execute("UPDATE Curriculos SET Principal=0 WHERE ID_Candidatos=%s", (id_candidato,))

    id_curriculo = novo_uuid()
    await execute(
        """INSERT INTO Curriculos
           (ID_Curriculos, ID_Candidatos, Titulo, ArquivoUrl, ArquivoTamanhoBytes, ArquivoTipoMime, ArquivoHash, Principal)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_curriculo, id_candidato, titulo, info["url"], info["tamanho_bytes"],
         info["tipo_mime"], info["hash"], principal),
    )
    return await fetch_one("SELECT * FROM Curriculos WHERE ID_Curriculos=%s", (id_curriculo,))


@router.get("/candidatos/{id_candidato}/curriculos", tags=["Currículos"])
async def listar_curriculos(id_candidato: str):
    return await fetch_all(
        "SELECT * FROM Curriculos WHERE ID_Candidatos=%s AND Ativo=1 ORDER BY Principal DESC, AtualizadoEm DESC",
        (id_candidato,),
    )


@router.delete("/curriculos/{id_curriculo}", tags=["Currículos"])
async def excluir_curriculo(id_curriculo: str, sessao: dict = Depends(usuario_atual)):
    curriculo = await fetch_one("SELECT * FROM Curriculos WHERE ID_Curriculos=%s", (id_curriculo,))
    if not curriculo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Currículo não encontrado.")
    await _checar_dono_candidato(curriculo["ID_Candidatos"], sessao)
    await execute(
        "UPDATE Curriculos SET Ativo=0, DeletadoEm=NOW() WHERE ID_Curriculos=%s", (id_curriculo,)
    )
    return {"mensagem": "Currículo removido (soft delete)."}


# ==================== EXPERIÊNCIAS ====================

class ExperienciaCreate(BaseModel):
    empresa: str
    cargo: str
    descricao: str | None = None
    data_inicio: date
    data_fim: date | None = None
    atual: bool = False


@router.post("/candidatos/{id_candidato}/experiencias", status_code=201, tags=["Experiências"])
async def criar_experiencia(id_candidato: str, dados: ExperienciaCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    id_exp = novo_uuid()
    await execute(
        """INSERT INTO Experiencias (ID_Experiencias, ID_Candidatos, Empresa, Cargo, Descricao, DataInicio, DataFim, Atual)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_exp, id_candidato, dados.empresa, dados.cargo, dados.descricao,
         dados.data_inicio, dados.data_fim, dados.atual),
    )
    return await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_exp,))


@router.get("/candidatos/{id_candidato}/experiencias", tags=["Experiências"])
async def listar_experiencias(id_candidato: str):
    return await fetch_all(
        "SELECT * FROM Experiencias WHERE ID_Candidatos=%s ORDER BY DataInicio DESC", (id_candidato,)
    )


@router.put("/experiencias/{id_experiencia}", tags=["Experiências"])
async def atualizar_experiencia(id_experiencia: str, dados: ExperienciaCreate, sessao: dict = Depends(usuario_atual)):
    experiencia = await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))
    if not experiencia:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiência não encontrada.")
    await _checar_dono_candidato(experiencia["ID_Candidatos"], sessao)
    await execute(
        """UPDATE Experiencias SET Empresa=%s, Cargo=%s, Descricao=%s, DataInicio=%s, DataFim=%s, Atual=%s
           WHERE ID_Experiencias=%s""",
        (dados.empresa, dados.cargo, dados.descricao, dados.data_inicio, dados.data_fim,
         dados.atual, id_experiencia),
    )
    return await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))


@router.delete("/experiencias/{id_experiencia}", tags=["Experiências"])
async def excluir_experiencia(id_experiencia: str, sessao: dict = Depends(usuario_atual)):
    experiencia = await fetch_one("SELECT * FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))
    if not experiencia:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiência não encontrada.")
    await _checar_dono_candidato(experiencia["ID_Candidatos"], sessao)
    await execute("DELETE FROM Experiencias WHERE ID_Experiencias=%s", (id_experiencia,))
    return {"mensagem": "Experiência excluída."}


# ==================== FORMAÇÕES ====================

class FormacaoCreate(BaseModel):
    instituicao: str
    curso: str
    nivel: str | None = None
    data_inicio: date | None = None
    data_conclusao: date | None = None
    status_formacao: str | None = None


@router.post("/candidatos/{id_candidato}/formacoes", status_code=201, tags=["Formações"])
async def criar_formacao(id_candidato: str, dados: FormacaoCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    id_form = novo_uuid()
    await execute(
        """INSERT INTO Formacoes (ID_Formacoes, ID_Candidatos, Instituicao, Curso, Nivel, DataInicio, DataConclusao, Status)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_form, id_candidato, dados.instituicao, dados.curso, dados.nivel,
         dados.data_inicio, dados.data_conclusao, dados.status_formacao),
    )
    return await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_form,))


@router.get("/candidatos/{id_candidato}/formacoes", tags=["Formações"])
async def listar_formacoes(id_candidato: str):
    return await fetch_all(
        "SELECT * FROM Formacoes WHERE ID_Candidatos=%s ORDER BY DataInicio DESC", (id_candidato,)
    )


@router.put("/formacoes/{id_formacao}", tags=["Formações"])
async def atualizar_formacao(id_formacao: str, dados: FormacaoCreate, sessao: dict = Depends(usuario_atual)):
    formacao = await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))
    if not formacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Formação não encontrada.")
    await _checar_dono_candidato(formacao["ID_Candidatos"], sessao)
    await execute(
        """UPDATE Formacoes SET Instituicao=%s, Curso=%s, Nivel=%s, DataInicio=%s, DataConclusao=%s, Status=%s
           WHERE ID_Formacoes=%s""",
        (dados.instituicao, dados.curso, dados.nivel, dados.data_inicio,
         dados.data_conclusao, dados.status_formacao, id_formacao),
    )
    return await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))


@router.delete("/formacoes/{id_formacao}", tags=["Formações"])
async def excluir_formacao(id_formacao: str, sessao: dict = Depends(usuario_atual)):
    formacao = await fetch_one("SELECT * FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))
    if not formacao:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Formação não encontrada.")
    await _checar_dono_candidato(formacao["ID_Candidatos"], sessao)
    await execute("DELETE FROM Formacoes WHERE ID_Formacoes=%s", (id_formacao,))
    return {"mensagem": "Formação excluída."}