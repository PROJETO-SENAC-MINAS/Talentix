"""Atualização incremental, idempotente e sem apagar registros de negócio."""
from pathlib import Path
import pymysql
from app.core.config import settings


def migrate(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK('talentix_schema_migration', 10)")
        if cur.fetchone()[0] != 1:
            raise RuntimeError("Outra migração está em andamento.")
        try:
            checks = [
                ("Pagamentos", "SELECT TransacaoId FROM Pagamentos WHERE TransacaoId IS NOT NULL GROUP BY TransacaoId HAVING COUNT(*)>1"),
                ("Avaliacoes", "SELECT ID_Avaliador FROM Avaliacoes GROUP BY ID_Avaliador, ID_Candidaturas HAVING COUNT(*)>1"),
                ("Assinaturas", "SELECT ID_Empresas FROM Assinaturas WHERE ID_Status_Assinatura=1 GROUP BY ID_Empresas HAVING COUNT(*)>1"),
            ]
            # Conferir TODOS os conflitos antes de executar DDL (MySQL confirma DDL).
            for table, query in checks:
                cur.execute(query)
                if cur.fetchone():
                    raise RuntimeError(f"Revisar duplicidades em {table} antes de migrar. Nenhum registro será apagado automaticamente.")
            cur.execute("""CREATE TABLE IF NOT EXISTS Schema_Migrations
                       (Versao VARCHAR(100) PRIMARY KEY, AplicadaEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)
                       ENGINE=InnoDB""")
            cur.execute("SELECT Versao FROM Schema_Migrations WHERE Versao='001_estabilizacao'")
            if cur.fetchone():
                return False
            indexes = [
                ("Pagamentos", "UQ_Pagamentos_TransacaoId", "TransacaoId"),
                ("Avaliacoes", "UQ_Avaliacoes_Avaliador_Candidatura", "ID_Avaliador, ID_Candidaturas"),
            ]
            for table, name, columns in indexes:
                cur.execute("SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s", (settings.DB_NAME, table, name))
                if not cur.fetchone():
                    cur.execute(f"ALTER TABLE {table} ADD UNIQUE KEY {name} ({columns})")
            cur.execute("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='Assinaturas' AND COLUMN_NAME='EmpresaAtiva'", (settings.DB_NAME,))
            if not cur.fetchone():
                cur.execute("""ALTER TABLE Assinaturas ADD EmpresaAtiva CHAR(36) GENERATED ALWAYS AS
                           (CASE WHEN ID_Status_Assinatura=1 THEN ID_Empresas ELSE NULL END) VIRTUAL""")
            cur.execute("SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='Assinaturas' AND INDEX_NAME='UQ_Assinaturas_EmpresaAtiva'", (settings.DB_NAME,))
            if not cur.fetchone():
                cur.execute("ALTER TABLE Assinaturas ADD UNIQUE KEY UQ_Assinaturas_EmpresaAtiva (EmpresaAtiva)")
            for table in ("Analises_IA", "Recomendacoes_Vaga"):
                for column, definition in (("ProcessamentoIniciadoEm", "DATETIME NULL"), ("ErroProcessamento", "TEXT NULL")):
                    cur.execute("SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s", (settings.DB_NAME, table, column))
                    if not cur.fetchone():
                        cur.execute(f"ALTER TABLE {table} ADD {column} {definition}")
            sql = Path(__file__).resolve().parents[1] / "sql/migrations/001_contatos.sql"
            cur.execute(sql.read_text(encoding="utf-8"))
            cur.execute("UPDATE Pagamentos SET PagoEm=NULL WHERE ID_Status_Pagamento=3")
            cur.execute("INSERT INTO Schema_Migrations(Versao) VALUES ('001_estabilizacao')")
            return True
        finally:
            cur.execute("SELECT RELEASE_LOCK('talentix_schema_migration')")


def main():
    conn = pymysql.connect(host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
                           password=settings.DB_PASSWORD, database=settings.DB_NAME,
                           charset="utf8mb4", autocommit=True)
    try:
        changed = migrate(conn)
        print("Migração aplicada com dados preservados." if changed else "Banco já atualizado.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
