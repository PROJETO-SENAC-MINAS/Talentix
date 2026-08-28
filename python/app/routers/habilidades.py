"""
CRUD de Habilidades e Idiomas (catálogos) + associações Candidato_Habilidades
e Candidato_Idiomas.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo

router = APIRouter(tags=["Habilidades e Idiomas"])


# ==================== HABILIDADES (catálogo) ====================

class HabilidadeCreate(BaseModel):
    nome: str
    categoria: str | None = None


@router.post("/habilidades", status_code=201, tags=["Habilidades"])
async def criar_habilidade(dados: HabilidadeCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    existente = await fetch_one("SELECT * FROM Habilidades WHERE Nome=%s", (dados.nome,))
    if existente:
        return existente
    id_hab = novo_uuid()
    await execute(
        "INSERT INTO Habilidades (ID_Habilidades, Nome, Categoria) VALUES (%s, %s, %s)",
        (id_hab, dados.nome, dados.categoria),
    )
    return await fetch_one("SELECT * FROM Habilidades WHERE ID_Habilidades=%s", (id_hab,))


@router.get("/habilidades", tags=["Habilidades"])
async def listar_habilidades(categoria: str | None = None, busca: str | None = None):
    query = "SELECT * FROM Habilidades WHERE Ativo=1"
    params: list = []
    if categoria:
        query += " AND Categoria=%s"
        params.append(categoria)
    if busca:
        query += " AND Nome LIKE %s"
        params.append(f"%{busca}%")
    query += " ORDER BY Nome"
    return await fetch_all(query, tuple(params))


@router.delete("/habilidades/{id_habilidade}", tags=["Habilidades"])
async def desativar_habilidade(id_habilidade: str, sessao: dict = Depends(exigir_tipo("administrador"))):
    await execute("UPDATE Habilidades SET Ativo=0 WHERE ID_Habilidades=%s", (id_habilidade,))
    return {"mensagem": "Habilidade desativada."}


# ==================== CANDIDATO x HABILIDADE ====================

class CandidatoHabilidadeCreate(BaseModel):
    id_habilidade: str
    nivel: int | None = None
    anos_experiencia: int | None = None


async def _checar_dono_candidato(id_candidato: str, sessao: dict) -> None:
    if sessao["tipo_usuario"] == "administrador":
        return
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (id_candidato,))
    if not candidato or candidato["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre este candidato.")


@router.post("/candidatos/{id_candidato}/habilidades", status_code=201, tags=["Habilidades"])
async def adicionar_habilidade_candidato(
    id_candidato: str, dados: CandidatoHabilidadeCreate, sessao: dict = Depends(usuario_atual)
):
    await _checar_dono_candidato(id_candidato, sessao)
    id_ch = novo_uuid()
    await execute(
        """INSERT INTO Candidato_Habilidades (ID_Candidato_Habilidades, ID_Candidatos, ID_Habilidades, Nivel, AnosExperiencia)
           VALUES (%s, %s, %s, %s, %s)""",
        (id_ch, id_candidato, dados.id_habilidade, dados.nivel, dados.anos_experiencia),
    )
    return await fetch_one("SELECT * FROM Candidato_Habilidades WHERE ID_Candidato_Habilidades=%s", (id_ch,))


@router.get("/candidatos/{id_candidato}/habilidades", tags=["Habilidades"])
async def listar_habilidades_candidato(id_candidato: str):
    return await fetch_all(
        """SELECT ch.*, h.Nome AS NomeHabilidade, h.Categoria
           FROM Candidato_Habilidades ch
           JOIN Habilidades h ON h.ID_Habilidades = ch.ID_Habilidades
           WHERE ch.ID_Candidatos=%s""",
        (id_candidato,),
    )


@router.delete("/candidatos/{id_candidato}/habilidades/{id_candidato_habilidade}", tags=["Habilidades"])
async def remover_habilidade_candidato(
    id_candidato: str, id_candidato_habilidade: str, sessao: dict = Depends(usuario_atual)
):
    await _checar_dono_candidato(id_candidato, sessao)
    await execute(
        "DELETE FROM Candidato_Habilidades WHERE ID_Candidato_Habilidades=%s", (id_candidato_habilidade,)
    )
    return {"mensagem": "Habilidade removida do perfil."}


# ==================== IDIOMAS (catálogo) ====================

class IdiomaCreate(BaseModel):
    nome: str


@router.post("/idiomas", status_code=201, tags=["Idiomas"])
async def criar_idioma(dados: IdiomaCreate, sessao: dict = Depends(exigir_tipo("administrador"))):
    existente = await fetch_one("SELECT * FROM Idiomas WHERE Nome=%s", (dados.nome,))
    if existente:
        return existente
    id_idioma = novo_uuid()
    await execute("INSERT INTO Idiomas (ID_Idiomas, Nome) VALUES (%s, %s)", (id_idioma, dados.nome))
    return await fetch_one("SELECT * FROM Idiomas WHERE ID_Idiomas=%s", (id_idioma,))


@router.get("/idiomas", tags=["Idiomas"])
async def listar_idiomas():
    return await fetch_all("SELECT * FROM Idiomas ORDER BY Nome")


# ==================== CANDIDATO x IDIOMA ====================

class CandidatoIdiomaCreate(BaseModel):
    id_idioma: str
    nivel: str | None = None


@router.post("/candidatos/{id_candidato}/idiomas", status_code=201, tags=["Idiomas"])
async def adicionar_idioma_candidato(
    id_candidato: str, dados: CandidatoIdiomaCreate, sessao: dict = Depends(usuario_atual)
):
    await _checar_dono_candidato(id_candidato, sessao)
    id_ci = novo_uuid()
    await execute(
        """INSERT INTO Candidato_Idiomas (ID_Candidato_Idiomas, ID_Candidatos, ID_Idiomas, Nivel)
           VALUES (%s, %s, %s, %s)""",
        (id_ci, id_candidato, dados.id_idioma, dados.nivel),
    )
    return await fetch_one("SELECT * FROM Candidato_Idiomas WHERE ID_Candidato_Idiomas=%s", (id_ci,))


@router.get("/candidatos/{id_candidato}/idiomas", tags=["Idiomas"])
async def listar_idiomas_candidato(id_candidato: str):
    return await fetch_all(
        """SELECT ci.*, i.Nome AS NomeIdioma
           FROM Candidato_Idiomas ci
           JOIN Idiomas i ON i.ID_Idiomas = ci.ID_Idiomas
           WHERE ci.ID_Candidatos=%s""",
        (id_candidato,),
    )


@router.delete("/candidatos/{id_candidato}/idiomas/{id_candidato_idioma}", tags=["Idiomas"])
async def remover_idioma_candidato(id_candidato: str, id_candidato_idioma: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_candidato(id_candidato, sessao)
    await execute("DELETE FROM Candidato_Idiomas WHERE ID_Candidato_Idiomas=%s", (id_candidato_idioma,))
    return {"mensagem": "Idioma removido do perfil."}