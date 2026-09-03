"""
CRUD de Candidaturas, Etapas do Processo Seletivo e Entrevistas.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from datetime import datetime

from app.db.database import fetch_one, fetch_all, execute
from app.core.security import novo_uuid
from app.core.deps import usuario_atual, exigir_tipo
from app.core.notificar import notificar_usuario
from app.core.email_service import (
    email_nova_candidatura,
    email_status_candidatura_atualizado,
    email_entrevista_agendada,
    email_entrevista_reagendada,
    email_entrevista_cancelada,
)

router = APIRouter(tags=["Candidaturas"])

_ID_STATUS_ENVIADA = 1


# ==================== CANDIDATURAS ====================

class CandidaturaCreate(BaseModel):
    id_vaga: str
    curriculo_url: str | None = None
    carta_apresentacao: str | None = None


async def _obter_id_candidato_da_sessao(sessao: dict) -> str:
    candidato = await fetch_one("SELECT ID_Candidatos FROM Candidatos WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if not candidato:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas candidatos podem realizar esta ação.")
    return candidato["ID_Candidatos"]


@router.post("/candidaturas", status_code=201, tags=["Candidaturas"])
async def criar_candidatura(dados: CandidaturaCreate, sessao: dict = Depends(exigir_tipo("candidato"))):
    id_candidato = await _obter_id_candidato_da_sessao(sessao)

    vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s AND Ativo=1", (dados.id_vaga,))
    if not vaga:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vaga não encontrada.")

    existente = await fetch_one(
        "SELECT * FROM Candidaturas WHERE ID_Candidatos=%s AND ID_Vagas=%s",
        (id_candidato, dados.id_vaga),
    )
    if existente:
        raise HTTPException(status.HTTP_409_CONFLICT, "Você já se candidatou a esta vaga.")

    id_candidatura = novo_uuid()
    await execute(
        """INSERT INTO Candidaturas (ID_Candidaturas, ID_Candidatos, ID_Vagas, ID_Status_Candidatura, CurriculoUrl, CartaApresentacao)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (id_candidatura, id_candidato, dados.id_vaga, _ID_STATUS_ENVIADA,
         dados.curriculo_url, dados.carta_apresentacao),
    )

    # cria a primeira etapa do processo automaticamente
    id_etapa = novo_uuid()
    await execute(
        """INSERT INTO Etapas_Processo (ID_Etapas_Processo, ID_Candidaturas, ID_Status_Etapa, Nome, Ordem, InicioEm)
           VALUES (%s, %s, 1, 'Triagem inicial', 1, NOW())""",
        (id_etapa, id_candidatura),
    )

    # notifica a empresa dona da vaga (in-app + e-mail)
    empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (vaga["ID_Empresas"],))
    candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if empresa:
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Um candidato"
        await notificar_usuario(
            id_usuario=empresa["ID_Usuarios"],
            titulo="Nova candidatura recebida",
            mensagem=f"{nome_candidato} se candidatou à vaga '{vaga['Titulo']}'.",
            tipo="candidatura",
            enviar_email_fn=lambda email: email_nova_candidatura(
                email, empresa["NomeFantasia"] or empresa["RazaoSocial"], vaga["Titulo"], nome_candidato
            ),
        )

    return await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))


@router.get("/candidaturas", tags=["Candidaturas"])
async def listar_candidaturas(
    id_vaga: str | None = None,
    id_candidato: str | None = None,
    sessao: dict = Depends(usuario_atual),
):
    query = """
        SELECT c.*, v.Titulo AS TituloVaga, v.Localizacao AS LocalizacaoVaga,
               v.Modalidade AS ModalidadeVaga, e.NomeFantasia AS NomeEmpresa
        FROM Candidaturas c
        JOIN Vagas v ON v.ID_Vagas = c.ID_Vagas
        JOIN Empresas e ON e.ID_Empresas = v.ID_Empresas
        WHERE c.Ativo=1
    """
    params: list = []

    if sessao["tipo_usuario"] == "candidato":
        meu_id = await _obter_id_candidato_da_sessao(sessao)
        query += " AND c.ID_Candidatos=%s"
        params.append(meu_id)
    elif id_candidato:
        query += " AND c.ID_Candidatos=%s"
        params.append(id_candidato)

    if id_vaga:
        query += " AND c.ID_Vagas=%s"
        params.append(id_vaga)

    query += " ORDER BY c.CriadaEm DESC"
    return await fetch_all(query, tuple(params))


async def _checar_acesso_candidatura(candidatura: dict, sessao: dict) -> None:
    if sessao["tipo_usuario"] == "administrador":
        return
    if sessao["tipo_usuario"] == "candidato":
        candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (candidatura["ID_Candidatos"],))
        if candidato and candidato["ID_Usuarios"] == sessao["id_usuario"]:
            return
    if sessao["tipo_usuario"] == "empresa":
        vaga = await fetch_one("SELECT * FROM Vagas WHERE ID_Vagas=%s", (candidatura["ID_Vagas"],))
        empresa = await fetch_one("SELECT * FROM Empresas WHERE ID_Empresas=%s", (vaga["ID_Empresas"],)) if vaga else None
        if empresa and empresa["ID_Usuarios"] == sessao["id_usuario"]:
            return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Sem permissão sobre esta candidatura.")


@router.get("/candidaturas/{id_candidatura}", tags=["Candidaturas"])
async def obter_candidatura(id_candidatura: str, sessao: dict = Depends(usuario_atual)):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s AND Ativo=1", (id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
    await _checar_acesso_candidatura(candidatura, sessao)
    etapas = await fetch_all(
        "SELECT * FROM Etapas_Processo WHERE ID_Candidaturas=%s ORDER BY Ordem", (id_candidatura,)
    )
    entrevistas = await fetch_all(
        "SELECT * FROM Entrevistas WHERE ID_Candidaturas=%s ORDER BY DataHora", (id_candidatura,)
    )
    return {**candidatura, "etapas": etapas, "entrevistas": entrevistas}


@router.patch("/candidaturas/{id_candidatura}/status", tags=["Candidaturas"])
async def atualizar_status_candidatura(
    id_candidatura: str, id_status_candidatura: int, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))
):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
    await _checar_acesso_candidatura(candidatura, sessao)
    await execute(
        "UPDATE Candidaturas SET ID_Status_Candidatura=%s WHERE ID_Candidaturas=%s",
        (id_status_candidatura, id_candidatura),
    )

    # notifica o candidato sobre a mudança de status (in-app + e-mail)
    novo_status = await fetch_one(
        "SELECT Descricao FROM Status_Candidatura WHERE ID_Status_Candidatura=%s", (id_status_candidatura,)
    )
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (candidatura["ID_Candidatos"],))
    vaga = await fetch_one("SELECT Titulo FROM Vagas WHERE ID_Vagas=%s", (candidatura["ID_Vagas"],))
    if candidato and novo_status and vaga:
        candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (candidato["ID_Usuarios"],))
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Candidato"
        await notificar_usuario(
            id_usuario=candidato["ID_Usuarios"],
            titulo="Status da candidatura atualizado",
            mensagem=f"Sua candidatura para '{vaga['Titulo']}' agora está: {novo_status['Descricao']}.",
            tipo="candidatura",
            enviar_email_fn=lambda email: email_status_candidatura_atualizado(
                email, nome_candidato, vaga["Titulo"], novo_status["Descricao"]
            ),
        )

    return await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))


@router.delete("/candidaturas/{id_candidatura}", tags=["Candidaturas"])
async def cancelar_candidatura(id_candidatura: str, sessao: dict = Depends(usuario_atual)):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
    await _checar_acesso_candidatura(candidatura, sessao)
    await execute(
        "UPDATE Candidaturas SET Ativo=0, DeletadoEm=NOW(), ID_Status_Candidatura=7 WHERE ID_Candidaturas=%s",
        (id_candidatura,),
    )
    return {"mensagem": "Candidatura cancelada."}


# ==================== ETAPAS DO PROCESSO ====================

class EtapaCreate(BaseModel):
    nome: str
    ordem: int


@router.post("/candidaturas/{id_candidatura}/etapas", status_code=201, tags=["Etapas do Processo"])
async def criar_etapa(
    id_candidatura: str, dados: EtapaCreate, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))
):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
    await _checar_acesso_candidatura(candidatura, sessao)

    id_etapa = novo_uuid()
    await execute(
        """INSERT INTO Etapas_Processo (ID_Etapas_Processo, ID_Candidaturas, ID_Status_Etapa, Nome, Ordem)
           VALUES (%s, %s, 1, %s, %s)""",
        (id_etapa, id_candidatura, dados.nome, dados.ordem),
    )
    return await fetch_one("SELECT * FROM Etapas_Processo WHERE ID_Etapas_Processo=%s", (id_etapa,))


@router.patch("/etapas/{id_etapa}/concluir", tags=["Etapas do Processo"])
async def concluir_etapa(id_etapa: str, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))):
    etapa = await fetch_one("SELECT * FROM Etapas_Processo WHERE ID_Etapas_Processo=%s", (id_etapa,))
    if not etapa:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Etapa não encontrada.")
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (etapa["ID_Candidaturas"],))
    await _checar_acesso_candidatura(candidatura, sessao)
    await execute(
        "UPDATE Etapas_Processo SET ID_Status_Etapa=3, FimEm=NOW() WHERE ID_Etapas_Processo=%s", (id_etapa,)
    )
    return {"mensagem": "Etapa concluída."}


@router.patch("/etapas/{id_etapa}/reabrir", tags=["Etapas do Processo"])
async def reabrir_etapa(id_etapa: str, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))):
    await execute(
        "UPDATE Etapas_Processo SET ID_Status_Etapa=2, FimEm=NULL WHERE ID_Etapas_Processo=%s", (id_etapa,)
    )
    return {"mensagem": "Etapa reaberta."}


# ==================== ENTREVISTAS ====================

class EntrevistaCreate(BaseModel):
    id_recrutador: str
    data_hora: datetime
    tipo: str | None = None
    local_ou_link: str | None = None
    observacoes: str | None = None


@router.post("/candidaturas/{id_candidatura}/entrevistas", status_code=201, tags=["Entrevistas"])
async def agendar_entrevista(
    id_candidatura: str, dados: EntrevistaCreate, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))
):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
    await _checar_acesso_candidatura(candidatura, sessao)

    id_entrevista = novo_uuid()
    await execute(
        """INSERT INTO Entrevistas (ID_Entrevistas, ID_Candidaturas, ID_Recrutadores, ID_Status_Entrevista,
               DataHora, Tipo, LocalOuLink, Observacoes)
           VALUES (%s, %s, %s, 1, %s, %s, %s, %s)""",
        (id_entrevista, id_candidatura, dados.id_recrutador, dados.data_hora,
         dados.tipo, dados.local_ou_link, dados.observacoes),
    )

    # notifica o candidato sobre a entrevista agendada (in-app + e-mail)
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (candidatura["ID_Candidatos"],))
    vaga = await fetch_one("SELECT Titulo FROM Vagas WHERE ID_Vagas=%s", (candidatura["ID_Vagas"],))
    if candidato and vaga:
        candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (candidato["ID_Usuarios"],))
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Candidato"
        data_formatada = dados.data_hora.strftime("%d/%m/%Y às %H:%M")
        await notificar_usuario(
            id_usuario=candidato["ID_Usuarios"],
            titulo="Entrevista agendada",
            mensagem=f"Uma entrevista foi agendada para a vaga '{vaga['Titulo']}' em {data_formatada}.",
            tipo="entrevista",
            enviar_email_fn=lambda email: email_entrevista_agendada(
                email, nome_candidato, vaga["Titulo"], data_formatada, dados.local_ou_link
            ),
        )

    return await fetch_one("SELECT * FROM Entrevistas WHERE ID_Entrevistas=%s", (id_entrevista,))


@router.get("/candidaturas/{id_candidatura}/entrevistas", tags=["Entrevistas"])
async def listar_entrevistas(id_candidatura: str, sessao: dict = Depends(usuario_atual)):
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (id_candidatura,))
    if not candidatura:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidatura não encontrada.")
    await _checar_acesso_candidatura(candidatura, sessao)
    return await fetch_all(
        "SELECT * FROM Entrevistas WHERE ID_Candidaturas=%s ORDER BY DataHora", (id_candidatura,)
    )


async def _obter_contexto_entrevista(id_entrevista: str) -> tuple[dict, dict, dict] | None:
    """Busca candidatura, candidato e vaga associados a uma entrevista, para fins de notificação."""
    entrevista = await fetch_one("SELECT * FROM Entrevistas WHERE ID_Entrevistas=%s", (id_entrevista,))
    if not entrevista:
        return None
    candidatura = await fetch_one("SELECT * FROM Candidaturas WHERE ID_Candidaturas=%s", (entrevista["ID_Candidaturas"],))
    if not candidatura:
        return None
    candidato = await fetch_one("SELECT * FROM Candidatos WHERE ID_Candidatos=%s", (candidatura["ID_Candidatos"],))
    vaga = await fetch_one("SELECT Titulo FROM Vagas WHERE ID_Vagas=%s", (candidatura["ID_Vagas"],))
    if not candidato or not vaga:
        return None
    return candidato, vaga, entrevista


@router.patch("/entrevistas/{id_entrevista}/reagendar", tags=["Entrevistas"])
async def reagendar_entrevista(
    id_entrevista: str, nova_data_hora: datetime, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))
):
    await execute(
        "UPDATE Entrevistas SET DataHora=%s, ID_Status_Entrevista=3 WHERE ID_Entrevistas=%s",
        (nova_data_hora, id_entrevista),
    )

    contexto = await _obter_contexto_entrevista(id_entrevista)
    if contexto:
        candidato, vaga, _ = contexto
        candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (candidato["ID_Usuarios"],))
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Candidato"
        data_formatada = nova_data_hora.strftime("%d/%m/%Y às %H:%M")
        await notificar_usuario(
            id_usuario=candidato["ID_Usuarios"],
            titulo="Entrevista reagendada",
            mensagem=f"Sua entrevista para '{vaga['Titulo']}' foi reagendada para {data_formatada}.",
            tipo="entrevista",
            enviar_email_fn=lambda email: email_entrevista_reagendada(
                email, nome_candidato, vaga["Titulo"], data_formatada
            ),
        )

    return {"mensagem": "Entrevista reagendada."}


@router.patch("/entrevistas/{id_entrevista}/cancelar", tags=["Entrevistas"])
async def cancelar_entrevista(id_entrevista: str, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))):
    contexto = await _obter_contexto_entrevista(id_entrevista)

    await execute("UPDATE Entrevistas SET ID_Status_Entrevista=4 WHERE ID_Entrevistas=%s", (id_entrevista,))

    if contexto:
        candidato, vaga, _ = contexto
        candidato_usuario = await fetch_one("SELECT Nome FROM Usuarios WHERE ID_Usuarios=%s", (candidato["ID_Usuarios"],))
        nome_candidato = candidato_usuario["Nome"] if candidato_usuario else "Candidato"
        await notificar_usuario(
            id_usuario=candidato["ID_Usuarios"],
            titulo="Entrevista cancelada",
            mensagem=f"Sua entrevista para '{vaga['Titulo']}' foi cancelada.",
            tipo="entrevista",
            enviar_email_fn=lambda email: email_entrevista_cancelada(email, nome_candidato, vaga["Titulo"]),
        )

    return {"mensagem": "Entrevista cancelada."}


@router.patch("/entrevistas/{id_entrevista}/realizar", tags=["Entrevistas"])
async def marcar_entrevista_realizada(id_entrevista: str, sessao: dict = Depends(exigir_tipo("empresa", "administrador"))):
    await execute("UPDATE Entrevistas SET ID_Status_Entrevista=2 WHERE ID_Entrevistas=%s", (id_entrevista,))
    return {"mensagem": "Entrevista marcada como realizada."}