"""Exportação própria, consentimentos versionados e pedidos de exclusão reversíveis."""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.security import novo_uuid, verificar_senha
from app.core.config import settings
from app.core.audit import registrar_auditoria
from app.core.privacy import ultimo_owner
from app.db.database import fetch_one, fetch_all, execute

router = AtomicRouter(prefix="/privacidade", tags=["Privacidade"])


@router.get("/meus-dados")
async def exportar(request: Request, s=Depends(usuario_atual)):
    uid = s["id_usuario"]
    out = {
        "conta": await fetch_one(
            "SELECT ID_Usuarios,Nome,Email,Telefone,CriadoEm FROM Usuarios WHERE ID_Usuarios=%s",
            (uid,),
        )
    }
    c = await fetch_one("SELECT * FROM Candidatos WHERE ID_Usuarios=%s", (uid,))
    out["perfil"] = c
    if c:
        for table in (
            "Experiencias",
            "Formacoes",
            "Candidato_Itens",
            "Candidato_Habilidades",
            "Candidato_Idiomas",
            "Curriculos",
            "ATS_Consentimentos",
        ):
            out[table] = await fetch_all(
                f"SELECT * FROM {table} WHERE ID_Candidatos=%s", (c["ID_Candidatos"],)
            )
        out["candidaturas"] = await fetch_all(
            "SELECT ID_Candidaturas,ID_Vagas,ID_Status_Candidatura,CriadaEm,Ativo FROM Candidaturas WHERE ID_Candidatos=%s",
            (c["ID_Candidatos"],),
        )
    out["consentimentos"] = await fetch_all(
        "SELECT Finalidade,Autorizado,VersaoPolitica,CriadoEm FROM Privacidade_Consentimentos WHERE ID_Usuarios=%s",
        (uid,),
    )
    out["preferencias"] = await fetch_one(
        "SELECT EmailAtivo,LotesAtivos FROM Preferencias_Notificacao WHERE ID_Usuarios=%s",
        (uid,),
    )
    out["mensagens_enviadas"] = await fetch_all(
        "SELECT Conteudo,EnviadaEm,ID_Candidaturas FROM Mensagens WHERE ID_Remetente=%s",
        (uid,),
    )
    await registrar_auditoria(request, "privacidade.exportar", "Usuarios", uid, uid)
    return JSONResponse(
        jsonable_encoder(out),
        headers={
            "Content-Disposition": 'attachment; filename="talentix-meus-dados.json"',
            "Cache-Control": "private, no-store",
        },
    )


class Consentimento(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finalidade: Literal["emails", "comunicacao_em_massa", "pesquisa_produto"]
    autorizado: bool


@router.get("/consentimentos")
async def consentimentos(s=Depends(usuario_atual)):
    return await fetch_all(
        "SELECT Finalidade,Autorizado,VersaoPolitica,CriadoEm FROM Privacidade_Consentimentos WHERE ID_Usuarios=%s ORDER BY CriadoEm DESC LIMIT 100",
        (s["id_usuario"],),
    )


@router.post("/consentimentos", status_code=201)
async def consentir(d: Consentimento, request: Request, s=Depends(usuario_atual)):
    await execute(
        "INSERT INTO Privacidade_Consentimentos(ID_Consentimento,ID_Usuarios,Finalidade,Autorizado,VersaoPolitica) VALUES (%s,%s,%s,%s,%s)",
        (novo_uuid(), s["id_usuario"], d.finalidade, d.autorizado, "2026-10-v1"),
    )
    if d.finalidade in {"emails", "comunicacao_em_massa"}:
        p = await fetch_one(
            "SELECT * FROM Preferencias_Notificacao WHERE ID_Usuarios=%s",
            (s["id_usuario"],),
        )
        field = "EmailAtivo" if d.finalidade == "emails" else "LotesAtivos"
        if p:
            await execute(
                f"UPDATE Preferencias_Notificacao SET {field}=%s WHERE ID_Usuarios=%s",
                (d.autorizado, s["id_usuario"]),
            )
        else:
            await execute(
                f"INSERT INTO Preferencias_Notificacao(ID_Usuarios,{field}) VALUES (%s,%s)",
                (s["id_usuario"], d.autorizado),
            )
    await registrar_auditoria(
        request,
        "privacidade.consentir",
        "Privacidade_Consentimentos",
        s["id_usuario"],
        novo=d.model_dump(),
    )
    return {"mensagem": "Preferência registrada com histórico."}


class Exclusao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    senha: str = Field(min_length=1, max_length=72, repr=False)
    confirmacao: Literal["EXCLUIR MINHA CONTA"]


@router.get("/solicitacoes")
async def solicitacoes(s=Depends(usuario_atual)):
    return await fetch_all(
        "SELECT ID_Solicitacao,Tipo,Estado,ExecutarApos,CriadoEm,ConcluidaEm FROM Privacidade_Solicitacoes WHERE ID_Usuarios=%s ORDER BY CriadoEm DESC LIMIT 100",
        (s["id_usuario"],),
    )


@router.post("/exclusao", status_code=201)
async def excluir(d: Exclusao, request: Request, s=Depends(usuario_atual)):
    u = await fetch_one(
        "SELECT SenhaHash FROM Usuarios WHERE ID_Usuarios=%s FOR UPDATE",
        (s["id_usuario"],),
    )
    if not await asyncio.to_thread(verificar_senha, d.senha, u["SenhaHash"]):
        raise HTTPException(403, "Senha incorreta.")
    if await ultimo_owner(s["id_usuario"]):
        raise HTTPException(
            409, "Transfira a responsabilidade da organização antes de excluir a conta."
        )
    if await fetch_one(
        "SELECT ID_Solicitacao FROM Privacidade_Solicitacoes WHERE ID_Usuarios=%s AND Estado='pendente'",
        (s["id_usuario"],),
    ):
        raise HTTPException(409, "Você já possui uma solicitação pendente.")
    id = novo_uuid()
    after = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=settings.PRIVACY_DELETE_GRACE_DAYS
    )
    await execute(
        "INSERT INTO Privacidade_Solicitacoes(ID_Solicitacao,ID_Usuarios,Tipo,ExecutarApos) VALUES (%s,%s,'exclusao',%s)",
        (id, s["id_usuario"], after),
    )
    await registrar_auditoria(
        request,
        "privacidade.solicitar_exclusao",
        "Usuarios",
        s["id_usuario"],
        s["id_usuario"],
    )
    return {
        "id": id,
        "executar_apos": after,
        "mensagem": "Solicitação registrada. Você pode cancelar até o processamento. Históricos necessários têm retenção separada.",
    }


@router.delete("/solicitacoes/{id}")
async def cancelar(id: str, request: Request, s=Depends(usuario_atual)):
    row = await fetch_one(
        "SELECT * FROM Privacidade_Solicitacoes WHERE ID_Solicitacao=%s AND ID_Usuarios=%s FOR UPDATE",
        (id, s["id_usuario"]),
    )
    if not row:
        raise HTTPException(404, "Solicitação indisponível.")
    if row["Estado"] not in {"pendente", "bloqueado"}:
        raise HTTPException(409, "Solicitação já processada.")
    await execute(
        "UPDATE Privacidade_Solicitacoes SET Estado='cancelado' WHERE ID_Solicitacao=%s",
        (id,),
    )
    await registrar_auditoria(
        request, "privacidade.cancelar", "Privacidade_Solicitacoes", s["id_usuario"], id
    )
    return {"mensagem": "Solicitação cancelada."}


@router.get("/politica-operacional")
async def politica():
    return {
        "versao": "2026-10-v1",
        "retencao_curriculo_arquivado_dias": settings.DATA_RETENTION_DAYS,
        "carencia_exclusao_dias": settings.PRIVACY_DELETE_GRACE_DAYS,
        "retencao_separada": "Documentos vinculados a processos são preservados até revisão da finalidade e obrigações aplicáveis pelo responsável.",
        "controles": "Dados privados exigem autenticação, contexto e autorização. Corrija seu perfil pelos formulários e seu e-mail pelo fluxo de confirmação da conta.",
    }
