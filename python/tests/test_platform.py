"""Regressões do fluxo integrado, permissões negativas e idempotência observável."""

import asyncio
import json
from datetime import datetime, timezone, timedelta
from app import worker_platform
from app.core import privacy
from app.routers.intelligence import explicar


def setup(db):
    db.execute(
        "INSERT INTO Recrutadores(ID_Recrutadores,ID_Empresas,ID_Usuarios) VALUES ('r1','e1','ue1')"
    )
    db.execute(
        "INSERT INTO Org_Membros(ID_Empresas,ID_Usuarios,Papel) VALUES ('e1','ue1','owner')"
    )
    db.execute(
        "INSERT INTO Org_Membros(ID_Empresas,ID_Usuarios,Papel) VALUES ('e2','ue2','owner')"
    )
    db.commit()


def agendamento(**kw):
    return {
        "id_candidatura": "ca1",
        "id_recrutador": "r1",
        "data_hora": (datetime.now(timezone.utc) + timedelta(days=10))
        .replace(microsecond=0)
        .isoformat(),
        "duracao_min": 45,
        "fuso": "America/Sao_Paulo",
        "chave": "agenda-regressao-1",
        **kw,
    }


def test_tenant_selector_never_grants_access(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "uc1", "candidato")
    assert c.get("/auth/me", headers={"X-Organization-ID": "e1"}).status_code == 403
    assert c.get("/organizacoes").json() == []
    autenticar(c, "ue1", "empresa")
    assert c.get("/organizacoes/contexto").json()["papel"] == "owner"
    assert c.get("/organizacoes/contexto?id_empresa=e2").status_code == 403
    assert c.get("/auth/me", headers={"X-Organization-ID": "e2"}).status_code == 403


def test_rbac_applies_to_legacy_routes_and_revocation(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    db.execute(
        "INSERT INTO Org_Membros(ID_Empresas,ID_Usuarios,Papel) VALUES ('e1','uc2','hiring_manager')"
    )
    db.commit()
    autenticar(c, "uc2", "candidato")
    c.headers["X-Organization-ID"] = "e1"
    assert c.get("/empresas/me").status_code == 200
    assert c.put("/vagas/v1", json={"titulo": "Invasão"}).status_code == 403
    assert (
        c.post(
            "/comunicacao/lotes",
            json={"candidaturas": ["ca1"], "conteudo": "teste", "chave": "chave-12345"},
        ).status_code
        == 403
    )
    db.execute("UPDATE Org_Membros SET Ativo=0 WHERE ID_Usuarios='uc2'")
    db.commit()
    assert c.get("/empresas/me").status_code == 403


def test_last_owner_and_version_conflict(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    assert (
        c.put(
            "/organizacoes/membros/ue1",
            json={"papel": "recrutador", "ativo": True, "versao": 1},
        ).status_code
        == 409
    )
    assert (
        c.put(
            "/organizacoes/membros/ue1",
            json={"papel": "owner", "ativo": True, "versao": 9},
        ).status_code
        == 409
    )
    assert (
        db.execute("SELECT Papel FROM Org_Membros WHERE ID_Usuarios='ue1'").fetchone()[
            0
        ]
        == "owner"
    )


def test_invitation_is_email_bound_and_one_use(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    r = c.post(
        "/organizacoes/convites",
        json={"email": "uc2@example.com", "papel": "entrevistador"},
    )
    assert r.status_code == 201
    token = r.json()["token"]
    assert token not in db.execute("SELECT TokenHash FROM Org_Convites").fetchone()[0]
    autenticar(c, "uc1", "candidato")
    assert (
        c.post("/organizacoes/convites/aceitar", json={"token": token}).status_code
        == 403
    )
    autenticar(c, "uc2", "candidato")
    assert (
        c.post("/organizacoes/convites/aceitar", json={"token": token}).status_code
        == 200
    )
    assert (
        c.post("/organizacoes/convites/aceitar", json={"token": token}).status_code
        == 403
    )
    c.headers["X-Organization-ID"] = "e1"
    assert (
        c.get("/organizacoes/contexto?id_empresa=e1").json()["papel"] == "entrevistador"
    )
    assert c.get("/agenda?id_empresa=e1").status_code == 200
    assert c.get("/organizacoes/membros?id_empresa=e1").status_code == 403
    assert c.get("/candidatos/c1").status_code == 403
    assert c.post("/agenda", json=agendamento()).status_code == 403
    assert c.get("/comunicacao/candidaturas").status_code == 403


def test_manual_agenda_idempotence_conflict_timezone_and_isolation(
    ambiente, autenticar
):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    data = agendamento()
    r = c.post("/agenda", json=data)
    assert r.status_code == 201, r.text
    id = r.json()["ID_Entrevistas"]
    assert c.post("/agenda", json=data).json()["ID_Entrevistas"] == id
    assert c.post("/agenda", json={**data, "duracao_min": 60}).status_code == 409
    assert (
        c.post("/agenda", json={**data, "chave": "segunda-entrevista"}).status_code
        == 409
    )
    assert (
        db.execute(
            "SELECT COUNT(*) FROM Entrevistas WHERE ID_Candidaturas=?", ("ca1",)
        ).fetchone()[0]
        == 1
    )
    assert (
        c.post(
            "/agenda",
            json={**agendamento(chave="outro-fuso-123"), "fuso": "Inexistente/Local"},
        ).status_code
        == 422
    )
    assert (
        c.put("/agenda/" + id, json={"acao": "cancelar", "versao": 9}).status_code
        == 409
    )
    autenticar(c, "ue2", "empresa")
    assert (
        c.put("/agenda/" + id, json={"acao": "cancelar", "versao": 1}).status_code
        == 403
    )
    autenticar(c, "uc1", "candidato")
    rows = c.get("/agenda").json()
    assert len(rows) == 1 and rows[0]["DataHoraUtc"].endswith("Z")
    assert "Observacoes" not in rows[0]
    assert (
        c.put("/agenda/" + id, json={"acao": "cancelar", "versao": 1}).status_code
        == 403
    )


def test_bulk_consent_deduplication_and_atomic_authorization(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    data = {
        "candidaturas": ["ca1"],
        "conteudo": "<img src=x onerror=alert(1)>",
        "chave": "lote-primeiro-123",
    }
    assert c.post("/comunicacao/lotes", json=data).json()["ignorado"] == 1
    autenticar(c, "uc1", "candidato")
    assert (
        c.post(
            "/privacidade/consentimentos",
            json={"finalidade": "comunicacao_em_massa", "autorizado": True},
        ).status_code
        == 201
    )
    autenticar(c, "ue1", "empresa")
    data["chave"] = "lote-segundo-123"
    first = c.post("/comunicacao/lotes", json=data)
    assert first.status_code == 201 and first.json()["enviado"] == 1
    assert c.post("/comunicacao/lotes", json=data).json()["repetido"] is True
    assert db.execute("SELECT COUNT(*) FROM Mensagens").fetchone()[0] == 1
    assert (
        c.post(
            "/comunicacao/lotes",
            json={**data, "candidaturas": ["ca1", "ca2"], "chave": "lote-terceiro-123"},
        ).status_code
        == 403
    )
    assert db.execute("SELECT COUNT(*) FROM Comunicacao_Lotes").fetchone()[0] == 2
    autenticar(c, "uc1", "candidato")
    timeline = c.get("/comunicacao/candidaturas/ca1/timeline")
    assert timeline.status_code == 200
    assert any(x["tipo"] == "mensagem" for x in timeline.json())
    assert c.get("/comunicacao/candidaturas/ca2/timeline").status_code == 403


def test_automation_runs_once_and_never_changes_application(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    assert c.post("/ats/vagas/v1/inicializar").status_code == 200
    b = c.get("/ats/vagas/v1/pipeline").json()
    stage = b["etapas"][1]["ID_Etapa"]
    r = c.post(
        "/automacoes",
        json={
            "nome": "Avisar triagem",
            "gatilho": "mudanca_etapa",
            "acao": "tarefa",
            "conteudo": "Revisar currículo",
            "ativa": True,
        },
    )
    assert r.status_code == 201
    assert (
        c.put(
            "/ats/candidaturas/ca1/card",
            json={"id_etapa": stage, "versao": 1, "ordem": 0},
        ).status_code
        == 200
    )
    before = db.execute(
        "SELECT ID_Status_Candidatura FROM Candidaturas WHERE ID_Candidaturas='ca1'"
    ).fetchone()[0]
    asyncio.run(worker_platform.regras())
    asyncio.run(worker_platform.regras())
    assert db.execute("SELECT COUNT(*) FROM Tarefas").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM Automacao_Execucoes").fetchone()[0] == 1
    assert (
        db.execute(
            "SELECT ID_Status_Candidatura FROM Candidaturas WHERE ID_Candidaturas='ca1'"
        ).fetchone()[0]
        == before
    )


def test_smtp_outbox_retries_and_respects_opt_out(ambiente, autenticar, monkeypatch):
    from app.core import delivery
    from app.core.config import settings

    c, db = ambiente
    autenticar(c, "uc1", "candidato")
    c.post(
        "/privacidade/consentimentos", json={"finalidade": "emails", "autorizado": True}
    )
    asyncio.run(
        delivery.enfileirar_email("uc1", "Assunto", "Texto <script>", "unica-chave")
    )
    monkeypatch.setattr(settings, "SMTP_ENABLED", True)
    monkeypatch.setattr(worker_platform, "enviar_email", lambda *a: False)
    assert asyncio.run(worker_platform.entregar_email()) is True
    row = db.execute("SELECT Estado,Tentativas FROM Outbox_Email").fetchone()
    assert tuple(row) == ("pendente", 1)
    db.execute("UPDATE Outbox_Email SET ProximaEm=CURRENT_TIMESTAMP")
    db.commit()
    calls = []
    monkeypatch.setattr(
        worker_platform, "enviar_email", lambda *args: calls.append(args) or True
    )
    asyncio.run(worker_platform.entregar_email())
    assert len(calls) == 1 and "&lt;script&gt;" in calls[0][2]
    assert asyncio.run(worker_platform.entregar_email()) is False


def test_ia_is_explained_and_has_no_sensitive_factors():
    r = explicar(
        "Python APIs",
        "Python APIs",
        [{"Nome": "PY", "Nivel": 3}],
        [{"Nome": "Python", "NivelMinimo": 2, "Obrigatoria": True, "Peso": 2}],
    )
    assert r["score"] > 80 and r["fatores"]["requisitos"][0]["atendida"]
    assert "idade" in r["atributos_excluidos"] and "sem embeddings" in r["limites"]
    assert explicar("", "", [], [])["score"] == 0


def test_publication_is_explicit_escaped_and_omits_confidential_salary(
    ambiente, autenticar
):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    assert c.get("/p/empresa/teste-empresa").status_code == 404
    assert (
        c.put(
            "/publicacao/empresa",
            json={
                "slug": "teste-empresa",
                "publicada": True,
                "cultura": "<script>alert(1)</script>",
            },
        ).status_code
        == 200
    )
    db.execute(
        "UPDATE Vagas SET Descricao='Python APIs',Modalidade='Remoto',SalarioConfidencial=1,SalarioMin=9876 WHERE ID_Vagas='v1'"
    )
    db.commit()
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    assert (
        c.put(
            "/publicacao/vagas/v1", json={"slug": "python-teste", "expira_em": future}
        ).status_code
        == 200
    )
    page = c.get("/p/empresa/teste-empresa")
    assert (
        "<script>alert(1)</script>" not in page.text and "&lt;script&gt;" in page.text
    )
    job = c.get("/p/vaga/python-teste")
    assert (
        job.status_code == 200 and "JobPosting" in job.text and "9876" not in job.text
    )
    assert "/p/vaga/python-teste" in c.get("/sitemap.xml").text
    db.execute("UPDATE Vagas SET ID_Status_Vaga=4 WHERE ID_Vagas='v1'")
    db.commit()
    closed = c.get("/p/vaga/python-teste")
    assert closed.status_code == 410 and "JobPosting" not in closed.text
    assert "/p/vaga/python-teste" not in c.get("/sitemap.xml").text


def test_privacy_export_no_secrets_and_cancel_exclusion(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "uc1", "candidato")
    export = c.get("/privacidade/meus-dados")
    assert export.status_code == 200
    assert (
        "SenhaHash" not in export.text
        and "uc2@example.com" not in export.text
        and "auth_tag" not in export.text
    )
    r = c.post(
        "/privacidade/exclusao",
        json={"senha": "senha-de-teste", "confirmacao": "EXCLUIR MINHA CONTA"},
    )
    assert r.status_code == 201
    assert c.delete("/privacidade/solicitacoes/" + r.json()["id"]).status_code == 200
    assert (
        db.execute("SELECT Estado FROM Privacidade_Solicitacoes").fetchone()[0]
        == "cancelado"
    )
    autenticar(c, "ue1", "empresa")
    assert (
        c.post(
            "/privacidade/exclusao",
            json={"senha": "senha-de-teste", "confirmacao": "EXCLUIR MINHA CONTA"},
        ).status_code
        == 409
    )


def test_sensitive_api_csrf_and_cache(ambiente, autenticar):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    c.headers.pop("X-CSRF-Token")
    assert c.post("/agenda", json=agendamento()).status_code == 403
    assert "no-store" in c.get("/comunicacao/candidaturas").headers["cache-control"]
    assert c.get("/comunicacao/candidaturas").headers.get("x-request-id")


def test_privacy_worker_anonymizes_and_revokes_account(ambiente, autenticar):
    c, db = ambiente
    autenticar(c, "uc1", "candidato")
    result = c.post(
        "/privacidade/exclusao",
        json={"senha": "senha-de-teste", "confirmacao": "EXCLUIR MINHA CONTA"},
    )
    assert result.status_code == 201
    db.execute("UPDATE Privacidade_Solicitacoes SET ExecutarApos=CURRENT_TIMESTAMP")
    db.commit()
    asyncio.run(privacy.processar_solicitacoes())
    account = db.execute(
        "SELECT Nome,Email,Ativo FROM Usuarios WHERE ID_Usuarios='uc1'"
    ).fetchone()
    assert (
        account["Nome"] == "Conta excluída"
        and account["Email"].endswith("@invalid.example")
        and account["Ativo"] == 0
    )
    assert c.get("/auth/me").status_code == 401
    assert (
        db.execute("SELECT Estado FROM Privacidade_Solicitacoes").fetchone()[0]
        == "concluido"
    )


def test_role_changes_do_not_replay_automation_and_publication_requires_control(
    ambiente, autenticar
):
    c, db = ambiente
    setup(db)
    autenticar(c, "ue1", "empresa")
    c.post("/ats/vagas/v1/inicializar")
    rid = c.post(
        "/automacoes",
        json={
            "nome": "Checar fila",
            "gatilho": "parado",
            "dias": 1,
            "acao": "tarefa",
            "conteudo": "Revisar",
            "ativa": True,
        },
    ).json()["id"]
    db.execute(
        "UPDATE ATS_Cards SET EntradaEm='2026-01-01' WHERE ID_Candidaturas='ca1'"
    )
    db.commit()
    asyncio.run(worker_platform.regras())
    assert db.execute("SELECT COUNT(*) FROM Tarefas").fetchone()[0] == 1
    assert (
        c.put("/automacoes/" + rid, json={"ativa": False, "versao": 1}).status_code
        == 200
    )
    assert (
        c.put("/automacoes/" + rid, json={"ativa": True, "versao": 2}).status_code
        == 200
    )
    asyncio.run(worker_platform.regras())
    assert db.execute("SELECT COUNT(*) FROM Tarefas").fetchone()[0] == 1
    db.execute(
        "INSERT INTO Org_Membros(ID_Empresas,ID_Usuarios,Papel) VALUES ('e1','uc2','recrutador')"
    )
    db.commit()
    autenticar(c, "uc2", "candidato")
    c.headers["X-Organization-ID"] = "e1"
    assert c.patch("/vagas/v1/publicar").status_code == 403


def test_direct_message_requires_existing_context(ambiente, autenticar):
    c, db = ambiente
    autenticar(c, "uc1", "candidato")
    assert (
        c.post(
            "/mensagens",
            json={"id_destinatario": "uc2", "conteudo": "Contato não autorizado"},
        ).status_code
        == 403
    )
