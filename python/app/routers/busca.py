"""Busca paginada pública; histórico, preferências e alertas pertencem à sessão."""
import json
from datetime import datetime, timedelta
from typing import Annotated, Literal
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.routes import AtomicRouter
from app.core.deps import usuario_opcional, exigir_tipo
from app.core.security import novo_uuid
from app.db.database import fetch_all, fetch_one, execute

router = AtomicRouter(tags=["Busca profissional"])


class FiltrosBusca(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cargo: str = Field("", max_length=200)
    palavra_chave: str = Field("", max_length=200)
    localizacao: str = Field("", max_length=200)
    modalidade: Literal["", "remoto", "hibrido", "presencial", "Remoto", "Híbrido", "Presencial"] = ""
    salario_min: float | None = Field(None, ge=0, le=99999999)
    salario_max: float | None = Field(None, ge=0, le=99999999)
    nivel: str = Field("", max_length=50)
    tipo_contrato: str = Field("", max_length=50)
    empresa: str = Field("", max_length=200)
    dias: int | None = Field(None, ge=1, le=365)
    habilidades: str = Field("", max_length=500)
    area: str = Field("", max_length=100)
    ordenar: Literal["relevancia", "data", "salario"] = "relevancia"
    pagina: int = Field(1, ge=1, le=10000)
    por_pagina: int = Field(20, ge=1, le=50)

    @model_validator(mode="after")
    def faixa(self):
        if self.salario_min is not None and self.salario_max is not None and self.salario_min > self.salario_max:
            raise ValueError("A faixa salarial está invertida.")
        if len(self.habilidades.split(",")) > 10:
            raise ValueError("Use no máximo dez habilidades.")
        return self


def like(value):
    # Metacaracteres LIKE não viram curingas escolhidos pelo usuário.
    return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def predicado(f):
    clauses = ["v.Ativo=1", "v.ID_Status_Vaga=2", "e.Ativo=1"]
    args = []
    for field, column in (("cargo", "v.Titulo"), ("localizacao", "v.Localizacao"), ("empresa", "COALESCE(e.NomeFantasia,e.RazaoSocial)")):
        if getattr(f, field):
            clauses.append(f"{column} LIKE %s ESCAPE '!'")
            args.append(like(getattr(f, field)))
    if f.palavra_chave:
        clauses.append("(v.Titulo LIKE %s ESCAPE '!' OR v.Descricao LIKE %s ESCAPE '!')")
        args.extend([like(f.palavra_chave)] * 2)
    for field, column in (("nivel", "v.Nivel"), ("tipo_contrato", "v.TipoContrato"), ("area", "v.AreaProfissional")):
        if getattr(f, field):
            clauses.append(f"{column}=%s")
            args.append(getattr(f, field))
    if f.modalidade:
        aliases = {"hibrido": "Híbrido", "Híbrido": "Híbrido", "remoto": "Remoto", "presencial": "Presencial"}
        clauses.append("v.Modalidade=%s")
        args.append(aliases.get(f.modalidade, f.modalidade))
    if f.salario_min is not None:
        clauses.append("v.SalarioConfidencial=0 AND COALESCE(v.SalarioMax,v.SalarioMin)>=%s")
        args.append(f.salario_min)
    if f.salario_max is not None:
        clauses.append("v.SalarioConfidencial=0 AND COALESCE(v.SalarioMin,v.SalarioMax)<=%s")
        args.append(f.salario_max)
    if f.dias:
        clauses.append("v.PublicadaEm>=%s")
        args.append(datetime.now() - timedelta(days=f.dias))
    for skill in filter(None, (s.strip() for s in f.habilidades.split(","))):
        clauses.append("""EXISTS (SELECT 1 FROM Vaga_Habilidades vh JOIN Habilidades h ON h.ID_Habilidades=vh.ID_Habilidades
            WHERE vh.ID_Vagas=v.ID_Vagas AND h.Ativo=1 AND h.Nome LIKE %s ESCAPE '!')""")
        args.append(like(skill))
    return " AND ".join(clauses), args


@router.get("/vagas/busca")
async def buscar(filtros: Annotated[FiltrosBusca, Query()], sessao=Depends(usuario_opcional)):
    where, args = predicado(filtros)
    base = "FROM Vagas v JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas WHERE " + where
    total = await fetch_one("SELECT COUNT(*) AS total " + base, tuple(args))
    # Sem dados privados empresariais. Salários confidenciais não influenciam a ordenação.
    columns = """v.ID_Vagas,v.ID_Empresas,v.Titulo,v.Descricao,v.Modalidade,v.Nivel,v.TipoContrato,
        v.Localizacao,v.AreaProfissional,v.PublicadaEm,v.CriadoEm,v.SalarioConfidencial,
        CASE WHEN v.SalarioConfidencial=0 THEN v.SalarioMin ELSE NULL END AS SalarioMin,
        CASE WHEN v.SalarioConfidencial=0 THEN v.SalarioMax ELSE NULL END AS SalarioMax,
        COALESCE(e.NomeFantasia,e.RazaoSocial) AS NomeEmpresa"""
    order = "v.PublicadaEm DESC,v.CriadoEm DESC,v.ID_Vagas"
    order_args = []
    candidate = None
    skills = {}
    if sessao and sessao["tipo_usuario"] == "candidato":
        candidate = await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1", (sessao["id_usuario"],))
        if candidate:
            skills = {s["ID_Habilidades"]: s.get("Nivel") or 0 for s in await fetch_all(
                "SELECT ID_Habilidades,Nivel FROM Candidato_Habilidades WHERE ID_Candidatos=%s", (candidate["ID_Candidatos"],))}
    if filtros.ordenar == "salario":
        order = "CASE WHEN v.SalarioConfidencial=0 THEN COALESCE(v.SalarioMax,v.SalarioMin) ELSE NULL END DESC," + order
    elif filtros.ordenar == "relevancia" and (filtros.cargo or filtros.palavra_chave):
        order = "CASE WHEN v.Titulo=%s THEN 2 WHEN v.Titulo LIKE %s ESCAPE '!' THEN 1 ELSE 0 END DESC," + order
        term = filtros.cargo or filtros.palavra_chave
        order_args = [term, like(term)]
    elif filtros.ordenar == "relevancia" and candidate:
        order = """(SELECT COUNT(*) FROM Vaga_Habilidades vh JOIN Candidato_Habilidades ch ON ch.ID_Habilidades=vh.ID_Habilidades
            JOIN Habilidades h ON h.ID_Habilidades=vh.ID_Habilidades AND h.Ativo=1
            WHERE vh.ID_Vagas=v.ID_Vagas AND ch.ID_Candidatos=%s AND COALESCE(ch.Nivel,0)>=COALESCE(vh.NivelMinimo,0)) DESC,""" + order
        order_args = [candidate["ID_Candidatos"]]
    rows = await fetch_all("SELECT " + columns + " " + base + " ORDER BY " + order + " LIMIT %s OFFSET %s",
        tuple(args + order_args + [filtros.por_pagina, (filtros.pagina - 1) * filtros.por_pagina]))
    for row in rows:
        required = await fetch_all("""SELECT h.ID_Habilidades,h.Nome,vh.NivelMinimo,vh.Obrigatoria FROM Vaga_Habilidades vh
            JOIN Habilidades h ON h.ID_Habilidades=vh.ID_Habilidades AND h.Ativo=1 WHERE vh.ID_Vagas=%s""", (row["ID_Vagas"],))
        row["habilidades"] = required
        row["compatibilidade"] = round(100 * sum(s["ID_Habilidades"] in skills and skills[s["ID_Habilidades"]] >= (s["NivelMinimo"] or 0) for s in required) / len(required)) if candidate and required else None
        row["ja_candidatado"] = bool(candidate and await fetch_one("SELECT ID_Candidaturas FROM Candidaturas WHERE ID_Candidatos=%s AND ID_Vagas=%s AND Ativo=1", (candidate["ID_Candidatos"], row["ID_Vagas"])))
    return {"resultados": rows, "total": total["total"], "pagina": filtros.pagina, "por_pagina": filtros.por_pagina,
            "compatibilidade_base": "Correspondência de habilidades e níveis cadastrados; não é previsão de contratação."}


@router.get("/vagas/autocomplete")
async def autocomplete(q: str = Query(min_length=2, max_length=100), limite: int = Query(8, ge=1, le=10)):
    return await fetch_all("""SELECT DISTINCT v.Titulo FROM Vagas v JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas
        WHERE v.Ativo=1 AND v.ID_Status_Vaga=2 AND e.Ativo=1 AND v.Titulo LIKE %s ESCAPE '!'
        ORDER BY v.Titulo LIMIT %s""", (like(q), limite))


class BuscaSalva(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    nome: str = Field(min_length=1, max_length=100)
    filtros: FiltrosBusca
    ativa: bool = False


@router.get("/buscas")
async def salvas(sessao=Depends(exigir_tipo("candidato"))):
    rows = await fetch_all("SELECT * FROM Buscas_Salvas WHERE ID_Usuarios=%s ORDER BY CriadoEm DESC", (sessao["id_usuario"],))
    for row in rows:
        if isinstance(row["Filtros"], (str, bytes)):
            row["Filtros"] = json.loads(row["Filtros"])
    return rows


@router.post("/buscas", status_code=201)
async def salvar(dados: BuscaSalva, sessao=Depends(exigir_tipo("candidato"))):
    await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s FOR UPDATE", (sessao["id_usuario"],))
    count = await fetch_one("SELECT COUNT(*) AS total FROM Buscas_Salvas WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if count["total"] >= 30:
        raise HTTPException(409, "Limite de 30 buscas salvas. Remova uma antes de adicionar outra.")
    ident = novo_uuid()
    await execute("INSERT INTO Buscas_Salvas(ID_Busca,ID_Usuarios,Nome,Filtros,Ativa) VALUES (%s,%s,%s,%s,%s)",
        (ident, sessao["id_usuario"], dados.nome, dados.filtros.model_dump_json(), dados.ativa))
    return {"ID_Busca": ident}


@router.put("/buscas/{id_busca}")
async def alterar(id_busca: str, dados: BuscaSalva, sessao=Depends(exigir_tipo("candidato"))):
    if not await fetch_one("SELECT ID_Busca FROM Buscas_Salvas WHERE ID_Busca=%s AND ID_Usuarios=%s", (id_busca, sessao["id_usuario"])):
        raise HTTPException(404, "Busca não encontrada.")
    await execute("UPDATE Buscas_Salvas SET Nome=%s,Filtros=%s,Ativa=%s WHERE ID_Busca=%s AND ID_Usuarios=%s",
        (dados.nome, dados.filtros.model_dump_json(), dados.ativa, id_busca, sessao["id_usuario"]))
    return {"mensagem": "Busca atualizada."}


@router.delete("/buscas/{id_busca}")
async def excluir(id_busca: str, sessao=Depends(exigir_tipo("candidato"))):
    await execute("DELETE FROM Buscas_Salvas WHERE ID_Busca=%s AND ID_Usuarios=%s", (id_busca, sessao["id_usuario"]))
    return {"mensagem": "Busca removida, se existente."}


@router.get("/buscas-historico")
async def historico(sessao=Depends(exigir_tipo("candidato"))):
    rows = await fetch_all("SELECT * FROM Historico_Buscas WHERE ID_Usuarios=%s ORDER BY CriadoEm DESC, ID_Historico LIMIT 20", (sessao["id_usuario"],))
    for row in rows:
        row["Filtros"] = json.loads(row["Filtros"]) if isinstance(row["Filtros"], (str, bytes)) else row["Filtros"]
    return rows


@router.post("/buscas-historico", status_code=201)
async def registrar(filtros: FiltrosBusca, sessao=Depends(exigir_tipo("candidato"))):
    await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s FOR UPDATE", (sessao["id_usuario"],))
    # Retenção limitada: 20 últimas pesquisas por conta.
    rows = await fetch_all("SELECT ID_Historico FROM Historico_Buscas WHERE ID_Usuarios=%s ORDER BY CriadoEm DESC, ID_Historico", (sessao["id_usuario"],))
    for row in rows[19:]:
        await execute("DELETE FROM Historico_Buscas WHERE ID_Historico=%s AND ID_Usuarios=%s", (row["ID_Historico"], sessao["id_usuario"]))
    await execute("INSERT INTO Historico_Buscas(ID_Historico,ID_Usuarios,Filtros) VALUES (%s,%s,%s)", (novo_uuid(), sessao["id_usuario"], filtros.model_dump_json()))
    return {"mensagem": "Pesquisa registrada."}
