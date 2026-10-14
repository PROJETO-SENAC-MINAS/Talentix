"""python -m app.worker_platform [--once]: automações, lembretes e outbox SMTP."""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from app.core.config import settings
from app.core.agenda import horario_utc
from app.core.delivery import enfileirar_email, corpo_email
from app.core.email_service import enviar_email
from app.core.security import novo_uuid
from app.db.database import (
    init_pool,
    close_pool,
    fetch_one,
    fetch_all,
    execute,
    transaction,
)

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def unpack(v):
    return json.loads(v) if isinstance(v, str) else v


def dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


async def regras():
    rules = await fetch_all(
        "SELECT * FROM Automacoes WHERE Ativa=1 ORDER BY CriadoEm LIMIT 500"
    )
    for r in rules:
        from app.core.organizations import responsaveis_empresa

        owners = await responsaveis_empresa(r["ID_Empresas"])
        if not owners:
            continue
        cond = unpack(r["Condicoes"])
        rows = await fetch_all(
            """SELECT c.ID_Candidaturas,ca.ID_Usuarios AS CandidatoUsuario,e.ID_Usuarios AS Owner,
            card.ID_Etapa,card.EntradaEm,st.Nome AS Etapa FROM Candidaturas c
            JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas JOIN Empresas e ON e.ID_Empresas=v.ID_Empresas AND e.Ativo=1
            JOIN Candidatos ca ON ca.ID_Candidatos=c.ID_Candidatos AND ca.Ativo=1
            JOIN ATS_Cards card ON card.ID_Candidaturas=c.ID_Candidaturas AND card.Estado='ativo'
            JOIN ATS_Etapas st ON st.ID_Etapa=card.ID_Etapa WHERE v.ID_Empresas=%s AND c.Ativo=1
            ORDER BY c.CriadaEm LIMIT 1000""",
            (r["ID_Empresas"],),
        )
        for row in rows:
            row["Owner"] = owners[0]
            if (
                r["Gatilho"] == "parado"
                and cond.get("etapa")
                and cond["etapa"].casefold() != row["Etapa"].casefold()
            ):
                continue
            events = []
            if r["Gatilho"] == "parado":
                if dt(row["EntradaEm"]) > utcnow() - timedelta(days=cond["dias"]):
                    continue
                events = [
                    f"parado:{row['ID_Candidaturas']}:{row['ID_Etapa']}:{row['EntradaEm']}"
                ]
            else:
                changes = await fetch_all(
                    """SELECT ID_Evento,Depois FROM ATS_Eventos WHERE ID_Candidaturas=%s AND CriadoEm>=%s AND Acao='ats.movimentacao' ORDER BY Sequencia LIMIT 100""",
                    (row["ID_Candidaturas"], r["CriadoEm"]),
                )
                for change in changes:
                    after = unpack(change["Depois"]) or {}
                    if (
                        cond.get("etapa")
                        and after.get("NomeEtapa", "").casefold()
                        != cond["etapa"].casefold()
                    ):
                        continue
                    events.append("etapa:" + change["ID_Evento"])
            for event in events:
                async with transaction():
                    # Lock revalidates deactivation and serializes the unique execution.
                    current = await fetch_one(
                        "SELECT * FROM Automacoes WHERE ID_Regra=%s FOR UPDATE",
                        (r["ID_Regra"],),
                    )
                    if not current["Ativa"] or current["Versao"] != r["Versao"]:
                        break
                    key = event[:180]
                    if await fetch_one(
                        "SELECT ID_Execucao FROM Automacao_Execucoes WHERE ID_Regra=%s AND EventoChave=%s",
                        (r["ID_Regra"], key),
                    ):
                        continue
                    live = await fetch_one(
                        "SELECT c.Ativo,card.Estado FROM Candidaturas c JOIN ATS_Cards card ON card.ID_Candidaturas=c.ID_Candidaturas WHERE c.ID_Candidaturas=%s FOR UPDATE",
                        (row["ID_Candidaturas"],),
                    )
                    if not live or not live["Ativo"] or live["Estado"] != "ativo":
                        continue
                    uid = (
                        row["CandidatoUsuario"]
                        if cond["destino"] == "candidato"
                        else row["Owner"]
                    )
                    xid = novo_uuid()
                    state = "concluido"
                    if r["Acao"] == "tarefa":
                        await execute(
                            "INSERT INTO Tarefas(ID_Tarefa,ID_Empresas,ID_Candidaturas,ID_Responsavel,Titulo) VALUES (%s,%s,%s,%s,%s)",
                            (
                                novo_uuid(),
                                r["ID_Empresas"],
                                row["ID_Candidaturas"],
                                row["Owner"],
                                r["Conteudo"],
                            ),
                        )
                    elif r["Acao"] == "email":
                        ok = await enfileirar_email(
                            uid,
                            "Atualização do processo",
                            r["Conteudo"],
                            "automacao:" + xid,
                        )
                        if not ok:
                            state = "ignorado"
                    else:
                        await execute(
                            "INSERT INTO Notificacoes(ID_Notificacoes,ID_Usuarios,Titulo,Mensagem,Tipo) VALUES (%s,%s,%s,%s,%s)",
                            (novo_uuid(), uid, r["Nome"], r["Conteudo"], "automacao"),
                        )
                    await execute(
                        "INSERT INTO Automacao_Execucoes(ID_Execucao,ID_Regra,EventoChave,Estado) VALUES (%s,%s,%s,%s)",
                        (xid, r["ID_Regra"], key, state),
                    )


async def lembretes():
    rows = await fetch_all(
        """SELECT en.ID_Entrevistas,en.DataHora,d.Versao,d.Fuso,r.ID_Usuarios AS RH,ca.ID_Usuarios AS CandidatoUsuario
        FROM Entrevistas en JOIN Candidaturas c ON c.ID_Candidaturas=en.ID_Candidaturas AND c.Ativo=1
        JOIN Candidatos ca ON ca.ID_Candidatos=c.ID_Candidatos AND ca.Ativo=1
        JOIN Recrutadores r ON r.ID_Recrutadores=en.ID_Recrutadores AND r.Ativo=1
        LEFT JOIN Agenda_Detalhes d ON d.ID_Entrevistas=en.ID_Entrevistas
        WHERE en.ID_Status_Entrevista IN (1,3) AND en.DataHora>=%s AND en.DataHora<=%s LIMIT 1000""",
        (utcnow() - timedelta(hours=14), utcnow() + timedelta(hours=38)),
    )
    for row in rows:
        remaining = (
            horario_utc(row["DataHora"], "UTC" if row["Fuso"] else "America/Sao_Paulo")
            - utcnow()
        ).total_seconds() / 60
        # Do not send the 24h reminder late after the 1h window has started.
        for minutes in (1440, 60):
            if not (0 < remaining <= minutes) or (minutes == 1440 and remaining <= 60):
                continue
            for uid in set((row["RH"], row["CandidatoUsuario"])):
                async with transaction():
                    live = await fetch_one(
                        "SELECT ID_Status_Entrevista,DataHora FROM Entrevistas WHERE ID_Entrevistas=%s FOR UPDATE",
                        (row["ID_Entrevistas"],),
                    )
                    if (
                        live["ID_Status_Entrevista"] not in (1, 3)
                        or live["DataHora"] != row["DataHora"]
                    ):
                        continue
                    params = (row["ID_Entrevistas"], row["Versao"] or 1, uid, minutes)
                    if await fetch_one(
                        "SELECT ID_Entrevistas FROM Agenda_Lembretes WHERE ID_Entrevistas=%s AND Versao=%s AND ID_Usuarios=%s AND AntecedenciaMin=%s",
                        params,
                    ):
                        continue
                    await execute(
                        "INSERT INTO Agenda_Lembretes(ID_Entrevistas,Versao,ID_Usuarios,AntecedenciaMin) VALUES (%s,%s,%s,%s)",
                        params,
                    )
                    text = "Sua entrevista está próxima. Confira data, fuso e local na agenda."
                    await execute(
                        "INSERT INTO Notificacoes(ID_Notificacoes,ID_Usuarios,Titulo,Mensagem,Tipo) VALUES (%s,%s,%s,%s,%s)",
                        (
                            novo_uuid(),
                            uid,
                            "Lembrete de entrevista",
                            text,
                            "entrevista",
                        ),
                    )
                    await enfileirar_email(
                        uid,
                        "Lembrete de entrevista",
                        text,
                        f"lembrete:{row['ID_Entrevistas']}:{row['Versao'] or 1}:{uid}:{minutes}",
                    )


async def entregar_email():
    if not settings.SMTP_ENABLED:
        return False
    async with transaction():
        row = await fetch_one(
            """SELECT * FROM Outbox_Email WHERE Estado IN ('pendente','processando') AND Tentativas<5 AND ProximaEm<=NOW() ORDER BY ProximaEm LIMIT 1 FOR UPDATE SKIP LOCKED"""
        )
        if not row:
            return False
        attempt = row["Tentativas"] + 1
        await execute(
            "UPDATE Outbox_Email SET Estado='processando',Tentativas=%s,ProximaEm=%s WHERE ID_Email=%s",
            (attempt, utcnow() + timedelta(seconds=90), row["ID_Email"]),
        )
    u = await fetch_one(
        """SELECT u.Email,u.EmailConfirmadoEm,p.EmailAtivo FROM Usuarios u LEFT JOIN Preferencias_Notificacao p ON p.ID_Usuarios=u.ID_Usuarios WHERE u.ID_Usuarios=%s AND u.Ativo=1""",
        (row["ID_Usuarios"],),
    )
    if not u or not u["EmailConfirmadoEm"] or not u["EmailAtivo"]:
        state = "ignorado"
    else:
        ok = await asyncio.to_thread(
            enviar_email, u["Email"], row["Assunto"], corpo_email(row["Corpo"])
        )
        state = "enviado" if ok else ("falhou" if attempt >= 5 else "pendente")
    await execute(
        "UPDATE Outbox_Email SET Estado=%s,ProximaEm=%s WHERE ID_Email=%s AND Tentativas=%s AND Estado=%s",
        (
            state,
            utcnow() + timedelta(seconds=min(3600, 30 * 2**attempt)),
            row["ID_Email"],
            attempt,
            "processando",
        ),
    )
    return True


async def executar_ciclo():
    await regras()
    await lembretes()
    for _ in range(20):
        if not await entregar_email():
            break
    from app.core.privacy import processar_solicitacoes, retencao

    await processar_solicitacoes()
    await retencao()
    from app.core.push_delivery import processar_push

    await processar_push()


async def main(once=False):
    await init_pool()
    try:
        while True:
            try:
                await executar_ciclo()
            except Exception:
                if once:
                    raise
                logger.exception("Falha no ciclo da plataforma; será retomado.")
            if once:
                break
            await asyncio.sleep(30)
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    asyncio.run(main(parser.parse_args().once))
