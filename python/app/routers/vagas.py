"""
CRUD de Vagas, incluindo transições de status (publicar, pausar, encerrar)
e busca com filtros básicos.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo

router = APIRouter(prefix="/vagas", tags=["Vagas"])

_ID_STATUS_RASCUNHO = 1
_ID_STATUS_PUBLICADA = 2
_ID_STATUS_PAUSADA = 3
_ID_STATUS_ENCERRADA = 4


class VagaCreate(BaseModel):
    id_empresa: str
    titulo: str
    descricao: str
    modalidade: str | None = None
    nivel: str | None = None
    tipo_contrato: str | None = None
    salario_min: float | None = None
    salario_max: float | None = None
    localizacao: str | None = None
    salario_confidencial: bool = False


class VagaUpdate(BaseModel):
    titulo: str | None = None
    descricao: str | None = None
    modalidade: str | None = None
    nivel: str | None = None
    tipo_contrato: str | None = None
    salario_min: float | None = None
    salario_max: float | None = None
    localizacao: str | None = None
    salario_confidencial: bool | None = None


async def _checar_dono_vaga(id_vaga: str, sessao: dict) -> dict:
    vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (id_vaga,))
    if not vaga:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    if sessao["tipo_usuario"] == "administrador":
        return vaga
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (vaga["ID_Empresas"],))
    if not empresa or empresa["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta vaga.")
    return vaga


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar_vaga(dados: VagaCreate, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))):
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (dados.id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    if sessao["tipo_usuario"] == "empresa" and empresa["ID_Usuarios"] != sessao["id_usuario"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta empresa.")

    id_vaga = novo_uuid()
    await execute(
        """INSERT INTO Vagas (ID_Vagas, ID_Empresas, ID_Status_Vaga, Titulo, Descricao,
               Modalidade, Nivel, TipoContrato, SalarioMin, SalarioMax, Localizacao, SalarioConfidencial)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_vaga, dados.id_empresa, _ID_STATUS_RASCUNHO, dados.titulo, dados.descricao,
         dados.modalidade, dados.nivel, dados.tipo_contrato, dados.salario_min,
         dados.salario_max, dados.localizacao, dados.salario_confidencial),
    )
    return await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (id_vaga,))


@router.get("")
async def listar_vagas(
    titulo: str | None = None,
    modalidade: str | None = None,
    nivel: str | None = None,
    localizacao: str | None = None,
    id_empresa: str | None = None,
    apenas_publicadas: bool = True,
):
    query = "SELECT * FROM Vagas WHERE Ativo=1"
    params: list = []
    if apenas_publicadas:
        query += " AND ID_Status_Vaga=%s"
        params.append(_ID_STATUS_PUBLICADA)
    if titulo:
        query += " AND Titulo LIKE %s"
        params.append(f"%{titulo}%")
    if modalidade:
        query += " AND Modalidade=%s"
        params.append(modalidade)
    if nivel:
        query += " AND Nivel=%s"
        params.append(nivel)
    if localizacao:
        query += " AND Localizacao LIKE %s"
        params.append(f"%{localizacao}%")
    if id_empresa:
        query += " AND ID_Empresas=%s"
        params.append(id_empresa)
    query += " ORDER BY PublicadaEm DESC, CriadoEm DESC"
    return await fetch_all(query, tuple(params))


@router.get("/{id_vaga}")
async def obter_vaga(id_vaga: str):
    vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (id_vaga,))
    if not vaga:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    habilidades = await fetch_all(
        """SELECT vh.*, h.Nome AS NomeHabilidade, h.Categoria
           FROM Vaga_Habilidades vh
           JOIN Habilidades h ON h.ID_Habilidades = vh.ID_Habilidades
           WHERE vh.ID_Vagas=%s""",
        (id_vaga,),
    )
    return {**vaga, "habilidades": habilidades}


@router.put("/{id_vaga}")
async def atualizar_vaga(id_vaga: str, dados: VagaUpdate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        return await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (id_vaga,))

    mapa_colunas = {
        "titulo": "Titulo", "descricao": "Descricao", "modalidade": "Modalidade",
        "nivel": "Nivel", "tipo_contrato": "TipoContrato", "salario_min": "SalarioMin",
        "salario_max": "SalarioMax", "localizacao": "Localizacao",
        "salario_confidencial": "SalarioConfidencial",
    }
    set_clauses = [f"{mapa_colunas[k]}=%s" for k in campos]
    valores = list(campos.values()) + [id_vaga]
    await execute(f"UPDATE Vagas SET {', '.join(set_clauses)} WHERE ID_Vagas=%s", tuple(valores))
    return await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (id_vaga,))


@router.patch("/{id_vaga}/publicar")
async def publicar_vaga(id_vaga: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    await execute(
        "UPDATE Vagas SET ID_Status_Vaga=%s, PublicadaEm=NOW() WHERE ID_Vagas=%s",
        (_ID_STATUS_PUBLICADA, id_vaga),
    )
    return {"mensagem": "Vaga publicada."}


@router.patch("/{id_vaga}/pausar")
async def pausar_vaga(id_vaga: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    await execute("UPDATE Vagas SET ID_Status_Vaga=%s WHERE ID_Vagas=%s", (_ID_STATUS_PAUSADA, id_vaga))
    return {"mensagem": "Vaga pausada."}


@router.patch("/{id_vaga}/encerrar")
async def encerrar_vaga(id_vaga: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    await execute(
        "UPDATE Vagas SET ID_Status_Vaga=%s, EncerradaEm=NOW() WHERE ID_Vagas=%s",
        (_ID_STATUS_ENCERRADA, id_vaga),
    )
    return {"mensagem": "Vaga encerrada."}


@router.delete("/{id_vaga}")
async def excluir_vaga(id_vaga: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    await execute("UPDATE Vagas SET Ativo=0, DeletadoEm=NOW() WHERE ID_Vagas=%s", (id_vaga,))
    return {"mensagem": "Vaga excluída (soft delete)."}


# ---------- Vaga x Habilidades ----------

class VagaHabilidadeCreate(BaseModel):
    id_habilidade: str
    obrigatoria: bool = False
    nivel_minimo: int | None = None
    peso: int | None = None


@router.post("/{id_vaga}/habilidades", status_code=201)
async def adicionar_habilidade_vaga(id_vaga: str, dados: VagaHabilidadeCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    id_vh = novo_uuid()
    await execute(
        """INSERT INTO Vaga_Habilidades (ID_Vaga_Habilidades, ID_Vagas, ID_Habilidades, Obrigatoria, NivelMinimo, Peso)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (id_vh, id_vaga, dados.id_habilidade, dados.obrigatoria, dados.nivel_minimo, dados.peso),
    )
    return await fetch_one("SELECT * FROM Vaga_Habilidades WHERE ID_Vaga_Habilidades=%s", (id_vh,))


@router.delete("/{id_vaga}/habilidades/{id_vaga_habilidade}")
async def remover_habilidade_vaga(id_vaga: str, id_vaga_habilidade: str, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    await execute("DELETE FROM Vaga_Habilidades WHERE ID_Vaga_Habilidades=%s", (id_vaga_habilidade,))
    return {"mensagem": "Requisito de habilidade removido."}