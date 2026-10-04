"""Tipos de entrada compatíveis com limites e regras de persistência."""
from decimal import Decimal
from typing import Annotated
from urllib.parse import urlsplit
from pydantic import AfterValidator, Field


def password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("A senha deve ter no máximo 72 bytes em UTF-8.")
    return value


Password = Annotated[str, Field(min_length=10, max_length=72), AfterValidator(password_bytes)]
Money = Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


def safe_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in value):
        raise ValueError("Informe uma URL http(s) válida, sem credenciais.")
    return value


def normalize_state(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip().upper()
    states = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
              "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}
    if value not in states:
        raise ValueError("Informe uma UF brasileira com duas letras.")
    return value
