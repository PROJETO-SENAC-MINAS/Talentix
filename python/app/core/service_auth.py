"""Autenticação exclusiva para o worker de IA e o gateway de pagamentos."""
from secrets import compare_digest

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

_ia_header = APIKeyHeader(name="X-IA-Worker-Token", auto_error=False)
_pagamento_header = APIKeyHeader(name="X-Payment-Webhook-Token", auto_error=False)


def _validar_token(recebido: str | None, esperado: str) -> None:
    if not esperado:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Integração não configurada.")
    # Compare bytes para rejeitar também cabeçalhos com caracteres não ASCII.
    if not recebido or not compare_digest(recebido.encode("utf-8"), esperado.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credencial de serviço inválida.")


def exigir_worker_ia(token: str | None = Depends(_ia_header)) -> None:
    _validar_token(token, settings.IA_WORKER_TOKEN)


def exigir_gateway_pagamento(token: str | None = Depends(_pagamento_header)) -> None:
    _validar_token(token, settings.PAYMENT_WEBHOOK_TOKEN)
