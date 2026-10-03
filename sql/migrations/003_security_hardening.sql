-- ============================================================================
-- 003_security_hardening.sql
-- Talentix / MySQL 8
--
-- MySQL 8 não oferece Row-Level Security nativa como PostgreSQL.
-- O isolamento por linha é aplicado na API via owner/role checks (app/core/access.py
-- e deps.py). Esta migration complementa a proteção com menor privilégio no banco.
-- Execute com uma conta DBA.
-- ============================================================================

USE talentix;

CREATE ROLE IF NOT EXISTS 'talentix_app_role';
GRANT SELECT, INSERT, UPDATE, DELETE ON talentix.* TO 'talentix_app_role';

CREATE ROLE IF NOT EXISTS 'talentix_auditor_role';
GRANT SELECT ON talentix.* TO 'talentix_auditor_role';

-- Crie o usuário operacional fora do Git, usando segredo vindo de vault/.env:
-- CREATE USER IF NOT EXISTS 'talentix_app'@'10.%' IDENTIFIED BY '<SECRET_FROM_VAULT>';
-- GRANT 'talentix_app_role' TO 'talentix_app'@'10.%';
-- SET DEFAULT ROLE 'talentix_app_role' TO 'talentix_app'@'10.%';

-- Garante o administrador fundador se a conta já existir.
INSERT INTO Administradores (
    ID_Administradores,
    ID_Usuarios,
    NivelAcesso,
    Ativo
)
SELECT UUID(), u.ID_Usuarios, 'superadmin', TRUE
FROM Usuarios u
WHERE LOWER(u.Email) = LOWER('arthurhpb7@gmail.com')
  AND u.Ativo = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM Administradores a
      WHERE a.ID_Usuarios = u.ID_Usuarios
  );

-- O frontend nunca deve se conectar diretamente ao MySQL.
-- Fluxo suportado: navegador -> FastAPI -> MySQL.
