"""
CRUD de perfis: Candidatos, Empresas, Administradores, Recrutadores.
(Usuarios em si não tem rota de criação direta — isso acontece via /auth/cadastro/*)
"""
from app.core.routes import AtomicRouter as APIRouter

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.access import checar_leitura_candidato, checar_dono_candidato, checar_empresa, empresa_da_sessao
from app.core.validation import Money, normalize_state

router = APIRouter(tags=["Perfis"])


# ==================== CANDIDATOS ====================

class CandidatoUpdate(BaseModel):
    titulo_profissional: str | None = Field(default=None, max_length=150)
    resumo: str | None = None
    cidade: str | None = Field(default=None, max_length=100)
    estado: str | None = Field(default=None, max_length=2)
    linkedin_url: str | None = Field(default=None, max_length=300)
    github_url: str | None = Field(default=None, max_length=300)
    portfolio_url: str | None = Field(default=None, max_length=300)
    experiencia_anos: int | None = Field(default=None, ge=0, le=80)
    pretensao_salarial: Money | None = None
    disponivel: bool | None = None

    _uf = field_validator("estado", mode="before")(normalize_state)


@router.get("/candidatos", tags=["Candidatos"])
async def listar_candidatos(
    cidade: str | None = None,
    disponivel: bool | None = None,
    sessao: dict = Depends(exigir_tipo("candidato", "empresa", "recrutador", "administrador")),
):
    query = "SELECT c.* FROM Candidatos c WHERE c.Ativo=1"
    params: list = []
    if sessao["tipo_usuario"] == "candidato":
        query += " AND c.ID_Usuarios=%s"
        params.append(sessao["id_usuario"])
    elif sessao["tipo_usuario"] in {"empresa", "recrutador"}:
        empresa = await empresa_da_sessao(sessao)
        query += """ AND EXISTS (SELECT 1 FROM Candidaturas ca
            JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas
            JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
            WHERE ca.ID_Candidatos=c.ID_Candidatos AND ca.Ativo=1 AND e.ID_Empresas=%s)"""
        params.append(empresa["ID_Empresas"])
    if cidade:
        query += " AND c.Cidade=%s"
        params.append(cidade)
    if disponivel is not None:
        query += " AND c.Disponivel=%s"
        params.append(disponivel)
    query += " ORDER BY c.CriadoEm DESC"
    return await fetch_all(query, tuple(params))


@router.get("/candidatos/me", tags=["Candidatos"])
async def obter_meu_perfil_candidato(sessao: dict = Depends(usuario_atual)):
    candidato = await fetch_one(
        "SELECT * FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1", (sessao["id_usuario"],)
    )
    if not candidato:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Perfil de candidato não encontrado para este usuário.")
    return candidato


@router.get("/candidatos/{id_candidato}", tags=["Candidatos"])
async def obter_candidato(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    return await checar_leitura_candidato(id_candidato, sessao)


@router.put("/candidatos/{id_candidato}", tags=["Candidatos"])
async def atualizar_candidato(
    id_candidato: str, dados: CandidatoUpdate, sessao: dict = Depends(usuario_atual)
):
    candidato = await checar_dono_candidato(id_candidato, sessao)
    if not candidato:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidato não encontrado.")
    if candidato["ID_Usuarios"] != sessao["id_usuario"] and sessao["tipo_usuario"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você só pode editar seu próprio perfil.")

    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return candidato

    mapa_colunas = {
        "titulo_profissional": "TituloProfissional", "resumo": "Resumo", "cidade": "Cidade",
        "estado": "Estado", "linkedin_url": "LinkedinUrl", "github_url": "GithubUrl",
        "portfolio_url": "PortfolioUrl", "experiencia_anos": "ExperienciaAnos",
        "pretensao_salarial": "PretensaoSalarial", "disponivel": "Disponivel",
    }
    set_clauses = [f"{mapa_colunas[k]}=%s" for k in campos]
    valores = list(campos.values()) + [id_candidato]
    await execute(f"UPDATE Candidatos SET {', '.join(set_clauses)} WHERE ID_Candidatos=%s", tuple(valores))

    return await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (id_candidato,))


@router.delete("/candidatos/{id_candidato}", tags=["Candidatos"])
async def desativar_candidato(id_candidato: str, sessao: dict = Depends(usuario_atual)):
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (id_candidato,))
    if not candidato:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidato não encontrado.")
    if candidato["ID_Usuarios"] != sessao["id_usuario"] and sessao["tipo_usuario"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute(
        "UPDATE Candidatos SET Ativo=0, DeletadoEm=NOW() WHERE ID_Candidatos=%s", (id_candidato,)
    )
    return {"mensagem": "Candidato desativado (soft delete)."}


# ==================== EMPRESAS ====================

class EmpresaUpdate(BaseModel):
    nome_fantasia: str | None = Field(default=None, max_length=200)
    descricao: str | None = None
    setor: str | None = Field(default=None, max_length=100)
    porte: str | None = Field(default=None, max_length=50)
    site_url: str | None = Field(default=None, max_length=300)
    endereco: str | None = Field(default=None, max_length=300)


@router.get("/empresas", tags=["Empresas"])
async def listar_empresas(setor: str | None = None):
    query = "SELECT * FROM Empresas WHERE Ativo=1"
    params: list = []
    if setor:
        query += " AND Setor=%s"
        params.append(setor)
    query += " ORDER BY CriadoEm DESC"
    return await fetch_all(query, tuple(params))


@router.get("/empresas/me", tags=["Empresas"])
async def minha_empresa(sessao: dict = Depends(exigir_tipo("empresa", "recrutador"))):
    return await empresa_da_sessao(sessao)


@router.get("/empresas/{id_empresa}", tags=["Empresas"])
async def obter_empresa(id_empresa: str):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    return empresa


@router.put("/empresas/{id_empresa}", tags=["Empresas"])
async def atualizar_empresa(id_empresa: str, dados: EmpresaUpdate, sessao: dict = Depends(usuario_atual)):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    if empresa["ID_Usuarios"] != sessao["id_usuario"] and sessao["tipo_usuario"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")

    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return empresa

    mapa_colunas = {
        "nome_fantasia": "NomeFantasia", "descricao": "Descricao", "setor": "Setor",
        "porte": "Porte", "site_url": "SiteUrl", "endereco": "Endereco",
    }
    set_clauses = [f"{mapa_colunas[k]}=%s" for k in campos]
    valores = list(campos.values()) + [id_empresa]
    await execute(f"UPDATE Empresas SET {', '.join(set_clauses)} WHERE ID_Empresas=%s", tuple(valores))

    return await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))


@router.patch("/empresas/{id_empresa}/verificar", tags=["Empresas"])
async def verificar_empresa(id_empresa: str, sessao: dict = Depends(exigir_tipo("administrador"))):
    await checar_empresa(id_empresa, sessao)
    await execute("UPDATE Empresas SET Verificada=1 WHERE ID_Empresas=%s", (id_empresa,))
    return {"mensagem": "Empresa verificada."}


@router.delete("/empresas/{id_empresa}", tags=["Empresas"])
async def desativar_empresa(id_empresa: str, sessao: dict = Depends(usuario_atual)):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    if empresa["ID_Usuarios"] != sessao["id_usuario"] and sessao["tipo_usuario"] != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")
    await execute("UPDATE Empresas SET Ativo=0, DeletadoEm=NOW() WHERE ID_Empresas=%s", (id_empresa,))
    return {"mensagem": "Empresa desativada (soft delete)."}


# ==================== RECRUTADORES ====================

class RecrutadorCreate(BaseModel):
    id_usuario_recrutador: str = Field(min_length=1, max_length=36)
    cargo: str | None = Field(default=None, max_length=100)


@router.post("/empresas/{id_empresa}/recrutadores", status_code=201, tags=["Recrutadores"])
async def adicionar_recrutador(
    id_empresa: str, dados: RecrutadorCreate, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))
):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    if sessao["tipo_usuario"] == "empresa" and empresa["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta empresa.")

    if not await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1", (dados.id_usuario_recrutador,)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário do recrutador não encontrado.")
    existente = await fetch_one("SELECT * FROM Recrutadores WHERE ID_Usuarios=%s", (dados.id_usuario_recrutador,))
    if existente:
        if existente["Ativo"] or existente["ID_Empresas"] != id_empresa:
            raise HTTPException(status.HTTP_409_CONFLICT, "Usuário já possui vínculo de recrutamento.")
        await execute("UPDATE Recrutadores SET Ativo=1, DeletadoEm=NULL, Cargo=%s WHERE ID_Recrutadores=%s",
                      (dados.cargo, existente["ID_Recrutadores"]))
        return await fetch_one("SELECT * FROM Recrutadores WHERE ID_Recrutadores=%s", (existente["ID_Recrutadores"],))
    id_recrutador = novo_uuid()
    await execute(
        """INSERT INTO Recrutadores (ID_Recrutadores, ID_Empresas, ID_Usuarios, Cargo)
           VALUES (%s, %s, %s, %s)""",
        (id_recrutador, id_empresa, dados.id_usuario_recrutador, dados.cargo),
    )
    return await fetch_one("SELECT * FROM Recrutadores WHERE ID_Recrutadores=%s", (id_recrutador,))


@router.get("/empresas/{id_empresa}/recrutadores", tags=["Recrutadores"])
async def listar_recrutadores(id_empresa: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_empresa_recrutador(id_empresa, sessao)
    return await fetch_all(
        "SELECT * FROM Recrutadores WHERE ID_Empresas=%s AND Ativo=1", (id_empresa,)
    )


@router.delete("/recrutadores/{id_recrutador}", tags=["Recrutadores"])
async def remover_recrutador(id_recrutador: str, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))):
    recrutador = await fetch_one("SELECT * FROM Recrutadores WHERE ID_Recrutadores=%s", (id_recrutador,))
    if not recrutador:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recrutador não encontrado.")
    await _checar_dono_empresa_recrutador(recrutador["ID_Empresas"], sessao)
    await execute(
        "UPDATE Recrutadores SET Ativo=0, DeletadoEm=NOW() WHERE ID_Recrutadores=%s", (id_recrutador,)
    )
    return {"mensagem": "Recrutador removido (soft delete)."}


async def _checar_dono_empresa_recrutador(id_empresa: str, sessao: dict) -> None:
    await checar_empresa(id_empresa, sessao)


# ==================== ADMINISTRADORES ====================

@router.get("/administradores", tags=["Administradores"])
async def listar_administradores(sessao: dict = Depends(exigir_tipo("administrador"))):
    return await fetch_all("SELECT * FROM Administradores WHERE Ativo=1")
