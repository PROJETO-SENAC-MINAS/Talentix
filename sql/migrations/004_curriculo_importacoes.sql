-- Importação inteligente de currículos.
-- Mantém uma prévia estruturada separada dos dados oficiais do perfil.
CREATE TABLE IF NOT EXISTS Curriculo_Importacoes (
    ID_Curriculo_Importacoes CHAR(36) NOT NULL,
    ID_Curriculos CHAR(36) NOT NULL,
    ID_Status_Processamento_IA TINYINT UNSIGNED NOT NULL DEFAULT 1,
    DadosExtraidos JSON NULL,
    TextoCaracteres INT UNSIGNED NULL,
    ErroProcessamento VARCHAR(500) NULL,
    ProcessamentoIniciadoEm DATETIME NULL,
    ProcessadoEm DATETIME NULL,
    AplicadoEm DATETIME NULL,
    CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Curriculo_Importacoes),
    UNIQUE KEY UQ_Curriculo_Importacoes_Curriculo (ID_Curriculos),
    KEY IX_Curriculo_Importacoes_Status (ID_Status_Processamento_IA),
    CONSTRAINT FK_Curriculo_Importacoes_Curriculo
        FOREIGN KEY (ID_Curriculos) REFERENCES Curriculos (ID_Curriculos) ON DELETE CASCADE,
    CONSTRAINT FK_Curriculo_Importacoes_Status
        FOREIGN KEY (ID_Status_Processamento_IA)
        REFERENCES Status_Processamento_IA (ID_Status_Processamento_IA)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
