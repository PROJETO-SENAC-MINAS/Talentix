"""
Serviço de envio de e-mails via SMTP genérico (Gmail, Outlook, etc.).
Envio síncrono simples: chama smtplib diretamente na requisição.
Falhas de e-mail NUNCA devem quebrar o fluxo principal da API — por isso
todas as chamadas são envolvidas em try/except e apenas logadas.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger("talentix.email")


def _montar_mensagem(destinatario: str, assunto: str, corpo_html: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html", "utf-8"))
    return msg


def enviar_email(destinatario: str, assunto: str, corpo_html: str) -> bool:
    """
    Envia um e-mail de forma síncrona via SMTP.
    Retorna True se enviado com sucesso, False em caso de falha (não lança exceção).
    """
    if not settings.SMTP_ENABLED:
        logger.info(f"[EMAIL DESATIVADO] Para: {destinatario} | Assunto: {assunto}")
        return False

    try:
        msg = _montar_mensagem(destinatario, assunto, corpo_html)
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as servidor:
            servidor.starttls()
            servidor.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            servidor.sendmail(settings.SMTP_FROM_EMAIL, [destinatario], msg.as_string())
        logger.info(f"E-mail enviado para {destinatario} | Assunto: {assunto}")
        return True
    except Exception as erro:
        logger.error(f"Falha ao enviar e-mail para {destinatario}: {erro}")
        return False


# ============================================================================
# Templates de e-mail para cada evento do sistema (espelham as Notificacoes)
# ============================================================================

def email_nova_candidatura(destinatario: str, nome_empresa: str, titulo_vaga: str, nome_candidato: str) -> bool:
    assunto = f"Nova candidatura recebida: {titulo_vaga}"
    corpo = f"""
    <p>Olá, {nome_empresa}!</p>
    <p><strong>{nome_candidato}</strong> se candidatou à vaga <strong>{titulo_vaga}</strong>.</p>
    <p>Acesse o painel do Talentix para revisar o perfil do candidato.</p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_status_candidatura_atualizado(destinatario: str, nome_candidato: str, titulo_vaga: str, novo_status: str) -> bool:
    assunto = f"Atualização da sua candidatura: {titulo_vaga}"
    corpo = f"""
    <p>Olá, {nome_candidato}!</p>
    <p>Sua candidatura para <strong>{titulo_vaga}</strong> mudou de status para: <strong>{novo_status}</strong>.</p>
    <p>Acesse o Talentix para mais detalhes.</p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_entrevista_agendada(destinatario: str, nome_candidato: str, titulo_vaga: str, data_hora_formatada: str, local_ou_link: str | None) -> bool:
    assunto = f"Entrevista agendada: {titulo_vaga}"
    local_html = f"<p>Local/Link: {local_ou_link}</p>" if local_ou_link else ""
    corpo = f"""
    <p>Olá, {nome_candidato}!</p>
    <p>Uma entrevista foi agendada para a vaga <strong>{titulo_vaga}</strong>.</p>
    <p>Data e horário: <strong>{data_hora_formatada}</strong></p>
    {local_html}
    """
    return enviar_email(destinatario, assunto, corpo)


def email_entrevista_reagendada(destinatario: str, nome_candidato: str, titulo_vaga: str, nova_data_hora_formatada: str) -> bool:
    assunto = f"Entrevista reagendada: {titulo_vaga}"
    corpo = f"""
    <p>Olá, {nome_candidato}!</p>
    <p>Sua entrevista para a vaga <strong>{titulo_vaga}</strong> foi reagendada.</p>
    <p>Nova data e horário: <strong>{nova_data_hora_formatada}</strong></p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_entrevista_cancelada(destinatario: str, nome_candidato: str, titulo_vaga: str) -> bool:
    assunto = f"Entrevista cancelada: {titulo_vaga}"
    corpo = f"""
    <p>Olá, {nome_candidato}!</p>
    <p>Sua entrevista para a vaga <strong>{titulo_vaga}</strong> foi cancelada.</p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_nova_mensagem(destinatario: str, nome_remetente: str) -> bool:
    assunto = f"Nova mensagem de {nome_remetente}"
    corpo = f"""
    <p>Você recebeu uma nova mensagem de <strong>{nome_remetente}</strong> no Talentix.</p>
    <p>Acesse o Talentix para ler e responder.</p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_denuncia_recebida(destinatario: str, motivo: str) -> bool:
    assunto = "Nova denúncia registrada"
    corpo = f"""
    <p>Uma nova denúncia foi registrada na plataforma.</p>
    <p>Motivo: <strong>{motivo}</strong></p>
    <p>Acesse o painel administrativo para revisar.</p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_denuncia_resolvida(destinatario: str, motivo: str, novo_status: str) -> bool:
    assunto = "Sua denúncia foi analisada"
    corpo = f"""
    <p>Olá!</p>
    <p>Sua denúncia sobre "<strong>{motivo}</strong>" foi analisada.</p>
    <p>Status final: <strong>{novo_status}</strong></p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_recomendacao_curso(destinatario: str, nome_candidato: str, titulo_curso: str, motivo: str | None) -> bool:
    assunto = "Nova recomendação de curso para você"
    motivo_html = f"<p>Motivo: {motivo}</p>" if motivo else ""
    corpo = f"""
    <p>Olá, {nome_candidato}!</p>
    <p>Recomendamos o curso <strong>{titulo_curso}</strong> para você.</p>
    {motivo_html}
    """
    return enviar_email(destinatario, assunto, corpo)


def email_recomendacao_vaga(destinatario: str, nome_candidato: str, titulo_vaga: str, motivo: str | None) -> bool:
    assunto = f"Nova vaga recomendada: {titulo_vaga}"
    motivo_html = f"<p>Motivo: {motivo}</p>" if motivo else ""
    corpo = f"""
    <p>Olá, {nome_candidato}!</p>
    <p>Encontramos uma vaga que combina com seu perfil: <strong>{titulo_vaga}</strong>.</p>
    {motivo_html}
    """
    return enviar_email(destinatario, assunto, corpo)


def email_pagamento_processado(destinatario: str, valor: float, aprovado: bool) -> bool:
    status_txt = "aprovado" if aprovado else "recusado"
    assunto = f"Pagamento {status_txt}"
    corpo = f"""
    <p>Seu pagamento de <strong>R$ {valor:.2f}</strong> foi <strong>{status_txt}</strong>.</p>
    """
    return enviar_email(destinatario, assunto, corpo)


def email_boas_vindas(destinatario: str, nome: str) -> bool:
    assunto = "Bem-vindo(a) ao Talentix!"
    corpo = f"""
    <p>Olá, {nome}!</p>
    <p>Seu cadastro no Talentix foi realizado com sucesso.</p>
    <p>Estamos felizes em ter você na plataforma.</p>
    """
    return enviar_email(destinatario, assunto, corpo)