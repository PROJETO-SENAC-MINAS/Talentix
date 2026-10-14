"""Fluxo integrado em MySQL real descartável, inclusive concorrência e worker."""

import io, json, os, subprocess, sys, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx, pymysql
from pypdf import PdfWriter

if os.getenv("TALENTIX_ISOLATED_TESTS") != "1" or not os.environ.get(
    "DB_NAME", ""
).startswith("talentix_test"):
    raise SystemExit("Somente MySQL descartável de testes.")
API = os.getenv("TEST_API_URL", "http://127.0.0.1:8000")
nonce = uuid.uuid4().hex[:10]
records = []
clients = []
db = pymysql.connect(
    host=os.environ["DB_HOST"],
    port=int(os.environ["DB_PORT"]),
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    database=os.environ["DB_NAME"],
    autocommit=True,
    cursorclass=pymysql.cursors.DictCursor,
)


def q(sql, args=()):
    with db.cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


class Client(httpx.Client):
    def request(self, method, url, **kw):
        if method in {"POST", "PUT", "PATCH", "DELETE"} and self.cookies.get(
            "talentix_csrf"
        ):
            kw["headers"] = {
                **kw.get("headers", {}),
                "X-CSRF-Token": self.cookies.get("talentix_csrf"),
            }
        return super().request(method, url, **kw)


def call(c, method, path, expected=200, **kw):
    r = c.request(method, path, **kw)
    records.append(
        {
            "method": method,
            "path": path,
            "status": r.status_code,
            "passed": r.status_code == expected,
        }
    )
    assert r.status_code == expected, (method, path, r.status_code, r.text[:500])
    return r.json() if "json" in r.headers.get("content-type", "") else r


def account(role):
    c = Client(base_url=API, timeout=30, trust_env=False)
    clients.append(c)
    email = f"platform-{role}-{len(clients)}-{nonce}@example.com"
    data = {
        "nome": "Teste Plataforma " + role,
        "email": email,
        "senha": "Plataforma123!",
    }
    if role == "empresa":
        data.update(
            razao_social="Empresa Plataforma",
            nome_fantasia="Empresa Plataforma",
            cnpj=str(int(uuid.uuid4().hex[:12], 16)).zfill(14)[-14:],
        )
    ids = call(c, "POST", "/auth/cadastro/" + role, 201, json=data)
    q(
        "UPDATE Usuarios SET EmailConfirmadoEm=NOW() WHERE ID_Usuarios=%s",
        (ids["id_usuario"],),
    )
    call(c, "POST", "/auth/login", json={"email": email, "senha": data["senha"]})
    return c, ids, email


def worker():
    p = subprocess.run(
        [sys.executable, "-m", "app.worker_platform", "--once"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stderr[-1000:]


try:
    e, ed, _ = account("empresa")
    other, od, _ = account("empresa")
    c, cd, _ = account("candidato")
    r, rd, re = account("recrutador")
    eid = ed["id_empresa"]
    cid = cd["id_candidato"]
    recruiter = call(
        e,
        "POST",
        f"/empresas/{eid}/recrutadores",
        201,
        json={"id_usuario_recrutador": rd["id_usuario"], "cargo": "Entrevistador"},
    )["ID_Recrutadores"]
    vid = call(
        e,
        "POST",
        "/vagas",
        201,
        json={
            "id_empresa": eid,
            "titulo": "Python Plataforma " + nonce,
            "descricao": "Python APIs e SQL",
            "modalidade": "Remoto",
            "localizacao": "Brasil",
            "salario_confidencial": True,
            "salario_min": 9999,
        },
    )["ID_Vagas"]
    call(e, "PATCH", f"/vagas/{vid}/publicar")
    app = call(c, "POST", "/candidaturas", 201, json={"id_vaga": vid})[
        "ID_Candidaturas"
    ]
    call(e, "POST", f"/ats/vagas/{vid}/inicializar")
    call(
        c,
        "POST",
        "/privacidade/consentimentos",
        201,
        json={"finalidade": "comunicacao_em_massa", "autorizado": True},
    )
    call(
        c,
        "POST",
        "/privacidade/consentimentos",
        201,
        json={"finalidade": "emails", "autorizado": True},
    )
    batch = {
        "candidaturas": [app],
        "conteudo": "Mensagem de teste integrada",
        "chave": "lote-" + nonce,
    }
    call(e, "POST", "/comunicacao/lotes", 201, json=batch)
    assert call(e, "POST", "/comunicacao/lotes", 201, json=batch)["repetido"]
    assert (
        q("SELECT COUNT(*) AS n FROM Mensagens WHERE ID_Candidaturas=%s", (app,))[0][
            "n"
        ]
        == 1
    )
    call(other, "GET", f"/comunicacao/candidaturas/{app}/timeline", 403)
    call(c, "GET", f"/comunicacao/candidaturas/{app}/timeline")
    future = (
        (datetime.now(timezone.utc) + timedelta(days=40))
        .replace(microsecond=0)
        .isoformat()
    )
    schedule = {
        "id_candidatura": app,
        "id_recrutador": recruiter,
        "data_hora": future,
        "duracao_min": 45,
        "fuso": "America/Sao_Paulo",
        "chave": "agenda-" + nonce,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        bookings = list(
            pool.map(lambda _: call(e, "POST", "/agenda", 201, json=schedule), range(2))
        )
    interview = bookings[0]["ID_Entrevistas"]
    assert bookings[1]["ID_Entrevistas"] == interview
    call(e, "POST", "/agenda", 409, json={**schedule, "chave": "conflito-" + nonce})
    call(
        e,
        "POST",
        f"/candidaturas/{app}/entrevistas",
        409,
        json={"id_recrutador": recruiter, "data_hora": future},
    )
    call(
        other,
        "PUT",
        f"/agenda/{interview}",
        403,
        json={"acao": "cancelar", "versao": 1},
    )
    call(c, "PUT", f"/agenda/{interview}", 403, json={"acao": "cancelar", "versao": 1})
    assert all("Observacoes" not in en for en in call(c, "GET", "/agenda"))
    rule = call(
        e,
        "POST",
        "/automacoes",
        201,
        json={
            "nome": "Revisar triagem",
            "gatilho": "mudanca_etapa",
            "acao": "tarefa",
            "conteudo": "Revisar candidato",
            "ativa": True,
        },
    )
    board = call(e, "GET", f"/ats/vagas/{vid}/pipeline")
    call(
        e,
        "PUT",
        f"/ats/candidaturas/{app}/card",
        json={"id_etapa": board["etapas"][1]["ID_Etapa"], "versao": 1, "ordem": 0},
    )
    worker()
    worker()
    assert (
        q(
            "SELECT COUNT(*) AS n FROM Automacao_Execucoes WHERE ID_Regra=%s",
            (rule["id"],),
        )[0]["n"]
        == 1
    )
    call(e, "GET", "/automacoes/registros/tarefas")
    explanation = call(
        c,
        "POST",
        "/inteligencia/analises",
        201,
        json={"id_candidato": cid, "id_vaga": vid},
    )
    assert explanation["modelo"].endswith("v2") and explanation["revisao_humana"]
    call(other, "GET", f"/inteligencia/candidatos/{cid}/vagas/{vid}", 403)
    slug = "empresa-" + nonce
    call(
        e,
        "PUT",
        "/publicacao/empresa",
        json={"slug": slug, "publicada": True, "cultura": "Aprendizado e colaboração"},
    )
    jobslug = "vaga-" + nonce
    call(
        e,
        "PUT",
        f"/publicacao/vagas/{vid}",
        json={"slug": jobslug, "expira_em": future},
    )
    public = call(c, "GET", "/p/vaga/" + jobslug)
    assert "JobPosting" in public.text and "9999" not in public.text
    call(e, "GET", "/analytics")
    assert (
        call(e, "GET", "/analytics/exportar/csv")
        .headers["content-type"]
        .startswith("text/csv")
    )
    assert call(e, "GET", "/analytics/exportar/pdf").content.startswith(b"%PDF-")
    call(other, "GET", "/analytics?id_empresa=" + eid, 403)
    members = call(e, "GET", "/organizacoes/membros")
    owner = next(m for m in members if m["ID_Usuarios"] == ed["id_usuario"])
    call(
        e,
        "PUT",
        "/organizacoes/membros/" + ed["id_usuario"],
        409,
        json={"papel": "recrutador", "ativo": True, "versao": owner["Versao"]},
    )
    invite = call(
        e,
        "POST",
        "/organizacoes/convites",
        201,
        json={"email": re, "papel": "hiring_manager"},
    )
    call(r, "POST", "/organizacoes/convites/aceitar", json={"token": invite["token"]})
    call(
        r,
        "PUT",
        "/vagas/" + vid,
        403,
        headers={"X-Organization-ID": eid},
        json={"titulo": "Não autorizado"},
    )
    call(r, "GET", "/analytics", headers={"X-Organization-ID": eid})
    pdf = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf)
    attachment = call(
        e,
        "POST",
        f"/comunicacao/candidaturas/{app}/anexos",
        201,
        files={"arquivo": ("teste.pdf", pdf.getvalue(), "application/pdf")},
    )
    call(c, "GET", attachment["url"])
    call(other, "GET", attachment["url"], 403)
    export = call(c, "GET", "/privacidade/meus-dados")
    assert "SenhaHash" not in json.dumps(export)
    request = call(
        c,
        "POST",
        "/privacidade/exclusao",
        201,
        json={"senha": "Plataforma123!", "confirmacao": "EXCLUIR MINHA CONTA"},
    )
    call(c, "DELETE", "/privacidade/solicitacoes/" + request["id"])
    # Dados necessários ao navegador, somente fictícios; nenhum token/senha é salvo.
    out = Path(os.environ.get("TEST_RESULTS_DIR", "test-results"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "platform-fixture.json").write_text(
        json.dumps(
            {
                "nonce": nonce,
                "empresa": eid,
                "candidato": cid,
                "vaga": vid,
                "candidatura": app,
                "entrevista": interview,
                "slug_empresa": slug,
                "slug_vaga": jobslug,
                "email_empresa": f"platform-empresa-1-{nonce}@example.com",
                "email_candidato": f"platform-candidato-3-{nonce}@example.com",
            }
        )
    )
    print(
        f"Plataforma integrada: {len(records)} operações MySQL aprovadas, incluindo concorrência, isolamento e worker."
    )
finally:
    out = Path(os.environ.get("TEST_RESULTS_DIR", "test-results"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "platform-api-tests.json").write_text(json.dumps(records, indent=2))
    for client in clients:
        client.close()
    db.close()
