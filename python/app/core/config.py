"""
Configurações centrais da aplicação.
Os valores vêm do ambiente e, no desenvolvimento local, de python/.env.
"""
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    API_DOCS_ENABLED: bool = True

    FRONTEND_RESET_URL: str = "http://127.0.0.1:5500/html/login.html"

    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = Field(default="", repr=False)
    DB_NAME: str = "talentix"

    SECRET_KEY: str = Field(min_length=64, repr=False)
    SESSION_COOKIE_NAME: str = "talentix_session"
    SESSION_MAX_AGE_SECONDS: int = 86400
    SESSION_COOKIE_SECURE: bool = True

    IA_WORKER_TOKEN: str = Field(default="", repr=False)
    PAYMENT_WEBHOOK_TOKEN: str = Field(default="", repr=False)

    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    FRONTEND_ORIGIN: str = "http://localhost:3000"

    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = Field(default="", repr=False)
    SMTP_FROM_EMAIL: str = "no-reply@talentix.com"

    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_SECONDS: int = 900
    RATE_LIMIT_REQUESTS: int = 120
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    EMAIL_CONFIRMATION_REQUIRED: bool = False

    @field_validator("SECRET_KEY", "IA_WORKER_TOKEN", "PAYMENT_WEBHOOK_TOKEN")
    @classmethod
    def validar_chave(cls, valor: str, info) -> str:
        if not valor and info.field_name != "SECRET_KEY":
            return valor
        if len(valor) < 64 or not valor.isascii() or any(c.isspace() for c in valor):
            raise ValueError("Gere uma chave exclusiva com secrets.token_hex(32).")
        if any(marcador in valor.lower() for marcador in ("change-me", "changeme", "substitua", "your-secret")):
            raise ValueError("Chaves de exemplo não podem ser usadas.")
        return valor

    @field_validator("LOG_LEVEL")
    @classmethod
    def validar_log_level(cls, valor: str) -> str:
        valor = valor.upper()
        if valor not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL inválido.")
        return valor

    @model_validator(mode="after")
    def validar_producao(self):
        if self.APP_ENV == "production" and not self.SESSION_COOKIE_SECURE:
            raise ValueError("SESSION_COOKIE_SECURE deve ser true em produção.")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
        extra="ignore",
    )


settings = Settings()
