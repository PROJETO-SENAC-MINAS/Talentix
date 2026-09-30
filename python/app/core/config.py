"""
Configurações centrais da aplicação, carregadas do arquivo .env
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):

    # URL do frontend, usada para montar o link de redefinição de senha no e-mail
    FRONTEND_RESET_URL: str = "http://127.0.0.1:5500/login.html"

    # Banco de dados
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = Field(default="", repr=False)
    DB_NAME: str = "talentix"

    # Sessão
    # Sem chave padrão: uma instalação deve gerar sua própria chave aleatória.
    # 64 caracteres também impedem reutilizar a chave exposta no repositório.
    SECRET_KEY: str = Field(min_length=64, repr=False)
    SESSION_COOKIE_NAME: str = "talentix_session"
    SESSION_MAX_AGE_SECONDS: int = 86400
    SESSION_COOKIE_SECURE: bool = True

    # Credenciais separadas para integrações servidor-servidor. Vazio desativa a rota.
    IA_WORKER_TOKEN: str = Field(default="", repr=False)
    PAYMENT_WEBHOOK_TOKEN: str = Field(default="", repr=False)

    # Upload
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # CORS
    FRONTEND_ORIGIN: str = "http://localhost:3000"

    # E-mail (SMTP genérico)
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = Field(default="", repr=False)
    SMTP_FROM_EMAIL: str = "no-reply@talentix.com"

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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", hide_input_in_errors=True)


settings = Settings()
