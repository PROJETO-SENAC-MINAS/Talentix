"""
Funções de segurança: hash de senha (bcrypt) e geração de identificadores.
"""
import uuid
import bcrypt


def hash_senha(senha_plana: str) -> str:
    """Gera o hash bcrypt de uma senha em texto plano."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(senha_plana.encode("utf-8"), salt).decode("utf-8")


def verificar_senha(senha_plana: str, senha_hash: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado."""
    try:
        return bcrypt.checkpw(senha_plana.encode("utf-8"), senha_hash.encode("utf-8"))
    except ValueError:
        return False


def novo_uuid() -> str:
    """Gera um novo UUID v4 em formato string (usado como PK em CHAR(36))."""
    return str(uuid.uuid4())