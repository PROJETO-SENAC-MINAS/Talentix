"""Organizações, convites de uso único e papéis sem elevação pelo cliente."""

from datetime import datetime, timezone, timedelta
from hashlib import sha256
import secrets
from typing import Literal
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual
from app.core.access import empresa_da_sessao
from app.core.organizations import PAPEIS, autorizar_empresa, papel_empresa
from app.core.security import novo_uuid
from app.core.audit import registrar_auditoria
from app.db.database import fetch_one, fetch_all, execute

router = AtomicRouter(prefix="/organizacoes", tags=["Organizações"])
Role = Literal["owner", "rh_admin", "recrutador", "hiring_manager", "entrevistador"]


async def contexto_empresa(s, id_empresa=None, permissao="ler"):
    if s["tipo_usuario"] == "administrador":
        if not id_empresa:
            raise HTTPException(
                422, "Selecione uma empresa para a operação administrativa."
            )
        e = await fetch_one(
            "SELECT * FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (id_empresa,)
        )
        if not e:
            raise HTTPException(404, "Empresa indisponível.")
    else:
        e = await empresa_da_sessao({**s, "_enterprise_permission": permissao})
        if id_empresa and e["ID_Empresas"] != id_empresa:
            raise HTTPException(403, "Organização fora do contexto ativo.")
    await autorizar_empresa(e, s, permissao)
    return e


@router.get("")
async def listar(s=Depends(usuario_atual)):
    rows = await fetch_all(
        """SELECT e.ID_Empresas,e.NomeFantasia,e.RazaoSocial,m.Papel FROM Org_Membros m
        JOIN Empresas e ON e.ID_Empresas=m.ID_Empresas AND e.Ativo=1
        WHERE m.ID_Usuarios=%s AND m.Ativo=1 ORDER BY e.NomeFantasia,e.ID_Empresas""",
        (s["id_usuario"],),
    )
    # Contas legadas/nova empresa continuam utilizáveis sem criar registros em GET.
    native = await fetch_all(
        """SELECT e.* FROM Empresas e WHERE e.Ativo=1 AND
        (e.ID_Usuarios=%s OR EXISTS (SELECT 1 FROM Recrutadores r WHERE r.ID_Empresas=e.ID_Empresas AND r.ID_Usuarios=%s AND r.Ativo=1))""",
        (s["id_usuario"], s["id_usuario"]),
    )
    for e in native:
        if not any(r["ID_Empresas"] == e["ID_Empresas"] for r in rows):
            try:
                role = await papel_empresa(e, s)
            except HTTPException:
                continue
            rows.append(
                {k: e.get(k) for k in ("ID_Empresas", "NomeFantasia", "RazaoSocial")}
                | {"Papel": role}
            )
    return [{**r, "permissoes": sorted(PAPEIS.get(r["Papel"], set()))} for r in rows]


@router.get("/contexto")
async def contexto(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "contexto")
    role = await papel_empresa(e, s)
    return {
        "empresa": {
            k: e.get(k) for k in ("ID_Empresas", "NomeFantasia", "RazaoSocial")
        },
        "papel": role,
        "permissoes": sorted(PAPEIS[role]),
    }


@router.get("/membros")
async def membros(id_empresa: str | None = None, s=Depends(usuario_atual)):
    e = await contexto_empresa(s, id_empresa, "equipe")
    return await fetch_all(
        """SELECT m.ID_Usuarios,u.Nome,u.Email,m.Papel,m.Ativo,m.Versao FROM Org_Membros m
        JOIN Usuarios u ON u.ID_Usuarios=m.ID_Usuarios WHERE m.ID_Empresas=%s ORDER BY u.Nome""",
        (e["ID_Empresas"],),
    )


class Convite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: EmailStr
    papel: Role = "recrutador"


@router.post("/convites", status_code=201)
async def convidar(
    d: Convite,
    request: Request,
    id_empresa: str | None = None,
    s=Depends(usuario_atual),
):
    e = await contexto_empresa(s, id_empresa, "equipe")
    caller = await papel_empresa(e, s)
    if d.papel in {"owner", "rh_admin"} and caller != "owner":
        raise HTTPException(403, "Somente Owner pode conceder papéis administrativos.")
    token = secrets.token_urlsafe(32)
    id = novo_uuid()
    await execute(
        "INSERT INTO Org_Convites(ID_Convite,ID_Empresas,Email,Papel,TokenHash,ExpiraEm) VALUES (%s,%s,%s,%s,%s,%s)",
        (
            id,
            e["ID_Empresas"],
            str(d.email).lower(),
            d.papel,
            sha256(token.encode()).hexdigest(),
            datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
        ),
    )
    await registrar_auditoria(
        request,
        "organizacao.convidar",
        "Org_Convites",
        s["id_usuario"],
        id,
        novo={"papel": d.papel},
    )
    return {
        "id": id,
        "token": token,
        "expira_em_dias": 7,
        "orientacao": "Compartilhe o código com a pessoa convidada; ele é exibido somente agora.",
    }


class Aceite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=30, max_length=100)


@router.post("/convites/aceitar")
async def aceitar(d: Aceite, request: Request, s=Depends(usuario_atual)):
    invite = await fetch_one(
        """SELECT * FROM Org_Convites WHERE TokenHash=%s AND AceitoEm IS NULL AND RevogadoEm IS NULL AND ExpiraEm>NOW() FOR UPDATE""",
        (sha256(d.token.encode()).hexdigest(),),
    )
    u = await fetch_one(
        "SELECT Email,EmailConfirmadoEm FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1",
        (s["id_usuario"],),
    )
    if (
        not invite
        or not u
        or not u["EmailConfirmadoEm"]
        or u["Email"].lower() != invite["Email"].lower()
    ):
        raise HTTPException(
            403, "Convite inválido, expirado ou incompatível com seu e-mail confirmado."
        )
    e = await fetch_one(
        "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s AND Ativo=1 FOR UPDATE",
        (invite["ID_Empresas"],),
    )
    if not e:
        raise HTTPException(409, "Organização indisponível.")
    existing = await fetch_one(
        "SELECT * FROM Org_Membros WHERE ID_Empresas=%s AND ID_Usuarios=%s FOR UPDATE",
        (invite["ID_Empresas"], s["id_usuario"]),
    )
    if existing and existing["Ativo"]:
        raise HTTPException(
            409,
            "Você já possui um vínculo ativo; a alteração de papel requer ação do Owner.",
        )
    if existing:
        await execute(
            "UPDATE Org_Membros SET Ativo=1,Papel=%s,Versao=Versao+1 WHERE ID_Empresas=%s AND ID_Usuarios=%s",
            (invite["Papel"], invite["ID_Empresas"], s["id_usuario"]),
        )
    else:
        await execute(
            "INSERT INTO Org_Membros(ID_Empresas,ID_Usuarios,Papel) VALUES (%s,%s,%s)",
            (invite["ID_Empresas"], s["id_usuario"], invite["Papel"]),
        )
    await execute(
        "UPDATE Org_Convites SET AceitoEm=NOW() WHERE ID_Convite=%s",
        (invite["ID_Convite"],),
    )
    await registrar_auditoria(
        request,
        "organizacao.aceitar",
        "Org_Membros",
        s["id_usuario"],
        invite["ID_Empresas"],
    )
    return {"mensagem": "Vínculo aceito. Selecione a organização para trabalhar."}


class Membro(BaseModel):
    model_config = ConfigDict(extra="forbid")
    papel: Role
    ativo: bool = True
    versao: int = Field(ge=1)


@router.put("/membros/{id_usuario}")
async def editar(
    id_usuario: str,
    d: Membro,
    request: Request,
    id_empresa: str | None = None,
    s=Depends(usuario_atual),
):
    e = await contexto_empresa(s, id_empresa, "equipe")
    await fetch_one(
        "SELECT ID_Empresas FROM Empresas WHERE ID_Empresas=%s FOR UPDATE",
        (e["ID_Empresas"],),
    )
    caller = await papel_empresa(e, s)
    old = await fetch_one(
        "SELECT * FROM Org_Membros WHERE ID_Empresas=%s AND ID_Usuarios=%s FOR UPDATE",
        (e["ID_Empresas"], id_usuario),
    )
    if not old:
        raise HTTPException(404, "Membro indisponível.")
    if old["Versao"] != d.versao:
        raise HTTPException(409, "Vínculo alterado; recarregue.")
    if caller != "owner" and (
        old["Papel"] in {"owner", "rh_admin"} or d.papel in {"owner", "rh_admin"}
    ):
        raise HTTPException(403, "Somente Owner pode alterar papéis administrativos.")
    if old["Papel"] == "owner" and old["Ativo"] and (not d.ativo or d.papel != "owner"):
        count = await fetch_one(
            "SELECT COUNT(*) AS total FROM Org_Membros WHERE ID_Empresas=%s AND Papel='owner' AND Ativo=1 FOR UPDATE",
            (e["ID_Empresas"],),
        )
        if count["total"] <= 1:
            raise HTTPException(
                409, "Não é permitido remover ou rebaixar o último Owner."
            )
    await execute(
        "UPDATE Org_Membros SET Papel=%s,Ativo=%s,Versao=Versao+1 WHERE ID_Empresas=%s AND ID_Usuarios=%s",
        (d.papel, d.ativo, e["ID_Empresas"], id_usuario),
    )
    await registrar_auditoria(
        request,
        "organizacao.membro.editar",
        "Org_Membros",
        s["id_usuario"],
        id_usuario,
        {"papel": old["Papel"], "ativo": old["Ativo"]},
        d.model_dump(),
    )
    return {"mensagem": "Permissões atualizadas; efeito imediato."}
