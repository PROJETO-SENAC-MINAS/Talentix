"""Auditoria HTTP/SQL com dados fictícios em MySQL descartável.

Não deve ser executada contra banco de desenvolvimento compartilhado/produção.
Requer variáveis de ambiente e TALENTIX_ISOLATED_TESTS=1.
Não imprime ou inclui credenciais, cookies e tokens nos resultados.
"""
import json
import os
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import bcrypt
import httpx
import pymysql
from itsdangerous import URLSafeTimedSerializer

BASE = Path(__file__).resolve().parents[2]
if os.getenv("TALENTIX_ISOLATED_TESTS") != "1":
    raise SystemExit("Execute somente em MySQL descartável, com TALENTIX_ISOLATED_TESTS=1.")
CONFIG = {k:os.environ[k] for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME", "SECRET_KEY", "IA_WORKER_TOKEN", "PAYMENT_WEBHOOK_TOKEN", "FRONTEND_ORIGIN")}
assert CONFIG["DB_HOST"] in ("127.0.0.1", "localhost")
assert CONFIG["DB_NAME"].startswith("talentix_test") or (CONFIG["DB_PORT"] == "33307" and CONFIG["DB_NAME"] == "talentix")
OUT = Path(os.getenv("TEST_RESULTS_DIR", "test-results"))
OUT.mkdir(parents=True, exist_ok=True)
records, examples = [], {}
clients = {name: httpx.Client(base_url=os.getenv("TEST_API_URL", "http://127.0.0.1:8000"), timeout=20, trust_env=False)
           for name in ("anon", "c1", "c2", "e1", "e2", "admin", "r1", "r2")}
sql = pymysql.connect(host=CONFIG["DB_HOST"], port=int(CONFIG["DB_PORT"]),
                      user=CONFIG["DB_USER"], password=CONFIG["DB_PASSWORD"],
                      database=CONFIG["DB_NAME"], autocommit=True,
                      cursorclass=pymysql.cursors.DictCursor)

def query(statement, params=()):
    with sql.cursor() as cur:
        cur.execute(statement, params)
        return cur.fetchall()

def clean(value):
    if isinstance(value, dict):
        return {k: ("[omitido]" if any(s in k.lower() for s in ("senha", "password", "token", "secret", "cookie")) else clean(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value

def route_for(method, path):
    actual = urlsplit(path).path
    for route, methods in spec["paths"].items():
        if method.lower() in methods and re.fullmatch(re.sub(r"\{[^}]+\}", "[^/]+", route), actual):
            return route
    return actual

def call(label, role, method, path, expected=200, check=None, kind="funcional", **kwargs):
    expected = [expected] if isinstance(expected, int) else list(expected)
    route = route_for(method, path)
    result = {"case": label, "kind": kind, "role": role, "method": method,
              "path": path, "route": route, "expected_status": expected}
    if "json" in kwargs:
        result["request_body"] = clean(kwargs["json"])
    try:
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            csrf = clients[role].cookies.get("talentix_csrf")
            if csrf:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault("X-CSRF-Token", csrf)
                kwargs["headers"] = headers
        response = clients[role].request(method, path, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = {"content_type": response.headers.get("content-type"), "bytes": len(response.content)}
        code_ok = response.status_code in expected
        data_ok = bool(check(body, response)) if code_ok and check else True
        result.update(status=response.status_code, passed=code_ok and data_ok,
                      data_check=data_ok, response=clean(body))
        if response.status_code < 300 and kind == "funcional":
            examples.setdefault((method, route), (path, kwargs))
    except Exception as exc:
        body = {}
        result.update(status=None, passed=False, error=f"{type(exc).__name__}: {exc}")
    records.append(result)
    if not result["passed"]:
        print(f"FALHA [{kind}]: {label}: HTTP {result.get('status')} (esperado {expected}); conteúdo={result.get('data_check')}", flush=True)
    return body

def ident(body, key):
    if key not in body:
        raise RuntimeError(f"Pré-condição ausente: {key}; resposta={clean(body)}")
    return body[key]

def seed_user(role, administrator=False):
    uid = str(uuid.uuid4())
    email = f"{role}@audit.example.com"
    query("INSERT INTO Usuarios (ID_Usuarios, Nome, Email, SenhaHash) VALUES (%s,%s,%s,%s)",
          (uid, f"Auditoria {role}", email, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()))
    if administrator:
        query("INSERT INTO Administradores (ID_Administradores, ID_Usuarios, NivelAcesso) VALUES (%s,%s,%s)",
              (str(uuid.uuid4()), uid, "ADMIN"))
    return uid

if query("SELECT ID_Usuarios FROM Usuarios LIMIT 1"):
    raise SystemExit("A suíte exige um banco de testes vazio. Nenhum dado existente foi apagado.")
PASSWORD = "Auditoria123!"
spec = clients["anon"].get("/openapi.json").json()
(OUT / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2))
failure = None
try:
    call("raiz", "anon", "GET", "/", check=lambda b,r: b["status"] == "online")
    call("saude", "anon", "GET", "/saude", check=lambda b,r: b["status"] == "ok")
    domains = call("oito dominios", "anon", "GET", "/dominios", check=lambda b,r: len(b) == 8)
    for name, values in domains.items():
        call(f"dominio {name}", "anon", "GET", f"/dominios/{name}", check=lambda b,r,n=len(values): len(b)==n)
    ids = {}
    for role in ("c1", "c2", "e1", "e2"):
        payload = {"nome": f"Auditoria {role}", "email": f"{role}@audit.example.com", "senha": PASSWORD}
        endpoint = "/auth/cadastro/candidato"
        if role.startswith("e"):
            endpoint = "/auth/cadastro/empresa"
            payload.update(razao_social=f"Empresa {role}", cnpj="12.345.678/000" + ("1-90" if role=="e1" else "2-70"))
        ids[role] = call(f"cadastro {role}", "anon", "POST", endpoint, 201, json=payload)
        ident(ids[role], "id_usuario")
    ids["admin"] = {"id_usuario": seed_user("admin", True)}
    for role in ("r1", "r2"):
        ids[role] = {"id_usuario": seed_user(role)}
    for role in ids:
        result = call(f"login {role}", role, "POST", "/auth/login", json={"email":f"{role}@audit.example.com", "senha":PASSWORD},
                      check=lambda b,r: "httponly" in r.headers.get("set-cookie", "").lower())
        call(f"sessao {role}", role, "GET", "/auth/me", check=lambda b,r: "SenhaHash" not in b)
    C1, C2 = ids["c1"]["id_candidato"], ids["c2"]["id_candidato"]
    E1, E2 = ids["e1"]["id_empresa"], ids["e2"]["id_empresa"]
    call("minha empresa", "e1", "GET", "/empresas/me", check=lambda b,r: b["ID_Empresas"]==E1)
    account = call("cadastro recrutador sem perfil candidato", "anon", "POST", "/auth/cadastro/recrutador", 201,
                   json={"nome":"Recrutador aguardando", "email":"aguardando@audit.example.com", "senha":PASSWORD})
    call("conta recrutador aguarda vinculo", "anon", "POST", "/auth/login", check=lambda b,r: b["tipo_usuario"]=="usuario",
         json={"email":"aguardando@audit.example.com", "senha":PASSWORD})
    clients["anon"].cookies.clear()
    CT = ident(call("contato gravado", "anon", "POST", "/contato", 201,
         json={"nome":"Contato ficticio", "email":"contato@audit.example.com", "assunto":"Suporte", "mensagem":"Mensagem de teste persistida."}), "id_contato")
    call("caixa contato admin", "admin", "GET", "/contato", check=lambda b,r: len(b)==1 and b[0]["ID_Contatos"]==CT)
    call("contato marcar lido", "admin", "PATCH", f"/contato/{CT}/marcar-lido")
    call("contato inexistente", "admin", "PATCH", f"/contato/{uuid.uuid4()}/marcar-lido", 404, kind="validacao")
    call("caixa contato candidato bloqueado", "c1", "GET", "/contato", 403, kind="seguranca")
    call("login incorreto", "anon", "POST", "/auth/login", 401, kind="seguranca", json={"email":"c1@audit.example.com","senha":"errada"})
    call("email duplicado", "anon", "POST", "/auth/cadastro/candidato", 409, kind="validacao", json={"nome":"Duplicado","email":"c1@audit.example.com","senha":PASSWORD})
    call("email invalido", "anon", "POST", "/auth/cadastro/candidato", 422, kind="validacao", json={"nome":"Teste","email":"invalido","senha":PASSWORD})
    call("recuperacao senha existente", "anon", "POST", "/auth/recuperar-senha", json={"email":"c2@audit.example.com"})
    call("recuperacao senha inexistente", "anon", "POST", "/auth/recuperar-senha", json={"email":"inexistente@audit.example.com"})
    call("token reset invalido", "anon", "POST", "/auth/redefinir-senha", 400, kind="seguranca", json={"token":"invalido","nova_senha":PASSWORD})
    call("candidato me", "c1", "GET", "/candidatos/me", check=lambda b,r: b["ID_Candidatos"]==C1)
    call("atualizar candidato", "c1", "PUT", f"/candidatos/{C1}", json={"titulo_profissional":"Desenvolvedor Python","cidade":"Belo Horizonte","estado":"MG","resumo":"Perfil de auditoria","experiencia_anos":1,"pretensao_salarial":2300.50})
    call("ler candidato proprio", "c1", "GET", f"/candidatos/{C1}")
    call("listar candidatos proprio", "c1", "GET", "/candidatos", check=lambda b,r: len(b)==1 and b[0]["ID_Candidatos"]==C1)
    call("listar candidatos admin", "admin", "GET", "/candidatos", check=lambda b,r: len(b)==2)
    call("outro candidato privado", "c2", "GET", f"/candidatos/{C1}", 403, kind="seguranca")
    call("empresa sem candidatura", "e2", "GET", f"/candidatos/{C1}", 403, kind="seguranca")
    call("atualizar empresa", "e1", "PUT", f"/empresas/{E1}", json={"nome_fantasia":"Talentix Audit","setor":"Tecnologia","descricao":"Dados ficticios"})
    call("listar empresas", "anon", "GET", "/empresas", check=lambda b,r: len(b)==2)
    call("ler empresa", "anon", "GET", f"/empresas/{E1}")
    call("verificar empresa", "admin", "PATCH", f"/empresas/{E1}/verificar")
    call("listar admins", "admin", "GET", "/administradores", check=lambda b,r: len(b)==1)
    R1 = ident(call("adicionar recrutador e1", "e1", "POST", f"/empresas/{E1}/recrutadores", 201, json={"id_usuario_recrutador":ids["r1"]["id_usuario"],"cargo":"RH"}), "ID_Recrutadores")
    R2 = ident(call("adicionar recrutador e2", "e2", "POST", f"/empresas/{E2}/recrutadores", 201, json={"id_usuario_recrutador":ids["r2"]["id_usuario"],"cargo":"RH"}), "ID_Recrutadores")
    call("listar recrutadores", "e1", "GET", f"/empresas/{E1}/recrutadores")
    H = ident(call("criar habilidade", "c1", "POST", "/habilidades", 201, json={"nome":"Python auditoria","categoria":"Tecnologia"}), "ID_Habilidades")
    call("listar habilidade filtros", "anon", "GET", "/habilidades?categoria=Tecnologia&busca=Py", check=lambda b,r: len(b)==1)
    CH = ident(call("adicionar habilidade perfil", "c1", "POST", f"/candidatos/{C1}/habilidades", 201, json={"id_habilidade":H,"nivel":3,"anos_experiencia":1}), "ID_Candidato_Habilidades")
    call("listar habilidade perfil", "c1", "GET", f"/candidatos/{C1}/habilidades")
    I = ident(call("criar idioma", "admin", "POST", "/idiomas", 201, json={"nome":"Português"}), "ID_Idiomas")
    call("listar idiomas", "anon", "GET", "/idiomas")
    CI = ident(call("adicionar idioma perfil", "c1", "POST", f"/candidatos/{C1}/idiomas", 201, json={"id_idioma":I,"nivel":"Nativo"}), "ID_Candidato_Idiomas")
    call("listar idioma perfil", "c1", "GET", f"/candidatos/{C1}/idiomas")
    exp_payload = {"empresa":"Empresa ficticia", "cargo":"Estagiario", "data_inicio":"2025-01-01", "data_fim":"2025-12-31", "atual":False}
    X = ident(call("criar experiencia", "c1", "POST", f"/candidatos/{C1}/experiencias", 201, json=exp_payload), "ID_Experiencias")
    call("listar experiencias", "c1", "GET", f"/candidatos/{C1}/experiencias")
    call("editar experiencia", "c1", "PUT", f"/experiencias/{X}", json={**exp_payload,"cargo":"Desenvolvedor"})
    form_payload = {"instituicao":"Senac", "curso":"Desenvolvimento de Sistemas", "nivel":"Técnico", "data_inicio":"2025-01-01", "status_formacao":"Em andamento"}
    F = ident(call("criar formacao", "c1", "POST", f"/candidatos/{C1}/formacoes", 201, json=form_payload), "ID_Formacoes")
    call("listar formacoes", "c1", "GET", f"/candidatos/{C1}/formacoes")
    call("editar formacao", "c1", "PUT", f"/formacoes/{F}", json={**form_payload,"status_formacao":"Concluído","data_conclusao":"2026-09-30"})
    pdf = b"%PDF-1.4\n%Arquivo ficticio para teste de transporte; sem dados reais.\n%%EOF\n"
    CV = call("upload curriculo", "c1", "POST", f"/candidatos/{C1}/curriculos", 201, data={"titulo":"Curriculo Auditoria","principal":"true"}, files={"arquivo":("curriculo.pdf",pdf,"application/pdf")})
    CVID, CVURL = ident(CV,"ID_Curriculos"), ident(CV,"ArquivoUrl")
    call("listar curriculos", "c1", "GET", f"/candidatos/{C1}/curriculos", check=lambda b,r: len(b)==1)
    call("download proprio curriculo", "c1", "GET", CVURL, check=lambda b,r: r.content==pdf and "no-store" in r.headers.get("cache-control", ""))
    call("download curriculo anonimo", "anon", "GET", CVURL, 401, kind="seguranca")
    call("download curriculo outro candidato", "c2", "GET", CVURL, 404, kind="seguranca")
    call("download curriculo empresa sem candidatura", "e1", "GET", CVURL, 404, kind="seguranca")
    call("upload extensao proibida", "c1", "POST", f"/candidatos/{C1}/curriculos", 400, kind="validacao", data={"titulo":"Invalido"}, files={"arquivo":("teste.exe",b"MZ","application/octet-stream")})
    call("upload maior que limite", "c1", "POST", f"/candidatos/{C1}/curriculos", 413, kind="validacao", data={"titulo":"Invalido"}, files={"arquivo":("grande.pdf",b"x"*(1024*1024+1),"application/pdf")})
    from io import BytesIO
    from PIL import Image
    image_buffer=BytesIO();Image.new('RGB',(16,16),'blue').save(image_buffer,'PNG');png=image_buffer.getvalue()
    photo = call("upload foto", "c1", "POST", "/uploads/foto-perfil", files={"arquivo":("foto.png",png,"image/png")})
    call("foto protegida", "anon", "GET", ident(photo,"url"), 401, kind="seguranca")
    call("foto do dono", "c1", "GET", ident(photo,"url"), check=lambda b,r: r.content.startswith(b'\x89PNG') and 'no-store' in r.headers.get('cache-control',''))
    logo = call("upload logo", "e1", "POST", f"/uploads/logo-empresa/{E1}", files={"arquivo":("logo.png",png,"image/png")})
    call("logo publica", "anon", "GET", ident(logo,"url"), check=lambda b,r: r.content.startswith(b'\x89PNG'))
    call("logo svg bloqueado", "e1", "POST", f"/uploads/logo-empresa/{E1}", 400, kind="seguranca", files={"arquivo":("logo.svg",b"<svg/>","image/svg+xml")})
    VP = {"id_empresa":E1,"titulo":"Desenvolvedor Python","descricao":"Vaga ficticia","modalidade":"Remoto","nivel":"Júnior","salario_min":2000,"salario_max":3000,"localizacao":"Belo Horizonte"}
    V = ident(call("criar vaga principal", "e1", "POST", "/vagas", 201, json=VP), "ID_Vagas")
    VD = ident(call("criar vaga rascunho", "e1", "POST", "/vagas", 201, json={**VP,"titulo":"Rascunho privado"}), "ID_Vagas")
    V2 = ident(call("criar vaga e2", "e2", "POST", "/vagas", 201, json={**VP,"id_empresa":E2,"titulo":"Vaga empresa dois"}), "ID_Vagas")
    call("rascunhos ausentes listagem padrao", "anon", "GET", "/vagas", check=lambda b,r: len(b)==0)
    call("rascunho nao deve aparecer no filtro publico", "anon", "GET", "/vagas?apenas_publicadas=false", check=lambda b,r: all(x["ID_Status_Vaga"]==2 for x in b), kind="regra_negocio")
    call("detalhe rascunho restrito", "anon", "GET", f"/vagas/{VD}", (403,404), kind="regra_negocio")
    call("candidatura rascunho bloqueada", "c2", "POST", "/candidaturas", (400,403,409), kind="regra_negocio", json={"id_vaga":VD})
    call("alterar vaga", "e1", "PUT", f"/vagas/{V}", json={"descricao":"Vaga ficticia para a demonstracao"})
    VH = ident(call("adicionar habilidade vaga", "e1", "POST", f"/vagas/{V}/habilidades", 201, json={"id_habilidade":H,"obrigatoria":True,"nivel_minimo":2,"peso":3}), "ID_Vaga_Habilidades")
    call("publicar vaga", "e1", "PATCH", f"/vagas/{V}/publicar")
    call("publicar vaga e2", "e2", "PATCH", f"/vagas/{V2}/publicar")
    call("buscar vagas filtros", "anon", "GET", "/vagas?titulo=Python&modalidade=Remoto&nivel=Júnior&localizacao=Belo", check=lambda b,r: len(b)==1)
    call("detalhar vaga publicada", "anon", "GET", f"/vagas/{V}", check=lambda b,r: len(b["habilidades"])==1)
    call("favoritar vaga", "c1", "POST", "/favoritos", 201, json={"id_vaga":V})
    call("favoritos", "c1", "GET", "/favoritos", check=lambda b,r: len(b)==1)
    application = call("candidatar com curriculo", "c1", "POST", "/candidaturas", 201, json={"id_vaga":V,"curriculo_url":CVURL,"carta_apresentacao":"Quero participar da demonstracao"})
    A = ident(application, "ID_Candidaturas")
    A2 = ident(call("candidatura candidato dois e2", "c2", "POST", "/candidaturas", 201, json={"id_vaga":V2}), "ID_Candidaturas")
    call("duplicata candidatura", "c1", "POST", "/candidaturas", 409, kind="validacao", json={"id_vaga":V})
    call("curriculo alheio bloqueado", "c2", "POST", "/candidaturas", 403, kind="seguranca", json={"id_vaga":V,"curriculo_url":CVURL})
    call("listar candidaturas candidato", "c1", "GET", "/candidaturas", check=lambda b,r: len(b)==1 and b[0]["ID_Candidatos"]==C1)
    call("listar candidaturas empresa", "e1", "GET", "/candidaturas", check=lambda b,r: all(x["ID_Vagas"] in (V,VD) for x in b))
    call("detalhar candidatura e etapa inicial", "e1", "GET", f"/candidaturas/{A}", check=lambda b,r: len(b["etapas"])==1)
    call("candidatura de outra empresa bloqueada", "e2", "GET", f"/candidaturas/{A}", 403, kind="seguranca")
    call("ler perfil candidato inscrito", "e1", "GET", f"/candidatos/{C1}")
    call("download empresa vinculada", "e1", "GET", CVURL, check=lambda b,r: r.content==pdf)
    call("download empresa alheia bloqueado", "e2", "GET", CVURL, 404, kind="seguranca")
    call("acervo curriculos empresa bloqueado", "e1", "GET", f"/candidatos/{C1}/curriculos", 403, kind="seguranca")
    S = ident(call("criar etapa", "e1", "POST", f"/candidaturas/{A}/etapas", 201, json={"nome":"Entrevista tecnica","ordem":2}), "ID_Etapas_Processo")
    call("concluir etapa", "e1", "PATCH", f"/etapas/{S}/concluir")
    call("reabrir etapa", "e1", "PATCH", f"/etapas/{S}/reabrir")
    call("etapa alheia bloqueada", "e2", "PATCH", f"/etapas/{S}/concluir", 403, kind="seguranca")
    interview_payload = {"id_recrutador":R1,"data_hora":"2026-10-20T10:00:00","tipo":"Online","local_ou_link":"https://example.com/entrevista"}
    EN = ident(call("agendar entrevista", "e1", "POST", f"/candidaturas/{A}/entrevistas", 201, json=interview_payload), "ID_Entrevistas")
    call("listar entrevistas candidato", "c1", "GET", f"/candidaturas/{A}/entrevistas", check=lambda b,r: len(b)==1)
    call("reagendar entrevista", "e1", "PATCH", f"/entrevistas/{EN}/reagendar?nova_data_hora=2026-10-21T10:00:00")
    call("entrevista alheia bloqueada", "e2", "PATCH", f"/entrevistas/{EN}/realizar", 403, kind="seguranca")
    call("realizar entrevista", "e1", "PATCH", f"/entrevistas/{EN}/realizar")
    call("cancelar entrevista", "e1", "PATCH", f"/entrevistas/{EN}/cancelar")
    call("recrutador outra empresa bloqueado", "e1", "POST", f"/candidaturas/{A}/entrevistas", (400,403,404), kind="regra_negocio", json={**interview_payload,"id_recrutador":R2})
    call("recrutador deve gerir candidatura", "r1", "GET", f"/candidaturas/{A}", kind="regra_negocio")
    call("avancar status", "e1", "PATCH", f"/candidaturas/{A}/status?id_status_candidatura=4", check=lambda b,r: b["ID_Status_Candidatura"]==4)
    call("status inexistente deve gerar 4xx", "e1", "PATCH", f"/candidaturas/{A}/status?id_status_candidatura=99", (400,422), kind="validacao")
    AI = ident(call("solicitar analise IA", "c1", "POST", "/analises-ia", 201, json={"id_candidato":C1,"id_vaga":V,"id_candidatura":A}), "ID_Analises_IA")
    AI2 = ident(call("solicitar outra analise IA", "c1", "POST", "/analises-ia", 201, json={"id_candidato":C1,"id_vaga":V}), "ID_Analises_IA")
    call("listar analises empresa", "e1", "GET", "/analises-ia", check=lambda b,r: len(b)==2)
    call("detalhar analise", "c1", "GET", f"/analises-ia/{AI}")
    call("IA token ausente", "anon", "PATCH", f"/analises-ia/{AI}/processar", 401, kind="seguranca", json={"score_compatibilidade":80})
    call("IA score invalido", "anon", "PATCH", f"/analises-ia/{AI}/processar", 422, kind="validacao", headers={"X-IA-Worker-Token":CONFIG["IA_WORKER_TOKEN"]}, json={"score_compatibilidade":101})
    call("IA processar callback simulado", "anon", "PATCH", f"/analises-ia/{AI}/processar", headers={"X-IA-Worker-Token":CONFIG["IA_WORKER_TOKEN"]}, json={"score_compatibilidade":85,"pontos_fortes":"Python","lacunas":"Testes","modelo_ia":"simulacao-auditoria"}, check=lambda b,r: b["ID_Status_Processamento_IA"]==3)
    call("IA falhar callback simulado", "anon", "PATCH", f"/analises-ia/{AI2}/falhar", headers={"X-IA-Worker-Token":CONFIG["IA_WORKER_TOKEN"]})
    RV = ident(call("recomendacao vaga admin", "admin", "POST", "/recomendacoes-vaga", 201, json={"id_candidato":C1,"id_vaga":V2}), "ID_Recomendacoes_Vaga")
    call("processar recomendacao callback simulado", "anon", "PATCH", f"/recomendacoes-vaga/{RV}/processar", headers={"X-IA-Worker-Token":CONFIG["IA_WORKER_TOKEN"]}, json={"score":80,"motivo":"Perfil compativel"})
    call("listar recomendacoes vagas", "c1", "GET", f"/candidatos/{C1}/recomendacoes-vaga", check=lambda b,r: len(b)==1)
    call("marcar recomendacao visualizada", "c1", "PATCH", f"/recomendacoes-vaga/{RV}/marcar-visualizada")
    course = {"titulo":"Testes de API","plataforma":"Senac","url":"https://example.com/curso","categoria":"Tecnologia","nivel":"Básico","carga_horaria":20}
    CO = ident(call("criar curso", "admin", "POST", "/cursos", 201, json=course), "ID_Cursos")
    call("listar cursos filtros", "anon", "GET", "/cursos?categoria=Tecnologia&nivel=Básico", check=lambda b,r: len(b)==1)
    call("detalhar curso", "anon", "GET", f"/cursos/{CO}")
    call("editar curso", "admin", "PUT", f"/cursos/{CO}", json={**course,"carga_horaria":30})
    RC = ident(call("recomendar curso", "admin", "POST", "/recomendacoes-curso", 201, json={"id_candidato":C1,"id_curso":CO,"motivo":"Complementar testes","prioridade":1}), "ID_Recomendacoes_Curso")
    call("listar recomendacoes curso", "c1", "GET", f"/candidatos/{C1}/recomendacoes-curso", check=lambda b,r: len(b)==1)
    call("concluir recomendacao curso", "c1", "PATCH", f"/recomendacoes-curso/{RC}/concluir")
    M = ident(call("mensagem contextualizada", "e1", "POST", "/mensagens", 201, json={"id_destinatario":ids["c1"]["id_usuario"],"conteudo":"Podemos agendar entrevista?","id_candidatura":A}), "ID_Mensagens")
    call("ler conversa", "c1", "GET", f"/mensagens/conversas/{ids['e1']['id_usuario']}", check=lambda b,r: len(b)==1)
    call("ler mensagens nao lidas", "c1", "GET", "/mensagens?apenas_nao_lidas=true", check=lambda b,r: len(b)==1)
    call("marcar mensagem lida", "c1", "PATCH", f"/mensagens/{M}/marcar-lida")
    call("marcar mensagem alheia bloqueada", "c2", "PATCH", f"/mensagens/{M}/marcar-lida", 403, kind="seguranca")
    call("contexto candidatura alheia em mensagem bloqueado", "c2", "POST", "/mensagens", (400,403,404), kind="regra_negocio", json={"id_destinatario":ids["e1"]["id_usuario"],"conteudo":"Contexto indevido","id_candidatura":A})
    call("aprovar candidatura", "e1", "PATCH", f"/candidaturas/{A}/status?id_status_candidatura=5")
    AV = ident(call("avaliacao participante", "c1", "POST", "/avaliacoes", 201, json={"id_candidatura":A,"id_empresa":E1,"nota":5,"comentario":"Boa entrevista"}), "ID_Avaliacoes")
    call("listar avaliacoes", "anon", "GET", f"/avaliacoes?id_empresa={E1}")
    call("avaliacao nota invalida", "c1", "POST", "/avaliacoes", 422, kind="validacao", json={"id_candidatura":A,"id_empresa":E1,"nota":6})
    call("avaliacao por terceiro bloqueada", "c2", "POST", "/avaliacoes", (400,403,404), kind="seguranca", json={"id_candidatura":A,"id_empresa":E1,"nota":1,"comentario":"Terceiro nao participante"})
    call("avaliacao alvo incompativel bloqueada", "c1", "POST", "/avaliacoes", (400,403,422), kind="regra_negocio", json={"id_candidatura":A,"id_empresa":E2,"nota":1})
    D = ident(call("criar denuncia", "c1", "POST", "/denuncias", 201, json={"id_usuario_alvo":ids["e1"]["id_usuario"],"id_vaga":V,"motivo":"Teste de moderacao","descricao":"Somente auditoria"}), "ID_Denuncias")
    call("listar denuncias admin", "admin", "GET", "/denuncias", check=lambda b,r: len(b)==1)
    call("listar minhas denuncias", "c1", "GET", "/denuncias/minhas", check=lambda b,r: len(b)==1)
    call("resolver denuncia", "admin", "PATCH", f"/denuncias/{D}/resolver", json={"id_status_denuncia":3}, check=lambda b,r: b["ID_Status_Denuncia"]==3)
    call("resolucao nao aceita status aberto", "admin", "PATCH", f"/denuncias/{D}/resolver", (400,422), kind="regra_negocio", json={"id_status_denuncia":1})
    N = ident(call("criar notificacao manual", "admin", "POST", "/notificacoes", 201, json={"id_usuario":ids["c1"]["id_usuario"],"titulo":"Auditoria","mensagem":"Mensagem manual","tipo":"teste"}), "ID_Notificacoes")
    call("listar notificacoes", "c1", "GET", "/notificacoes?apenas_nao_lidas=true", check=lambda b,r: len(b)>1)
    call("notificacao de terceiro bloqueada", "c2", "PATCH", f"/notificacoes/{N}/marcar-lida", 403, kind="seguranca")
    call("marcar notificacao lida", "c1", "PATCH", f"/notificacoes/{N}/marcar-lida")
    call("marcar todas notificacoes", "c1", "PATCH", "/notificacoes/marcar-todas-lidas")
    call("confirmar notificacoes lidas", "c1", "GET", "/notificacoes?apenas_nao_lidas=true", check=lambda b,r: b==[])
    AS = ident(call("criar assinatura", "admin", "POST", "/assinaturas", 201, json={"id_empresa":E1,"plano":"Demonstracao","valor":99.90,"inicio":"2026-09-30","fim":"2026-10-30"}), "ID_Assinaturas")
    call("ler assinatura empresa", "e1", "GET", f"/empresas/{E1}/assinatura")
    call("renovar assinatura", "admin", "PATCH", f"/assinaturas/{AS}/renovar?nova_data_fim=2026-11-30")
    PA = ident(call("registrar pagamento", "e1", "POST", "/pagamentos", 201, json={"id_assinatura":AS,"valor":99.90,"metodo":"PIX","transacao_id":"audit-001"}), "ID_Pagamentos")
    call("listar pagamentos", "e1", "GET", f"/assinaturas/{AS}/pagamentos", check=lambda b,r: len(b)==1)
    call("pagamento outra empresa bloqueado", "e2", "GET", f"/assinaturas/{AS}/pagamentos", 403, kind="seguranca")
    call("webhook sem token bloqueado", "e1", "PATCH", f"/pagamentos/{PA}/processar?aprovado=true", 401, kind="seguranca")
    call("webhook token errado bloqueado", "anon", "PATCH", f"/pagamentos/{PA}/processar?aprovado=true", 401, kind="seguranca", headers={"X-Payment-Webhook-Token":"incorreto"})
    call("processar pagamento callback simulado", "anon", "PATCH", f"/pagamentos/{PA}/processar?aprovado=true", headers={"X-Payment-Webhook-Token":CONFIG["PAYMENT_WEBHOOK_TOKEN"]}, check=lambda b,r: b["ID_Status_Pagamento"]==2)
    before = query("SELECT COUNT(*) AS total FROM Notificacoes WHERE ID_Usuarios=%s", (ids["e1"]["id_usuario"],))[0]["total"]
    call("webhook repetido idempotente", "anon", "PATCH", f"/pagamentos/{PA}/processar?aprovado=true", headers={"X-Payment-Webhook-Token":CONFIG["PAYMENT_WEBHOOK_TOKEN"]}, kind="regra_negocio", check=lambda b,r: query("SELECT COUNT(*) AS total FROM Notificacoes WHERE ID_Usuarios=%s",(ids["e1"]["id_usuario"],))[0]["total"]==before)
    call("pagamento negativo bloqueado", "e1", "POST", "/pagamentos", (400,422), kind="validacao", json={"id_assinatura":AS,"valor":-1})
    call("pagamento transacao duplicada bloqueado", "e1", "POST", "/pagamentos", (400,409,422), kind="regra_negocio", json={"id_assinatura":AS,"valor":99.90,"transacao_id":"audit-001"})
    PR = ident(call("registrar pagamento recusa", "e1", "POST", "/pagamentos", 201, json={"id_assinatura":AS,"valor":99.90,"transacao_id":"audit-refused"}), "ID_Pagamentos")
    call("pagamento recusado nao tem data pago", "anon", "PATCH", f"/pagamentos/{PR}/processar?aprovado=false", headers={"X-Payment-Webhook-Token":CONFIG["PAYMENT_WEBHOOK_TOKEN"]}, kind="regra_negocio", check=lambda b,r: b["ID_Status_Pagamento"]==3 and b["PagoEm"] is None)
    call("estornar pagamento simulado", "admin", "PATCH", f"/pagamentos/{PA}/estornar")
    call("cancelar assinatura", "e1", "PATCH", f"/assinaturas/{AS}/cancelar")
    call("dashboard candidato", "c1", "GET", "/dashboard/candidato", check=lambda b,r: b["total_candidaturas"]==1)
    call("dashboard empresa", "e1", "GET", f"/dashboard/empresa/{E1}", check=lambda b,r: b["total_vagas"]==2)
    call("dashboard admin", "admin", "GET", "/dashboard/admin", check=lambda b,r: b["total_candidatos"]==2)
    call("estado maior que dois caracteres tratado", "c1", "PUT", f"/candidatos/{C1}", (400,422), kind="validacao", json={"estado":"MINAS GERAIS"})
    call("anos experiencia negativos tratados", "c1", "PUT", f"/candidatos/{C1}", (400,422), kind="validacao", json={"experiencia_anos":-1})
    call("habilidade duplicada tratada", "c1", "POST", f"/candidatos/{C1}/habilidades", (400,409), kind="validacao", json={"id_habilidade":H})
    call("recrutador usuario inexistente tratado", "e1", "POST", f"/empresas/{E1}/recrutadores", (400,404), kind="validacao", json={"id_usuario_recrutador":str(uuid.uuid4())})
    call("curso inexistente ao editar", "admin", "PUT", f"/cursos/{uuid.uuid4()}", 404, kind="validacao", json=course)
    call("empresa inexistente ao verificar", "admin", "PATCH", f"/empresas/{uuid.uuid4()}/verificar", 404, kind="validacao")
    call("pagamento inexistente ao estornar", "admin", "PATCH", f"/pagamentos/{uuid.uuid4()}/estornar", 404, kind="validacao")
    VC = ident(call("criar vaga salario confidencial", "e1", "POST", "/vagas", 201, json={**VP,"titulo":"Vaga confidencial","salario_confidencial":True}), "ID_Vagas")
    call("publicar vaga confidencial", "e1", "PATCH", f"/vagas/{VC}/publicar")
    call("salario confidencial oculto na API publica", "anon", "GET", f"/vagas/{VC}", kind="regra_negocio", check=lambda b,r: b.get("SalarioMin") is None and b.get("SalarioMax") is None)
    call("pausar vaga", "e1", "PATCH", f"/vagas/{V}/pausar")
    call("candidatura vaga pausada bloqueada", "c2", "POST", "/candidaturas", (400,403,409), kind="regra_negocio", json={"id_vaga":V})
    call("encerrar vaga", "e2", "PATCH", f"/vagas/{V2}/encerrar")
    call("candidatura vaga encerrada bloqueada", "c1", "POST", "/candidaturas", (400,403,409), kind="regra_negocio", json={"id_vaga":V2})
    call("remover favorito", "c1", "DELETE", f"/favoritos/{V}")
    call("remover habilidade perfil", "c1", "DELETE", f"/candidatos/{C1}/habilidades/{CH}")
    call("remover idioma perfil", "c1", "DELETE", f"/candidatos/{C1}/idiomas/{CI}")
    call("remover experiencia", "c1", "DELETE", f"/experiencias/{X}")
    call("remover formacao", "c1", "DELETE", f"/formacoes/{F}")
    call("remover habilidade vaga", "e1", "DELETE", f"/vagas/{V}/habilidades/{VH}")
    call("desativar habilidade", "admin", "DELETE", f"/habilidades/{H}")
    call("habilidade desativada nao e reutilizada", "c1", "POST", "/habilidades", 409, kind="regra_negocio", json={"nome":"Python auditoria"})
    call("habilidade desativada nao entra no perfil", "c1", "POST", f"/candidatos/{C1}/habilidades", 404, kind="regra_negocio", json={"id_habilidade":H})
    call("habilidade desativada nao entra na vaga", "e1", "POST", f"/vagas/{V}/habilidades", 404, kind="regra_negocio", json={"id_habilidade":H})
    call("remover curriculo", "c1", "DELETE", f"/curriculos/{CVID}")
    call("download curriculo desativado bloqueado", "c1", "GET", CVURL, 404, kind="seguranca")
    call("desativar curso", "admin", "DELETE", f"/cursos/{CO}")
    call("remover mensagem", "c1", "DELETE", f"/mensagens/{M}")
    call("remover avaliacao", "c1", "DELETE", f"/avaliacoes/{AV}")
    call("remover notificacao", "c1", "DELETE", f"/notificacoes/{N}")
    call("remover recrutador", "e1", "DELETE", f"/recrutadores/{R1}")
    call("cancelar candidatura", "c1", "DELETE", f"/candidaturas/{A}")
    call("excluir vaga", "e1", "DELETE", f"/vagas/{V}")
    call("desativar candidato", "c2", "DELETE", f"/candidatos/{C2}")
    call("candidato desativado deve perder acesso", "c2", "GET", "/dashboard/candidato", (401,403,404), kind="seguranca")
    call("desativar empresa", "e2", "DELETE", f"/empresas/{E2}")
    call("empresa desativada deve perder permissao", "e2", "PATCH", f"/vagas/{V2}/publicar", (401,403,404), kind="seguranca")
    call("logout", "c1", "POST", "/auth/logout")
    call("sessao encerrada", "c1", "GET", "/auth/me", 401, kind="seguranca")
    current_hash = query("SELECT SenhaHash FROM Usuarios WHERE ID_Usuarios=%s",(ids["c1"]["id_usuario"],))[0]["SenhaHash"]
    reset = URLSafeTimedSerializer(CONFIG["SECRET_KEY"],salt="talentix-reset-senha").dumps({"id_usuario":ids["c1"]["id_usuario"],"fingerprint":current_hash[-16:]})
    new_password = "NovaSenhaAuditoria123!"
    call("reset valido sem SMTP externo", "anon", "POST", "/auth/redefinir-senha", json={"token":reset,"nova_senha":new_password})
    call("reset token uso unico", "anon", "POST", "/auth/redefinir-senha", 400, kind="seguranca", json={"token":reset,"nova_senha":new_password})
    call("senha anterior rejeitada apos reset", "anon", "POST", "/auth/login", 401, kind="seguranca", json={"email":"c1@audit.example.com","senha":PASSWORD})
    call("senha nova autentica apos reset", "c1", "POST", "/auth/login", json={"email":"c1@audit.example.com","senha":new_password})
    public = {("GET", p) for p in ("/", "/saude", "/dominios", "/dominios/{chave}", "/empresas", "/empresas/{id_empresa}", "/vagas", "/vagas/{id_vaga}", "/habilidades", "/idiomas", "/cursos", "/cursos/{id_curso}", "/avaliacoes")}
    public.update(("POST", "/auth/" + p) for p in ("cadastro/candidato", "cadastro/empresa", "login", "recuperar-senha", "redefinir-senha"))
    public.update({("POST", "/auth/cadastro/recrutador"), ("POST", "/contato")})
    public.add(("POST", "/auth/logout"))  # Logout sem sessão é uma operação idempotente válida.
    for (method, route), (path, kwargs) in list(examples.items()):
        if (method, route) in public or route.startswith("/uploads/fotos/") or route.startswith("/uploads/logos/"):
            continue
        guard_kwargs = {k:v for k,v in kwargs.items() if k != "headers"}
        call(f"anonimo bloqueado: {method} {route}", "anon", method, path, 401, kind="seguranca_anonima", **guard_kwargs)
    cors = clients["anon"].options("/auth/login", headers={"Origin":CONFIG["FRONTEND_ORIGIN"],"Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"content-type"})
    records.append({"case":"CORS origem configurada", "kind":"infraestrutura", "method":"OPTIONS", "path":"/auth/login", "status":cors.status_code,"passed":cors.status_code==200 and cors.headers.get("access-control-allow-origin")==CONFIG["FRONTEND_ORIGIN"] and cors.headers.get("access-control-allow-credentials")=="true"})
    cors = clients["anon"].options("/auth/login", headers={"Origin":"https://origem-alheia.example","Access-Control-Request-Method":"POST"})
    records.append({"case":"CORS origem alheia rejeitada", "kind":"infraestrutura", "method":"OPTIONS", "path":"/auth/login", "status":cors.status_code,"passed":cors.status_code==400 and "access-control-allow-origin" not in cors.headers})
except Exception as exc:
    failure = f"{type(exc).__name__}: {exc}"
    print("EXECUCAO INTERROMPIDA:", failure, flush=True)
finally:
    operations = {(m.upper(),p) for p,ms in spec["paths"].items() for m in ms if m in ("get","post","put","patch","delete")}
    touched = {(r["method"],r.get("route")) for r in records}
    functional = {(r["method"],r.get("route")) for r in records if r["kind"]=="funcional" and r["passed"]}
    summary = {"database":"MySQL 8 isolado", "commit":os.getenv("GITHUB_SHA", "working-tree"),
               "cases":len(records),
               "passed":sum(r["passed"] for r in records), "failed":sum(not r["passed"] for r in records),
               "kinds":dict(Counter(r["kind"] for r in records)), "openapi_operations":len(operations),
               "operations_exercised":len(operations & touched), "operations_functional_success":len(operations & functional),
               "unexercised":sorted(operations-touched), "without_functional_success":sorted(operations-functional),
               "execution_error":failure, "external_services":"SMTP desativado; worker e gateway simulados apenas nos callbacks internos"}
    (OUT / "api-tests.json").write_text(json.dumps({"summary":summary,"cases":records}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    for client in clients.values():
        client.close()
    sql.close()
sys.exit(2 if failure else (1 if summary["failed"] else 0))
