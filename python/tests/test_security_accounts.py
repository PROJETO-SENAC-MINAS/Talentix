"""Regressões específicas do Update 2 de segurança."""
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.security_accounts import gerar_segredo_totp, validar_totp


def test_request_id_esta_na_resposta(ambiente):
    client, _ = ambiente
    resposta = client.get("/saude")
    assert resposta.status_code == 200
    assert resposta.headers.get("x-request-id")


def test_totp_valida_janela_padrao():
    segredo = gerar_segredo_totp()
    # A função deve rejeitar formatos inválidos sem lançar exceção.
    assert validar_totp(segredo, "abc123") is False
    assert validar_totp(segredo, "123") is False


def test_login_cria_sessao_persistida(ambiente):
    client, conn = ambiente
    resposta = client.post("/auth/login", json={"email": "uc1@example.com", "senha": "senha-de-teste"})
    assert resposta.status_code == 200
    assert resposta.json()["tipo_usuario"] == "candidato"
    assert conn.execute("SELECT COUNT(*) FROM Sessoes WHERE ID_Usuarios='uc1'").fetchone()[0] == 1


def test_bloqueio_temporario_impede_login(ambiente):
    client, conn = ambiente
    conn.execute("UPDATE Usuarios SET BloqueadoAte=? WHERE ID_Usuarios='uc1'", ((datetime.utcnow()+timedelta(minutes=10)).isoformat(),))
    conn.commit()
    resposta = client.post("/auth/login", json={"email": "uc1@example.com", "senha": "senha-de-teste"})
    assert resposta.status_code == 423


def test_me_expoe_permissoes(ambiente, autenticar):
    client, _ = ambiente
    autenticar(client, "uc1", "candidato")
    resposta = client.get("/auth/me")
    assert resposta.status_code == 200
    assert "perfil:editar" in resposta.json()["permissoes"]
