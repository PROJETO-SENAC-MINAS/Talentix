"""
Funções de segurança: hash de senha (bcrypt), geração de identificadores
e tokens assinados de uso único (ex: redefinição de senha).
"""
import uuid
import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from app.core.config import settings


def _validar_senha_bcrypt(senha_plana: str) -> None:
    if len(senha_plana) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(f"A senha deve ter no mínimo {settings.PASSWORD_MIN_LENGTH} caracteres.")
    if len(senha_plana.encode("utf-8")) > 72:
        raise ValueError("A senha deve ter no máximo 72 bytes em UTF-8.")


def hash_senha(senha_plana: str) -> str:
    """Gera hash bcrypt irreversível para senhas de usuários."""
    _validar_senha_bcrypt(senha_plana)
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(senha_plana.encode("utf-8"), salt).decode("utf-8")


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado."""
    try:
        if len(senha_plana.encode("utf-8")) > 72:
            return False
        return bcrypt.checkpw(senha_plana.encode("utf-8"), senha_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def novo_uuid() -> str:
    """Gera um novo UUID v4 em formato string (usado como PK em CHAR(36))."""
    return str(uuid.uuid4())


# ============================================================================
# Token de redefinição de senha (assinado, com expiração, sem estado no banco)
# ============================================================================

_TOKEN_RESET_MAX_AGE_SEGUNDOS = 900  # 15 minutos
_reset_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="talentix-reset-senha")


def gerar_token_reset_senha(id_usuario: str, senha_hash_atual: str) -> str:
    """
    Gera um token assinado contendo o ID do usuário e um "fingerprint" do
    hash de senha atual. Incluir o hash atual no payload faz o token ser
    automaticamente invalidado assim que a senha for trocada uma vez
    (o hash muda -> o token antigo não bate mais na validação), sem
    precisar de tabela extra no banco para controlar tokens usados.
    """
    payload = {"id_usuario": id_usuario, "fingerprint": senha_hash_atual[-16:]}
    return _reset_serializer.dumps(payload)


def validar_token_reset_senha(token: str, senha_hash_atual: str) -> str | None:
    """
    Valida o token de reset. Retorna o id_usuario se válido, ou None se
    inválido, expirado, ou se a senha já foi trocada desde a emissão.
    """
    try:
        payload = _reset_serializer.loads(token, max_age=_TOKEN_RESET_MAX_AGE_SEGUNDOS)
    except (BadSignature, SignatureExpired):
        return None

    if payload.get("fingerprint") != senha_hash_atual[-16:]:
        return None

    return payload.get("id_usuario")