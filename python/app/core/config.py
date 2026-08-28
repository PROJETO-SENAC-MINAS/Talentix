"""
Configurações centrais da aplicação, carregadas do arquivo .env
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Banco de dados
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "talentix"

    # Sessão
    SECRET_KEY: str = "change-me"
    SESSION_COOKIE_NAME: str = "talentix_session"
    SESSION_MAX_AGE_SECONDS: int = 86400

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
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "no-reply@talentix.com"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()