"""Regras administrativas determinísticas; IA não executa decisões de contratação."""

import json
from typing import Literal
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.audit import registrar_auditoria
from app.core.security import novo_uuid
from app.db.database import fetch_one, fetch_all, execute
from app.routers.organizations import contexto_empresa

router = AtomicRouter(prefix="/automacoes", tags=["Automações"])


class Regra(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: str = Field(min_length=1, max_length=120)
    gatilho: Literal["mudanca_etapa", "parado"]
    dias: int = Field(default=7, ge=1, le=90)
    etapa: str = Field(default="", max_length=150)
    acao: Literal["tarefa", "notificacao", "email"]
    destino: Literal["rh", "candidato"] = "rh"
    conteudo: str = Field(min_length=1, max_length=1000)
    ativa: bool = False


@router.get("")
async def listar(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "automacoes")
    return await fetch_all(
        "SELECT * FROM Automacoes WHERE ID_Empresas=%s ORDER BY CriadoEm DESC LIMIT 100",
        (e["ID_Empresas"],),
    )


@router.post("", status_code=201)
async def criar(
    d: Regra, request: Request, id_empresa: str | None = None, s=Depends(usuario_atual)
):
    e = await contexto_empresa(s, id_empresa, "automacoes")
    id = novo_uuid()
    cond = json.dumps(
        {"dias": d.dias, "etapa": d.etapa, "destino": d.destino}, ensure_ascii=False
    )
    await execute(
        "INSERT INTO Automacoes(ID_Regra,ID_Empresas,Nome,Gatilho,Condicoes,Acao,Conteudo,Ativa) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (id, e["ID_Empresas"], d.nome, d.gatilho, cond, d.acao, d.conteudo, d.ativa),
    )
    await registrar_auditoria(
        request,
        "automacao.criar",
        "Automacoes",
        s["id_usuario"],
        id,
        novo={"gatilho": d.gatilho, "acao": d.acao, "ativa": d.ativa},
    )
    return {"id": id}


class Estado(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ativa: bool
    versao: int = Field(ge=1)


@router.put("/{id}")
async def estado(id: str, d: Estado, request: Request, s=Depends(usuario_atual)):
    r = await fetch_one("SELECT * FROM Automacoes WHERE ID_Regra=%s FOR UPDATE", (id,))
    if not r:
        raise HTTPException(404, "Regra indisponível.")
    await contexto_empresa(s, r["ID_Empresas"], "automacoes")
    if r["Versao"] != d.versao:
        raise HTTPException(409, "Regra alterada; recarregue.")
    await execute(
        "UPDATE Automacoes SET Ativa=%s,Versao=Versao+1 WHERE ID_Regra=%s",
        (d.ativa, id),
    )
    await registrar_auditoria(
        request,
        "automacao.estado",
        "Automacoes",
        s["id_usuario"],
        id,
        novo=d.model_dump(),
    )
    return {"mensagem": "Regra atualizada."}


@router.get("/registros/execucoes")
async def execucoes(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "automacoes")
    return await fetch_all(
        """SELECT x.*,r.Nome FROM Automacao_Execucoes x JOIN Automacoes r ON r.ID_Regra=x.ID_Regra
        WHERE r.ID_Empresas=%s ORDER BY x.CriadoEm DESC LIMIT 100""",
        (e["ID_Empresas"],),
    )


@router.get("/registros/tarefas")
async def tarefas(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "ler")
    return await fetch_all(
        "SELECT * FROM Tarefas WHERE ID_Empresas=%s ORDER BY Concluida,CriadoEm DESC LIMIT 100",
        (e["ID_Empresas"],),
    )


@router.patch("/tarefas/{id}/concluir")
async def concluir(id: str, request: Request, s=Depends(usuario_atual)):
    t = await fetch_one("SELECT * FROM Tarefas WHERE ID_Tarefa=%s FOR UPDATE", (id,))
    if not t:
        raise HTTPException(404, "Tarefa indisponível.")
    await contexto_empresa(s, t["ID_Empresas"], "processos")
    await execute("UPDATE Tarefas SET Concluida=1 WHERE ID_Tarefa=%s", (id,))
    await registrar_auditoria(
        request, "tarefa.concluir", "Tarefas", s["id_usuario"], id
    )
    return {"mensagem": "Tarefa concluída."}
