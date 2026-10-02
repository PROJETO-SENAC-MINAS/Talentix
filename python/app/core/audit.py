"""Auditoria persistente de ações sensíveis."""
import json

from fastapi import Request

from app.core.security import novo_uuid
from app.db.database import execute


async def registrar_auditoria(
    request: Request | None,
    acao: str,
    recurso: str,
    id_usuario: str | None = None,
    recurso_id: str | None = None,
    anterior=None,
    novo=None,
) -> None:
    request_id = getattr(getattr(request, "state", None), "request_id", None) if request else None
    user_agent = request.headers.get("user-agent", "")[:500] if request else None
    await execute(
        """INSERT INTO Audit_Logs
           (ID_Audit_Logs, ID_Usuarios, Acao, Recurso, RecursoId, RequestId, UserAgent, ValorAnterior, ValorNovo)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            novo_uuid(), id_usuario, acao[:100], recurso[:100], recurso_id,
            request_id, user_agent,
            json.dumps(anterior, ensure_ascii=False, default=str) if anterior is not None else None,
            json.dumps(novo, ensure_ascii=False, default=str) if novo is not None else None,
        ),
    )
