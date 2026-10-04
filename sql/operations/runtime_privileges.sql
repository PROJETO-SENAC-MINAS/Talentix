-- Execute como DBA apenas depois de criar a conta talentix_app.
-- Adapte banco/host para sua instalação. Nunca execute com o usuário da API.
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'talentix_app'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON talentix.* TO 'talentix_app'@'%';
