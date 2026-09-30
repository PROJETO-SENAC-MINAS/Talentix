"""Crie o primeiro administrador local sem registrar a senha no código."""
import argparse
import asyncio
import getpass
from pydantic import EmailStr, TypeAdapter, ValidationError
from app.core.security import hash_senha, novo_uuid
from app.core.validation import Password
from app.db.database import init_pool, close_pool, transaction, fetch_one, execute


async def create(name, email, password):
    await init_pool()
    try:
        async with transaction():
            if await fetch_one("SELECT ID_Usuarios FROM Usuarios WHERE Email=%s", (email,)):
                raise SystemExit("Este e-mail já está cadastrado. Não foram alteradas permissões existentes.")
            uid = novo_uuid()
            await execute("INSERT INTO Usuarios (ID_Usuarios, Nome, Email, SenhaHash) VALUES (%s,%s,%s,%s)", (uid,name,email,hash_senha(password)))
            await execute("INSERT INTO Administradores (ID_Administradores, ID_Usuarios, NivelAcesso) VALUES (%s,%s,'ADMIN')", (novo_uuid(),uid))
        print("Administrador criado. Entre pela tela de login.")
    finally:
        await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nome", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    if not 1 <= len(args.nome) <= 150:
        raise SystemExit("Nome deve ter entre 1 e 150 caracteres.")
    email = TypeAdapter(EmailStr).validate_python(args.email)
    try:
        password = TypeAdapter(Password).validate_python(getpass.getpass("Senha (não será exibida): "))
    except ValidationError:
        raise SystemExit("Senha inválida: use pelo menos 6 caracteres e no máximo 72 bytes UTF-8.") from None
    if password != getpass.getpass("Confirme a senha: "):
        raise SystemExit("Senhas diferentes; nada foi criado.")
    asyncio.run(create(args.nome,email,password))
