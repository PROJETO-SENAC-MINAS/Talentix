-- ============================================================================
-- TALENTIX — SCRIPT DE CRIAÇÃO DO BANCO DE DADOS (MySQL 8)
-- Padrões adotados:
--   - Herança: tabelas separadas com FK 1:1 (Class Table Inheritance)
--   - Status/Enums: tabelas de domínio separadas
--   - Exclusão: soft delete (ativo + deletado_em)
--   - Arquivos: URL + metadados (tamanho, tipo MIME, hash)
--   - IA/Recomendações: campos de controle para processamento assíncrono
--   - Charset: utf8mb4 / utf8mb4_unicode_ci
--   - Nomenclatura de PK/FK: ID_<NomeDaTabela>
-- ============================================================================

CREATE DATABASE IF NOT EXISTS talentix_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE talentix;

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================================
-- 1. TABELAS DE DOMÍNIO (STATUS / ENUMS)
-- ============================================================================

CREATE TABLE Status_Vaga (
    ID_Status_Vaga     TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo             VARCHAR(30) NOT NULL,
    Descricao          VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Vaga),
    UNIQUE KEY UQ_Status_Vaga_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Vaga (Codigo, Descricao) VALUES
 ('RASCUNHO','Rascunho'), ('PUBLICADA','Publicada'),
 ('PAUSADA','Pausada'), ('ENCERRADA','Encerrada');

CREATE TABLE Status_Candidatura (
    ID_Status_Candidatura TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo                 VARCHAR(30) NOT NULL,
    Descricao              VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Candidatura),
    UNIQUE KEY UQ_Status_Candidatura_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Candidatura (Codigo, Descricao) VALUES
 ('ENVIADA','Enviada'), ('EM_ANALISE','Em análise'), ('TRIAGEM','Triagem'),
 ('ENTREVISTA','Entrevista'), ('APROVADA','Aprovada'),
 ('RECUSADA','Recusada'), ('CANCELADA','Cancelada');

CREATE TABLE Status_Etapa (
    ID_Status_Etapa    TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo             VARCHAR(30) NOT NULL,
    Descricao          VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Etapa),
    UNIQUE KEY UQ_Status_Etapa_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Etapa (Codigo, Descricao) VALUES
 ('PENDENTE','Pendente'), ('EM_ANDAMENTO','Em andamento'),
 ('CONCLUIDA','Concluída'), ('CANCELADA','Cancelada');

CREATE TABLE Status_Entrevista (
    ID_Status_Entrevista TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo                VARCHAR(30) NOT NULL,
    Descricao             VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Entrevista),
    UNIQUE KEY UQ_Status_Entrevista_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Entrevista (Codigo, Descricao) VALUES
 ('AGENDADA','Agendada'), ('REALIZADA','Realizada'),
 ('REAGENDADA','Reagendada'), ('CANCELADA','Cancelada');

CREATE TABLE Status_Denuncia (
    ID_Status_Denuncia TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo              VARCHAR(30) NOT NULL,
    Descricao           VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Denuncia),
    UNIQUE KEY UQ_Status_Denuncia_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Denuncia (Codigo, Descricao) VALUES
 ('ABERTA','Aberta'), ('EM_ANALISE','Em análise'),
 ('RESOLVIDA','Resolvida'), ('REJEITADA','Rejeitada');

CREATE TABLE Status_Assinatura (
    ID_Status_Assinatura TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo                 VARCHAR(30) NOT NULL,
    Descricao              VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Assinatura),
    UNIQUE KEY UQ_Status_Assinatura_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Assinatura (Codigo, Descricao) VALUES
 ('ATIVA','Ativa'), ('INADIMPLENTE','Inadimplente'),
 ('CANCELADA','Cancelada'), ('EXPIRADA','Expirada');

CREATE TABLE Status_Pagamento (
    ID_Status_Pagamento TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo                VARCHAR(30) NOT NULL,
    Descricao             VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Pagamento),
    UNIQUE KEY UQ_Status_Pagamento_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Pagamento (Codigo, Descricao) VALUES
 ('PENDENTE','Pendente'), ('APROVADO','Aprovado'),
 ('RECUSADO','Recusado'), ('ESTORNADO','Estornado');

-- Domínio de status de processamento assíncrono (IA)
CREATE TABLE Status_Processamento_IA (
    ID_Status_Processamento_IA TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
    Codigo                       VARCHAR(30) NOT NULL,
    Descricao                    VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Status_Processamento_IA),
    UNIQUE KEY UQ_Status_Processamento_IA_Codigo (Codigo)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT INTO Status_Processamento_IA (Codigo, Descricao) VALUES
 ('NA_FILA','Na fila'), ('PROCESSANDO','Processando'),
 ('CONCLUIDO','Concluído'), ('FALHOU','Falhou');

-- ============================================================================
-- 2. USUÁRIO (BASE) E ESPECIALIZAÇÕES (FK 1:1)
-- ============================================================================

CREATE TABLE Usuarios (
    ID_Usuarios      CHAR(36) NOT NULL,
    Nome             VARCHAR(150) NOT NULL,
    Email            VARCHAR(150) NOT NULL,
    SenhaHash        VARCHAR(255) NOT NULL,
    Telefone         VARCHAR(20) NULL,
    FotoUrl          VARCHAR(500) NULL,
    FotoTamanhoBytes BIGINT UNSIGNED NULL,
    FotoTipoMime     VARCHAR(100) NULL,
    FotoHash         VARCHAR(128) NULL,
    Ativo            BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm       DATETIME NULL,
    PRIMARY KEY (ID_Usuarios),
    UNIQUE KEY UQ_Usuarios_Email (Email)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Candidatos (
    ID_Candidatos        CHAR(36) NOT NULL,
    ID_Usuarios          CHAR(36) NOT NULL,
    TituloProfissional   VARCHAR(150) NULL,
    Resumo               TEXT NULL,
    Cidade               VARCHAR(100) NULL,
    Estado               VARCHAR(2) NULL,
    LinkedinUrl          VARCHAR(300) NULL,
    GithubUrl            VARCHAR(300) NULL,
    PortfolioUrl         VARCHAR(300) NULL,
    ExperienciaAnos      SMALLINT UNSIGNED NULL,
    PretensaoSalarial    DECIMAL(10,2) NULL,
    Disponivel           BOOLEAN NOT NULL DEFAULT TRUE,
    Ativo                BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm           DATETIME NULL,
    PRIMARY KEY (ID_Candidatos),
    UNIQUE KEY UQ_Candidatos_ID_Usuarios (ID_Usuarios),
    CONSTRAINT FK_Candidatos_ID_Usuarios FOREIGN KEY (ID_Usuarios)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Empresas (
    ID_Empresas          CHAR(36) NOT NULL,
    ID_Usuarios          CHAR(36) NOT NULL,
    RazaoSocial          VARCHAR(200) NOT NULL,
    NomeFantasia         VARCHAR(200) NULL,
    Cnpj                 VARCHAR(18) NOT NULL,
    Descricao            TEXT NULL,
    Setor                VARCHAR(100) NULL,
    Porte                VARCHAR(50) NULL,
    LogoUrl              VARCHAR(500) NULL,
    LogoTamanhoBytes     BIGINT UNSIGNED NULL,
    LogoTipoMime         VARCHAR(100) NULL,
    LogoHash             VARCHAR(128) NULL,
    SiteUrl              VARCHAR(300) NULL,
    Endereco             VARCHAR(300) NULL,
    Verificada           BOOLEAN NOT NULL DEFAULT FALSE,
    Ativo                BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm           DATETIME NULL,
    PRIMARY KEY (ID_Empresas),
    UNIQUE KEY UQ_Empresas_ID_Usuarios (ID_Usuarios),
    UNIQUE KEY UQ_Empresas_Cnpj (Cnpj),
    CONSTRAINT FK_Empresas_ID_Usuarios FOREIGN KEY (ID_Usuarios)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Administradores (
    ID_Administradores CHAR(36) NOT NULL,
    ID_Usuarios         CHAR(36) NOT NULL,
    NivelAcesso         VARCHAR(50) NOT NULL,
    Ativo                BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm           DATETIME NULL,
    PRIMARY KEY (ID_Administradores),
    UNIQUE KEY UQ_Administradores_ID_Usuarios (ID_Usuarios),
    CONSTRAINT FK_Administradores_ID_Usuarios FOREIGN KEY (ID_Usuarios)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Recrutadores (
    ID_Recrutadores CHAR(36) NOT NULL,
    ID_Empresas       CHAR(36) NOT NULL,
    ID_Usuarios       CHAR(36) NOT NULL,
    Cargo              VARCHAR(100) NULL,
    Ativo              BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm         DATETIME NULL,
    PRIMARY KEY (ID_Recrutadores),
    UNIQUE KEY UQ_Recrutadores_ID_Usuarios (ID_Usuarios),
    KEY IX_Recrutadores_ID_Empresas (ID_Empresas),
    CONSTRAINT FK_Recrutadores_ID_Empresas FOREIGN KEY (ID_Empresas)
        REFERENCES Empresas (ID_Empresas) ON DELETE CASCADE,
    CONSTRAINT FK_Recrutadores_ID_Usuarios FOREIGN KEY (ID_Usuarios)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 3. VAGAS
-- ============================================================================

CREATE TABLE Vagas (
    ID_Vagas               CHAR(36) NOT NULL,
    ID_Empresas             CHAR(36) NOT NULL,
    ID_Status_Vaga          TINYINT UNSIGNED NOT NULL,
    Titulo                   VARCHAR(200) NOT NULL,
    Descricao                TEXT NOT NULL,
    Modalidade               VARCHAR(50) NULL,
    Nivel                    VARCHAR(50) NULL,
    TipoContrato             VARCHAR(50) NULL,
    SalarioMin               DECIMAL(10,2) NULL,
    SalarioMax               DECIMAL(10,2) NULL,
    Localizacao              VARCHAR(200) NULL,
    SalarioConfidencial      BOOLEAN NOT NULL DEFAULT FALSE,
    Ativo                    BOOLEAN NOT NULL DEFAULT TRUE,
    PublicadaEm              DATETIME NULL,
    EncerradaEm              DATETIME NULL,
    CriadoEm                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm                DATETIME NULL,
    PRIMARY KEY (ID_Vagas),
    KEY IX_Vagas_ID_Empresas (ID_Empresas),
    KEY IX_Vagas_ID_Status_Vaga (ID_Status_Vaga),
    CONSTRAINT FK_Vagas_ID_Empresas FOREIGN KEY (ID_Empresas)
        REFERENCES Empresas (ID_Empresas) ON DELETE CASCADE,
    CONSTRAINT FK_Vagas_ID_Status_Vaga FOREIGN KEY (ID_Status_Vaga)
        REFERENCES Status_Vaga (ID_Status_Vaga)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 4. PERFIL DO CANDIDATO: CURRÍCULO, EXPERIÊNCIA, FORMAÇÃO
-- ============================================================================

CREATE TABLE Curriculos (
    ID_Curriculos     CHAR(36) NOT NULL,
    ID_Candidatos      CHAR(36) NOT NULL,
    Titulo              VARCHAR(150) NOT NULL,
    ArquivoUrl          VARCHAR(500) NOT NULL,
    ArquivoTamanhoBytes BIGINT UNSIGNED NULL,
    ArquivoTipoMime     VARCHAR(100) NULL,
    ArquivoHash         VARCHAR(128) NULL,
    Principal           BOOLEAN NOT NULL DEFAULT FALSE,
    Ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm          DATETIME NULL,
    PRIMARY KEY (ID_Curriculos),
    KEY IX_Curriculos_ID_Candidatos (ID_Candidatos),
    CONSTRAINT FK_Curriculos_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Experiencias (
    ID_Experiencias CHAR(36) NOT NULL,
    ID_Candidatos    CHAR(36) NOT NULL,
    Empresa           VARCHAR(150) NOT NULL,
    Cargo             VARCHAR(150) NOT NULL,
    Descricao         TEXT NULL,
    DataInicio        DATE NOT NULL,
    DataFim           DATE NULL,
    Atual             BOOLEAN NOT NULL DEFAULT FALSE,
    CriadoEm          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Experiencias),
    KEY IX_Experiencias_ID_Candidatos (ID_Candidatos),
    CONSTRAINT FK_Experiencias_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Formacoes (
    ID_Formacoes     CHAR(36) NOT NULL,
    ID_Candidatos     CHAR(36) NOT NULL,
    Instituicao        VARCHAR(200) NOT NULL,
    Curso               VARCHAR(200) NOT NULL,
    Nivel               VARCHAR(50) NULL,
    DataInicio          DATE NULL,
    DataConclusao       DATE NULL,
    Status              VARCHAR(50) NULL,
    CriadoEm            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Formacoes),
    KEY IX_Formacoes_ID_Candidatos (ID_Candidatos),
    CONSTRAINT FK_Formacoes_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 5. HABILIDADES E IDIOMAS (CATÁLOGOS + N:N)
-- ============================================================================

CREATE TABLE Habilidades (
    ID_Habilidades CHAR(36) NOT NULL,
    Nome            VARCHAR(100) NOT NULL,
    Categoria       VARCHAR(100) NULL,
    Ativo           BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Habilidades),
    UNIQUE KEY UQ_Habilidades_Nome (Nome)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Candidato_Habilidades (
    ID_Candidato_Habilidades CHAR(36) NOT NULL,
    ID_Candidatos              CHAR(36) NOT NULL,
    ID_Habilidades             CHAR(36) NOT NULL,
    Nivel                       TINYINT UNSIGNED NULL,
    AnosExperiencia             SMALLINT UNSIGNED NULL,
    CriadoEm                    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Candidato_Habilidades),
    UNIQUE KEY UQ_Candidato_Habilidades_Par (ID_Candidatos, ID_Habilidades),
    KEY IX_Candidato_Habilidades_ID_Habilidades (ID_Habilidades),
    CONSTRAINT FK_Candidato_Habilidades_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Candidato_Habilidades_ID_Habilidades FOREIGN KEY (ID_Habilidades)
        REFERENCES Habilidades (ID_Habilidades) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Vaga_Habilidades (
    ID_Vaga_Habilidades CHAR(36) NOT NULL,
    ID_Vagas              CHAR(36) NOT NULL,
    ID_Habilidades         CHAR(36) NOT NULL,
    Obrigatoria             BOOLEAN NOT NULL DEFAULT FALSE,
    NivelMinimo             TINYINT UNSIGNED NULL,
    Peso                    TINYINT UNSIGNED NULL,
    CriadoEm                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Vaga_Habilidades),
    UNIQUE KEY UQ_Vaga_Habilidades_Par (ID_Vagas, ID_Habilidades),
    KEY IX_Vaga_Habilidades_ID_Habilidades (ID_Habilidades),
    CONSTRAINT FK_Vaga_Habilidades_ID_Vagas FOREIGN KEY (ID_Vagas)
        REFERENCES Vagas (ID_Vagas) ON DELETE CASCADE,
    CONSTRAINT FK_Vaga_Habilidades_ID_Habilidades FOREIGN KEY (ID_Habilidades)
        REFERENCES Habilidades (ID_Habilidades) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Idiomas (
    ID_Idiomas CHAR(36) NOT NULL,
    Nome        VARCHAR(100) NOT NULL,
    PRIMARY KEY (ID_Idiomas),
    UNIQUE KEY UQ_Idiomas_Nome (Nome)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Candidato_Idiomas (
    ID_Candidato_Idiomas CHAR(36) NOT NULL,
    ID_Candidatos          CHAR(36) NOT NULL,
    ID_Idiomas              CHAR(36) NOT NULL,
    Nivel                    VARCHAR(50) NULL,
    CriadoEm                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Candidato_Idiomas),
    UNIQUE KEY UQ_Candidato_Idiomas_Par (ID_Candidatos, ID_Idiomas),
    KEY IX_Candidato_Idiomas_ID_Idiomas (ID_Idiomas),
    CONSTRAINT FK_Candidato_Idiomas_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Candidato_Idiomas_ID_Idiomas FOREIGN KEY (ID_Idiomas)
        REFERENCES Idiomas (ID_Idiomas) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 6. CANDIDATURAS, ETAPAS E ENTREVISTAS
-- ============================================================================

CREATE TABLE Candidaturas (
    ID_Candidaturas         CHAR(36) NOT NULL,
    ID_Candidatos             CHAR(36) NOT NULL,
    ID_Vagas                  CHAR(36) NOT NULL,
    ID_Status_Candidatura     TINYINT UNSIGNED NOT NULL,
    CurriculoUrl               VARCHAR(500) NULL,
    CurriculoTamanhoBytes      BIGINT UNSIGNED NULL,
    CurriculoTipoMime          VARCHAR(100) NULL,
    CurriculoHash               VARCHAR(128) NULL,
    CartaApresentacao          TEXT NULL,
    Compatibilidade             TINYINT UNSIGNED NULL,
    Ativo                       BOOLEAN NOT NULL DEFAULT TRUE,
    CriadaEm                    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadaEm                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    DeletadoEm                  DATETIME NULL,
    PRIMARY KEY (ID_Candidaturas),
    UNIQUE KEY UQ_Candidaturas_Par (ID_Candidatos, ID_Vagas),
    KEY IX_Candidaturas_ID_Vagas (ID_Vagas),
    KEY IX_Candidaturas_ID_Status_Candidatura (ID_Status_Candidatura),
    CONSTRAINT FK_Candidaturas_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Candidaturas_ID_Vagas FOREIGN KEY (ID_Vagas)
        REFERENCES Vagas (ID_Vagas) ON DELETE CASCADE,
    CONSTRAINT FK_Candidaturas_ID_Status_Candidatura FOREIGN KEY (ID_Status_Candidatura)
        REFERENCES Status_Candidatura (ID_Status_Candidatura)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Etapas_Processo (
    ID_Etapas_Processo CHAR(36) NOT NULL,
    ID_Candidaturas      CHAR(36) NOT NULL,
    ID_Status_Etapa       TINYINT UNSIGNED NOT NULL,
    Nome                   VARCHAR(150) NOT NULL,
    Ordem                  SMALLINT UNSIGNED NOT NULL,
    InicioEm               DATETIME NULL,
    FimEm                  DATETIME NULL,
    CriadoEm               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Etapas_Processo),
    KEY IX_Etapas_Processo_ID_Candidaturas (ID_Candidaturas),
    KEY IX_Etapas_Processo_ID_Status_Etapa (ID_Status_Etapa),
    CONSTRAINT FK_Etapas_Processo_ID_Candidaturas FOREIGN KEY (ID_Candidaturas)
        REFERENCES Candidaturas (ID_Candidaturas) ON DELETE CASCADE,
    CONSTRAINT FK_Etapas_Processo_ID_Status_Etapa FOREIGN KEY (ID_Status_Etapa)
        REFERENCES Status_Etapa (ID_Status_Etapa)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Entrevistas (
    ID_Entrevistas       CHAR(36) NOT NULL,
    ID_Candidaturas        CHAR(36) NOT NULL,
    ID_Recrutadores         CHAR(36) NOT NULL,
    ID_Status_Entrevista    TINYINT UNSIGNED NOT NULL,
    DataHora                 DATETIME NOT NULL,
    Tipo                     VARCHAR(50) NULL,
    LocalOuLink               VARCHAR(300) NULL,
    Observacoes               TEXT NULL,
    CriadoEm                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadoEm               DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Entrevistas),
    KEY IX_Entrevistas_ID_Candidaturas (ID_Candidaturas),
    KEY IX_Entrevistas_ID_Recrutadores (ID_Recrutadores),
    KEY IX_Entrevistas_ID_Status_Entrevista (ID_Status_Entrevista),
    CONSTRAINT FK_Entrevistas_ID_Candidaturas FOREIGN KEY (ID_Candidaturas)
        REFERENCES Candidaturas (ID_Candidaturas) ON DELETE CASCADE,
    CONSTRAINT FK_Entrevistas_ID_Recrutadores FOREIGN KEY (ID_Recrutadores)
        REFERENCES Recrutadores (ID_Recrutadores) ON DELETE CASCADE,
    CONSTRAINT FK_Entrevistas_ID_Status_Entrevista FOREIGN KEY (ID_Status_Entrevista)
        REFERENCES Status_Entrevista (ID_Status_Entrevista)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 7. FAVORITOS
-- ============================================================================

CREATE TABLE Favoritos_Vaga (
    ID_Favoritos_Vaga CHAR(36) NOT NULL,
    ID_Candidatos        CHAR(36) NOT NULL,
    ID_Vagas             CHAR(36) NOT NULL,
    CriadoEm              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Favoritos_Vaga),
    UNIQUE KEY UQ_Favoritos_Vaga_Par (ID_Candidatos, ID_Vagas),
    KEY IX_Favoritos_Vaga_ID_Vagas (ID_Vagas),
    CONSTRAINT FK_Favoritos_Vaga_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Favoritos_Vaga_ID_Vagas FOREIGN KEY (ID_Vagas)
        REFERENCES Vagas (ID_Vagas) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 8. INTELIGÊNCIA ARTIFICIAL: ANÁLISES E RECOMENDAÇÕES
-- ============================================================================

CREATE TABLE Analises_IA (
    ID_Analises_IA               CHAR(36) NOT NULL,
    ID_Candidatos                  CHAR(36) NOT NULL,
    ID_Vagas                       CHAR(36) NOT NULL,
    ID_Candidaturas                CHAR(36) NULL,
    ID_Status_Processamento_IA     TINYINT UNSIGNED NOT NULL,
    ScoreCompatibilidade            TINYINT UNSIGNED NULL,
    PontosFortes                    TEXT NULL,
    Lacunas                          TEXT NULL,
    Justificativa                   TEXT NULL,
    ModeloIA                        VARCHAR(100) NULL,
    AnalisadaEm                     DATETIME NULL,
    CriadoEm                        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Analises_IA),
    KEY IX_Analises_IA_ID_Candidatos (ID_Candidatos),
    KEY IX_Analises_IA_ID_Vagas (ID_Vagas),
    KEY IX_Analises_IA_ID_Candidaturas (ID_Candidaturas),
    KEY IX_Analises_IA_ID_Status_Processamento_IA (ID_Status_Processamento_IA),
    CONSTRAINT FK_Analises_IA_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Analises_IA_ID_Vagas FOREIGN KEY (ID_Vagas)
        REFERENCES Vagas (ID_Vagas) ON DELETE CASCADE,
    CONSTRAINT FK_Analises_IA_ID_Candidaturas FOREIGN KEY (ID_Candidaturas)
        REFERENCES Candidaturas (ID_Candidaturas) ON DELETE SET NULL,
    CONSTRAINT FK_Analises_IA_ID_Status_Processamento_IA FOREIGN KEY (ID_Status_Processamento_IA)
        REFERENCES Status_Processamento_IA (ID_Status_Processamento_IA)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Recomendacoes_Vaga (
    ID_Recomendacoes_Vaga       CHAR(36) NOT NULL,
    ID_Candidatos                  CHAR(36) NOT NULL,
    ID_Vagas                       CHAR(36) NOT NULL,
    ID_Status_Processamento_IA     TINYINT UNSIGNED NOT NULL,
    Score                           TINYINT UNSIGNED NULL,
    Motivo                          TEXT NULL,
    Visualizada                     BOOLEAN NOT NULL DEFAULT FALSE,
    CriadaEm                        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Recomendacoes_Vaga),
    UNIQUE KEY UQ_Recomendacoes_Vaga_Par (ID_Candidatos, ID_Vagas),
    KEY IX_Recomendacoes_Vaga_ID_Vagas (ID_Vagas),
    KEY IX_Recomendacoes_Vaga_ID_Status_Processamento_IA (ID_Status_Processamento_IA),
    CONSTRAINT FK_Recomendacoes_Vaga_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Recomendacoes_Vaga_ID_Vagas FOREIGN KEY (ID_Vagas)
        REFERENCES Vagas (ID_Vagas) ON DELETE CASCADE,
    CONSTRAINT FK_Recomendacoes_Vaga_ID_Status_Processamento_IA FOREIGN KEY (ID_Status_Processamento_IA)
        REFERENCES Status_Processamento_IA (ID_Status_Processamento_IA)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 9. CURSOS E RECOMENDAÇÕES DE CURSO
-- ============================================================================

CREATE TABLE Cursos (
    ID_Cursos      CHAR(36) NOT NULL,
    Titulo          VARCHAR(200) NOT NULL,
    Descricao       TEXT NULL,
    Plataforma      VARCHAR(100) NULL,
    Url              VARCHAR(500) NULL,
    Nivel            VARCHAR(50) NULL,
    Categoria        VARCHAR(100) NULL,
    CargaHoraria     SMALLINT UNSIGNED NULL,
    Ativo            BOOLEAN NOT NULL DEFAULT TRUE,
    CriadoEm         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Cursos)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Recomendacoes_Curso (
    ID_Recomendacoes_Curso     CHAR(36) NOT NULL,
    ID_Candidatos                CHAR(36) NOT NULL,
    ID_Cursos                    CHAR(36) NOT NULL,
    ID_Status_Processamento_IA   TINYINT UNSIGNED NOT NULL,
    Motivo                        TEXT NULL,
    Prioridade                    TINYINT UNSIGNED NULL,
    Concluida                     BOOLEAN NOT NULL DEFAULT FALSE,
    CriadaEm                      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Recomendacoes_Curso),
    UNIQUE KEY UQ_Recomendacoes_Curso_Par (ID_Candidatos, ID_Cursos),
    KEY IX_Recomendacoes_Curso_ID_Cursos (ID_Cursos),
    KEY IX_Recomendacoes_Curso_ID_Status_Processamento_IA (ID_Status_Processamento_IA),
    CONSTRAINT FK_Recomendacoes_Curso_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Recomendacoes_Curso_ID_Cursos FOREIGN KEY (ID_Cursos)
        REFERENCES Cursos (ID_Cursos) ON DELETE CASCADE,
    CONSTRAINT FK_Recomendacoes_Curso_ID_Status_Processamento_IA FOREIGN KEY (ID_Status_Processamento_IA)
        REFERENCES Status_Processamento_IA (ID_Status_Processamento_IA)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 10. NOTIFICAÇÕES E MENSAGENS
-- ============================================================================

CREATE TABLE Notificacoes (
    ID_Notificacoes CHAR(36) NOT NULL,
    ID_Usuarios       CHAR(36) NOT NULL,
    Titulo             VARCHAR(150) NOT NULL,
    Mensagem           TEXT NOT NULL,
    Tipo               VARCHAR(50) NULL,
    Lida               BOOLEAN NOT NULL DEFAULT FALSE,
    CriadaEm           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Notificacoes),
    KEY IX_Notificacoes_ID_Usuarios (ID_Usuarios),
    CONSTRAINT FK_Notificacoes_ID_Usuarios FOREIGN KEY (ID_Usuarios)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Mensagens (
    ID_Mensagens      CHAR(36) NOT NULL,
    ID_Remetente        CHAR(36) NOT NULL,
    ID_Destinatario      CHAR(36) NOT NULL,
    ID_Candidaturas      CHAR(36) NULL,
    Conteudo              TEXT NOT NULL,
    Lida                  BOOLEAN NOT NULL DEFAULT FALSE,
    EnviadaEm             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Mensagens),
    KEY IX_Mensagens_ID_Remetente (ID_Remetente),
    KEY IX_Mensagens_ID_Destinatario (ID_Destinatario),
    KEY IX_Mensagens_ID_Candidaturas (ID_Candidaturas),
    CONSTRAINT FK_Mensagens_ID_Remetente FOREIGN KEY (ID_Remetente)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE,
    CONSTRAINT FK_Mensagens_ID_Destinatario FOREIGN KEY (ID_Destinatario)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE,
    CONSTRAINT FK_Mensagens_ID_Candidaturas FOREIGN KEY (ID_Candidaturas)
        REFERENCES Candidaturas (ID_Candidaturas) ON DELETE SET NULL
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 11. AVALIAÇÕES E DENÚNCIAS
-- ============================================================================

CREATE TABLE Avaliacoes (
    ID_Avaliacoes     CHAR(36) NOT NULL,
    ID_Avaliador        CHAR(36) NOT NULL,
    ID_Candidatos        CHAR(36) NULL,
    ID_Empresas          CHAR(36) NULL,
    ID_Candidaturas      CHAR(36) NOT NULL,
    Nota                  TINYINT UNSIGNED NOT NULL,
    Comentario            TEXT NULL,
    CriadaEm              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Avaliacoes),
    KEY IX_Avaliacoes_ID_Avaliador (ID_Avaliador),
    KEY IX_Avaliacoes_ID_Candidatos (ID_Candidatos),
    KEY IX_Avaliacoes_ID_Empresas (ID_Empresas),
    KEY IX_Avaliacoes_ID_Candidaturas (ID_Candidaturas),
    CONSTRAINT FK_Avaliacoes_ID_Avaliador FOREIGN KEY (ID_Avaliador)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE,
    CONSTRAINT FK_Avaliacoes_ID_Candidatos FOREIGN KEY (ID_Candidatos)
        REFERENCES Candidatos (ID_Candidatos) ON DELETE CASCADE,
    CONSTRAINT FK_Avaliacoes_ID_Empresas FOREIGN KEY (ID_Empresas)
        REFERENCES Empresas (ID_Empresas) ON DELETE CASCADE,
    CONSTRAINT FK_Avaliacoes_ID_Candidaturas FOREIGN KEY (ID_Candidaturas)
        REFERENCES Candidaturas (ID_Candidaturas) ON DELETE CASCADE,
    CONSTRAINT CK_Avaliacoes_Nota CHECK (Nota BETWEEN 1 AND 5)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Denuncias (
    ID_Denuncias        CHAR(36) NOT NULL,
    ID_Denunciante         CHAR(36) NOT NULL,
    ID_Usuario_Alvo         CHAR(36) NULL,
    ID_Vagas                CHAR(36) NULL,
    ID_Status_Denuncia      TINYINT UNSIGNED NOT NULL,
    ID_Administradores      CHAR(36) NULL,
    Motivo                   VARCHAR(200) NOT NULL,
    Descricao                TEXT NULL,
    CriadaEm                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ResolvidaEm               DATETIME NULL,
    PRIMARY KEY (ID_Denuncias),
    KEY IX_Denuncias_ID_Denunciante (ID_Denunciante),
    KEY IX_Denuncias_ID_Usuario_Alvo (ID_Usuario_Alvo),
    KEY IX_Denuncias_ID_Vagas (ID_Vagas),
    KEY IX_Denuncias_ID_Status_Denuncia (ID_Status_Denuncia),
    KEY IX_Denuncias_ID_Administradores (ID_Administradores),
    CONSTRAINT FK_Denuncias_ID_Denunciante FOREIGN KEY (ID_Denunciante)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE CASCADE,
    CONSTRAINT FK_Denuncias_ID_Usuario_Alvo FOREIGN KEY (ID_Usuario_Alvo)
        REFERENCES Usuarios (ID_Usuarios) ON DELETE SET NULL,
    CONSTRAINT FK_Denuncias_ID_Vagas FOREIGN KEY (ID_Vagas)
        REFERENCES Vagas (ID_Vagas) ON DELETE SET NULL,
    CONSTRAINT FK_Denuncias_ID_Status_Denuncia FOREIGN KEY (ID_Status_Denuncia)
        REFERENCES Status_Denuncia (ID_Status_Denuncia),
    CONSTRAINT FK_Denuncias_ID_Administradores FOREIGN KEY (ID_Administradores)
        REFERENCES Administradores (ID_Administradores) ON DELETE SET NULL
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ============================================================================
-- 12. FINANCEIRO: ASSINATURAS E PAGAMENTOS
-- ============================================================================

CREATE TABLE Assinaturas (
    ID_Assinaturas       CHAR(36) NOT NULL,
    ID_Empresas             CHAR(36) NOT NULL,
    ID_Status_Assinatura    TINYINT UNSIGNED NOT NULL,
    Plano                    VARCHAR(50) NOT NULL,
    Valor                    DECIMAL(10,2) NOT NULL,
    Inicio                   DATE NOT NULL,
    Fim                      DATE NULL,
    CriadaEm                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    AtualizadaEm              DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Assinaturas),
    KEY IX_Assinaturas_ID_Empresas (ID_Empresas),
    KEY IX_Assinaturas_ID_Status_Assinatura (ID_Status_Assinatura),
    CONSTRAINT FK_Assinaturas_ID_Empresas FOREIGN KEY (ID_Empresas)
        REFERENCES Empresas (ID_Empresas) ON DELETE CASCADE,
    CONSTRAINT FK_Assinaturas_ID_Status_Assinatura FOREIGN KEY (ID_Status_Assinatura)
        REFERENCES Status_Assinatura (ID_Status_Assinatura)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE Pagamentos (
    ID_Pagamentos       CHAR(36) NOT NULL,
    ID_Assinaturas         CHAR(36) NOT NULL,
    ID_Status_Pagamento     TINYINT UNSIGNED NOT NULL,
    Valor                    DECIMAL(10,2) NOT NULL,
    Metodo                   VARCHAR(50) NULL,
    TransacaoId              VARCHAR(150) NULL,
    PagoEm                   DATETIME NULL,
    CriadoEm                 DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ID_Pagamentos),
    KEY IX_Pagamentos_ID_Assinaturas (ID_Assinaturas),
    KEY IX_Pagamentos_ID_Status_Pagamento (ID_Status_Pagamento),
    CONSTRAINT FK_Pagamentos_ID_Assinaturas FOREIGN KEY (ID_Assinaturas)
        REFERENCES Assinaturas (ID_Assinaturas) ON DELETE CASCADE,
    CONSTRAINT FK_Pagamentos_ID_Status_Pagamento FOREIGN KEY (ID_Status_Pagamento)
        REFERENCES Status_Pagamento (ID_Status_Pagamento)
) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;