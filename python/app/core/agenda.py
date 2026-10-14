"""Fusos e exclusão de sobreposição, compartilhados pelas APIs nova e legada."""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import HTTPException
from app.db.database import fetch_one, fetch_all


def horario_utc(value, fuso="America/Sao_Paulo"):
    try:
        zone = ZoneInfo(fuso)
        dt = (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            if isinstance(value, str)
            else value
        )
        if dt.tzinfo is None:
            if (
                dt.replace(tzinfo=zone, fold=0).utcoffset()
                != dt.replace(tzinfo=zone, fold=1).utcoffset()
            ):
                raise ValueError(
                    "Horário ambíguo em mudança de fuso; informe o offset."
                )
            dt = dt.replace(tzinfo=zone)
            if dt.astimezone(timezone.utc).astimezone(zone).replace(
                tzinfo=None
            ) != dt.replace(tzinfo=None):
                raise ValueError("Horário inexistente neste fuso.")
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, AttributeError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(
            422, "Data ou fuso inválido. Informe um horário inequívoco."
        ) from exc


async def validar_conflito(candidatura, recrutador, inicio, duracao=30, ignorar=None):
    # Locks persistem na transação HTTP: também serializam candidato em empresas distintas.
    await fetch_one(
        "SELECT ID_Candidatos FROM Candidatos WHERE ID_Candidatos=%s FOR UPDATE",
        (candidatura["ID_Candidatos"],),
    )
    await fetch_one(
        "SELECT ID_Recrutadores FROM Recrutadores WHERE ID_Recrutadores=%s FOR UPDATE",
        (recrutador,),
    )
    rows = await fetch_all(
        """SELECT e.ID_Entrevistas,e.DataHora,d.DuracaoMin,d.Fuso FROM Entrevistas e
        JOIN Candidaturas c ON c.ID_Candidaturas=e.ID_Candidaturas
        LEFT JOIN Agenda_Detalhes d ON d.ID_Entrevistas=e.ID_Entrevistas
        WHERE e.ID_Status_Entrevista IN (1,3) AND (e.ID_Recrutadores=%s OR c.ID_Candidatos=%s)
        AND e.DataHora>=%s AND e.DataHora<=%s FOR UPDATE""",
        (
            recrutador,
            candidatura["ID_Candidatos"],
            inicio - timedelta(hours=28),
            inicio + timedelta(hours=28),
        ),
    )
    for row in rows:
        if row["ID_Entrevistas"] == ignorar:
            continue
        start = horario_utc(
            row["DataHora"], "UTC" if row["Fuso"] else "America/Sao_Paulo"
        )
        if inicio < start + timedelta(
            minutes=row["DuracaoMin"] or 30
        ) and start < inicio + timedelta(minutes=duracao):
            raise HTTPException(
                409, "Há conflito de horário para o candidato ou recrutador."
            )


async def projetar_entrevistas(rows):
    """APIs legadas mantêm horário local legível e acrescentam fuso/UTC explícitos."""
    if not rows:
        return rows
    marks = ",".join(["%s"] * len(rows))
    details = await fetch_all(
        "SELECT ID_Entrevistas,Fuso,DuracaoMin,Versao FROM Agenda_Detalhes WHERE ID_Entrevistas IN ("
        + marks
        + ")",
        tuple(r["ID_Entrevistas"] for r in rows),
    )
    lookup = {d["ID_Entrevistas"]: d for d in details}
    for row in rows:
        detail = lookup.get(row["ID_Entrevistas"])
        if not detail:
            continue
        utc = horario_utc(row["DataHora"], "UTC")
        row["DataHoraUtc"] = utc.isoformat() + "Z"
        row["DataHora"] = (
            utc.replace(tzinfo=timezone.utc)
            .astimezone(ZoneInfo(detail["Fuso"]))
            .isoformat()
        )
        row.update({k: detail[k] for k in ("Fuso", "DuracaoMin", "Versao")})
    return rows
