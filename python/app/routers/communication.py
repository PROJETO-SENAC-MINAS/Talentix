"""Timeline, preferências, modelos, lotes idempotentes e anexos privados."""

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from fastapi import Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.config import settings
from app.core.audit import registrar_auditoria
from app.core.security import novo_uuid
from app.core.delivery import enfileirar_email
from app.core.upload import salvar_arquivo
from app.db.database import fetch_one, fetch_all, execute
from app.routers.organizations import contexto_empresa
from app.routers.agenda import candidatura_contexto

router = AtomicRouter(prefix="/comunicacao", tags=["Comunicação"])


class Preferencias(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_ativo: bool = False
    lotes_ativos: bool = False


@router.get("/preferencias")
async def preferencias(s=Depends(usuario_atual)):
    row = await fetch_one(
        "SELECT EmailAtivo,LotesAtivos FROM Preferencias_Notificacao WHERE ID_Usuarios=%s",
        (s["id_usuario"],),
    )
    return row or {"EmailAtivo": False, "LotesAtivos": False}


@router.put("/preferencias")
async def salvar_preferencias(
    d: Preferencias, request: Request, s=Depends(usuario_atual)
):
    old = await fetch_one(
        "SELECT * FROM Preferencias_Notificacao WHERE ID_Usuarios=%s",
        (s["id_usuario"],),
    )
    if old:
        await execute(
            "UPDATE Preferencias_Notificacao SET EmailAtivo=%s,LotesAtivos=%s,AtualizadoEm=NOW() WHERE ID_Usuarios=%s",
            (d.email_ativo, d.lotes_ativos, s["id_usuario"]),
        )
    else:
        await execute(
            "INSERT INTO Preferencias_Notificacao(ID_Usuarios,EmailAtivo,LotesAtivos) VALUES (%s,%s,%s)",
            (s["id_usuario"], d.email_ativo, d.lotes_ativos),
        )
    await registrar_auditoria(
        request,
        "comunicacao.preferencias",
        "Preferencias_Notificacao",
        s["id_usuario"],
        novo=d.model_dump(),
    )
    return {
        "mensagem": "Preferências salvas. Avisos essenciais continuam disponíveis no site."
    }


@router.get("/candidaturas")
async def processos(id_empresa: str | None = None, s=Depends(usuario_atual)):
    params = []
    query = """SELECT c.ID_Candidaturas,c.ID_Status_Candidatura,c.ID_Candidatos,v.ID_Vagas,v.Titulo,u.Nome,
        ca.ID_Usuarios AS CandidatoUsuario,e.ID_Usuarios AS EmpresaUsuario,e.ID_Empresas
        FROM Candidaturas c JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas
        JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
        JOIN Candidatos ca ON ca.ID_Candidatos=c.ID_Candidatos
        JOIN Usuarios u ON u.ID_Usuarios=ca.ID_Usuarios AND u.Ativo=1 WHERE c.Ativo=1"""
    if s["tipo_usuario"] == "candidato":
        query += " AND ca.ID_Usuarios=%s"
        params.append(s["id_usuario"])
    else:
        e = await contexto_empresa(s, id_empresa, "ler")
        query += " AND e.ID_Empresas=%s"
        params.append(e["ID_Empresas"])
    rows = await fetch_all(
        query + " ORDER BY c.CriadaEm DESC,c.ID_Candidaturas LIMIT 500", tuple(params)
    )
    from app.core.organizations import responsaveis_empresa

    owners = {}
    for row in rows:
        eid = row["ID_Empresas"]
        if eid not in owners:
            owners[eid] = await responsaveis_empresa(eid)
        if owners[eid]:
            row["EmpresaUsuario"] = owners[eid][0]
    return rows


@router.get("/candidaturas/{id}/timeline")
async def timeline(id: str, s=Depends(usuario_atual)):
    c = await candidatura_contexto(id, s, "comunicacao")
    # Candidate receives public process events; internal ATS notes never enter this projection.
    if s["tipo_usuario"] == "candidato":
        messages = await fetch_all(
            """SELECT ID_Mensagens,Conteudo,EnviadaEm,Lida,ID_Remetente,ID_Destinatario FROM Mensagens
            WHERE ID_Candidaturas=%s AND (ID_Remetente=%s OR ID_Destinatario=%s) ORDER BY EnviadaEm,ID_Mensagens LIMIT 200""",
            (id, s["id_usuario"], s["id_usuario"]),
        )
    else:
        messages = await fetch_all(
            """SELECT ID_Mensagens,Conteudo,EnviadaEm,Lida,ID_Remetente,ID_Destinatario FROM Mensagens
            WHERE ID_Candidaturas=%s ORDER BY EnviadaEm,ID_Mensagens LIMIT 200""",
            (id,),
        )
    interviews = await fetch_all(
        "SELECT ID_Entrevistas,DataHora,Tipo,LocalOuLink,ID_Status_Entrevista FROM Entrevistas WHERE ID_Candidaturas=%s ORDER BY DataHora LIMIT 100",
        (id,),
    )
    files = await fetch_all(
        "SELECT ID_Anexo,Nome,CriadoEm FROM Comunicacao_Anexos WHERE ID_Candidaturas=%s ORDER BY CriadoEm LIMIT 100",
        (id,),
    )
    items = [
        {"tipo": "candidatura", "data": c["CriadaEm"], "texto": "Candidatura enviada"}
    ]
    items += [
        {
            "tipo": "mensagem",
            "data": r["EnviadaEm"],
            "texto": r["Conteudo"],
            "id": r["ID_Mensagens"],
            "lida": r["Lida"],
            "remetente": r["ID_Remetente"],
        }
        for r in messages
    ]
    items += [
        {
            "tipo": "entrevista",
            "data": r["DataHora"],
            "texto": f"Entrevista: {r['Tipo'] or 'Não informado'} — {r['LocalOuLink'] or ''}",
            "status": r["ID_Status_Entrevista"],
        }
        for r in interviews
    ]
    items += [
        {
            "tipo": "anexo",
            "data": r["CriadoEm"],
            "texto": r["Nome"],
            "url": "/comunicacao/anexos/" + r["ID_Anexo"],
        }
        for r in files
    ]
    outbox = await fetch_all(
        """SELECT o.Assunto,o.Estado,o.CriadoEm FROM Outbox_Email o WHERE o.ID_Usuarios=%s AND o.Chave LIKE %s ORDER BY o.CriadoEm LIMIT 100""",
        (s["id_usuario"], "processo:" + id + ":%"),
    )
    items += [
        {
            "tipo": "email",
            "data": r["CriadoEm"],
            "texto": r["Assunto"],
            "status": r["Estado"],
        }
        for r in outbox
    ]
    return sorted(items, key=lambda r: str(r["data"]), reverse=True)


class Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nome: str = Field(min_length=1, max_length=120)
    conteudo: str = Field(min_length=1, max_length=10000)


@router.get("/modelos")
async def modelos(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "comunicacao")
    return await fetch_all(
        "SELECT * FROM Comunicacao_Modelos WHERE ID_Empresas=%s ORDER BY Nome LIMIT 100",
        (e["ID_Empresas"],),
    )


@router.post("/modelos", status_code=201)
async def criar_modelo(
    d: Modelo, request: Request, id_empresa: str | None = None, s=Depends(usuario_atual)
):
    e = await contexto_empresa(s, id_empresa, "comunicacao")
    id = novo_uuid()
    await execute(
        "INSERT INTO Comunicacao_Modelos(ID_Modelo,ID_Empresas,Nome,Conteudo) VALUES (%s,%s,%s,%s)",
        (id, e["ID_Empresas"], d.nome, d.conteudo),
    )
    await registrar_auditoria(
        request, "comunicacao.modelo", "Comunicacao_Modelos", s["id_usuario"], id
    )
    return {"id": id}


class Lote(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    candidaturas: list[str] = Field(min_length=1, max_length=100)
    conteudo: str = Field(min_length=1, max_length=10000)
    chave: str = Field(min_length=8, max_length=80)


@router.get("/lotes")
async def lotes(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "comunicacao")
    return await fetch_all(
        """SELECT l.ID_Lote,l.CriadoEm,d.Estado,COUNT(*) AS total FROM Comunicacao_Lotes l
        JOIN Comunicacao_Destinos d ON d.ID_Lote=l.ID_Lote WHERE l.ID_Empresas=%s
        GROUP BY l.ID_Lote,l.CriadoEm,d.Estado ORDER BY l.CriadoEm DESC LIMIT 100""",
        (e["ID_Empresas"],),
    )


@router.post("/lotes", status_code=201)
async def enviar_lote(
    d: Lote, request: Request, id_empresa: str | None = None, s=Depends(usuario_atual)
):
    e = await contexto_empresa(s, id_empresa, "comunicacao")
    ids = list(dict.fromkeys(d.candidaturas))
    digest = sha256((s["id_usuario"] + d.model_dump_json()).encode()).hexdigest()
    await fetch_one(
        "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE",
        (e["ID_Empresas"],),
    )
    old = await fetch_one(
        "SELECT ID_Lote,PayloadHash FROM Comunicacao_Lotes WHERE ID_Empresas=%s AND Chave=%s FOR UPDATE",
        (e["ID_Empresas"], d.chave),
    )
    if old:
        if old["PayloadHash"] != digest:
            raise HTTPException(409, "Chave de envio já usada com outro conteúdo.")
        return {"id": old["ID_Lote"], "repetido": True}
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    count = await fetch_one(
        "SELECT COUNT(*) AS total FROM Comunicacao_Lotes WHERE ID_Empresas=%s AND CriadoEm>=%s FOR UPDATE",
        (e["ID_Empresas"], today),
    )
    if count["total"] >= 10:
        raise HTTPException(
            429, "Limite de dez lotes por organização por dia atingido."
        )
    contexts = []
    for id in ids:
        c = await candidatura_contexto(id, s, "comunicacao")
        if c["ID_Empresas"] != e["ID_Empresas"] or not c["Ativo"]:
            raise HTTPException(403, "Destinatário fora do contexto autorizado.")
        contexts.append(c)
    id = novo_uuid()
    await execute(
        "INSERT INTO Comunicacao_Lotes(ID_Lote,ID_Empresas,ID_Usuarios,Chave,PayloadHash,Conteudo) VALUES (%s,%s,%s,%s,%s,%s)",
        (id, e["ID_Empresas"], s["id_usuario"], d.chave, digest, d.conteudo),
    )
    sent = set()
    counts = {"enviado": 0, "ignorado": 0}
    for c in contexts:
        uid = c["CandidatoUsuario"]
        p = await fetch_one(
            "SELECT LotesAtivos FROM Preferencias_Notificacao WHERE ID_Usuarios=%s",
            (uid,),
        )
        state = "enviado" if p and p["LotesAtivos"] and uid not in sent else "ignorado"
        mid = None
        if state == "enviado":
            mid = novo_uuid()
            sent.add(uid)
            await execute(
                "INSERT INTO Mensagens(ID_Mensagens,ID_Remetente,ID_Destinatario,ID_Candidaturas,Conteudo) VALUES (%s,%s,%s,%s,%s)",
                (mid, s["id_usuario"], uid, c["ID_Candidaturas"], d.conteudo),
            )
            await execute(
                "INSERT INTO Notificacoes(ID_Notificacoes,ID_Usuarios,Titulo,Mensagem,Tipo) VALUES (%s,%s,%s,%s,%s)",
                (
                    novo_uuid(),
                    uid,
                    "Nova mensagem do processo",
                    "Consulte a central de comunicação.",
                    "mensagem",
                ),
            )
            await enfileirar_email(
                uid,
                "Mensagem do Talentix",
                d.conteudo,
                f"processo:{c['ID_Candidaturas']}:lote:{id}:{uid}",
            )
        counts[state] += 1
        await execute(
            "INSERT INTO Comunicacao_Destinos(ID_Lote,ID_Candidaturas,ID_Mensagens,Estado) VALUES (%s,%s,%s,%s)",
            (id, c["ID_Candidaturas"], mid, state),
        )
    await registrar_auditoria(
        request,
        "comunicacao.lote",
        "Comunicacao_Lotes",
        s["id_usuario"],
        id,
        novo=counts,
    )
    return {"id": id, **counts}


@router.post("/candidaturas/{id}/anexos", status_code=201)
async def anexar(
    id: str, request: Request, arquivo: UploadFile = File(...), s=Depends(usuario_atual)
):
    await candidatura_contexto(id, s, "comunicacao")
    # Categoria separada nunca é montada como StaticFiles nem reutiliza ACL de currículos.
    if Path(arquivo.filename or "").suffix.lower() != ".pdf":
        raise HTTPException(422, "Anexos da comunicação aceitam somente PDF.")
    info = await salvar_arquivo(arquivo, "comunicacao")
    key = novo_uuid()
    await execute(
        "INSERT INTO Comunicacao_Anexos(ID_Anexo,ID_Candidaturas,ID_Usuarios,Arquivo,Nome,Mime) VALUES (%s,%s,%s,%s,%s,%s)",
        (
            key,
            id,
            s["id_usuario"],
            Path(info["url"]).name,
            Path(arquivo.filename or "anexo.pdf").name[:150],
            "application/pdf",
        ),
    )
    await registrar_auditoria(
        request, "comunicacao.anexo", "Comunicacao_Anexos", s["id_usuario"], key
    )
    return {"id": key, "url": "/comunicacao/anexos/" + key}


@router.get("/anexos/{id}")
async def baixar(id: str, request: Request, s=Depends(usuario_atual)):
    row = await fetch_one("SELECT * FROM Comunicacao_Anexos WHERE ID_Anexo=%s", (id,))
    if not row:
        raise HTTPException(404, "Anexo indisponível.")
    await candidatura_contexto(row["ID_Candidaturas"], s, "ler")
    path = Path(settings.UPLOAD_DIR) / "comunicacao" / row["Arquivo"]
    if Path(row["Arquivo"]).name != row["Arquivo"] or not path.is_file():
        raise HTTPException(404, "Anexo indisponível.")
    # A auditoria de leitura tem transação própria pois esta rota é GET.
    await registrar_auditoria(
        request, "comunicacao.anexo.ler", "Comunicacao_Anexos", s["id_usuario"], id
    )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename="anexo.pdf",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
