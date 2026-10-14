"""Agenda manual integrada: UTC no banco, fuso explícito, versão e idempotência."""

from datetime import datetime, timezone
from hashlib import sha256
from typing import Literal
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.organizations import papel_empresa
from app.core.agenda import horario_utc, validar_conflito
from app.core.audit import registrar_auditoria
from app.core.notificar import notificar_usuario
from app.core.delivery import enfileirar_email
from app.core.security import novo_uuid
from app.core.validation import safe_url
from app.db.database import fetch_one, fetch_all, execute
from app.routers.organizations import contexto_empresa

router = AtomicRouter(prefix="/agenda", tags=["Agenda"])


async def candidatura_contexto(id, s, permissao="entrevistas"):
    row = await fetch_one(
        """SELECT c.*,v.ID_Empresas,v.Titulo,ca.ID_Usuarios AS CandidatoUsuario
        FROM Candidaturas c JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas
        JOIN Candidatos ca ON ca.ID_Candidatos=c.ID_Candidatos WHERE c.ID_Candidaturas=%s""",
        (id,),
    )
    if not row:
        raise HTTPException(404, "Candidatura indisponível.")
    if s["tipo_usuario"] == "candidato":
        if row["CandidatoUsuario"] != s["id_usuario"]:
            raise HTTPException(403, "Candidatura de outra pessoa.")
    else:
        await contexto_empresa(s, row["ID_Empresas"], permissao)
    return row


@router.get("")
async def listar(
    inicio: datetime | None = None,
    fim: datetime | None = None,
    id_empresa: str | None = None,
    s=Depends(usuario_atual),
):
    params = []
    query = """SELECT e.*,d.Fuso,d.DuracaoMin,d.Versao,v.Titulo,ca.ID_Usuarios AS CandidatoUsuario,
        r.ID_Usuarios AS RecrutadorUsuario FROM Entrevistas e
        JOIN Candidaturas c ON c.ID_Candidaturas=e.ID_Candidaturas
        JOIN Candidatos ca ON ca.ID_Candidatos=c.ID_Candidatos
        JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas
        JOIN Recrutadores r ON r.ID_Recrutadores=e.ID_Recrutadores
        LEFT JOIN Agenda_Detalhes d ON d.ID_Entrevistas=e.ID_Entrevistas WHERE c.Ativo=1"""
    if s["tipo_usuario"] == "candidato":
        query += " AND ca.ID_Usuarios=%s"
        params.append(s["id_usuario"])
    else:
        e = await contexto_empresa(
            s,
            id_empresa,
            "entrevistas:ler" if s.get("papel_empresa") == "entrevistador" else "ler",
        )
        role = await papel_empresa(e, s)
        query += " AND v.ID_Empresas=%s"
        params.append(e["ID_Empresas"])
        if role == "entrevistador":
            query += " AND r.ID_Usuarios=%s"
            params.append(s["id_usuario"])
    rows = await fetch_all(query + " ORDER BY e.DataHora DESC LIMIT 500", tuple(params))
    result = []
    for r in rows:
        utc = horario_utc(r["DataHora"], "UTC" if r["Fuso"] else "America/Sao_Paulo")
        if inicio and utc < horario_utc(inicio, "UTC"):
            continue
        if fim and utc > horario_utc(fim, "UTC"):
            continue
        r["DataHoraUtc"] = utc.isoformat() + "Z"
        r["Fuso"] = r["Fuso"] or "America/Sao_Paulo"
        r["DuracaoMin"] = r["DuracaoMin"] or 30
        r["Versao"] = r["Versao"] or 1
        if s["tipo_usuario"] == "candidato":
            r.pop("Observacoes", None)
        result.append(r)
    return result


class Agendamento(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id_candidatura: str = Field(min_length=1, max_length=36)
    id_recrutador: str = Field(min_length=1, max_length=36)
    data_hora: datetime
    fuso: str = Field(default="America/Sao_Paulo", max_length=80)
    duracao_min: int = Field(default=30, ge=15, le=240)
    tipo: Literal["Presencial", "Online", "Telefone"] = "Online"
    local_ou_link: str = Field(default="", max_length=300)
    observacoes: str = Field(default="", max_length=5000)
    chave: str = Field(min_length=8, max_length=80)

    @field_validator("local_ou_link")
    @classmethod
    def link(cls, v):
        if "://" in v:
            return safe_url(v)
        return v


async def avisar(c, actor, text, key):
    await notificar_usuario(
        c["CandidatoUsuario"],
        text,
        f"{text}: {c['Titulo']}. Consulte sua agenda.",
        "entrevista",
    )
    await enfileirar_email(
        c["CandidatoUsuario"],
        text,
        f"{text}: {c['Titulo']}. Consulte sua agenda no Talentix.",
        key,
    )


@router.post("", status_code=201)
async def agendar(d: Agendamento, request: Request, s=Depends(usuario_atual)):
    if s["tipo_usuario"] == "candidato":
        raise HTTPException(403, "Agendamento manual é responsabilidade do RH.")
    c = await candidatura_contexto(d.id_candidatura, s)
    if not c["Ativo"] or c["ID_Status_Candidatura"] in (5, 6, 7):
        raise HTTPException(409, "Processo encerrado.")
    inicio = horario_utc(d.data_hora, d.fuso)
    chave = sha256((s["id_usuario"] + c["ID_Empresas"] + d.chave).encode()).hexdigest()
    payload = sha256(d.model_dump_json(exclude={"chave"}).encode()).hexdigest()
    await fetch_one(
        "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE",
        (c["ID_Empresas"],),
    )
    old = await fetch_one(
        "SELECT * FROM Agenda_Detalhes WHERE Chave=%s FOR UPDATE", (chave,)
    )
    if old:
        if old["PayloadHash"] != payload:
            raise HTTPException(409, "Chave já usada com dados diferentes.")
        return {"ID_Entrevistas": old["ID_Entrevistas"], "repetido": True}
    if inicio <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(422, "A entrevista deve estar no futuro.")
    r = await fetch_one(
        """SELECT r.ID_Recrutadores FROM Recrutadores r JOIN Usuarios u ON u.ID_Usuarios=r.ID_Usuarios
        WHERE r.ID_Recrutadores=%s AND r.ID_Empresas=%s AND r.Ativo=1 AND u.Ativo=1""",
        (d.id_recrutador, c["ID_Empresas"]),
    )
    if not r:
        raise HTTPException(422, "Escolha um recrutador ativo desta empresa.")
    await validar_conflito(c, d.id_recrutador, inicio, d.duracao_min)
    id = novo_uuid()
    await execute(
        """INSERT INTO Entrevistas(ID_Entrevistas,ID_Candidaturas,ID_Recrutadores,ID_Status_Entrevista,DataHora,Tipo,LocalOuLink,Observacoes)
        VALUES (%s,%s,%s,1,%s,%s,%s,%s)""",
        (
            id,
            d.id_candidatura,
            d.id_recrutador,
            inicio,
            d.tipo,
            d.local_ou_link,
            d.observacoes,
        ),
    )
    await execute(
        "INSERT INTO Agenda_Detalhes(ID_Entrevistas,Fuso,DuracaoMin,Chave,PayloadHash) VALUES (%s,%s,%s,%s,%s)",
        (id, d.fuso, d.duracao_min, chave, payload),
    )
    await avisar(c, s, "Entrevista agendada", "agenda:" + id + ":1")
    await registrar_auditoria(
        request,
        "agenda.criar",
        "Entrevistas",
        s["id_usuario"],
        id,
        novo={"inicio_utc": inicio, "duracao": d.duracao_min, "fuso": d.fuso},
    )
    return {"ID_Entrevistas": id, "versao": 1, "inicio_utc": inicio.isoformat() + "Z"}


class Alteracao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    acao: Literal["reagendar", "cancelar", "realizar"]
    versao: int = Field(ge=1)
    data_hora: datetime | None = None
    fuso: str = Field(default="America/Sao_Paulo", max_length=80)


@router.put("/{id}")
async def alterar(id: str, d: Alteracao, request: Request, s=Depends(usuario_atual)):
    if s["tipo_usuario"] == "candidato":
        raise HTTPException(403, "Solicite a alteração ao RH pelo processo.")
    en = await fetch_one("SELECT * FROM Entrevistas WHERE ID_Entrevistas=%s", (id,))
    if not en:
        raise HTTPException(404, "Entrevista indisponível.")
    c = await candidatura_contexto(en["ID_Candidaturas"], s)
    await fetch_one(
        "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE",
        (c["ID_Empresas"],),
    )
    en = await fetch_one(
        "SELECT * FROM Entrevistas WHERE ID_Entrevistas=%s FOR UPDATE", (id,)
    )
    detail = await fetch_one(
        "SELECT * FROM Agenda_Detalhes WHERE ID_Entrevistas=%s FOR UPDATE", (id,)
    )
    version = detail["Versao"] if detail else 1
    if d.versao != version:
        raise HTTPException(409, "Entrevista alterada; recarregue a agenda.")
    if en["ID_Status_Entrevista"] in (2, 4):
        raise HTTPException(409, "Entrevista encerrada.")
    start = en["DataHora"]
    if d.acao == "reagendar":
        if not d.data_hora:
            raise HTTPException(422, "Informe o novo horário.")
        start = horario_utc(d.data_hora, d.fuso)
        if start <= datetime.now(timezone.utc).replace(tzinfo=None):
            raise HTTPException(422, "Informe um horário futuro.")
        await validar_conflito(
            c, en["ID_Recrutadores"], start, detail["DuracaoMin"] if detail else 30, id
        )
    await execute(
        "UPDATE Entrevistas SET DataHora=%s,ID_Status_Entrevista=%s WHERE ID_Entrevistas=%s",
        (start, {"reagendar": 3, "cancelar": 4, "realizar": 2}[d.acao], id),
    )
    if detail:
        await execute(
            "UPDATE Agenda_Detalhes SET Versao=Versao+1,Fuso=%s WHERE ID_Entrevistas=%s",
            (d.fuso if d.acao == "reagendar" else detail["Fuso"], id),
        )
    else:
        if d.acao != "reagendar":
            start = horario_utc(en["DataHora"])
        await execute(
            "UPDATE Entrevistas SET DataHora=%s WHERE ID_Entrevistas=%s", (start, id)
        )
        await execute(
            "INSERT INTO Agenda_Detalhes(ID_Entrevistas,Fuso,DuracaoMin,Versao,Chave,PayloadHash) VALUES (%s,%s,30,2,%s,%s)",
            (id, d.fuso, "legado:" + id, "0" * 64),
        )
    text = {
        "reagendar": "Entrevista reagendada",
        "cancelar": "Entrevista cancelada",
        "realizar": "Entrevista realizada",
    }[d.acao]
    await avisar(c, s, text, f"agenda:{id}:{version + 1}")
    await registrar_auditoria(
        request,
        "agenda." + d.acao,
        "Entrevistas",
        s["id_usuario"],
        id,
        {"status": en["ID_Status_Entrevista"]},
        {"status": d.acao, "inicio": start},
    )
    return {"mensagem": text, "versao": version + 1}
