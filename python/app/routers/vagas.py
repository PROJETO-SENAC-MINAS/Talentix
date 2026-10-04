"""
CRUD de Vagas, incluindo transições de status (publicar, pausar, encerrar)
e busca com filtros básicos.
"""
from app.core.routes import AtomicRouter as APIRouter

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo, usuario_opcional
from app.core.access import checar_empresa, empresa_da_sessao, checar_habilidade_ativa
from app.core.validation import Money

router = APIRouter(prefix="/vagas", tags=["Vagas"])

_ID_STATUS_RASCUNHO = 1
_ID_STATUS_PUBLICADA = 2
_ID_STATUS_PAUSADA = 3
_ID_STATUS_ENCERRADA = 4


class VagaCreate(BaseModel):
    area_profissional: str | None = Field(None, max_length=100)
    id_empresa: str
    titulo: str = Field(min_length=1, max_length=200)
    descricao: str = Field(min_length=1, max_length=20000)
    modalidade: str | None = Field(default=None, max_length=50)
    nivel: str | None = Field(default=None, max_length=50)
    tipo_contrato: str | None = Field(default=None, max_length=50)
    salario_min: Money | None = None
    salario_max: Money | None = None
    localizacao: str | None = Field(default=None, max_length=200)
    salario_confidencial: bool = False

    @model_validator(mode="after")
    def salary_range(self):
        if self.salario_min is not None and self.salario_max is not None and self.salario_min > self.salario_max:
            raise ValueError("Salário mínimo não pode superar o máximo.")
        return self


class VagaUpdate(BaseModel):
    area_profissional: str | None = Field(None, max_length=100)
    titulo: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = Field(default=None, min_length=1, max_length=20000)
    modalidade: str | None = Field(default=None, max_length=50)
    nivel: str | None = Field(default=None, max_length=50)
    tipo_contrato: str | None = Field(default=None, max_length=50)
    salario_min: Money | None = None
    salario_max: Money | None = None
    localizacao: str | None = Field(default=None, max_length=200)
    salario_confidencial: bool | None = None


async def _checar_dono_vaga(id_vaga: str, sessao: dict) -> dict:
    vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (id_vaga,))
    if not vaga:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    await checar_empresa(vaga["ID_Empresas"], sessao)
    return vaga


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar_vaga(dados: VagaCreate, sessao: dict = Depends(exigir_tipo("empresa", "recrutador", "administrador"))):
    await checar_empresa(dados.id_empresa, sessao)

    id_vaga = novo_uuid()
    await execute(
        """INSERT INTO Vagas (ID_Vagas, ID_Empresas, ID_Status_Vaga, Titulo, Descricao,
               Modalidade, Nivel, TipoContrato, SalarioMin, SalarioMax, Localizacao, SalarioConfidencial)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (id_vaga, dados.id_empresa, _ID_STATUS_RASCUNHO, dados.titulo, dados.descricao,
         dados.modalidade, dados.nivel, dados.tipo_contrato, dados.salario_min,
         dados.salario_max, dados.localizacao, dados.salario_confidencial),
    )
    await execute("UPDATE Vagas SET AreaProfissional=%s WHERE ID_Vagas=%s", (dados.area_profissional, id_vaga))
    return await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (id_vaga,))


@router.get("")
async def listar_vagas(
    titulo: str | None = None,
    modalidade: str | None = None,
    nivel: str | None = None,
    localizacao: str | None = None,
    id_empresa: str | None = None,
    apenas_publicadas: bool = True,
    sessao: dict | None = Depends(usuario_opcional),
):
    query = """SELECT * FROM Vagas WHERE Ativo=1 AND EXISTS
            (SELECT 1 FROM Empresas e WHERE e.ID_Empresas=Vagas.ID_Empresas AND e.Ativo=1)"""
    params: list = []
    empresa_id = None
    if sessao and sessao["tipo_usuario"] in {"empresa", "recrutador"}:
        empresa_id = (await empresa_da_sessao(sessao))["ID_Empresas"]
    if not apenas_publicadas and empresa_id:
        query += " AND ID_Empresas=%s"
        params.append(empresa_id)
    elif apenas_publicadas or not sessao or sessao["tipo_usuario"] != "administrador":
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
    return [_serializar_vaga(v, sessao, empresa_id) for v in await fetch_all(query, tuple(params))]


def _serializar_vaga(vaga: dict, sessao: dict | None, empresa_id: str | None):
    pode_ver = sessao and (sessao["tipo_usuario"] == "administrador" or empresa_id == vaga["ID_Empresas"])
    if vaga.get("SalarioConfidencial") and not pode_ver:
        return {**vaga, "SalarioMin": None, "SalarioMax": None}
    return vaga


@router.get("/{id_vaga}")
async def obter_vaga(id_vaga: str, sessao: dict | None = Depends(usuario_opcional)):
    vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (id_vaga,))
    if not vaga:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    if not await fetch_one("SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (vaga["ID_Empresas"],)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    empresa_id = None
    if sessao and sessao["tipo_usuario"] in {"empresa", "recrutador"}:
        empresa_id = (await empresa_da_sessao(sessao))["ID_Empresas"]
    if vaga["ID_Status_Vaga"] == _ID_STATUS_RASCUNHO and not (
        sessao and (sessao["tipo_usuario"] == "administrador" or empresa_id == vaga["ID_Empresas"])
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    habilidades = await fetch_all(
        """SELECT vh.*, h.Nome AS NomeHabilidade, h.Categoria
           FROM Vaga_Habilidades vh
           JOIN Habilidades h ON h.ID_Habilidades = vh.ID_Habilidades AND h.Ativo=1
           WHERE vh.ID_Vagas=%s""",
        (id_vaga,),
    )
    return {**_serializar_vaga(vaga, sessao, empresa_id), "habilidades": habilidades}


@router.put("/{id_vaga}")
async def atualizar_vaga(id_vaga: str, dados: VagaUpdate, sessao: dict = Depends(usuario_atual)):
    atual = await _checar_dono_vaga(id_vaga, sessao)
    campos = dados.model_dump(exclude_unset=True)
    minimo = campos.get("salario_min", atual.get("SalarioMin"))
    maximo = campos.get("salario_max", atual.get("SalarioMax"))
    if minimo is not None and maximo is not None and minimo > maximo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Salário mínimo não pode superar o máximo.")
    if not campos:
        return await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (id_vaga,))

    mapa_colunas = {
        "area_profissional": "AreaProfissional",
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
    nivel_minimo: int | None = Field(default=None, ge=0, le=255)
    peso: int | None = Field(default=None, ge=0, le=255)


@router.post("/{id_vaga}/habilidades", status_code=201)
async def adicionar_habilidade_vaga(id_vaga: str, dados: VagaHabilidadeCreate, sessao: dict = Depends(usuario_atual)):
    await _checar_dono_vaga(id_vaga, sessao)
    await checar_habilidade_ativa(dados.id_habilidade)
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
    await execute(
        "DELETE FROM Vaga_Habilidades WHERE ID_Vaga_Habilidades=%s AND ID_Vagas=%s",
        (id_vaga_habilidade, id_vaga),
    )
    return {"mensagem": "Requisito de habilidade removido."}
