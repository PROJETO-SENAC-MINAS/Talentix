"""Testes HTTP com sessões reais e banco isolado; não usam SMTP nem o MySQL local."""
import importlib
from datetime import datetime, date
from decimal import Decimal
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from contextlib import asynccontextmanager
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update({
    "SECRET_KEY": "1" * 64,
    "IA_WORKER_TOKEN": "2" * 64,
    "PAYMENT_WEBHOOK_TOKEN": "3" * 64,
    "SMTP_ENABLED": "false",
    "SESSION_COOKIE_SECURE": "true",
    "UPLOAD_DIR": tempfile.mkdtemp(prefix="talentix-test-uploads-"),
})

from app.core.config import settings
from app.core.security import hash_senha
from app.core.session import _serializer
from app.main import app

main = importlib.import_module("app.main")
SENHA_HASH = hash_senha("senha-de-teste")
ARQUIVO_A = "a" * 64 + ".pdf"
ARQUIVO_B = "b" * 64 + ".pdf"
URL_A = "/uploads/curriculos/" + ARQUIVO_A
URL_B = "/uploads/curriculos/" + ARQUIVO_B

SCHEMA = """
CREATE TABLE IF NOT EXISTS Contatos (
               ID_Contatos CHAR(36) NOT NULL PRIMARY KEY,
               Nome VARCHAR(150) NOT NULL,
               Email VARCHAR(150) NOT NULL,
               Assunto VARCHAR(100) NOT NULL,
               Mensagem TEXT NOT NULL,
               Lido BOOLEAN NOT NULL DEFAULT FALSE,
               CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
           );
CREATE TABLE IF NOT EXISTS Curriculo_Importacoes (
               ID_Curriculo_Importacoes CHAR(36) NOT NULL PRIMARY KEY,
               ID_Curriculos CHAR(36) NOT NULL UNIQUE,
               ID_Status_Processamento_IA INTEGER NOT NULL DEFAULT 1,
               DadosExtraidos TEXT NULL,
               TextoExtraido TEXT NULL,
               DadosConfirmados TEXT NULL,
               TextoCaracteres INTEGER NULL,
               ErroProcessamento VARCHAR(500) NULL,
               ProcessamentoIniciadoEm DATETIME NULL,
               ProcessadoEm DATETIME NULL,
               AplicadoEm DATETIME NULL,
               CriadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
               AtualizadoEm DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
           );

CREATE TABLE Usuarios (ID_Usuarios TEXT PRIMARY KEY, Nome TEXT, Email TEXT, EmailConfirmadoEm TEXT,
  SenhaHash TEXT, TentativasLogin INTEGER DEFAULT 0, BloqueadoAte TEXT, UltimoLoginEm TEXT,
  TwoFactorAtivo INTEGER DEFAULT 0, TwoFactorSecretEnc TEXT,
  Telefone TEXT, FotoUrl TEXT, FotoTamanhoBytes INTEGER,FotoTipoMime TEXT,FotoHash TEXT, Ativo INTEGER DEFAULT 1, CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Candidatos (ID_Candidatos TEXT PRIMARY KEY, ID_Usuarios TEXT, Ativo INTEGER DEFAULT 1,
  Cidade TEXT,Estado TEXT,TituloProfissional TEXT,Resumo TEXT,LinkedinUrl TEXT,GithubUrl TEXT,PortfolioUrl TEXT,
  ExperienciaAnos INTEGER,PretensaoSalarial REAL,Modalidades TEXT,TiposContrato TEXT,Preferencias TEXT,HabilidadesComportamentais TEXT,
  Disponivel INTEGER DEFAULT 1, CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Empresas (ID_Empresas TEXT PRIMARY KEY, ID_Usuarios TEXT, NomeFantasia TEXT,RazaoSocial TEXT,Descricao TEXT,Setor TEXT,Porte TEXT,LogoUrl TEXT,SiteUrl TEXT,Verificada INTEGER,CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP, Ativo INTEGER DEFAULT 1);
CREATE TABLE Administradores (ID_Administradores TEXT PRIMARY KEY, ID_Usuarios TEXT, Ativo INTEGER DEFAULT 1);
CREATE TABLE Vagas (ID_Vagas TEXT PRIMARY KEY, ID_Empresas TEXT, Titulo TEXT, Localizacao TEXT,
  Modalidade TEXT,Descricao TEXT,Nivel TEXT,TipoContrato TEXT,SalarioMin REAL,SalarioMax REAL,SalarioConfidencial INTEGER DEFAULT 0,
  AreaProfissional TEXT,PublicadaEm TEXT DEFAULT CURRENT_TIMESTAMP,CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP,
  ID_Status_Vaga INTEGER DEFAULT 2, Ativo INTEGER DEFAULT 1);
CREATE TABLE Candidaturas (ID_Candidaturas TEXT PRIMARY KEY, ID_Candidatos TEXT, ID_Vagas TEXT,
  ID_Status_Candidatura INTEGER DEFAULT 1, CurriculoUrl TEXT, CartaApresentacao TEXT,
  Ativo INTEGER DEFAULT 1, DeletadoEm TEXT, CriadaEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Etapas_Processo (ID_Etapas_Processo TEXT PRIMARY KEY, ID_Candidaturas TEXT,
  ID_Status_Etapa INTEGER, Nome TEXT, Ordem INTEGER, InicioEm TEXT, FimEm TEXT);
CREATE TABLE Entrevistas (ID_Entrevistas TEXT PRIMARY KEY, ID_Candidaturas TEXT, ID_Recrutadores TEXT,
  ID_Status_Entrevista INTEGER, DataHora TEXT, Tipo TEXT, LocalOuLink TEXT, Observacoes TEXT);
CREATE TABLE Recrutadores (ID_Recrutadores TEXT PRIMARY KEY, ID_Empresas TEXT, ID_Usuarios TEXT,
  Ativo INTEGER DEFAULT 1, DeletadoEm TEXT);
CREATE TABLE Curriculos (ID_Curriculos TEXT PRIMARY KEY, ID_Candidatos TEXT, Titulo TEXT,
  ArquivoUrl TEXT, ArquivoTamanhoBytes INTEGER, ArquivoTipoMime TEXT, ArquivoHash TEXT,
  Principal INTEGER DEFAULT 0, Versao INTEGER DEFAULT 1,Origem TEXT DEFAULT 'upload', DeletadoEm TEXT,
  Ativo INTEGER DEFAULT 1, AtualizadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Experiencias (ID_Experiencias TEXT PRIMARY KEY, ID_Candidatos TEXT, Empresa TEXT, Cargo TEXT, DataInicio TEXT,DataFim TEXT,Descricao TEXT,Atual INTEGER);
CREATE TABLE Formacoes (ID_Formacoes TEXT PRIMARY KEY, ID_Candidatos TEXT, Instituicao TEXT, Curso TEXT, DataInicio TEXT,DataConclusao TEXT,Nivel TEXT,Status TEXT);
CREATE TABLE Habilidades (ID_Habilidades TEXT PRIMARY KEY, Nome TEXT, Categoria TEXT, Ativo INTEGER DEFAULT 1);
CREATE TABLE Candidato_Habilidades (ID_Candidato_Habilidades TEXT PRIMARY KEY, ID_Candidatos TEXT, ID_Habilidades TEXT,Nivel INTEGER,AnosExperiencia INTEGER);
CREATE TABLE Idiomas (ID_Idiomas TEXT PRIMARY KEY, Nome TEXT);
CREATE TABLE Candidato_Idiomas (ID_Candidato_Idiomas TEXT PRIMARY KEY, ID_Candidatos TEXT, ID_Idiomas TEXT,Nivel TEXT);
CREATE TABLE Vaga_Habilidades (ID_Vaga_Habilidades TEXT PRIMARY KEY, ID_Vagas TEXT,ID_Habilidades TEXT,NivelMinimo INTEGER,Obrigatoria INTEGER);
CREATE TABLE Candidato_Itens(ID_Item TEXT PRIMARY KEY,ID_Candidatos TEXT,Tipo TEXT,Titulo TEXT,Instituicao TEXT,Descricao TEXT,Url TEXT,DataInicio TEXT,DataFim TEXT,CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Buscas_Salvas(ID_Busca TEXT PRIMARY KEY,ID_Usuarios TEXT,Nome TEXT,Filtros TEXT,Ativa INTEGER DEFAULT 0,CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Historico_Buscas(ID_Historico TEXT PRIMARY KEY,ID_Usuarios TEXT,Filtros TEXT,CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Alertas_Busca(ID_Busca TEXT,ID_Vagas TEXT,CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(ID_Busca,ID_Vagas));
CREATE TABLE Analises_IA (ID_Analises_IA TEXT PRIMARY KEY, ID_Candidatos TEXT, ID_Vagas TEXT,
  ID_Candidaturas TEXT, ID_Status_Processamento_IA INTEGER DEFAULT 1, ScoreCompatibilidade INTEGER,
  PontosFortes TEXT, Lacunas TEXT, Justificativa TEXT, ModeloIA TEXT, AnalisadaEm TEXT,
  CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Recomendacoes_Vaga (ID_Recomendacoes_Vaga TEXT PRIMARY KEY, ID_Candidatos TEXT, ID_Vagas TEXT,
  ID_Status_Processamento_IA INTEGER DEFAULT 3, Score INTEGER, Motivo TEXT, Visualizada INTEGER DEFAULT 0);
CREATE TABLE Cursos (ID_Cursos TEXT PRIMARY KEY, Titulo TEXT, Plataforma TEXT, Url TEXT);
CREATE TABLE Recomendacoes_Curso (ID_Recomendacoes_Curso TEXT PRIMARY KEY, ID_Candidatos TEXT, ID_Cursos TEXT,
  Concluida INTEGER DEFAULT 0, Prioridade INTEGER DEFAULT 1);
CREATE TABLE Assinaturas (ID_Assinaturas TEXT PRIMARY KEY, ID_Empresas TEXT, ID_Status_Assinatura INTEGER,
  Plano TEXT, Valor REAL, Inicio TEXT, Fim TEXT, CriadaEm TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE Pagamentos (ID_Pagamentos TEXT PRIMARY KEY, ID_Assinaturas TEXT,
  ID_Status_Pagamento INTEGER DEFAULT 1, Valor REAL, PagoEm TEXT);
CREATE TABLE Sessoes (ID_Sessoes TEXT PRIMARY KEY, ID_Usuarios TEXT, UserAgent TEXT,
  CriadaEm TEXT DEFAULT CURRENT_TIMESTAMP, UltimaAtividadeEm TEXT DEFAULT CURRENT_TIMESTAMP,
  ExpiraEm TEXT, RevogadaEm TEXT);
CREATE TABLE Audit_Logs (ID_Audit_Logs TEXT PRIMARY KEY, ID_Usuarios TEXT, Acao TEXT,
  Recurso TEXT, RecursoId TEXT, RequestId TEXT, UserAgent TEXT, ValorAnterior TEXT,
  ValorNovo TEXT, CriadoEm TEXT DEFAULT CURRENT_TIMESTAMP);
"""


@pytest.fixture
def ambiente(monkeypatch, tmp_path):
    sqlite3.register_adapter(datetime, lambda value: value.isoformat())
    sqlite3.register_adapter(date, lambda value: value.isoformat())
    sqlite3.register_adapter(Decimal, str)
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.executescript((Path(__file__).parent / "fixtures/ats_sqlite.sql").read_text())
    for usuario in ("uc1", "uc2", "ue1", "ue2", "ua", "ur2", "desativado"):
        conn.execute("INSERT INTO Usuarios(ID_Usuarios, Nome, Email, SenhaHash, Ativo) VALUES (?, ?, ?, ?, ?)",
                     (usuario, usuario, usuario + "@example.com", SENHA_HASH, usuario != "desativado"))
    conn.execute("UPDATE Usuarios SET EmailConfirmadoEm=CURRENT_TIMESTAMP")
    conn.executemany("INSERT INTO Candidatos(ID_Candidatos, ID_Usuarios) VALUES (?, ?)", [("c1", "uc1"), ("c2", "uc2")])
    conn.executemany("INSERT INTO Empresas(ID_Empresas, ID_Usuarios, NomeFantasia) VALUES (?, ?, ?)",
                     [("e1", "ue1", "Empresa 1"), ("e2", "ue2", "Empresa 2")])
    conn.execute("INSERT INTO Administradores(ID_Administradores, ID_Usuarios) VALUES ('admin', 'ua')")
    conn.executemany("INSERT INTO Vagas(ID_Vagas, ID_Empresas, Titulo) VALUES (?, ?, ?)",
                     [("v1", "e1", "Vaga 1"), ("v2", "e2", "Vaga 2")])
    conn.executemany("INSERT INTO Candidaturas(ID_Candidaturas, ID_Candidatos, ID_Vagas, CurriculoUrl) VALUES (?, ?, ?, ?)",
                     [("ca1", "c1", "v1", URL_A), ("ca2", "c2", "v2", URL_B)])
    conn.executemany("INSERT INTO Curriculos(ID_Curriculos, ID_Candidatos, Titulo, ArquivoUrl) VALUES (?, ?, ?, ?)",
                     [("cr1", "c1", "Meu CV", URL_A), ("cr2", "c2", "Outro CV", URL_B)])
    conn.execute("INSERT INTO Etapas_Processo VALUES ('et2', 'ca2', 3, 'Triagem', 1, NULL, NULL)")
    conn.execute("INSERT INTO Entrevistas VALUES ('en2', 'ca2', 'r2', 1, '2026-10-01T10:00:00', NULL, NULL, NULL)")
    conn.execute("INSERT INTO Recrutadores(ID_Recrutadores, ID_Empresas, ID_Usuarios) VALUES ('r2', 'e2', 'ur2')")
    conn.executemany("INSERT INTO Analises_IA(ID_Analises_IA, ID_Candidatos, ID_Vagas, ID_Candidaturas) VALUES (?, ?, ?, ?)",
                     [("a1", "c1", "v1", "ca1"), ("a2", "c2", "v2", "ca2")])
    conn.executemany("INSERT INTO Recomendacoes_Vaga(ID_Recomendacoes_Vaga, ID_Candidatos, ID_Vagas) VALUES (?, ?, ?)",
                     [("rv1", "c1", "v1"), ("rv2", "c2", "v2")])
    conn.execute("INSERT INTO Cursos VALUES ('curso', 'Python', 'Escola', 'https://example.com')")
    conn.execute("INSERT INTO Recomendacoes_Curso(ID_Recomendacoes_Curso, ID_Candidatos, ID_Cursos) VALUES ('rc2', 'c2', 'curso')")
    conn.execute("INSERT INTO Habilidades(ID_Habilidades, Nome) VALUES ('h', 'Python')")
    conn.execute("INSERT INTO Candidato_Habilidades(ID_Candidato_Habilidades,ID_Candidatos,ID_Habilidades) VALUES ('ch2', 'c2', 'h')")
    conn.execute("INSERT INTO Idiomas VALUES ('i', 'Inglês')")
    conn.execute("INSERT INTO Candidato_Idiomas(ID_Candidato_Idiomas,ID_Candidatos,ID_Idiomas) VALUES ('ci2', 'c2', 'i')")
    conn.execute("INSERT INTO Vaga_Habilidades(ID_Vaga_Habilidades,ID_Vagas) VALUES ('vh2', 'v2')")
    conn.execute("INSERT INTO Assinaturas VALUES ('s1', 'e1', 1, 'basico', 100, '2026-01-01', NULL, CURRENT_TIMESTAMP)")
    conn.execute("INSERT INTO Pagamentos(ID_Pagamentos, ID_Assinaturas, Valor) VALUES ('p1', 's1', 100)")
    conn.commit()

    def consulta(query, params=()):
        # SQLite executa as queries reais, adaptando somente placeholders e NOW().
        return conn.execute(query.replace("%s", "?").replace("NOW()", "CURRENT_TIMESTAMP").replace(" FOR UPDATE", ""), params)

    async def fetch_one(query, params=()):
        row = consulta(query, params).fetchone()
        return dict(row) if row else None

    async def fetch_all(query, params=()):
        return [dict(row) for row in consulta(query, params).fetchall()]

    async def execute(query, params=()):
        cur = consulta(query, params)
        return cur.rowcount

    @asynccontextmanager
    async def transaction():
        conn.execute("BEGIN")
        try:
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    import app.db.database as database
    monkeypatch.setattr(database, "transaction", transaction)

    async def sem_efeito(*args, **kwargs):
        return None

    for modulo in list(sys.modules.values()):
        if modulo and getattr(modulo, "__name__", "").startswith("app."):
            for nome, funcao in (("fetch_one", fetch_one), ("fetch_all", fetch_all), ("execute", execute),
                                 ("notificar_usuario", sem_efeito)):
                if hasattr(modulo, nome):
                    monkeypatch.setattr(modulo, nome, funcao)
    monkeypatch.setattr(main, "init_pool", sem_efeito)
    monkeypatch.setattr(main, "close_pool", sem_efeito)
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    for categoria in ("fotos", "logos", "curriculos"):
        (Path(settings.UPLOAD_DIR) / categoria).mkdir(parents=True)
    for nome in (ARQUIVO_A, ARQUIVO_B):
        (Path(settings.UPLOAD_DIR) / "curriculos" / nome).write_bytes(b"%PDF-1.4\nCV ficticio de teste\n")
    # Cada teste representa uma instância isolada, inclusive os buckets de rate limit.
    app.middleware_stack = None
    with TestClient(app, base_url="https://testserver") as client:
        yield client, conn
    conn.close()


@pytest.fixture
def autenticar():
    def entrar(client, usuario, tipo):
        client.cookies.clear()
        client.cookies.set(settings.SESSION_COOKIE_NAME,
                           _serializer.dumps({"id_usuario": usuario, "tipo_usuario": tipo,
                                              "auth_tag": sha256(SENHA_HASH.encode()).hexdigest()}))
        csrf = "csrf-token-de-teste"
        client.cookies.set(settings.CSRF_COOKIE_NAME, csrf)
        client.headers["X-CSRF-Token"] = csrf
    return entrar
