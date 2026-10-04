-- Segurança por registro: autorização na API (MySQL não possui RLS nativa).
-- O bootstrap cria uma conta de runtime limitada a DML, separada do migrador.
-- Contas existentes: o DBA aplica sql/operations/runtime_privileges.sql.
-- Administradores são criados explicitamente por create_admin.py ou pelo seed demo.
-- Não promover automaticamente uma conta com base apenas no endereço de e-mail.
SELECT 1;
