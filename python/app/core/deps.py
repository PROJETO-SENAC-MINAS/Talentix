"""Autenticação, papéis e permissões reutilizáveis."""
from hashlib import sha256
from hmac import compare_digest

from fastapi import Depends, HTTPException, Request, status

from app.core.session import ler_sessao
from app.db.database import execute, fetch_one


PERMISSOES_POR_PAPEL = {
    "administrador": {
        "admin:gerenciar", "usuarios:gerenciar", "empresas:gerenciar",
        "denuncias:gerenciar", "catalogo:gerenciar", "auditoria:ler",
    },
    "empresa": {
        "empresa:editar", "vagas:gerenciar", "candidaturas:gerenciar",
        "recrutadores:gerenciar", "entrevistas:gerenciar",
    },
    "recrutador": {"vagas:gerenciar", "candidaturas:gerenciar", "entrevistas:gerenciar"},
    "candidato": {"perfil:editar", "curriculos:gerenciar", "vagas:candidatar", "favoritos:gerenciar"},
    "usuario": set(),
}


def permissoes_usuario(tipo: str) -> list[str]:
    return sorted(PERMISSOES_POR_PAPEL.get(tipo, set()))


async def descobrir_tipo_usuario(id_usuario: str) -> str | None:
    for tabela, chave, tipo in (
        ("Administradores", "ID_Administradores", "administrador"),
        ("Empresas", "ID_Empresas", "empresa"),
    ):
        if await fetch_one(f"SELECT {chave} FROM {tabela} WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
            return tipo
    if await fetch_one(
        """SELECT r.ID_Recrutadores FROM Recrutadores r
           JOIN Empresas e ON e.ID_Empresas=r.ID_Empresas AND e.Ativo=1
           WHERE r.ID_Usuarios=%s AND r.Ativo=1""", (id_usuario,)
    ):
        return "recrutador"
    if await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
        return "candidato"
    for tabela in ("Candidatos", "Empresas", "Administradores", "Recrutadores"):
        if await fetch_one(f"SELECT ID_Usuarios FROM {tabela} WHERE ID_Usuarios=%s", (id_usuario,)):
            return None
    return "usuario"


async def descobrir_tipo_usuario_comum(id_usuario: str) -> str:
    if await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
        return "candidato"
    if await fetch_one("SELECT ID_Empresas FROM Empresas WHERE ID_Usuarios=%s AND Ativo=1", (id_usuario,)):
        return "empresa"
    if await fetch_one(
        """SELECT r.ID_Recrutadores FROM Recrutadores r
           JOIN Empresas e ON e.ID_Empresas=r.ID_Empresas AND e.Ativo=1
           WHERE r.ID_Usuarios=%s AND r.Ativo=1""", (id_usuario,)
    ):
        return "recrutador"
    return "usuario"


async def usuario_atual(request: Request) -> dict:
    sessao = ler_sessao(request)
    if sessao is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Não autenticado. Faça login novamente.")

    usuario = await fetch_one(
        "SELECT ID_Usuarios, SenhaHash FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1",
        (sessao["id_usuario"],),
    )
    if not usuario:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida. Faça login novamente.")
    if not isinstance(sessao.get("auth_tag"), str) or not compare_digest(
        sessao["auth_tag"], sha256(usuario["SenhaHash"].encode()).hexdigest()
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada. Faça login novamente.")

    id_sessao = sessao.get("id_sessao")
    if id_sessao:
        ativa = await fetch_one(
            """SELECT ID_Sessoes FROM Sessoes
               WHERE ID_Sessoes=%s AND ID_Usuarios=%s AND RevogadaEm IS NULL AND ExpiraEm>NOW()""",
            (id_sessao, sessao["id_usuario"]),
        )
        if not ativa:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão encerrada. Faça login novamente.")
        await execute("UPDATE Sessoes SET UltimaAtividadeEm=NOW() WHERE ID_Sessoes=%s", (id_sessao,))

    tipo_principal = await descobrir_tipo_usuario(sessao["id_usuario"])
    if tipo_principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Perfil ou vínculo desativado.")

    modo_usuario = bool(sessao.get("modo_usuario")) and tipo_principal == "administrador"
    tipo_efetivo = await descobrir_tipo_usuario_comum(sessao["id_usuario"]) if modo_usuario else tipo_principal
    return {
        **sessao,
        "tipo_usuario": tipo_efetivo,
        "tipo_principal": tipo_principal,
        "modo_usuario": modo_usuario,
        "permissoes": permissoes_usuario(tipo_efetivo),
    }


def exigir_tipo(*tipos_permitidos: str):
    def checador(sessao: dict = Depends(usuario_atual)) -> dict:
        if sessao["tipo_usuario"] not in tipos_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso restrito a: {', '.join(tipos_permitidos)}.",
            )
        return sessao
    return checador


def exigir_permissao(permissao: str):
    def checador(sessao: dict = Depends(usuario_atual)) -> dict:
        if permissao not in sessao.get("permissoes", ()):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Permissão insuficiente para esta operação.")
        return sessao
    return checador


async def usuario_opcional(request: Request) -> dict | None:
    if not ler_sessao(request):
        return None
    try:
        return await usuario_atual(request)
    except HTTPException:
        return None
