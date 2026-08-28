"""
Endpoints de métricas agregadas para os dashboards de Candidato, Empresa e Admin.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.db.database import fetch_one, fetch_all
from app.core.deps import usuario_atual, exigir_tipo

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/candidato")
async def metricas_candidato(sessao: dict = Depends(usuario_atual)):
    candidato = await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if not candidato:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas candidatos.")
    id_c = candidato["ID_Candidatos"]

    total_candidaturas = await fetch_one(
        "SELECT COUNT(*) AS total FROM Candidaturas WHERE ID_Candidatos=%s AND Ativo=1", (id_c,)
    )
    por_status = await fetch_all(
        """SELECT sc.Descricao, COUNT(*) AS total
           FROM Candidaturas c JOIN Status_Candidatura sc ON sc.ID_Status_Candidatura = c.ID_Status_Candidatura
           WHERE c.ID_Candidatos=%s AND c.Ativo=1 GROUP BY sc.Descricao""",
        (id_c,),
    )
    entrevistas_agendadas = await fetch_one(
        """SELECT COUNT(*) AS total FROM Entrevistas e
           JOIN Candidaturas c ON c.ID_Candidaturas = e.ID_Candidaturas
           WHERE c.ID_Candidatos=%s AND e.ID_Status_Entrevista=1""",
        (id_c,),
    )
    favoritos = await fetch_one("SELECT COUNT(*) AS total FROM Favoritos_Vaga WHERE ID_Candidatos=%s", (id_c,))

    return {
        "total_candidaturas": total_candidaturas["total"],
        "candidaturas_por_status": por_status,
        "entrevistas_agendadas": entrevistas_agendadas["total"],
        "vagas_favoritadas": favoritos["total"],
    }


@router.get("/empresa/{id_empresa}")
async def metricas_empresa(id_empresa: str, sessao: dict = Depends(usuario_atual)):
    if sessao["tipo_usuario"] != "administrador":
        empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (id_empresa,))
        if not empresa or empresa["ID_Usuarios"] != sessao["id_usuario"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão.")

    total_vagas = await fetch_one(
        "SELECT COUNT(*) AS total FROM Vagas WHERE ID_Empresas=%s AND Ativo=1", (id_empresa,)
    )
    vagas_publicadas = await fetch_one(
        "SELECT COUNT(*) AS total FROM Vagas WHERE ID_Empresas=%s AND ID_Status_Vaga=2 AND Ativo=1", (id_empresa,)
    )
    total_candidaturas = await fetch_one(
        """SELECT COUNT(*) AS total FROM Candidaturas c
           JOIN Vagas v ON v.ID_Vagas = c.ID_Vagas
           WHERE v.ID_Empresas=%s AND c.Ativo=1""",
        (id_empresa,),
    )
    candidaturas_por_vaga = await fetch_all(
        """SELECT v.Titulo, COUNT(c.ID_Candidaturas) AS total
           FROM Vagas v LEFT JOIN Candidaturas c ON c.ID_Vagas = v.ID_Vagas AND c.Ativo=1
           WHERE v.ID_Empresas=%s AND v.Ativo=1
           GROUP BY v.ID_Vagas, v.Titulo""",
        (id_empresa,),
    )

    return {
        "total_vagas": total_vagas["total"],
        "vagas_publicadas": vagas_publicadas["total"],
        "total_candidaturas_recebidas": total_candidaturas["total"],
        "candidaturas_por_vaga": candidaturas_por_vaga,
    }


@router.get("/admin")
async def metricas_admin(sessao: dict = Depends(exigir_tipo("administrador"))):
    total_usuarios = await fetch_one("SELECT COUNT(*) AS total FROM Usuarios WHERE Ativo=1")
    total_candidatos = await fetch_one("SELECT COUNT(*) AS total FROM Candidatos WHERE Ativo=1")
    total_empresas = await fetch_one("SELECT COUNT(*) AS total FROM Empresas WHERE Ativo=1")
    total_vagas_ativas = await fetch_one(
        "SELECT COUNT(*) AS total FROM Vagas WHERE ID_Status_Vaga=2 AND Ativo=1"
    )
    total_candidaturas = await fetch_one("SELECT COUNT(*) AS total FROM Candidaturas WHERE Ativo=1")
    denuncias_abertas = await fetch_one(
        "SELECT COUNT(*) AS total FROM Denuncias WHERE ID_Status_Denuncia=1"
    )
    assinaturas_ativas = await fetch_one(
        "SELECT COUNT(*) AS total FROM Assinaturas WHERE ID_Status_Assinatura=1"
    )

    return {
        "total_usuarios": total_usuarios["total"],
        "total_candidatos": total_candidatos["total"],
        "total_empresas": total_empresas["total"],
        "total_vagas_ativas": total_vagas_ativas["total"],
        "total_candidaturas": total_candidaturas["total"],
        "denuncias_abertas": denuncias_abertas["total"],
        "assinaturas_ativas": assinaturas_ativas["total"],
    }