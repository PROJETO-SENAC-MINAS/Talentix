"""Regras de acesso a dados privados de candidatos e às vagas das empresas."""
from fastapi import HTTPException, status

from app.db.database import fetch_one


async def checar_dono_candidato(id_candidato: str, sessao: dict) -> dict:
    candidato = await fetch_one(
        "SELECT * FROM Candidatos WHERE ID_Candidatos=%s AND Ativo=1", (id_candidato,)
    )
    if not candidato:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidato não encontrado.")
    if sessao["tipo_usuario"] == "administrador":
        return candidato
    if sessao["tipo_usuario"] == "candidato" and candidato["ID_Usuarios"] == sessao["id_usuario"]:
        return candidato
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre este candidato.")


async def checar_leitura_candidato(id_candidato: str, sessao: dict) -> dict:
    """Empresa só pode ler perfis de quem se candidatou a uma de suas vagas."""
    if sessao["tipo_usuario"] != "empresa":
        return await checar_dono_candidato(id_candidato, sessao)
    candidato = await fetch_one(
        """SELECT c.* FROM Candidatos c
           JOIN Candidaturas ca ON ca.ID_Candidatos=c.ID_Candidatos AND ca.Ativo=1
           JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas
           JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
           WHERE c.ID_Candidatos=%s AND c.Ativo=1 AND e.ID_Usuarios=%s LIMIT 1""",
        (id_candidato, sessao["id_usuario"]),
    )
    if not candidato:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre este candidato.")
    return candidato


async def checar_acesso_analise(id_candidato: str, id_vaga: str, sessao: dict) -> None:
    if sessao["tipo_usuario"] == "empresa":
        acesso = await fetch_one(
            """SELECT ca.ID_Candidaturas FROM Candidaturas ca
               JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas
               JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
               WHERE ca.ID_Candidatos=%s AND ca.ID_Vagas=%s AND ca.Ativo=1
                 AND e.ID_Usuarios=%s LIMIT 1""",
            (id_candidato, id_vaga, sessao["id_usuario"]),
        )
        if not acesso:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta análise.")
    else:
        await checar_dono_candidato(id_candidato, sessao)
