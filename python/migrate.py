"""Atualização incremental, idempotente e sem apagar registros de negócio."""
from pathlib import Path

import pymysql

from app.core.config import settings


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        (settings.DB_NAME, table, column),
    )
    return bool(cur.fetchone())


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
        (settings.DB_NAME, table),
    )
    return bool(cur.fetchone())


def _apply_001(cur) -> bool:
    cur.execute("SELECT Versao FROM Schema_Migrations WHERE Versao='001_estabilizacao'")
    if cur.fetchone():
        return False
    indexes = [
        ("Pagamentos", "UQ_Pagamentos_TransacaoId", "TransacaoId"),
        ("Avaliacoes", "UQ_Avaliacoes_Avaliador_Candidatura", "ID_Avaliador, ID_Candidaturas"),
    ]
    for table, name, columns in indexes:
        cur.execute(
            "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s",
            (settings.DB_NAME, table, name),
        )
        if not cur.fetchone():
            cur.execute(f"ALTER TABLE {table} ADD UNIQUE KEY {name} ({columns})")
    if not _column_exists(cur, "Assinaturas", "EmpresaAtiva"):
        cur.execute("""ALTER TABLE Assinaturas ADD EmpresaAtiva CHAR(36) GENERATED ALWAYS AS
                   (CASE WHEN ID_Status_Assinatura=1 THEN ID_Empresas ELSE NULL END) VIRTUAL""")
    cur.execute(
        "SELECT 1 FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='Assinaturas' AND INDEX_NAME='UQ_Assinaturas_EmpresaAtiva'",
        (settings.DB_NAME,),
    )
    if not cur.fetchone():
        cur.execute("ALTER TABLE Assinaturas ADD UNIQUE KEY UQ_Assinaturas_EmpresaAtiva (EmpresaAtiva)")
    for table in ("Analises_IA", "Recomendacoes_Vaga"):
        for column, definition in (("ProcessamentoIniciadoEm", "DATETIME NULL"), ("ErroProcessamento", "TEXT NULL")):
            if not _column_exists(cur, table, column):
                cur.execute(f"ALTER TABLE {table} ADD {column} {definition}")
    cur.execute((Path(__file__).resolve().parents[1] / "sql/migrations/001_contatos.sql").read_text(encoding="utf-8"))
    cur.execute("UPDATE Pagamentos SET PagoEm=NULL WHERE ID_Status_Pagamento=3")
    cur.execute("INSERT INTO Schema_Migrations(Versao) VALUES ('001_estabilizacao')")
    return True


def _apply_002(cur) -> bool:
    cur.execute("SELECT Versao FROM Schema_Migrations WHERE Versao='002_security_accounts'")
    if cur.fetchone():
        return False

    columns = (
        ("EmailConfirmadoEm", "DATETIME NULL"),
        ("TentativasLogin", "SMALLINT UNSIGNED NOT NULL DEFAULT 0"),
        ("BloqueadoAte", "DATETIME NULL"),
        ("UltimoLoginEm", "DATETIME NULL"),
        ("TwoFactorAtivo", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("TwoFactorSecretEnc", "TEXT NULL"),
    )
    for name, definition in columns:
        if not _column_exists(cur, "Usuarios", name):
            cur.execute(f"ALTER TABLE Usuarios ADD {name} {definition}")
    cur.execute("UPDATE Usuarios SET EmailConfirmadoEm=COALESCE(EmailConfirmadoEm, CriadoEm)")

    if not _table_exists(cur, "Sessoes"):
        cur.execute("""CREATE TABLE Sessoes (
            ID_Sessoes CHAR(36) PRIMARY KEY,
            ID_Usuarios CHAR(36) NOT NULL,
            UserAgent VARCHAR(500) NULL,
            CriadaEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UltimaAtividadeEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ExpiraEm DATETIME NOT NULL,
            RevogadaEm DATETIME NULL,
            KEY IX_Sessoes_Usuario (ID_Usuarios, RevogadaEm),
            CONSTRAINT FK_Sessoes_Usuarios FOREIGN KEY (ID_Usuarios)
              REFERENCES Usuarios(ID_Usuarios) ON DELETE CASCADE
        ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci""")
    if not _table_exists(cur, "Audit_Logs"):
        cur.execute("""CREATE TABLE Audit_Logs (
            ID_Audit_Logs CHAR(36) PRIMARY KEY,
            ID_Usuarios CHAR(36) NULL,
            Acao VARCHAR(100) NOT NULL,
            Recurso VARCHAR(100) NOT NULL,
            RecursoId VARCHAR(100) NULL,
            RequestId VARCHAR(64) NULL,
            UserAgent VARCHAR(500) NULL,
            ValorAnterior JSON NULL,
            ValorNovo JSON NULL,
            CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            KEY IX_Audit_Logs_Usuario (ID_Usuarios),
            KEY IX_Audit_Logs_Recurso (Recurso, RecursoId),
            KEY IX_Audit_Logs_CriadoEm (CriadoEm),
            CONSTRAINT FK_Audit_Logs_Usuarios FOREIGN KEY (ID_Usuarios)
              REFERENCES Usuarios(ID_Usuarios) ON DELETE SET NULL
        ) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci""")
    cur.execute("INSERT INTO Schema_Migrations(Versao) VALUES ('002_security_accounts')")
    return True


def migrate(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK('talentix_schema_migration', 10)")
        if cur.fetchone()[0] != 1:
            raise RuntimeError("Outra migração está em andamento.")
        changed = False
        try:
            checks = [
                ("Pagamentos", "SELECT TransacaoId FROM Pagamentos WHERE TransacaoId IS NOT NULL GROUP BY TransacaoId HAVING COUNT(*)>1"),
                ("Avaliacoes", "SELECT ID_Avaliador FROM Avaliacoes GROUP BY ID_Avaliador, ID_Candidaturas HAVING COUNT(*)>1"),
                ("Assinaturas", "SELECT ID_Empresas FROM Assinaturas WHERE ID_Status_Assinatura=1 GROUP BY ID_Empresas HAVING COUNT(*)>1"),
            ]
            for table, query in checks:
                cur.execute(query)
                if cur.fetchone():
                    raise RuntimeError(f"Revisar duplicidades em {table} antes de migrar. Nenhum registro será apagado automaticamente.")
            cur.execute("""CREATE TABLE IF NOT EXISTS Schema_Migrations
                       (Versao VARCHAR(100) PRIMARY KEY, AplicadaEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)
                       ENGINE=InnoDB""")
            changed |= _apply_001(cur)
            changed |= _apply_002(cur)
            return changed
        finally:
            cur.execute("SELECT RELEASE_LOCK('talentix_schema_migration')")


def main():
    conn = pymysql.connect(
        host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER,
        password=settings.DB_PASSWORD, database=settings.DB_NAME,
        charset="utf8mb4", autocommit=True,
    )
    try:
        changed = migrate(conn)
        print("Migrações aplicadas com dados preservados." if changed else "Banco já atualizado.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
