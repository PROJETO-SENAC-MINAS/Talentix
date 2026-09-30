"""Regras de acesso a dados privados de candidatos e às vagas das empresas."""
from fastapi import HTTPException, status

from app.db.database import fetch_one


async def checar_habilidade_ativa(id_habilidade: str) -> dict:
    habilidade = await fetch_one("SELECT * FROM Habilidades WHERE ID_Habilidades=%s AND Ativo=1", (id_habilidade,))
    if not habilidade:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Habilidade indisponível.")
    return habilidade


async def empresa_da_sessao(sessao: dict) -> dict:
    if sessao["tipo_usuario"] == "empresa":
        empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Usuarios=%s AND Ativo=1", (sessao["id_usuario"],))
    elif sessao["tipo_usuario"] == "recrutador":
        empresa = await fetch_one("""SELECT e.* FROM Empresas e JOIN Recrutadores r
                 ON r.ID_Empresas=e.ID_Empresas AND r.Ativo=1
                 WHERE r.ID_Usuarios=%s AND e.Ativo=1""", (sessao["id_usuario"],))
    else:
        empresa = None
    if not empresa:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Empresa ou vínculo ativo não encontrado.")
    return empresa


async def checar_empresa(id_empresa: str, sessao: dict, permitir_recrutador: bool = True) -> dict:
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s AND Ativo=1", (id_empresa,))
    if not empresa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Empresa não encontrada.")
    if sessao["tipo_usuario"] == "administrador":
        return empresa
    if not permitir_recrutador and sessao["tipo_usuario"] != "empresa":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Ação restrita ao responsável pela empresa.")
    vinculada = await empresa_da_sessao(sessao)
    if vinculada["ID_Empresas"] != id_empresa:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta empresa.")
    return empresa


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
    if sessao["tipo_usuario"] not in {"empresa", "recrutador"}:
        return await checar_dono_candidato(id_candidato, sessao)
    empresa = await empresa_da_sessao(sessao)
    candidato = await fetch_one(
        """SELECT c.* FROM Candidatos c
           JOIN Candidaturas ca ON ca.ID_Candidatos=c.ID_Candidatos AND ca.Ativo=1
           JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas
           JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
           WHERE c.ID_Candidatos=%s AND c.Ativo=1 AND e.ID_Empresas=%s LIMIT 1""",
        (id_candidato, empresa["ID_Empresas"]),
    )
    if not candidato:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre este candidato.")
    return candidato


async def checar_acesso_analise(id_candidato: str, id_vaga: str, sessao: dict) -> None:
    vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (id_vaga,))
    if not vaga:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")
    if sessao["tipo_usuario"] in {"empresa", "recrutador"}:
        empresa = await empresa_da_sessao(sessao)
        acesso = await fetch_one(
            """SELECT ca.ID_Candidaturas FROM Candidaturas ca
               JOIN Vagas v ON v.ID_Vagas=ca.ID_Vagas
               JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
               WHERE ca.ID_Candidatos=%s AND ca.ID_Vagas=%s AND ca.Ativo=1
                 AND e.ID_Empresas=%s LIMIT 1""",
            (id_candidato, id_vaga, empresa["ID_Empresas"]),
        )
        if not acesso:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta análise.")
    else:
        await checar_dono_candidato(id_candidato, sessao)
        if sessao["tipo_usuario"] != "administrador" and vaga["ID_Status_Vaga"] != 2:
            raise HTTPException(status.HTTP_409_CONFLICT, "Vaga indisponível para análise.")
