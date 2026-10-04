"""Instala o SQL apenas no banco descartável e vazio do CI."""
import os
import sys
from pathlib import Path
import pymysql
from pymysql.constants import CLIENT

assert os.getenv("CI") == "true" and os.getenv("TALENTIX_ISOLATED_TESTS") == "1"
name=os.environ["DB_NAME"]
assert name.startswith("talentix_test") and os.environ["DB_HOST"]=="127.0.0.1"
conn=pymysql.connect(host=os.environ["DB_HOST"],port=int(os.environ["DB_PORT"]),user="root",
                     password=os.environ["TEST_ROOT_PASSWORD"],autocommit=True,client_flag=CLIENT.MULTI_STATEMENTS)
try:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s",(name,))
        if cur.fetchone()[0]:raise SystemExit("Banco de testes deve estar vazio; nenhum dado será apagado.")
        sql=Path(__file__).resolve().parents[3]/"sql/talentix_db.sql"
        cur.execute(sql.read_text().replace("talentix",name))
        while cur.nextset():pass
    print("SQL instalado no MySQL descartável do CI.")
finally:conn.close()

# Exercise the same runner used outside CI, including migrations 003 and 004.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import settings
from migrate import migrate
conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT,
    user=settings.DB_USER, password=settings.DB_PASSWORD, database=settings.DB_NAME,
    autocommit=True, client_flag=CLIENT.MULTI_STATEMENTS)
try:
    assert migrate(conn) is True
    assert migrate(conn) is False
finally:
    conn.close()
