"""Bootstrap do Compose: migrations, conta restrita e seed opt-in antes da API."""
import os

import pymysql
from pymysql.constants import CLIENT

from app.core.config import settings
from migrate import migrate
from seed_demo import seed


def bootstrap():
    enabled = os.getenv("SEED_DEMO", "false").lower() == "true"
    password = os.getenv("DEMO_PASSWORD", "")
    if enabled and (settings.APP_ENV == "production" or len(password) < 12):
        raise RuntimeError("Seed requer ambiente não produtivo e DEMO_PASSWORD com 12+ caracteres.")
    runtime_password = os.environ["RUNTIME_DB_PASSWORD"]
    if not runtime_password:
        raise RuntimeError("Configure RUNTIME_DB_PASSWORD.")
    conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT,
                           user=settings.DB_USER, password=settings.DB_PASSWORD,
                           database=settings.DB_NAME, charset="utf8mb4", autocommit=True,
                           client_flag=CLIENT.MULTI_STATEMENTS)
    try:
        migrate(conn)
        with conn.cursor() as cur:
            # Fixed local Compose account; credentials are always bound parameters.
            cur.execute("CREATE USER IF NOT EXISTS 'talentix_app'@'%%' IDENTIFIED BY %s", (runtime_password,))
            cur.execute("ALTER USER 'talentix_app'@'%%' IDENTIFIED BY %s", (runtime_password,))
            cur.execute("REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'talentix_app'@'%'")
            database = settings.DB_NAME.replace("`", "``")
            cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON `{database}`.* TO 'talentix_app'@'%'")
    finally:
        conn.close()
    if enabled:
        seed(password)
    print("Bootstrap concluído: migrations aplicadas; seed " + ("aplicado." if enabled else "desativado."))


if __name__ == "__main__":
    bootstrap()
