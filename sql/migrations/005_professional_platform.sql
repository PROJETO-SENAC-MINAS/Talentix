-- Novembro: alterações aditivas. Nenhum currículo/perfil existente é apagado.
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Candidatos' AND COLUMN_NAME='Modalidades')=0,
 'ALTER TABLE Candidatos ADD Modalidades JSON NULL, ADD TiposContrato JSON NULL, ADD Preferencias TEXT NULL, ADD HabilidadesComportamentais JSON NULL', 'SELECT 1');
PREPARE migration_stmt FROM @sql; EXECUTE migration_stmt; DEALLOCATE PREPARE migration_stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Vagas' AND COLUMN_NAME='AreaProfissional')=0,
 'ALTER TABLE Vagas ADD AreaProfissional VARCHAR(100) NULL, ADD INDEX IX_Vagas_Busca (Ativo, ID_Status_Vaga, PublicadaEm)', 'SELECT 1');
PREPARE migration_stmt FROM @sql; EXECUTE migration_stmt; DEALLOCATE PREPARE migration_stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Curriculos' AND COLUMN_NAME='Versao')=0,
 'ALTER TABLE Curriculos ADD Versao INT UNSIGNED NOT NULL DEFAULT 0, ADD Origem VARCHAR(30) NOT NULL DEFAULT ''upload''', 'SELECT 1');
PREPARE migration_stmt FROM @sql; EXECUTE migration_stmt; DEALLOCATE PREPARE migration_stmt;
UPDATE Curriculos c JOIN (SELECT ID_Curriculos,ROW_NUMBER() OVER (PARTITION BY ID_Candidatos ORDER BY CriadoEm,ID_Curriculos) AS Numero FROM Curriculos) numbered
 ON numbered.ID_Curriculos=c.ID_Curriculos SET c.Versao=numbered.Numero WHERE c.Versao=0;
ALTER TABLE Curriculos ALTER COLUMN Versao SET DEFAULT 1;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Curriculos' AND INDEX_NAME='UQ_Curriculos_Versao')=0,
 'ALTER TABLE Curriculos ADD UNIQUE KEY UQ_Curriculos_Versao (ID_Candidatos,Versao)', 'SELECT 1');
PREPARE migration_stmt FROM @sql; EXECUTE migration_stmt; DEALLOCATE PREPARE migration_stmt;
SET @sql = IF((SELECT COUNT(*) FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='Curriculo_Importacoes' AND COLUMN_NAME='TextoExtraido')=0,
 'ALTER TABLE Curriculo_Importacoes ADD TextoExtraido MEDIUMTEXT NULL, ADD DadosConfirmados JSON NULL', 'SELECT 1');
PREPARE migration_stmt FROM @sql; EXECUTE migration_stmt; DEALLOCATE PREPARE migration_stmt;

CREATE TABLE IF NOT EXISTS Candidato_Itens (
 ID_Item CHAR(36) PRIMARY KEY, ID_Candidatos CHAR(36) NOT NULL,
 Tipo VARCHAR(20) NOT NULL, Titulo VARCHAR(200) NOT NULL, Instituicao VARCHAR(200) NULL,
 Descricao TEXT NULL, Url VARCHAR(300) NULL, DataInicio DATE NULL, DataFim DATE NULL,
 CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (ID_Candidatos) REFERENCES Candidatos(ID_Candidatos) ON DELETE CASCADE,
 KEY IX_Itens_Candidato (ID_Candidatos, Tipo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS Buscas_Salvas (
 ID_Busca CHAR(36) PRIMARY KEY, ID_Usuarios CHAR(36) NOT NULL,
 Nome VARCHAR(100) NOT NULL, Filtros JSON NOT NULL, Ativa BOOLEAN NOT NULL DEFAULT FALSE,
 CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (ID_Usuarios) REFERENCES Usuarios(ID_Usuarios) ON DELETE CASCADE,
 KEY IX_Buscas_Usuario (ID_Usuarios, Ativa)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS Historico_Buscas (
 ID_Historico CHAR(36) PRIMARY KEY, ID_Usuarios CHAR(36) NOT NULL, Filtros JSON NOT NULL,
 CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (ID_Usuarios) REFERENCES Usuarios(ID_Usuarios) ON DELETE CASCADE,
 KEY IX_Historico_Usuario (ID_Usuarios, CriadoEm)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS Alertas_Busca (
 ID_Busca CHAR(36) NOT NULL, ID_Vagas CHAR(36) NOT NULL,
 CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY (ID_Busca, ID_Vagas),
 FOREIGN KEY (ID_Busca) REFERENCES Buscas_Salvas(ID_Busca) ON DELETE CASCADE,
 FOREIGN KEY (ID_Vagas) REFERENCES Vagas(ID_Vagas) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
