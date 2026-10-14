"""Permissões empresariais centralizadas; seleção de tenant nunca concede acesso."""

from fastapi import HTTPException
from app.db.database import fetch_one

PAPEIS = {
    "owner": {
        "ler",
        "vagas",
        "processos",
        "entrevistas",
        "comunicacao",
        "automacoes",
        "equipe",
        "publicacao",
        "analytics",
        "financeiro",
        "avaliar",
    },
    "rh_admin": {
        "ler",
        "vagas",
        "processos",
        "entrevistas",
        "comunicacao",
        "automacoes",
        "equipe",
        "publicacao",
        "analytics",
        "avaliar",
    },
    "recrutador": {
        "ler",
        "vagas",
        "processos",
        "entrevistas",
        "comunicacao",
        "avaliar",
    },
    "hiring_manager": {"ler", "analytics", "avaliar"},
    "entrevistador": {"entrevistas:ler", "avaliar"},
}
for _permissions in PAPEIS.values():
    _permissions.add("contexto")


async def papel_empresa(empresa, sessao):
    if sessao["tipo_usuario"] == "administrador":
        return "owner"
    row = await fetch_one(
        "SELECT Papel,Ativo FROM Org_Membros WHERE ID_Empresas=%s AND ID_Usuarios=%s",
        (empresa["ID_Empresas"], sessao["id_usuario"]),
    )
    if row:
        if not row["Ativo"]:
            raise HTTPException(403, "Vínculo empresarial revogado.")
        return row["Papel"]
    # Compatibilidade com contas criadas pelas APIs anteriores após a migration.
    if empresa["ID_Usuarios"] == sessao["id_usuario"]:
        return "owner"
    linked = await fetch_one(
        "SELECT ID_Recrutadores FROM Recrutadores WHERE ID_Empresas=%s AND ID_Usuarios=%s AND Ativo=1",
        (empresa["ID_Empresas"], sessao["id_usuario"]),
    )
    if linked:
        return "recrutador"
    raise HTTPException(403, "Sem vínculo ativo com esta organização.")


async def autorizar_empresa(empresa, sessao, permissao="ler"):
    role = await papel_empresa(empresa, sessao)
    if permissao not in PAPEIS.get(role, set()):
        raise HTTPException(403, "Seu papel não permite esta ação na organização.")
    return role


async def responsaveis_empresa(id_empresa):
    from app.db.database import fetch_all

    rows = await fetch_all(
        """SELECT m.ID_Usuarios FROM Org_Membros m JOIN Usuarios u ON u.ID_Usuarios=m.ID_Usuarios AND u.Ativo=1
        WHERE m.ID_Empresas=%s AND m.Papel='owner' AND m.Ativo=1 ORDER BY m.CriadoEm,m.ID_Usuarios""",
        (id_empresa,),
    )
    if rows:
        return [r["ID_Usuarios"] for r in rows]
    legacy = await fetch_one(
        """SELECT e.ID_Usuarios FROM Empresas e JOIN Usuarios u ON u.ID_Usuarios=e.ID_Usuarios AND u.Ativo=1
        WHERE e.ID_Empresas=%s AND e.Ativo=1 AND NOT EXISTS(SELECT 1 FROM Org_Membros m WHERE m.ID_Empresas=e.ID_Empresas AND m.ID_Usuarios=e.ID_Usuarios)""",
        (id_empresa,),
    )
    return [legacy["ID_Usuarios"]] if legacy else []


def permissao_da_rota(method, path):
    write = method in {"POST", "PUT", "PATCH", "DELETE"}
    if "/assinatura" in path or path.startswith("/pagamentos"):
        return "financeiro"
    if "/recrutadores" in path:
        return "equipe" if write else "ler"
    if path.startswith("/ats/") and ("/avaliacoes" in path or "/scorecards" in path):
        return "processos" if write and "/avaliacoes" not in path else "avaliar"
    if path.startswith("/inteligencia/"):
        return "ler"
    if not write:
        return "ler"
    if path.startswith("/vagas/") and path.endswith(("/publicar", "/encerrar")):
        return "publicacao"
    if path.startswith("/vagas") or path.startswith("/vaga-habilidades"):
        return "vagas"
    if "/entrevista" in path:
        return "entrevistas"
    return "processos"
