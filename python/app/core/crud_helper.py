"""
Helper para expor rapidamente endpoints de LEITURA em tabelas de domínio
simples (Status_*), que raramente mudam e não precisam de rotas de escrita
customizadas via API (são geridas via seed/migração).
"""
from fastapi import APIRouter
from app.db.database import fetch_all


def criar_router_dominio(nome_tabela: str, nome_pk: str, prefixo: str, tag: str) -> APIRouter:
    router = APIRouter(prefix=prefixo, tags=[tag])

    @router.get("")
    async def listar():
        linhas = await fetch_all(f"SELECT * FROM {nome_tabela} ORDER BY {nome_pk}")
        return linhas

    return router