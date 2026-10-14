"""Métricas com definições explícitas, escopo por empresa e exportações privadas."""

import csv
import io
import json
from collections import Counter, defaultdict
from datetime import datetime, date, time, timedelta
from html import escape
from statistics import mean
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from app.core.routes import AtomicRouter
from app.core.deps import usuario_atual, exigir_tipo
from app.core.audit import registrar_auditoria
from app.db.database import fetch_all
from app.routers.organizations import contexto_empresa

router = AtomicRouter(prefix="/analytics", tags=["Analytics"])


def dt(v):
    return datetime.fromisoformat(v) if isinstance(v, str) else v


def unpack(v):
    return json.loads(v) if isinstance(v, str) else v


def media(v):
    return round(mean(v), 2) if v else None


async def metricas(
    s, id_empresa=None, inicio=None, fim=None, id_vaga=None, responsavel=None
):
    e = await contexto_empresa(s, id_empresa, "analytics")
    query = """SELECT c.ID_Candidaturas,c.ID_Status_Candidatura,c.CriadaEm,card.ID_Responsavel,v.ID_Vagas
        FROM Candidaturas c JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas
        LEFT JOIN ATS_Cards card ON card.ID_Candidaturas=c.ID_Candidaturas WHERE v.ID_Empresas=%s"""
    params = [e["ID_Empresas"]]
    if inicio:
        query += " AND c.CriadaEm>=%s"
        params.append(datetime.combine(inicio, time.min))
    if fim:
        query += " AND c.CriadaEm<%s"
        params.append(datetime.combine(fim + timedelta(days=1), time.min))
    if inicio and fim and fim < inicio:
        raise HTTPException(422, "Período inválido.")
    if id_vaga:
        query += " AND v.ID_Vagas=%s"
        params.append(id_vaga)
    if responsavel:
        query += " AND card.ID_Responsavel=%s"
        params.append(responsavel)
    rows = await fetch_all(query + " ORDER BY c.CriadaEm LIMIT 10001", tuple(params))
    if len(rows) > 10000:
        raise HTTPException(422, "Reduza o período para até 10 mil candidaturas.")
    counts = Counter(r["ID_Status_Candidatura"] for r in rows)
    durations = defaultdict(list)
    stagepeople = defaultdict(set)
    hired = []
    grouped_events = defaultdict(list)
    if rows:
        # Only placeholder count is interpolated. IDs remain bound parameters.
        placeholders = ','.join(['%s'] * len(rows))
        history = await fetch_all(
            'SELECT ID_Candidaturas,Acao,Depois,CriadoEm FROM ATS_Eventos WHERE ID_Candidaturas IN ('+placeholders+
            ") AND Acao IN ('ats.entrada','ats.movimentacao','ats.status') ORDER BY ID_Candidaturas,Sequencia LIMIT 100001",
            tuple(r['ID_Candidaturas'] for r in rows),
        )
        if len(history)>100000:
            raise HTTPException(422,'Reduza o período: histórico excede 100 mil eventos.')
        for event in history:
            grouped_events[event['ID_Candidaturas']].append(event)
    for c in rows:
        events = grouped_events[c['ID_Candidaturas']]
        start = None
        stage = None
        hire = None
        for event in events:
            data = unpack(event["Depois"]) or {}
            current = data.get("NomeEtapa") or data.get("ID_Etapa") or data.get("etapa")
            stamp = dt(event["CriadoEm"])
            if current:
                stagepeople[current].add(c["ID_Candidaturas"])
                if stage and current != stage and start:
                    durations[stage].append(
                        max(0, (stamp - start).total_seconds() / 3600)
                    )
                if current != stage:
                    stage = current
                    start = stamp
            if data.get("Estado", data.get("estado")) == "aprovado" and hire is None:
                hire = stamp
        if c["ID_Status_Candidatura"] == 5 and hire:
            hired.append(max(0, (hire - dt(c["CriadaEm"])).total_seconds() / 86400))
    all_interviews = await fetch_all(
        """SELECT en.ID_Candidaturas,en.ID_Status_Entrevista FROM Entrevistas en
        JOIN Candidaturas c ON c.ID_Candidaturas=en.ID_Candidaturas JOIN Vagas v ON v.ID_Vagas=c.ID_Vagas WHERE v.ID_Empresas=%s""",
        (e["ID_Empresas"],),
    )
    selected = {r["ID_Candidaturas"] for r in rows}
    interviews = [r for r in all_interviews if r["ID_Candidaturas"] in selected]
    total = len(rows)
    return {
        "empresa": e.get("NomeFantasia") or e.get("RazaoSocial"),
        "total_candidaturas": total,
        "aprovadas": counts[5],
        "recusadas": counts[6],
        "desistencias": counts[7],
        "conversao_aprovacao_percentual": round(100 * counts[5] / total, 2)
        if total
        else 0,
        "taxa_desistencia_percentual": round(100 * counts[7] / total, 2)
        if total
        else 0,
        "entrevistas": len(interviews),
        "entrevistas_realizadas": sum(
            r["ID_Status_Entrevista"] == 2 for r in interviews
        ),
        "dias_ate_aprovacao_media": media(hired),
        "amostra_tempo_contratacao": len(hired),
        "etapas": [
            {
                "nome": name,
                "candidatos_que_passaram": len(people),
                "horas_media_finalizadas": media(durations[name]),
                "amostra_tempo": len(durations[name]),
            }
            for name, people in stagepeople.items()
        ],
        "definicoes": {
            "coorte": "Candidaturas criadas no período, inclusive encerradas; filtro de responsável usa o responsável atual do card.",
            "aprovacao": "Status aprovado no processo, sem inferir vínculo trabalhista ou admissão externa.",
            "etapas": "Pessoas distintas por etapa; retornos à etapa não duplicam pessoas. Tempo usa somente passagens finalizadas com histórico.",
            "tempo_contratacao": "Da candidatura ao primeiro evento de aprovação; só processos atualmente aprovados com histórico válido.",
            "origem_departamento": "Não coletados na base atual; não são estimados.",
        },
    }


@router.get("")
async def painel(
    id_empresa: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    id_vaga: str | None = None,
    responsavel: str | None = None,
    s=Depends(usuario_atual),
):
    return await metricas(s, id_empresa, inicio, fim, id_vaga, responsavel)


def safe_cell(value):
    text = str(value if value is not None else "")
    return (
        "'" + text
        if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else text
    )


@router.get("/exportar/{formato}")
async def exportar(
    formato: str,
    request: Request,
    id_empresa: str | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    id_vaga: str | None = None,
    responsavel: str | None = None,
    s=Depends(usuario_atual),
):
    data = await metricas(s, id_empresa, inicio, fim, id_vaga, responsavel)
    rows = [["Métrica", "Valor"]] + [
        [k, v] for k, v in data.items() if isinstance(v, (int, float)) or v is None
    ]
    rows += [["Etapa", "Pessoas", "Horas médias finalizadas"]] + [
        [r["nome"], r["candidatos_que_passaram"], r["horas_media_finalizadas"]]
        for r in data["etapas"]
    ]
    if formato == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows([[safe_cell(c) for c in r] for r in rows])
        content = ("\ufeff" + output.getvalue()).encode()
        mime = "text/csv; charset=utf-8"
    elif formato == "pdf":
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

        output = io.BytesIO()
        styles = getSampleStyleSheet()
        flow = [
            Paragraph("Talentix — Analytics", styles["Title"]),
            Paragraph(escape(data["empresa"] or ""), styles["Heading2"]),
            Spacer(1, 12),
        ]
        flow += [
            Paragraph(
                escape(
                    " | ".join(str(c if c is not None else "Sem amostra") for c in r)
                ),
                styles["BodyText"],
            )
            for r in rows
        ]
        flow += [Spacer(1, 12), Paragraph("Definições", styles["Heading2"])] + [
            Paragraph(escape(v), styles["BodyText"])
            for v in data["definicoes"].values()
        ]
        SimpleDocTemplate(output).build(flow)
        content = output.getvalue()
        mime = "application/pdf"
    else:
        raise HTTPException(404, "Formato indisponível.")
    await registrar_auditoria(
        request,
        "analytics.exportar",
        "Empresas",
        s["id_usuario"],
        id_empresa,
        novo={"formato": formato},
    )
    return Response(
        content,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="talentix-analytics.{formato}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/auditoria")
async def auditoria(s=Depends(exigir_tipo("administrador"))):
    return await fetch_all("""SELECT a.ID_Audit_Logs,a.ID_Usuarios,a.Acao,a.Recurso,a.RecursoId,a.CriadoEm,a.RequestId,c.IP
        FROM Audit_Logs a LEFT JOIN Audit_Contexto c ON c.ID_Audit_Logs=a.ID_Audit_Logs ORDER BY a.CriadoEm DESC LIMIT 200""")
