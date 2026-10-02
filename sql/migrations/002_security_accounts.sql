-- Update 2 — Segurança e contas 2.0
ALTER TABLE Usuarios
  ADD COLUMN EmailConfirmadoEm DATETIME NULL AFTER Email,
  ADD COLUMN TentativasLogin SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER SenhaHash,
  ADD COLUMN BloqueadoAte DATETIME NULL AFTER TentativasLogin,
  ADD COLUMN UltimoLoginEm DATETIME NULL AFTER BloqueadoAte,
  ADD COLUMN TwoFactorAtivo BOOLEAN NOT NULL DEFAULT FALSE AFTER UltimoLoginEm,
  ADD COLUMN TwoFactorSecretEnc TEXT NULL AFTER TwoFactorAtivo;

UPDATE Usuarios SET EmailConfirmadoEm=COALESCE(EmailConfirmadoEm, CriadoEm);

CREATE TABLE Sessoes (
  ID_Sessoes CHAR(36) NOT NULL,
  ID_Usuarios CHAR(36) NOT NULL,
  UserAgent VARCHAR(500) NULL,
  CriadaEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UltimaAtividadeEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ExpiraEm DATETIME NOT NULL,
  RevogadaEm DATETIME NULL,
  PRIMARY KEY (ID_Sessoes),
  KEY IX_Sessoes_Usuario (ID_Usuarios, RevogadaEm),
  CONSTRAINT FK_Sessoes_Usuarios FOREIGN KEY (ID_Usuarios)
    REFERENCES Usuarios(ID_Usuarios) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Audit_Logs (
  ID_Audit_Logs CHAR(36) NOT NULL,
  ID_Usuarios CHAR(36) NULL,
  Acao VARCHAR(100) NOT NULL,
  Recurso VARCHAR(100) NOT NULL,
  RecursoId VARCHAR(100) NULL,
  RequestId VARCHAR(64) NULL,
  UserAgent VARCHAR(500) NULL,
  ValorAnterior JSON NULL,
  ValorNovo JSON NULL,
  CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (ID_Audit_Logs),
  KEY IX_Audit_Logs_Usuario (ID_Usuarios),
  KEY IX_Audit_Logs_Recurso (Recurso, RecursoId),
  KEY IX_Audit_Logs_CriadoEm (CriadoEm),
  CONSTRAINT FK_Audit_Logs_Usuarios FOREIGN KEY (ID_Usuarios)
    REFERENCES Usuarios(ID_Usuarios) ON DELETE SET NULL
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
