"""Autenticação, segurança de contas, sessões e recuperação de acesso."""
from datetime import datetime, timedelta

from app.core.routes import AtomicRouter as APIRouter
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.core.audit import registrar_auditoria
from app.core.config import settings
from app.core.deps import descobrir_tipo_usuario, usuario_atual
from app.core.email_service import (
    email_2fa_alterado,
    email_boas_vindas,
    email_confirmar_endereco,
    email_email_alterado,
    email_recuperar_senha,
    email_senha_redefinida,
)
from app.core.security import (
    gerar_token_reset_senha,
    hash_senha,
    novo_uuid,
    validar_token_reset_senha,
    verificar_senha,
)
from app.core.security_accounts import (
    criptografar_segredo,
    descriptografar_segredo,
    gerar_segredo_totp,
    gerar_token_email,
    otpauth_uri,
    validar_token_email,
    validar_totp,
)
from app.core.session import criar_cookie_sessao, destruir_cookie_sessao, novo_id_sessao
from app.core.validation import Password
from app.db.database import after_commit, execute, fetch_all, fetch_one

router = APIRouter(prefix="/auth", tags=["Autenticação"])


class CadastroCandidato(BaseModel):
    nome: str = Field(min_length=1, max_length=150)
    email: EmailStr
    senha: Password
    telefone: str | None = Field(default=None, max_length=20)


class CadastroEmpresa(CadastroCandidato):
    razao_social: str = Field(min_length=1, max_length=200)
    cnpj: str = Field(min_length=14, max_length=18)
    nome_fantasia: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str
    codigo_2fa: str | None = Field(default=None, min_length=6, max_length=6)


class RecuperarSenhaRequest(BaseModel):
    email: EmailStr


class RedefinirSenhaRequest(BaseModel):
    token: str
    nova_senha: Password


class AlterarSenhaRequest(BaseModel):
    senha_atual: str
    nova_senha: Password


class AlterarEmailRequest(BaseModel):
    novo_email: EmailStr
    senha: str


class TokenRequest(BaseModel):
    token: str


class AlternarModoRequest(BaseModel):
    modo_usuario: bool


class Codigo2FARequest(BaseModel):
    codigo: str = Field(min_length=6, max_length=6)


class Desativar2FARequest(Codigo2FARequest):
    senha: str


async def _descobrir_tipo_usuario(id_usuario: str) -> str:
    tipo = await descobrir_tipo_usuario(id_usuario)
    if tipo is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Perfil ou vínculo desativado.")
    return tipo


def _confirmado_em():
    return None if settings.EMAIL_CONFIRMATION_REQUIRED else datetime.utcnow()


async def _enviar_confirmacao(id_usuario: str, email: str, nome: str, finalidade: str = "confirmar") -> None:
    token = gerar_token_email(id_usuario, email, finalidade)
    separador = "&" if "?" in settings.FRONTEND_RESET_URL else "?"
    link = f"{settings.FRONTEND_RESET_URL}{separador}email_token={token}&email_action={finalidade}"
    await after_commit(lambda: email_confirmar_endereco(email, nome, link))


async def _criar_sessao(request: Request, response: Response, usuario: dict, tipo_usuario: str) -> str:
    id_sessao = novo_id_sessao()
    expira = datetime.utcnow() + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)
    await execute(
        """INSERT INTO Sessoes (ID_Sessoes, ID_Usuarios, UserAgent, ExpiraEm)
           VALUES (%s,%s,%s,%s)""",
        (id_sessao, usuario["ID_Usuarios"], request.headers.get("user-agent", "")[:500], expira),
    )
    criar_cookie_sessao(
        response, usuario["ID_Usuarios"], tipo_usuario, usuario["SenhaHash"], id_sessao=id_sessao
    )
    return id_sessao


async def _registrar_falha_login(request: Request, usuario: dict) -> None:
    tentativas = int(usuario.get("TentativasLogin") or 0) + 1
    bloqueado_ate = None
    if tentativas >= settings.LOGIN_MAX_ATTEMPTS:
        bloqueado_ate = datetime.utcnow() + timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
        tentativas = 0
    await execute(
        "UPDATE Usuarios SET TentativasLogin=%s, BloqueadoAte=%s WHERE ID_Usuarios=%s",
        (tentativas, bloqueado_ate, usuario["ID_Usuarios"]),
    )
    await registrar_auditoria(request, "LOGIN_FALHOU", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])


async def _cadastrar_usuario_base(dados: CadastroCandidato) -> str:
    if await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s", (dados.email,)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe um usuário com esse e-mail.")
    id_usuario = novo_uuid()
    await execute(
        """INSERT INTO Usuarios
           (ID_Usuarios, Nome, Email, EmailConfirmadoEm, SenhaHash, Telefone)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (id_usuario, dados.nome, dados.email, _confirmado_em(), hash_senha(dados.senha), dados.telefone),
    )
    await after_commit(lambda: email_boas_vindas(dados.email, dados.nome))
    if settings.EMAIL_CONFIRMATION_REQUIRED:
        await _enviar_confirmacao(id_usuario, dados.email, dados.nome)
    return id_usuario


@router.post("/cadastro/recrutador", status_code=201)
async def cadastrar_conta_recrutador(dados: CadastroCandidato):
    id_usuario = await _cadastrar_usuario_base(dados)
    return {"id_usuario": id_usuario, "tipo_usuario": "usuario", "mensagem": "Aguardando vínculo com uma empresa."}


@router.post("/cadastro/candidato", status_code=201)
async def cadastrar_candidato(dados: CadastroCandidato):
    id_usuario = await _cadastrar_usuario_base(dados)
    id_candidato = novo_uuid()
    await execute("INSERT INTO Candidatos (ID_Candidatos, ID_Usuarios) VALUES (%s,%s)", (id_candidato, id_usuario))
    return {"id_usuario": id_usuario, "id_candidato": id_candidato, "tipo_usuario": "candidato"}


@router.post("/cadastro/empresa", status_code=201)
async def cadastrar_empresa(dados: CadastroEmpresa):
    if await fetch_one("SELECT ID_Empresas FROM Empresas WHERE Cnpj=%s", (dados.cnpj,)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe uma empresa com esse CNPJ.")
    id_usuario = await _cadastrar_usuario_base(dados)
    id_empresa = novo_uuid()
    await execute(
        """INSERT INTO Empresas (ID_Empresas, ID_Usuarios, RazaoSocial, NomeFantasia, Cnpj)
           VALUES (%s,%s,%s,%s,%s)""",
        (id_empresa, id_usuario, dados.razao_social, dados.nome_fantasia, dados.cnpj),
    )
    return {"id_usuario": id_usuario, "id_empresa": id_empresa, "tipo_usuario": "empresa"}


@router.post("/login")
async def login(dados: LoginRequest, request: Request, response: Response):
    usuario = await fetch_one(
        """SELECT ID_Usuarios, Nome, Email, EmailConfirmadoEm, SenhaHash, Ativo,
                  TentativasLogin, BloqueadoAte, TwoFactorAtivo, TwoFactorSecretEnc
           FROM Usuarios WHERE Email=%s""",
        (dados.email,),
    )
    if not usuario or not usuario["Ativo"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos.")

    if usuario.get("BloqueadoAte") and usuario["BloqueadoAte"] > datetime.utcnow():
        raise HTTPException(
            status.HTTP_423_LOCKED,
            "Conta temporariamente bloqueada por tentativas de login. Tente novamente mais tarde.",
        )

    if not verificar_senha(dados.senha, usuario["SenhaHash"]):
        await _registrar_falha_login(request, usuario)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos.")

    if settings.EMAIL_CONFIRMATION_REQUIRED and not usuario.get("EmailConfirmadoEm"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Confirme seu e-mail antes de entrar.")

    if usuario.get("TwoFactorAtivo"):
        if not dados.codigo_2fa:
            return {"two_factor_required": True}
        secret = descriptografar_segredo(usuario.get("TwoFactorSecretEnc") or "")
        if not secret or not validar_totp(secret, dados.codigo_2fa):
            await registrar_auditoria(request, "2FA_FALHOU", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código de autenticação inválido.")

    tipo_usuario = await _descobrir_tipo_usuario(usuario["ID_Usuarios"])
    await execute(
        "UPDATE Usuarios SET TentativasLogin=0, BloqueadoAte=NULL, UltimoLoginEm=NOW() WHERE ID_Usuarios=%s",
        (usuario["ID_Usuarios"],),
    )
    id_sessao = await _criar_sessao(request, response, usuario, tipo_usuario)
    await registrar_auditoria(
        request, "LOGIN_SUCESSO", "Sessoes", usuario["ID_Usuarios"], id_sessao,
        novo={"tipo_usuario": tipo_usuario},
    )
    return {"id_usuario": usuario["ID_Usuarios"], "tipo_usuario": tipo_usuario, "two_factor_required": False}


@router.post("/alternar-modo")
async def alternar_modo(dados: AlternarModoRequest, response: Response, sessao: dict = Depends(usuario_atual)):
    if sessao.get("tipo_principal") != "administrador":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores podem alternar o modo de acesso.")
    usuario = await fetch_one("SELECT ID_Usuarios, SenhaHash FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1", (sessao["id_usuario"],))
    if not usuario:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    criar_cookie_sessao(
        response, sessao["id_usuario"], "administrador", usuario["SenhaHash"],
        modo_usuario=dados.modo_usuario, id_sessao=sessao.get("id_sessao"),
    )
    return {"modo_usuario": dados.modo_usuario, "tipo_usuario": "usuario" if dados.modo_usuario else "administrador"}


@router.post("/logout")
async def logout(response: Response, sessao: dict | None = Depends(usuario_atual)):
    if sessao and sessao.get("id_sessao"):
        await execute("UPDATE Sessoes SET RevogadaEm=NOW() WHERE ID_Sessoes=%s", (sessao["id_sessao"],))
    destruir_cookie_sessao(response)
    return {"mensagem": "Logout realizado com sucesso."}


@router.get("/me")
async def me(sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one(
        """SELECT ID_Usuarios, Nome, Email, Telefone, FotoUrl, Ativo, CriadoEm,
                  EmailConfirmadoEm, UltimoLoginEm, TwoFactorAtivo
           FROM Usuarios WHERE ID_Usuarios=%s""",
        (sessao["id_usuario"],),
    )
    if not usuario:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuário não encontrado.")
    return {
        **usuario,
        "email_confirmado": bool(usuario.get("EmailConfirmadoEm")),
        "two_factor_ativo": bool(usuario.get("TwoFactorAtivo")),
        "tipo_usuario": sessao["tipo_usuario"],
        "tipo_principal": sessao.get("tipo_principal", sessao["tipo_usuario"]),
        "modo_usuario": bool(sessao.get("modo_usuario")),
        "permissoes": sessao.get("permissoes", []),
    }


@router.get("/sessoes")
async def listar_sessoes(sessao: dict = Depends(usuario_atual)):
    registros = await fetch_all(
        """SELECT ID_Sessoes, UserAgent, CriadaEm, UltimaAtividadeEm, ExpiraEm, RevogadaEm
           FROM Sessoes WHERE ID_Usuarios=%s ORDER BY CriadaEm DESC LIMIT 50""",
        (sessao["id_usuario"],),
    )
    for item in registros:
        item["Atual"] = item["ID_Sessoes"] == sessao.get("id_sessao")
    return registros


@router.delete("/sessoes/{id_sessao}")
async def encerrar_sessao(id_sessao: str, response: Response, sessao: dict = Depends(usuario_atual)):
    registro = await fetch_one("SELECT ID_Sessoes FROM Sessoes WHERE ID_Sessoes=%s AND ID_Usuarios=%s", (id_sessao, sessao["id_usuario"]))
    if not registro:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sessão não encontrada.")
    await execute("UPDATE Sessoes SET RevogadaEm=COALESCE(RevogadaEm,NOW()) WHERE ID_Sessoes=%s", (id_sessao,))
    if id_sessao == sessao.get("id_sessao"):
        destruir_cookie_sessao(response)
    return {"mensagem": "Sessão encerrada."}


@router.post("/sessoes/encerrar-todas")
async def encerrar_todas_sessoes(response: Response, sessao: dict = Depends(usuario_atual)):
    await execute("UPDATE Sessoes SET RevogadaEm=COALESCE(RevogadaEm,NOW()) WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    destruir_cookie_sessao(response)
    return {"mensagem": "Todas as sessões foram encerradas."}


@router.get("/acessos")
async def historico_acessos(sessao: dict = Depends(usuario_atual)):
    return await fetch_all(
        """SELECT Acao, RequestId, UserAgent, CriadoEm
           FROM Audit_Logs WHERE ID_Usuarios=%s AND Acao IN ('LOGIN_SUCESSO','LOGIN_FALHOU','2FA_FALHOU')
           ORDER BY CriadoEm DESC LIMIT 100""",
        (sessao["id_usuario"],),
    )


@router.post("/alterar-senha")
async def alterar_senha(dados: AlterarSenhaRequest, request: Request, response: Response, sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one(
        "SELECT ID_Usuarios, Nome, Email, SenhaHash FROM Usuarios WHERE ID_Usuarios=%s AND Ativo=1 FOR UPDATE",
        (sessao["id_usuario"],),
    )
    if not usuario or not verificar_senha(dados.senha_atual, usuario["SenhaHash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta.")
    if verificar_senha(dados.nova_senha, usuario["SenhaHash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A nova senha deve ser diferente da senha atual.")
    await execute("UPDATE Usuarios SET SenhaHash=%s WHERE ID_Usuarios=%s", (hash_senha(dados.nova_senha), usuario["ID_Usuarios"]))
    await execute("UPDATE Sessoes SET RevogadaEm=COALESCE(RevogadaEm,NOW()) WHERE ID_Usuarios=%s", (usuario["ID_Usuarios"],))
    destruir_cookie_sessao(response)
    await registrar_auditoria(request, "SENHA_ALTERADA", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])
    await after_commit(lambda: email_senha_redefinida(usuario["Email"], usuario["Nome"]))
    return {"mensagem": "Senha alterada. Entre novamente em todos os dispositivos."}


@router.post("/email/solicitar-alteracao")
async def solicitar_alteracao_email(dados: AlterarEmailRequest, request: Request, sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one("SELECT ID_Usuarios, Nome, Email, SenhaHash FROM Usuarios WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if not usuario or not verificar_senha(dados.senha, usuario["SenhaHash"]):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha incorreta.")
    if dados.novo_email.lower() == usuario["Email"].lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Informe um e-mail diferente do atual.")
    if await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s", (dados.novo_email,)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Este e-mail já está em uso.")
    await _enviar_confirmacao(usuario["ID_Usuarios"], dados.novo_email, usuario["Nome"], "alterar")
    await registrar_auditoria(request, "EMAIL_ALTERACAO_SOLICITADA", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])
    return {"mensagem": "Enviamos uma confirmação para o novo endereço."}


@router.post("/email/confirmar")
async def confirmar_email(dados: TokenRequest, request: Request, response: Response):
    payload = validar_token_email(dados.token, "confirmar")
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação inválida ou expirada.")
    usuario = await fetch_one("SELECT ID_Usuarios, Email FROM Usuarios WHERE ID_Usuarios=%s", (payload["id_usuario"],))
    if not usuario or usuario["Email"].lower() != payload["email"].lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação inválida.")
    await execute("UPDATE Usuarios SET EmailConfirmadoEm=COALESCE(EmailConfirmadoEm,NOW()) WHERE ID_Usuarios=%s", (usuario["ID_Usuarios"],))
    await registrar_auditoria(request, "EMAIL_CONFIRMADO", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])
    return {"mensagem": "E-mail confirmado com sucesso."}


@router.post("/email/confirmar-alteracao")
async def confirmar_alteracao_email(dados: TokenRequest, request: Request, response: Response):
    payload = validar_token_email(dados.token, "alterar")
    if not payload:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Confirmação inválida ou expirada.")
    usuario = await fetch_one("SELECT ID_Usuarios, Nome, Email FROM Usuarios WHERE ID_Usuarios=%s", (payload["id_usuario"],))
    if not usuario:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Conta não encontrada.")
    if await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s AND ID_Usuarios<>%s", (payload["email"], usuario["ID_Usuarios"])):
        raise HTTPException(status.HTTP_409_CONFLICT, "O novo e-mail já está em uso.")
    email_antigo = usuario["Email"]
    await execute("UPDATE Usuarios SET Email=%s, EmailConfirmadoEm=NOW() WHERE ID_Usuarios=%s", (payload["email"], usuario["ID_Usuarios"]))
    await execute("UPDATE Sessoes SET RevogadaEm=COALESCE(RevogadaEm,NOW()) WHERE ID_Usuarios=%s", (usuario["ID_Usuarios"],))
    destruir_cookie_sessao(response)
    await registrar_auditoria(request, "EMAIL_ALTERADO", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"], {"email": email_antigo}, {"email": payload["email"]})
    await after_commit(lambda: email_email_alterado(email_antigo, usuario["Nome"]))
    return {"mensagem": "E-mail alterado. Entre novamente usando o novo endereço."}


@router.post("/2fa/iniciar")
async def iniciar_2fa(sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one("SELECT ID_Usuarios, Email, TwoFactorAtivo FROM Usuarios WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    if usuario.get("TwoFactorAtivo"):
        raise HTTPException(status.HTTP_409_CONFLICT, "A autenticação em dois fatores já está ativa.")
    secret = gerar_segredo_totp()
    await execute("UPDATE Usuarios SET TwoFactorSecretEnc=%s WHERE ID_Usuarios=%s", (criptografar_segredo(secret), usuario["ID_Usuarios"]))
    return {"secret": secret, "otpauth_uri": otpauth_uri(secret, usuario["Email"])}


@router.post("/2fa/confirmar")
async def confirmar_2fa(dados: Codigo2FARequest, request: Request, sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one("SELECT ID_Usuarios, Nome, Email, TwoFactorAtivo, TwoFactorSecretEnc FROM Usuarios WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    secret = descriptografar_segredo(usuario.get("TwoFactorSecretEnc") or "")
    if not secret or not validar_totp(secret, dados.codigo):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido.")
    await execute("UPDATE Usuarios SET TwoFactorAtivo=1 WHERE ID_Usuarios=%s", (usuario["ID_Usuarios"],))
    await registrar_auditoria(request, "2FA_ATIVADO", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])
    await after_commit(lambda: email_2fa_alterado(usuario["Email"], usuario["Nome"], True))
    return {"mensagem": "Autenticação em dois fatores ativada."}


@router.delete("/2fa")
async def desativar_2fa(dados: Desativar2FARequest, request: Request, sessao: dict = Depends(usuario_atual)):
    usuario = await fetch_one("SELECT ID_Usuarios, Nome, Email, SenhaHash, TwoFactorSecretEnc FROM Usuarios WHERE ID_Usuarios=%s", (sessao["id_usuario"],))
    secret = descriptografar_segredo(usuario.get("TwoFactorSecretEnc") or "")
    if not verificar_senha(dados.senha, usuario["SenhaHash"]) or not secret or not validar_totp(secret, dados.codigo):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha ou código inválido.")
    await execute("UPDATE Usuarios SET TwoFactorAtivo=0, TwoFactorSecretEnc=NULL WHERE ID_Usuarios=%s", (usuario["ID_Usuarios"],))
    await registrar_auditoria(request, "2FA_DESATIVADO", "Usuarios", usuario["ID_Usuarios"], usuario["ID_Usuarios"])
    await after_commit(lambda: email_2fa_alterado(usuario["Email"], usuario["Nome"], False))
    return {"mensagem": "Autenticação em dois fatores desativada."}


@router.post("/recuperar-senha")
async def recuperar_senha(dados: RecuperarSenhaRequest):
    usuario = await fetch_one("SELECT ID_Usuarios, Nome, SenhaHash, Ativo FROM Usuarios WHERE Email=%s", (dados.email,))
    if usuario and usuario["Ativo"]:
        token = gerar_token_reset_senha(usuario["ID_Usuarios"], usuario["SenhaHash"])
        link_reset = f"{settings.FRONTEND_RESET_URL}?token={token}"
        await after_commit(lambda: email_recuperar_senha(dados.email, usuario["Nome"], link_reset))
    return {"mensagem": "Se este e-mail estiver cadastrado, você receberá um link de redefinição em instantes."}


@router.post("/redefinir-senha")
async def redefinir_senha(dados: RedefinirSenhaRequest, response: Response):
    from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

    serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="talentix-reset-senha")
    try:
        payload = serializer.loads(dados.token, max_age=1800)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Link de redefinição inválido ou expirado.")

    usuario = await fetch_one(
        "SELECT ID_Usuarios, Nome, Email, SenhaHash, Ativo FROM Usuarios WHERE ID_Usuarios=%s FOR UPDATE",
        (payload.get("id_usuario"),),
    )
    if not usuario or not usuario["Ativo"] or validar_token_reset_senha(dados.token, usuario["SenhaHash"]) != usuario["ID_Usuarios"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Este link já foi utilizado ou expirou. Solicite um novo.")

    await execute("UPDATE Usuarios SET SenhaHash=%s, TentativasLogin=0, BloqueadoAte=NULL WHERE ID_Usuarios=%s", (hash_senha(dados.nova_senha), usuario["ID_Usuarios"]))
    await execute("UPDATE Sessoes SET RevogadaEm=COALESCE(RevogadaEm,NOW()) WHERE ID_Usuarios=%s", (usuario["ID_Usuarios"],))
    destruir_cookie_sessao(response)
    await after_commit(lambda: email_senha_redefinida(usuario["Email"], usuario["Nome"]))
    return {"mensagem": "Senha redefinida com sucesso. Você já pode entrar com a nova senha."}
