"""
Dependências reutilizáveis do FastAPI: usuário autenticado atual,
e checagem de tipo de usuário (Candidato / Empresa / Administrador).
"""
from fastapi import Request, HTTPException, status, Depends
from app.core.session import ler_sessao
from app.db.database import fetch_one


async def usuario_atual(request: Request) -> dict:
    """
    Exige que exista uma sessão válida (cookie). Retorna o payload da sessão:
    {"id_usuario": "...", "tipo_usuario": "candidato|empresa|administrador"}
    """
    sessao = ler_sessao(request)
    if sessao is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autenticado. Faça login novamente.",
        )
    usuario = await fetch_one(
        "SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1", (sessao["id_usuario"],)
    )
    if not usuario:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão inválida. Faça login novamente.")
    return sessao


def exigir_tipo(*tipos_permitidos: str):
    """
    Fábrica de dependência: exige que o usuário logado seja de um dos tipos informados.
    Uso: Depends(exigir_tipo("empresa", "administrador"))
    """

    def checador(sessao: dict = Depends(usuario_atual)) -> dict:
        if sessao["tipo_usuario"] not in tipos_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso restrito a: {', '.join(tipos_permitidos)}.",
            )
        return sessao

    return checador


async def usuario_opcional(request: Request) -> dict | None:
    """Retorna a sessão se existir, ou None (para endpoints públicos com comportamento extra se logado)."""
    sessao = ler_sessao(request)
    if not sessao:
        return None
    usuario = await fetch_one(
        "SELECT ID_Usuarios FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1", (sessao["id_usuario"],)
    )
    return sessao if usuario else None
