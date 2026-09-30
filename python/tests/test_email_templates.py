"""Conteúdo cadastrado pelo usuário deve permanecer texto no HTML de e-mails."""
import pytest
from html import escape
from app.core import email_service


@pytest.mark.parametrize("name,args",[
    ("email_boas_vindas",1),
    ("email_nova_candidatura",3),
    ("email_nova_mensagem",1),
    ("email_denuncia_recebida",1),
    ("email_recuperar_senha",2),
])
def test_email_escapes_untrusted_content(monkeypatch,name,args):
    captured = {}
    def send(recipient,subject,body):
        captured["body"] = body
        return True
    monkeypatch.setattr(email_service,"enviar_email",send)
    value = '<img src="x" onerror="alert(1)">'
    assert getattr(email_service,name)("destinatario@example.com", *([value]*args))
    assert value not in captured["body"]
    assert escape(value) in captured["body"]
