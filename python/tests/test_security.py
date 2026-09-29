from pathlib import Path

import pytest
from fastapi import Response
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.session import criar_cookie_sessao
from app.core.upload import remover_arquivo
from conftest import ARQUIVO_A, URL_A, URL_B


SERVICOS = [
    ("/analises-ia/a1/processar", {"score_compatibilidade": 90}, "X-IA-Worker-Token", "IA_WORKER_TOKEN"),
    ("/analises-ia/a1/falhar", None, "X-IA-Worker-Token", "IA_WORKER_TOKEN"),
    ("/recomendacoes-vaga/rv1/processar", {"score": 90}, "X-IA-Worker-Token", "IA_WORKER_TOKEN"),
    ("/pagamentos/p1/processar?aprovado=true", None, "X-Payment-Webhook-Token", "PAYMENT_WEBHOOK_TOKEN"),
]


@pytest.mark.parametrize("path,payload,header,config", SERVICOS)
def test_servicos_bloqueiam_anonimos_e_tokens_errados(ambiente, path, payload, header, config):
    client, conn = ambiente
    for headers in ({}, {header: "invalido"}, {header: settings.SECRET_KEY},
                    {header: settings.PAYMENT_WEBHOOK_TOKEN if config == "IA_WORKER_TOKEN" else settings.IA_WORKER_TOKEN}):
        assert client.patch(path, json=payload, headers=headers).status_code == 401
    assert conn.execute("SELECT ID_Status_Processamento_IA FROM Analises_IA WHERE ID_Analises_IA='a1'").fetchone()[0] == 1
    assert conn.execute("SELECT ID_Status_Pagamento FROM Pagamentos WHERE ID_Pagamentos='p1'").fetchone()[0] == 1


@pytest.mark.parametrize("path,payload,header,config", SERVICOS)
def test_servicos_aceitam_apenas_token_da_integracao(ambiente, path, payload, header, config):
    client, _ = ambiente
    resposta = client.patch(path, json=payload, headers={header: getattr(settings, config)})
    assert resposta.status_code == 200, resposta.text


@pytest.mark.parametrize("path,payload,header,config", SERVICOS)
def test_integracao_sem_configuracao_falha_fechada(ambiente, monkeypatch, path, payload, header, config):
    client, _ = ambiente
    monkeypatch.setattr(settings, config, "")
    assert client.patch(path, json=payload, headers={header: "qualquer"}).status_code == 503


@pytest.mark.parametrize("path", ["/analises-ia", "/analises-ia/a1", "/candidatos", "/candidatos/c1",
                                  "/candidatos/c1/curriculos", "/candidatos/c1/experiencias", "/candidatos/c1/formacoes",
                                  "/candidatos/c1/habilidades", "/candidatos/c1/idiomas", URL_A])
def test_dados_privados_exigem_login(ambiente, path):
    client, _ = ambiente
    assert client.get(path).status_code == 401


def test_candidaturas_isoladas_por_empresa_e_por_candidato(ambiente, autenticar):
    client, _ = ambiente
    for usuario, tipo, ids in (("ue1", "empresa", ["ca1"]), ("ue2", "empresa", ["ca2"]),
                               ("uc1", "candidato", ["ca1"]), ("ua", "administrador", ["ca1", "ca2"])):
        autenticar(client, usuario, tipo)
        assert sorted(row["ID_Candidaturas"] for row in client.get("/candidaturas").json()) == ids
    autenticar(client, "ue1", "empresa")
    for filtro in ("id_vaga=v2", "id_candidato=c2", "id_vaga=v2&id_candidato=c2"):
        assert client.get("/candidaturas?" + filtro).json() == []


@pytest.mark.parametrize("path", ["/entrevistas/en2/cancelar", "/entrevistas/en2/realizar",
                                  "/entrevistas/en2/reagendar?nova_data_hora=2026-10-02T10:00:00", "/etapas/et2/reabrir"])
def test_empresa_nao_altera_entrevistas_e_etapas_de_outra(ambiente, autenticar, path):
    client, conn = ambiente
    autenticar(client, "ue1", "empresa")
    assert client.patch(path).status_code == 403
    assert conn.execute("SELECT ID_Status_Entrevista FROM Entrevistas WHERE ID_Entrevistas='en2'").fetchone()[0] == 1
    assert conn.execute("SELECT ID_Status_Etapa FROM Etapas_Processo WHERE ID_Etapas_Processo='et2'").fetchone()[0] == 3
    autenticar(client, "ue2", "empresa")
    assert client.patch(path).status_code == 200


def test_download_privado_permite_dono_e_empresa_da_candidatura(ambiente, autenticar):
    client, _ = ambiente
    for usuario, tipo, codigo in (("uc1", "candidato", 200), ("ue1", "empresa", 200),
                                 ("uc2", "candidato", 404), ("ue2", "empresa", 404), ("ua", "administrador", 200)):
        autenticar(client, usuario, tipo)
        resposta = client.get(URL_A)
        assert resposta.status_code == codigo
        if codigo == 200:
            assert resposta.content.startswith(b"%PDF")
            assert resposta.headers["cache-control"] == "private, no-store"
            assert resposta.headers["content-disposition"].startswith("attachment;")


def test_empresa_nao_baixa_outro_curriculo_do_mesmo_candidato(ambiente, autenticar):
    client, conn = ambiente
    conn.execute("INSERT INTO Curriculos(ID_Curriculos, ID_Candidatos, ArquivoUrl) VALUES ('outro', 'c1', ?)", (URL_B,))
    conn.commit()
    autenticar(client, "ue1", "empresa")
    assert client.get(URL_B).status_code == 404


def test_cv_nao_tem_fallback_estatico_e_recusa_caminhos_invalidos(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "uc1", "candidato")
    for url in ("/uploads/curriculos/arquivo.pdf", "/uploads/curriculos/%2E%2E%2Farquivo.pdf", "/uploads/arquivo.pdf"):
        assert client.get(url).status_code == 404


def test_candidatura_nao_pode_anexar_curriculo_de_terceiro(ambiente, autenticar):
    client, conn = ambiente
    autenticar(client, "uc1", "candidato")
    assert client.post("/candidaturas", json={"id_vaga": "v2", "curriculo_url": URL_B}).status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM Candidaturas").fetchone()[0] == 2


def test_analises_nao_vazam_e_nao_aceitam_outro_candidato(ambiente, autenticar):
    client, _ = ambiente
    for usuario, tipo, ids in (("uc1", "candidato", ["a1"]), ("ue1", "empresa", ["a1"]),
                               ("ua", "administrador", ["a1", "a2"])):
        autenticar(client, usuario, tipo)
        assert sorted(row["ID_Analises_IA"] for row in client.get("/analises-ia").json()) == ids
    for usuario, tipo in (("uc1", "candidato"), ("ue1", "empresa")):
        autenticar(client, usuario, tipo)
        assert client.get("/analises-ia/a2").status_code == 403
        assert client.get("/analises-ia?id_candidato=c2&id_vaga=v2").json() == []
        assert client.post("/analises-ia", json={"id_candidato": "c2", "id_vaga": "v2"}).status_code == 403


def test_analise_nao_pode_associar_candidatura_incompativel(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "uc1", "candidato")
    assert client.post("/analises-ia", json={"id_candidato": "c1", "id_vaga": "v1", "id_candidatura": "ca2"}).status_code == 400
    assert client.post("/analises-ia", json={"id_candidato": "c1", "id_vaga": "v1", "id_candidatura": "ca1"}).status_code == 201


@pytest.mark.parametrize("path", ["/recomendacoes-vaga/rv2/marcar-visualizada", "/recomendacoes-curso/rc2/concluir"])
def test_candidato_nao_altera_recomendacao_de_terceiro(ambiente, autenticar, path):
    client, conn = ambiente
    autenticar(client, "uc1", "candidato")
    assert client.patch(path).status_code == 403
    assert conn.execute("SELECT Visualizada FROM Recomendacoes_Vaga WHERE ID_Recomendacoes_Vaga='rv2'").fetchone()[0] == 0
    assert conn.execute("SELECT Concluida FROM Recomendacoes_Curso WHERE ID_Recomendacoes_Curso='rc2'").fetchone()[0] == 0
    autenticar(client, "uc2", "candidato")
    assert client.patch(path).status_code == 200


@pytest.mark.parametrize("path,tabela,chave", [
    ("/candidatos/c1/habilidades/ch2", "Candidato_Habilidades", "ID_Candidato_Habilidades"),
    ("/candidatos/c1/idiomas/ci2", "Candidato_Idiomas", "ID_Candidato_Idiomas"),
    ("/vagas/v1/habilidades/vh2", "Vaga_Habilidades", "ID_Vaga_Habilidades"),
])
def test_id_filho_de_outro_dono_nao_e_excluido(ambiente, autenticar, path, tabela, chave):
    client, conn = ambiente
    autenticar(client, "ue1" if tabela == "Vaga_Habilidades" else "uc1", "empresa" if tabela == "Vaga_Habilidades" else "candidato")
    assert client.delete(path).status_code == 200
    assert conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0] == 1


def test_empresa_nao_remove_recrutador_de_outra(ambiente, autenticar):
    client, conn = ambiente
    autenticar(client, "ue1", "empresa")
    assert client.delete("/recrutadores/r2").status_code == 403
    assert client.get("/empresas/e2/recrutadores").status_code == 403
    assert conn.execute("SELECT Ativo FROM Recrutadores WHERE ID_Recrutadores='r2'").fetchone()[0] == 1
    autenticar(client, "ue2", "empresa")
    assert client.delete("/recrutadores/r2").status_code == 200


def test_perfils_privados_so_para_dono_ou_empresa_relacionada(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "ue1", "empresa")
    assert [row["ID_Candidatos"] for row in client.get("/candidatos").json()] == ["c1"]
    assert client.get("/candidatos/c1").status_code == 200
    for path in ("/candidatos/c2", "/candidatos/c2/experiencias", "/candidatos/c2/formacoes",
                 "/candidatos/c2/habilidades", "/candidatos/c2/idiomas"):
        assert client.get(path).status_code == 403
    # Mesmo a empresa relacionada não recebe todos os currículos pessoais do candidato.
    assert client.get("/candidatos/c1/curriculos").status_code == 403


def test_sessao_de_usuario_desativado_e_cookie_adulterado_sao_recusados(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "desativado", "administrador")
    assert client.get("/auth/me").status_code == 401
    client.cookies.set(settings.SESSION_COOKIE_NAME, "cookie-adulterado")
    assert client.get("/auth/me").status_code == 401


def test_login_emite_cookie_seguro(ambiente):
    client, _ = ambiente
    resposta = client.post("/auth/login", json={"email": "uc1@example.com", "senha": "senha-de-teste"})
    assert resposta.status_code == 200
    cookie = resposta.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    assert client.get("/auth/me").status_code == 200


def test_configuracao_recusa_chave_exposta_curta_e_chaves_de_exemplo():
    for chave in ("change-me", "x" * 48, "change-me" + "x" * 64):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, SECRET_KEY=chave)
    assert Settings(_env_file=None).SESSION_COOKIE_SECURE is True


def test_modo_local_pode_usar_cookie_em_http(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_COOKIE_SECURE", False)
    response = Response()
    criar_cookie_sessao(response, "uc1", "candidato")
    assert "secure" not in response.headers["set-cookie"].lower()


def test_empresa_nao_autoconcede_assinatura(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "ue1", "empresa")
    assert client.post("/assinaturas", json={"id_empresa": "e1", "plano": "premium", "valor": 1, "inicio": "2026-01-01"}).status_code == 403
    assert client.patch("/assinaturas/s1/renovar?nova_data_fim=2099-01-01").status_code == 403


def test_svg_ativo_nao_e_aceito_como_logo(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "ue1", "empresa")
    assert client.post("/uploads/logo-empresa/e1", files={"arquivo": ("logo.svg", b"<svg><script/></svg>", "image/svg+xml")}).status_code == 400


def test_remocao_fisica_respeita_pasta_de_uploads(ambiente, tmp_path):
    arquivo = Path(settings.UPLOAD_DIR) / "curriculos" / ARQUIVO_A
    externo = tmp_path / "nao-remover.txt"
    externo.write_text("fora de uploads")
    remover_arquivo(str(externo))
    remover_arquivo("/uploads/curriculos/../../nao-remover.txt")
    assert externo.exists()
    remover_arquivo(URL_A)
    assert not arquivo.exists()
