"""
Endpoints de leitura para as tabelas de domínio (status/enums).
Usados pelo front-end para popular selects/filtros.
"""
from fastapi import APIRouter
from app.db.database import fetch_all

router = APIRouter(prefix="/dominios", tags=["Domínios (Status)"])

_TABELAS = {
    "status-vaga": ("Status_Vaga", "ID_Status_Vaga"),
    "status-candidatura": ("Status_Candidatura", "ID_Status_Candidatura"),
    "status-etapa": ("Status_Etapa", "ID_Status_Etapa"),
    "status-entrevista": ("Status_Entrevista", "ID_Status_Entrevista"),
    "status-denuncia": ("Status_Denuncia", "ID_Status_Denuncia"),
    "status-assinatura": ("Status_Assinatura", "ID_Status_Assinatura"),
    "status-pagamento": ("Status_Pagamento", "ID_Status_Pagamento"),
    "status-processamento-ia": ("Status_Processamento_IA", "ID_Status_Processamento_IA"),
}


@router.get("/{chave}")
async def listar_dominio(chave: str):
    if chave not in _TABELAS:
        return []
    tabela, pk = _TABELAS[chave]
    return await fetch_all(f"SELECT * FROM {tabela} ORDER BY {pk}")


@router.get("")
async def listar_todos_dominios():
    """Retorna todas as tabelas de domínio de uma vez (útil para inicializar o front)."""
    resultado = {}
    for chave, (tabela, pk) in _TABELAS.items():
        resultado[chave] = await fetch_all(f"SELECT * FROM {tabela} ORDER BY {pk}")
    return resultado